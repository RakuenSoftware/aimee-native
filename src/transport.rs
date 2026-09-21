//! Read-only transport for recipient-specific published snapshots. Authorization
//! precedes delivery. Remote fallback retains its independent Aimee boundary.
use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    io::{BufRead, BufReader, Read, Write},
    os::{fd::AsRawFd, unix::net::UnixStream},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    time::{Duration, Instant},
};

#[derive(Debug)]
pub struct Denied;
impl std::fmt::Display for Denied {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("authorized memory read denied")
    }
}
impl std::error::Error for Denied {}

#[derive(Clone, Debug, Deserialize, Serialize, clap::Args)]
pub struct ImageConfig {
    #[arg(long)]
    pub image_reader: PathBuf,
    #[arg(long)]
    pub memory_image: PathBuf,
    #[arg(long)]
    pub authorization: Option<PathBuf>,
    #[arg(long)]
    pub authority_key: Option<PathBuf>,
    #[arg(long)]
    pub subject: Option<String>,
    #[arg(long)]
    pub policy_epoch: Option<String>,
}
pub struct ImageReader {
    child: Child,
    input: ChildStdin,
    output: ChildStdout,
    dead: bool,
    pub binding: String,
    pub view: String,
    pub published: bool,
}
impl ImageReader {
    pub fn start(c: &ImageConfig) -> Result<Self> {
        let published = c.authorization.is_none();
        let mut command = Command::new(&c.image_reader);
        if published {
            ensure!(
                c.authority_key.is_none() && c.subject.is_none() && c.policy_epoch.is_none(),
                "local reader needs only the published image"
            );
            command.arg("serve-published");
        } else {
            // Compatibility for the privileged fallback gateway, not local reads.
            command
                .arg("serve")
                .arg("--authorization")
                .arg(c.authorization.as_ref().unwrap())
                .arg("--authority-key")
                .arg(c.authority_key.as_ref().context("authority key required")?)
                .arg("--subject")
                .arg(c.subject.as_ref().context("subject required")?)
                .arg("--policy-epoch")
                .arg(c.policy_epoch.as_ref().context("policy epoch required")?);
        }
        let mut child = command
            .arg("--root")
            .arg(&c.memory_image)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()?;
        let input = child.stdin.take().context("reader stdin")?;
        let output = child.stdout.take().context("reader stdout")?;
        let mut s = Self {
            child,
            input,
            output,
            dead: false,
            binding: String::new(),
            view: String::new(),
            published,
        };
        s.pin()?;
        Ok(s)
    }
    pub fn call(&mut self, v: Value) -> Result<Value> {
        if self.dead {
            bail!("image reader unavailable")
        }
        let r = self.exchange(v);
        if r.as_ref()
            .is_err_and(|e| e.downcast_ref::<Denied>().is_none())
        {
            self.dead = true;
            let _ = self.child.kill();
        }
        r
    }
    fn exchange(&mut self, v: Value) -> Result<Value> {
        self.input.write_all(&serde_json::to_vec(&v)?)?;
        self.input.write_all(b"\n")?;
        self.input.flush()?;
        let until = Instant::now() + Duration::from_secs(30);
        let mut data = Vec::new();
        loop {
            let left = until.saturating_duration_since(Instant::now()).as_millis();
            ensure!(left > 0, "image reader timed out");
            let mut p = libc::pollfd {
                fd: self.output.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // Borrowed pipe descriptor remains alive for the entire poll/read.
            let n = unsafe { libc::poll(&mut p, 1, left.min(i32::MAX as u128) as i32) };
            ensure!(n > 0, "image reader timed out or poll failed");
            let mut buf = [0u8; 65536];
            let n = self.output.read(&mut buf)?;
            ensure!(n > 0, "image reader closed");
            data.extend_from_slice(&buf[..n]);
            ensure!(data.len() <= 16 << 20, "image response too large");
            if data.contains(&b'\n') {
                break;
            }
        }
        let r: Value = serde_json::from_slice(&data)?;
        if r.get("error").is_some() {
            return Err(Denied.into());
        }
        Ok(r)
    }
    pub fn pin(&mut self) -> Result<()> {
        let r = self.call(json!({"op":"pin"}))?;
        let binding = r[if self.published {
            "publication"
        } else {
            "authorization"
        }]
        .as_str()
        .filter(|s| !s.is_empty())
        .context("unbound image")?;
        if !self.published && !self.binding.is_empty() && self.binding != binding {
            return Err(Denied.into());
        }
        self.binding = binding.into();
        self.view = r["view"].as_str().context("missing view")?.into();
        Ok(())
    }
}
impl Drop for ImageReader {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub fn unix_post(path: &std::path::Path, route: &str, body: &Value) -> Result<Value> {
    let mut s = UnixStream::connect(path)?;
    s.set_read_timeout(Some(Duration::from_secs(60)))?;
    s.set_write_timeout(Some(Duration::from_secs(60)))?;
    let raw = serde_json::to_vec(body)?;
    write!(
        s,
        "POST {route} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {}\r\n\r\n",
        raw.len()
    )?;
    s.write_all(&raw)?;
    let mut reader = BufReader::new(s);
    let mut status = String::new();
    reader.read_line(&mut status)?;
    let code: u16 = status
        .split_whitespace()
        .nth(1)
        .context("invalid HTTP status")?
        .parse()?;
    let mut length = None;
    let mut header_bytes = 0;
    loop {
        let mut line = String::new();
        ensure!(reader.read_line(&mut line)? > 0, "incomplete HTTP headers");
        header_bytes += line.len();
        ensure!(header_bytes < 65536, "headers too large");
        if line == "\r\n" {
            break;
        }
        if let Some((k, v)) = line.split_once(':') {
            if k.eq_ignore_ascii_case("content-length") {
                ensure!(length.is_none(), "duplicate length");
                length = Some(v.trim().parse::<usize>()?);
            }
            ensure!(
                !k.eq_ignore_ascii_case("transfer-encoding"),
                "unsupported transfer encoding"
            );
        }
    }
    if matches!(code, 400 | 401 | 403) {
        return Err(Denied.into());
    }
    ensure!(code == 200, "memory gateway unavailable");
    let n = length.context("missing response length")?;
    ensure!(n <= 16 << 20, "response too large");
    let mut raw = vec![0; n];
    reader.read_exact(&mut raw)?;
    Ok(serde_json::from_slice(&raw)?)
}

pub trait MemorySource {
    fn retain_encodings(&mut self, proofs: &[Value]) -> Result<Vec<bool>> {
        Ok(vec![false; proofs.len()])
    }
    fn check_generation(&mut self, _expected: &str) -> Result<()> {
        Ok(())
    }

