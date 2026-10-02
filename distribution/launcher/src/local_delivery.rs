//! Private inference-host preparation. Aimee releases only selected source
//! records; this process owns model-specific compilation and immutable caching.
use crate::{Config, delivery, primitive, private_dir};
use anyhow::{Context, Result, ensure};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs, io::Write, os::unix::{fs::PermissionsExt, process::CommandExt}, path::Path, process::{Command, Stdio}, time::{Duration, Instant}};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Settings {
    pub compiler: Vec<String>,
    pub model_config_sha256: String,
    pub runtime_profile: String,
    pub encoding_revision: String,
    pub position_policy: String,
    #[serde(default = "default_limit")]
    pub limit_tokens: u32,
}
fn default_limit() -> u32 { 1024 }

impl Settings {
    pub fn validate(&self) -> Result<()> {
        ensure!(!self.compiler.is_empty() && self.compiler.len() <= 32,
            "local compiler is missing");
        ensure!(self.compiler[0].starts_with('/') && self.compiler.iter().all(|s| !s.is_empty()),
            "local compiler must use an absolute executable and fixed arguments");
        ensure!(self.model_config_sha256.len() == 64 && self.model_config_sha256.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()), "invalid model configuration digest");
        ensure!(!self.runtime_profile.is_empty() && !self.encoding_revision.is_empty()
            && !self.position_policy.is_empty(), "incomplete local preparation profile");
        ensure!((64..=8192).contains(&self.limit_tokens), "invalid memory token limit");
        Ok(())
    }
}

fn digest(value: &impl serde::Serialize) -> Result<String> {
    Ok(hex::encode(Sha256::digest(serde_json::to_vec(value)?)))
}

fn artifacts(root: &Path, model: &str, key: &str, budget: u64) -> Result<Vec<delivery::Artifact>> {
    let index = fs::read(root.join("index.json"))?;
    ensure!(index.len() <= 16 * 1024 * 1024, "native index exceeds limit");
    let manifest: Value = serde_json::from_slice(&index)?;
    ensure!(manifest["version"] == 1 && manifest["model"] == model
        && manifest["native_layout"] == true && manifest["records"].as_object().is_some_and(|r| r.len() == 1 && r.contains_key(key)),
        "local compiler returned a different native bank");
    let payload = root.join("compact.pack");
    let meta = fs::symlink_metadata(&payload)?;
    ensure!(meta.is_file() && !meta.file_type().is_symlink() && meta.len() > 0
        && meta.len() <= budget, "local native payload exceeds budget");
    let mut result = vec![delivery::Artifact { name:"index.json".into(), bytes:index.len() as u64,
        sha256:hex::encode(Sha256::digest(index)) }];
    let mut hasher = Sha256::new();
    let mut file = fs::File::open(payload)?;
    std::io::copy(&mut file, &mut hasher)?;
    result.push(delivery::Artifact { name:"compact.pack".into(), bytes:meta.len(),
        sha256:hex::encode(hasher.finalize()) });
    Ok(result)
}

