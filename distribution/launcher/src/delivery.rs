//! Authenticated native publication transport; never called by attention.
//! Credentials stay in the host process. The inference container receives only
//! approved immutable artifacts. Selection and authorization stay with Aimee.
use crate::{Config, atomic, component, private_dir};
use anyhow::{Context, Result, ensure};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Read, Write},
    os::unix::fs::OpenOptionsExt,
    path::PathBuf,
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Record {
    pub namespace: String,
    pub id: String,
    pub revision: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub name: String,
    pub bytes: u64,
    pub sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Offer {
    pub schema: u32,
    pub lease: String,
    pub expires: u64,
    pub recipient: String,
    pub model: String,
    pub key: String,
    pub authorized_view: String,
    pub records: Vec<Record>,
    pub artifacts: Vec<Artifact>,
}
#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    pub schema: u32,
    pub recipient: String,
    pub model: String,
    pub model_config_sha256: String,
}
pub fn bootstrap(http: &Client, endpoint: &str, token: &str) -> Result<Profile> {
    bootstrap_for_model(http, endpoint, token, None)
}
pub fn bootstrap_for_model(
    http: &Client,
    endpoint: &str,
    token: &str,
    model: Option<&str>,
) -> Result<Profile> {
    crate::validate_endpoint(endpoint)?;
    ensure!(
        !token.trim().is_empty() && token.len() <= 16384 && !token.trim().contains(['\r', '\n']),
        "invalid credential"
    );
    let mut request = http
        .get(format!(
            "{}/v1/native/bootstrap",
            endpoint.trim_end_matches('/')
        ))
        .bearer_auth(token.trim());
    if let Some(model) = model {
        ensure!(
            !model.is_empty() && model.len() <= 256,
            "invalid native model selection"
        );
        request = request.query(&[("model", model)]);
    }
    let p: Profile = read_json(request.send()?)?;
    ensure!(
        p.schema == 1
            && !p.recipient.is_empty()
            && !p.model.is_empty()
            && digest(&p.model_config_sha256),
        "invalid native profile"
    );
    ensure!(
        model.is_none_or(|model| p.model == model),
        "native model selection mismatch"
    );
    Ok(p)
}
fn digest(s: &str) -> bool {
    s.len() == 64
        && s.bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
impl Offer {
    pub fn validate(&self, recipient: &str, model: &str, budget: u64) -> Result<()> {
        ensure!(
            self.schema == 1 && self.recipient == recipient && self.model == model,
            "publication identity mismatch"
        );
        ensure!(
            digest(&self.lease) && digest(&self.key) && digest(&self.authorized_view),
            "invalid publication identity"
        );
        ensure!(
            !self.records.is_empty() && self.records.len() <= 32,
            "invalid working set"
        );
        let mut seen = std::collections::HashSet::new();
        for r in &self.records {
            ensure!(
                !r.namespace.is_empty()
                    && !r.id.is_empty()
                    && !r.revision.is_empty()
                    && seen.insert((&r.namespace, &r.id, &r.revision)),
                "invalid record set"
            );
        }
        ensure!(self.artifacts.len() == 2, "incomplete publication");
        let mut names = std::collections::HashSet::new();
        let mut total = 0u64;
        for a in &self.artifacts {
            ensure!(
                matches!(a.name.as_str(), "index.json" | "compact.pack")
                    && names.insert(&a.name)
                    && digest(&a.sha256)
                    && a.bytes > 0,
                "invalid publication artifact"
            );
            total = total
                .checked_add(a.bytes)
                .context("artifact size overflow")?;
            ensure!(
                a.name != "index.json" || a.bytes <= 16 * 1024 * 1024,
                "index too large"
            );
        }
        ensure!(total <= budget, "publication exceeds disk budget");
        self.current()
    }
    fn current(&self) -> Result<()> {
        ensure!(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_secs()
                < self.expires,
            "publication lease expired"
        );
        Ok(())
    }
}
fn read_json<T: serde::de::DeserializeOwned>(r: reqwest::blocking::Response) -> Result<T> {
    let mut raw = Vec::new();
    r.error_for_status()?
        .take(1024 * 1024 + 1)
        .read_to_end(&mut raw)?;
    ensure!(raw.len() <= 1024 * 1024, "publication response too large");
    Ok(serde_json::from_slice(&raw)?)
}
/// Returns only after a fresh remote approval. Existing local bytes are never
/// themselves authority. Do not serve on any error, including network failure.
pub fn fetch(
    http: &Client,
    connection: &Config,
    query: &str,
    recipient: &str,
    model: &str,
    budget: u64,
) -> Result<(Offer, PathBuf)> {
    ensure!(!query.is_empty() && query.len() <= 65536, "invalid query");
    let base = connection.endpoint.trim_end_matches('/');
    let url = reqwest::Url::parse(base)?;
    ensure!(
        url.scheme() == "https"
            && url.username().is_empty()
            && url.password().is_none()
            && url.query().is_none()
            && url.fragment().is_none(),
        "invalid authority endpoint"
    );
    let token = fs::read_to_string(&connection.token_file)?;
    let offer: Offer = read_json(
        http.post(format!("{base}/v1/native/select"))
            .query(&[("model", model)])
            .bearer_auth(token.trim())
            .header("Content-Type", "application/json")
            .body(serde_json::to_vec(&serde_json::json!({"query":query}))?)
            .send()?,
    )?;
    offer.validate(recipient, model, budget)?;
    let root = connection.memory_root.join("prepared");
    private_dir(&root)?;
    let final_path = root.join(&offer.key);
    // Immutable content identity includes the exact file descriptors. A reused
    // directory is accepted only when this control-plane receipt matches exactly.
    let receipt = serde_json::to_vec(
        &serde_json::json!({"recipient":offer.recipient,"model":offer.model,"key":offer.key,"authorized_view":offer.authorized_view,"records":offer.records,"artifacts":offer.artifacts}),
    )?;
    if !final_path.exists() {
        let mut used = 0u64;
        for entry in fs::read_dir(&root)? {
            let entry = entry?;
            ensure!(
                entry.file_type()?.is_dir(),
                "unexpected prepared-store entry"
            );
            for file in fs::read_dir(entry.path())? {
                let file = file?;
                ensure!(
                    file.file_type()?.is_file(),
                    "unexpected prepared-store file"
                );
                used = used
                    .checked_add(file.metadata()?.len())
                    .context("disk usage overflow")?;
            }
        }
        let incoming = offer
            .artifacts
            .iter()
            .try_fold(receipt.len() as u64, |n, a| n.checked_add(a.bytes))
            .context("disk usage overflow")?;
        ensure!(
            used.checked_add(incoming).is_some_and(|n| n <= budget),
            "prepared store disk budget exhausted"
        );
        let staged = tempfile::Builder::new()
            .prefix("download-")
            .tempdir_in(&root)?;
        for a in &offer.artifacts {
            offer.current()?;
            ensure!(component(&a.name), "invalid artifact path");
            let mut response = http
                .get(format!(
                    "{base}/v1/native/leases/{}/{}",
                    offer.lease, a.name
                ))
                .query(&[("model", model)])
                .bearer_auth(token.trim())
                .send()?
                .error_for_status()?
                .take(a.bytes + 1);
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .mode(0o600)
                .open(staged.path().join(&a.name))?;
            let mut hash = Sha256::new();
            let mut bytes = 0u64;
            let mut buffer = [0u8; 256 * 1024];
            loop {
                let n = response.read(&mut buffer)?;
                if n == 0 {
                    break;
                };
                bytes += n as u64;
                ensure!(bytes <= a.bytes, "oversized artifact");
                hash.update(&buffer[..n]);
                file.write_all(&buffer[..n])?;
            }
            ensure!(
                bytes == a.bytes && hex::encode(hash.finalize()) == a.sha256,
                "artifact integrity mismatch"
            );
            file.sync_all()?;
        }
        atomic(&staged.path().join("delivery.json"), &receipt)?;
        // Directory names are unguessable to other users (private parent). No symlink
        // or in-place replacement of a mapped artifact is allowed.
        ensure!(
            !final_path.exists(),
            "concurrent publication install; retry"
        );
        fs::rename(staged.path(), &final_path)?;
        fs::File::open(&root)?.sync_all()?;
    } else {
        ensure!(
            fs::symlink_metadata(&final_path)?.is_dir(),
            "invalid prepared directory"
        );
        ensure!(
            fs::read(final_path.join("delivery.json"))? == receipt,
            "immutable publication changed"
        );
    }
    approve(http, connection, &offer)?;
    Ok((offer, final_path))
}
pub fn approve(http: &Client, connection: &Config, offer: &Offer) -> Result<()> {
    offer.current()?;
    let token = fs::read_to_string(&connection.token_file)?;
    let base = connection.endpoint.trim_end_matches('/');
    let approved: serde_json::Value = read_json(
        http.post(format!("{base}/v1/native/leases/{}/approve", offer.lease))
            .query(&[("model", offer.model.as_str())])
            .bearer_auth(token.trim())
            .send()?,
    )?;
    ensure!(
        approved == serde_json::json!({"approved":true}),
        "final publication approval denied"
    );
    offer.current()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn offer() -> Offer {
        Offer {
            schema: 1,
            lease: "a".repeat(64),
            expires: u64::MAX,
            recipient: "alice".into(),
            model: "gemma".into(),
            key: "b".repeat(64),
            authorized_view: "c".repeat(64),
            records: vec![Record {
                namespace: "n".into(),
                id: "1".into(),
                revision: "r".into(),
            }],
            artifacts: vec![
                Artifact {
                    name: "index.json".into(),
                    bytes: 10,
                    sha256: "d".repeat(64),
                },
                Artifact {
                    name: "compact.pack".into(),
                    bytes: 100,
                    sha256: "e".repeat(64),
                },
            ],
        }
    }
    #[test]
    fn bindings_limits_and_expiry() {
        let mut o = offer();
        assert!(o.validate("alice", "gemma", 110).is_ok());
        assert!(o.validate("bob", "gemma", 110).is_err());
        assert!(o.validate("alice", "other", 110).is_err());
        assert!(o.validate("alice", "gemma", 109).is_err());
        o.expires = 0;
        assert!(o.validate("alice", "gemma", 110).is_err());
    }
    #[test]
    fn rejects_partial_duplicate_and_traversal() {
        let mut o = offer();
        o.artifacts[0].name = "../index.json".into();
        assert!(o.validate("alice", "gemma", 110).is_err());
        o = offer();
        o.records.push(o.records[0].clone());
        assert!(o.validate("alice", "gemma", 110).is_err());
        o = offer();
        o.artifacts.pop();
        assert!(o.validate("alice", "gemma", 110).is_err());
    }
}