    fn begin(&mut self) -> Result<String>;
    fn search(&mut self, query: &str, limit: usize) -> Result<Value>;
    fn native_search(&mut self, query: &str, limit: usize) -> Result<Value>;
}
pub struct LocalFirst {
    pub local: ImageReader,
    pub gateway: PathBuf,
    pub authority: String,
    admitted: bool,
    local_ready: bool,
    last_read_local: bool,
    remote_binding: Option<String>,
    pub events: Vec<Value>,
}
impl LocalFirst {
    pub fn state(&self) -> (bool, bool) {
        (self.admitted, self.local_ready)
    }
    pub fn new(local: ImageReader, gateway: PathBuf, authority: String) -> Self {
        Self {
            local,
            gateway,
            authority,
            admitted: false,
            local_ready: false,
            last_read_local: false,
            remote_binding: None,
            events: vec![],
        }
    }
    fn remote_binding(&mut self) -> Result<String> {
        if !self.local.published {
            return Ok(self.local.binding.clone());
        }
        if self.remote_binding.is_none() {
            // A local publication is not the remote Aimee identity. Discover
            // that independently, and only when an actual fallback is needed.
            let identity = unix_post(&self.gateway, "/identity", &json!({}))?;
            self.remote_binding = Some(
                identity["authorization"]
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .context("unbound remote memory")?
                    .into(),
            );
        }
        Ok(self.remote_binding.as_ref().unwrap().clone())
    }
    fn read(&mut self, query: &str, limit: usize) -> Result<Value> {
        self.last_read_local = false;
        if self.local_ready {
            match self
                .local
                .call(json!({"op":"recall","query":query,"limit":limit,"authority":self.authority}))
            {
                Ok(r) => {
                    ensure!(r["view"] == self.local.view, "image changed inside request");
                    if r["outcome"] == "hit" {
                        self.last_read_local = true;
                        self.events
                            .push(json!({"query":query,"outcome":"hit","remote":false}));
                        return Ok(r["response"].clone());
                    }
                }
                Err(e) if e.downcast_ref::<Denied>().is_some() => return Err(e),
                Err(_) => self.local_ready = false,
            }
        }
        self.events
            .push(json!({"query":query,"outcome":"fallback","remote":true}));
        let binding = self.remote_binding()?;
        unix_post(
            &self.gateway,
            "/search",
            &json!({"query":query,"limit":limit,"authorization":binding}),
        )
    }
}
impl MemorySource for LocalFirst {
    fn retain_encodings(&mut self, proofs: &[Value]) -> Result<Vec<bool>> {
        if !self.local.published || !self.local_ready {
            return Ok(vec![false; proofs.len()]);
        }
        let result = self.local.call(json!({"op":"retain","proofs":proofs}))?;
        ensure!(
            result["view"] == self.local.view,
            "retention generation differs"
        );
        let retained: Vec<bool> = serde_json::from_value(result["retained"].clone())?;
        ensure!(retained.len() == proofs.len(), "retention count differs");
        let view = self.local.view.clone();
        self.check_generation(&view)?;
        Ok(retained)
    }
    fn check_generation(&mut self, expected: &str) -> Result<()> {
        if self.local.published {
            let result = self.local.call(json!({"op":"check"}))?;
            ensure!(
                result["view"] == expected,
                "publication changed during generation; retry required"
            );
        }
        Ok(())
    }