fn compile(settings: &Settings, primitive: &primitive::Primitive, recipient: &str,
    model: &str, view: &str, key: &str, output: &Path) -> Result<()> {
    let records: Vec<Value> = primitive.records.iter().map(|r| json!({
        "namespace":r.version.owner_id,"id":r.version.record_id,
        "revision":r.version.record_revision})).collect();
    let facts: Vec<Value> = primitive.records.iter().map(|r| json!({"content":r.content})).collect();
    let request = json!({"identity":{"recipient":recipient,"authorized_view":view,
        "model_revision":model,"runtime_profile":settings.runtime_profile,
        "encoding_revision":settings.encoding_revision,"position_policy":settings.position_policy,
        "records":records},"response":{"facts":facts}});
    let mut child = Command::new(&settings.compiler[0]);
    child.args(&settings.compiler[1..]).arg("--output").arg(output)
        .arg("--identity").arg(model).arg("--key").arg(key)
        .env("AIMEE_NATIVE_PUBLISHER", std::env::current_exe()?)
        .env("HF_HUB_OFFLINE", "1")
        .stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null());
    unsafe {
        child.pre_exec(|| {
            if libc::setpgid(0, 0) != 0 { return Err(std::io::Error::last_os_error()); }
            Ok(())
        });
    }
    let mut child = child.spawn().context("local memory compiler unavailable")?;
    let sent = child.stdin.take().context("compiler stdin")?.write_all(&serde_json::to_vec(&request)?);
    if let Err(error) = sent {
        unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL); }
        let _ = child.wait(); return Err(error.into());
    }
    let deadline = Instant::now() + Duration::from_secs(600);
    loop {
        if let Some(status) = child.try_wait()? {
            ensure!(status.success(), "local native preparation failed");
            return Ok(());
        }
        if Instant::now() >= deadline {
            unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL); }
            let _ = child.wait();
            anyhow::bail!("local native preparation timed out");
        }
        std::thread::sleep(Duration::from_millis(100));
    }
}

pub fn select(http: &Client, connection: &Config, query: &str, recipient: &str,
    model: &str, budget: u64, settings: &Settings) -> Result<delivery::Selection> {
    select_from(connection, recipient, model, budget, settings,
        || primitive::fetch(http, connection, query, settings.limit_tokens))
}

fn select_from<F>(connection: &Config, recipient: &str, model: &str, budget: u64,
    settings: &Settings, mut fetch: F) -> Result<delivery::Selection>