    fn native_search(&mut self, query: &str, limit: usize) -> Result<Value> {
        let mut response = self.search(query, limit)?;
        if self.local.published && self.last_read_local {
            let facts = response["facts"].as_array().context("facts required")?;
            ensure!(
                facts.iter().all(|f| ["namespace", "id", "revision"]
                    .iter()
                    .all(|k| f["memory_ref"][*k].as_str().is_some_and(|v| !v.is_empty()))),
                "canonical local references required"
            );
            return Ok(response);
        }
        let binding = self.remote_binding()?;
        let result = if self.local_ready && !self.local.published {
            match self
                .local
                .call(json!({"op":"resolve_response", "response":response}))
            {
                Err(e) if e.downcast_ref::<Denied>().is_none() => {
                    self.local_ready = false;
                    unix_post(
                        &self.gateway,
                        "/resolve",
                        &json!({"authorization":binding,"response":response}),
                    )
                }
                other => other,
            }
        } else {
            unix_post(
                &self.gateway,
                "/resolve",
                &json!({"authorization":binding,"response":response}),
            )
        };
        let resolved = match result {
            Ok(v)
                if v["authorization"] == binding
                    && (self.local.published || v["view"] == self.local.view) =>
            {
                v
            }
            _ => {
                self.admitted = false;
                self.local_ready = false;
                return Err(Denied.into());
            }
        };
        let refs = resolved["refs"]
            .as_array()
            .context("canonical references required")?;
        let facts = response["facts"].as_array_mut().context("facts required")?;
        ensure!(
            refs.len() == facts.len(),
            "canonical reference count differs"
        );
        for (fact, reference) in facts.iter_mut().zip(refs) {
            ensure!(
                ["namespace", "id", "revision"]
                    .iter()
                    .all(|k| reference[*k].as_str().is_some_and(|v| !v.is_empty())),
                "invalid canonical reference"
            );
            fact["memory_ref"] = reference.clone();
        }
        Ok(response)
    }
    fn begin(&mut self) -> Result<String> {
        self.admitted = false;
        self.local_ready = false;
        self.events.clear();
        self.remote_binding = None;
        if self.local.published {
            self.local.pin()?;
            self.local_ready = true;
            self.admitted = true;
            // Cache identity is the actual generation, not an access decision.
            return Ok(self.local.view.clone());
        }
        let identity = unix_post(&self.gateway, "/identity", &json!({}))?;
        if identity["authorization"] != self.local.binding {
            return Err(Denied.into());
        }
        match self.local.pin() {
            Ok(()) => self.local_ready = true,
            Err(e) if e.downcast_ref::<Denied>().is_some() => return Err(e),
            Err(_) => {}
        }
        self.admitted = true;
        Ok(self.local.binding.clone())
    }
    fn search(&mut self, query: &str, limit: usize) -> Result<Value> {
        ensure!(self.admitted, "memory request has not begun");
        ensure!(
            !query.trim().is_empty() && (1..=32).contains(&limit),
            "invalid read"
        );
        let r = self.read(query, limit);
        if r.as_ref()
            .is_err_and(|e| e.downcast_ref::<Denied>().is_some())
        {
            self.admitted = false;
            self.local_ready = false;
        }
        r
    }
}