where F: FnMut() -> Result<primitive::Primitive> {
    settings.validate()?;
    let source = fetch()?;
    source.validate()?;
    let view = digest(&source)?;
    if source.records.is_empty() {
        return Ok(delivery::Selection::Empty(delivery::NoMemory { schema:1,
            outcome:"no_memory".into(), recipient:recipient.into(), model:model.into(),
            authorized_view:view }));
    }
    let records: Vec<delivery::Record> = source.records.iter().map(|r| delivery::Record {
        namespace:r.version.owner_id.clone(), id:r.version.record_id.clone(),
        revision:r.version.record_revision.clone() }).collect();
    let key = digest(&json!([recipient,model,view,settings.model_config_sha256,
        settings.runtime_profile,settings.encoding_revision,settings.position_policy,records]))?;
    let prepared = connection.memory_root.join("prepared-local");
    private_dir(&prepared)?;
    let root = prepared.join(&key);
    if !root.exists() {
        let stage = tempfile::Builder::new().prefix("prepare-").tempdir_in(&prepared)?;
        let output = stage.path().join("bank");
        compile(settings, &source, recipient, model, &view, &key, &output)?;
        let objects = artifacts(&output, model, &key, budget)?;
        let incoming = objects.iter().try_fold(0u64, |n, artifact| n.checked_add(artifact.bytes))
            .context("local bank extent overflow")?;
        let mut used = 0u64;
        for entry in fs::read_dir(&prepared)? {
            let entry = entry?;
            if !entry.file_type()?.is_dir() || !entry.file_name().to_string_lossy().bytes().all(|b| b.is_ascii_hexdigit()) {
                continue; // only completed content-addressed banks count
            }
            for name in ["index.json", "compact.pack"] {
                used = used.checked_add(fs::metadata(entry.path().join(name))?.len())
                    .context("local cache extent overflow")?;
            }
        }
        ensure!(used.checked_add(incoming).is_some_and(|n| n <= budget),
            "local native cache disk budget exhausted");
        let receipt = json!({"view":view,"key":key,"records":records,"artifacts":objects});
        fs::write(output.join("local-receipt.json"), serde_json::to_vec(&receipt)?)?;
        fs::set_permissions(&output, fs::Permissions::from_mode(0o700))?;
        fs::rename(&output, &root)?;
        fs::File::open(&prepared)?.sync_all()?;
    }
    ensure!(fs::symlink_metadata(&root)?.is_dir(), "invalid local prepared bank");
    let receipt: Value = serde_json::from_slice(&fs::read(root.join("local-receipt.json"))?)?;
    ensure!(receipt["view"] == view && receipt["key"] == key
        && receipt["records"] == json!(records), "local bank no longer matches Aimee selection");
    let artifact_list: Vec<delivery::Artifact> = serde_json::from_value(receipt["artifacts"].clone())?;
    ensure!(artifact_list.len() == 2, "incomplete local bank");
    let latest = fetch()?;
    latest.validate()?;
    ensure!(latest == source, "Aimee selection changed during local preparation");
    let offer = delivery::Offer { schema:1, lease:key.clone(),
        expires:std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs() + 3600,
        recipient:recipient.into(), model:model.into(), key, authorized_view:view, records,
        artifacts:artifact_list };
    offer.validate(recipient, model, budget)?;
    Ok(delivery::Selection::Memory(offer, root))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::primitive::{SourceRecord, SourceVersion};

    fn fixture(root: &Path) -> (Config, Settings, primitive::Primitive) {
        let memory = root.join("memory");
        private_dir(&memory).unwrap();
        let compiler = root.join("compile.py");
        fs::write(&compiler, r#"import argparse,json,pathlib,sys
p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--identity');p.add_argument('--key');a=p.parse_args()
wire=json.load(sys.stdin);assert len(wire['identity']['records'])==len(wire['response']['facts'])==2
pathlib.Path(a.output).mkdir();root=pathlib.Path(a.output)
(root/'index.json').write_text(json.dumps({'version':1,'model':a.identity,'native_layout':True,'records':{a.key:{'tokens':[1,2]}}}))
(root/'compact.pack').write_bytes(bytes(4096)+b'bank')
"#).unwrap();
        let connection = Config { schema:1, endpoint:"https://memory.example".into(),
            token_file:root.join("unused"), memory_root:memory, ca_file:None,
            client_identity:None, connect_address:None };
        let settings = Settings { compiler:vec!["/usr/bin/python3".into(), compiler.to_string_lossy().into_owned()],
            model_config_sha256:"a".repeat(64),runtime_profile:"test".into(),
            encoding_revision:"one".into(),position_policy:"negative".into(),limit_tokens:1024 };
        let records = (1..=2).map(|id| SourceRecord {id,
            content:format!("fact {id}"),version:SourceVersion {schema_version:1,
            owner_id:"00000000-0000-0000-0000-000000000001".into(),
            record_id:id.to_string(),record_revision:"1".into()}}).collect();
        (connection, settings, primitive::Primitive {schema:1,records})
    }

    #[test]
    fn compiles_every_record_once_and_refuses_changed_selection() {
        let temp = tempfile::tempdir().unwrap();
        let (connection,settings,source) = fixture(temp.path());
        let selected = select_from(&connection,"self","gemma",1<<20,&settings,||Ok(source.clone())).unwrap();
        let (first, path) = match selected { delivery::Selection::Memory(o,p)=>(o,p), _=>panic!("missing bank") };
        assert_eq!(first.records.len(),2);
        assert!(path.join("compact.pack").is_file());
        let again = select_from(&connection,"self","gemma",1<<20,&settings,||Ok(source.clone())).unwrap();
        let (second, reused) = match again { delivery::Selection::Memory(o,p)=>(o,p), _=>panic!("missing bank") };
        assert_eq!(first.key,second.key);
        assert_eq!(path,reused);
        let mut revised = source.clone();
        revised.records[1].version.record_revision = "2".into();
        let mut calls = 0;
        assert!(select_from(&connection,"self","gemma",1<<20,&settings,||{
            calls += 1;
            Ok(if calls == 1 {source.clone()} else {revised.clone()})
        }).is_err());
        assert_eq!(calls,2);
    }
}
