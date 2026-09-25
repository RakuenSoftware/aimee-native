//! Private control-plane preparation from an already authorized local publication.
//! Configuration and compiler command are operator-owned, never model input.
use aimee_qwen::{
    native_store::NativeStore,
    preparation_cache::{Cache, PreparationIdentity, RecordRevision},
    transport::{ImageConfig, ImageReader, LocalFirst, MemorySource},
};
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::Write,
    path::PathBuf,
    process::{Command, Stdio},
};
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Config {
    image_reader: PathBuf,
    #[serde(default)]
    gateway: Option<PathBuf>,
    memory_image: PathBuf,
    query: String,
    limit: usize,
    authority: String,
    recipient: String,
    model_revision: String,
    runtime_profile: String,
    encoding_revision: String,
    position_policy: String,
    cache_root: PathBuf,
    compiler: Vec<String>,
    host_memory_budget: usize,
}
fn revalidate(
    reader: &mut Option<ImageReader>,
    remote: &mut Option<LocalFirst>,
    response: &Value,
    approved: &Value,
    view: &str,
    query: &str,
    limit: usize,
) -> Result<()> {
    if let Some(source) = remote {
        let current = source.native_search(query, limit)?;
        ensure!(
            current["facts"] == response["facts"]
                && current["active_context_missing"] != true
                && current
                    .get("windows")
                    .is_none_or(|v| v.as_array().is_some_and(|a| a.is_empty())),
            "authoritative selection changed during preparation"
        );
        source.check_generation(view)?;
    } else {
        let current = reader
            .as_mut()
            .context("missing local reader")?
            .call(json!({"op":"resolve_local_response","response":response}))?;
        ensure!(
            current["view"] == view && current["refs"] == approved["refs"],
            "publication changed during preparation"
        );
    }
    Ok(())
}
fn run() -> Result<()> {
    let path = std::env::args_os()
        .nth(1)
        .context("operator configuration path required")?;
    let c: Config = serde_json::from_slice(&std::fs::read(path)?)?;
    ensure!(
        !c.compiler.is_empty() && (1..=32).contains(&c.limit),
        "invalid preparation configuration"
    );
    let mut reader = Some(ImageReader::start(&ImageConfig {
        image_reader: c.image_reader,
        memory_image: c.memory_image,
        authorization: None,
        authority_key: None,
        subject: None,
        policy_epoch: None,
    })?);
    let view = reader.as_ref().unwrap().view.clone();
    let recalled = reader
        .as_mut()
        .unwrap()
        .call(json!({"op":"recall","query":c.query,"limit":c.limit,"authority":c.authority}))?;
    ensure!(
        recalled["view"] == view,
        "publication changed during selection"
    );
    let mut remote = None;
    let (response, approved) = if recalled["outcome"] == "hit" {
        let response = recalled
            .get("response")
            .context("missing approved response")?
            .clone();
        let approved = reader
            .as_mut()
            .unwrap()
            .call(json!({"op":"resolve_local_response","response":response}))?;
        (response, approved)
    } else {
        let gateway = c
            .gateway
            .clone()
            .context("authoritative fallback is not configured")?;
        let mut source = LocalFirst::new(reader.take().unwrap(), gateway, c.authority.clone());
        ensure!(
            source.begin()? == view,
            "publication changed before fallback"
        );
        let response = source.native_search(&c.query, c.limit)?;
        // Complex contextual windows cannot silently become a partial fact bank.
        ensure!(
            response["active_context_missing"] != true
                && response
                    .get("windows")
                    .is_none_or(|v| v.as_array().is_some_and(|a| a.is_empty())),
            "authoritative read requires non-fact context"
        );
        let refs: Vec<Value> = response["facts"]
            .as_array()
            .context("authoritative facts missing")?
            .iter()
            .map(|f| f["memory_ref"].clone())
            .collect();
        let approved = json!({"view":view,"refs":refs});
        remote = Some(source);
        (response, approved)
    };
    ensure!(
        approved["view"] == view,
        "publication changed during selection"
    );
    let records: Vec<RecordRevision> = serde_json::from_value(approved["refs"].clone())?;
    let facts = response["facts"]
        .as_array()
        .context("approved response has no facts")?;
    ensure!(
        !facts.is_empty() && records.len() == facts.len(),
        "all selected facts require canonical revisions"
    );
    let identity = PreparationIdentity {
        recipient: c.recipient,
        authorized_view: view.clone(),
        model_revision: c.model_revision.clone(),
        runtime_profile: c.runtime_profile,
        encoding_revision: c.encoding_revision,
        position_policy: c.position_policy,
        records,
    };
    let key = identity.key()?;
    // Control-plane approval without compilation. Hosted delivery rechecks the
    // exact current selection after download and before activation.
    if std::env::args_os().nth(2).as_deref() == Some(std::ffi::OsStr::new("--check")) {
        revalidate(
            &mut reader,
            &mut remote,
            &response,
            &approved,
            &view,
            &c.query,
            c.limit,
        )?;
        println!(
            "{}",
            json!({"model":c.model_revision,"key":key,"recipient":identity.recipient,"authorized_view":view,"records":identity.records})
        );
        return Ok(());
    }

    let prepared = Cache::open(&c.cache_root)?.prepare(&identity, |output| {
        let mut child = Command::new(&c.compiler[0])
            .args(&c.compiler[1..])
            .arg("--output")
            .arg(output)
            .arg("--identity")
            .arg(&c.model_revision)
            .arg("--key")
            .arg(&key)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .spawn()?;
        let sent = child
            .stdin
            .take()
            .context("compiler stdin")?
            .write_all(&serde_json::to_vec(
                &json!({"identity":identity,"response":response}),
            )?);
        if let Err(error) = sent {
            let _ = child.kill();
            let _ = child.wait();
            return Err(error.into());
        }
        ensure!(child.wait()?.success(), "native compilation failed");
        NativeStore::admit(output, &c.model_revision, &key, c.host_memory_budget)?;
        Ok(())
    })?;
    // Revalidate even for cache hits. A stored tensor is not continuing authority.
    revalidate(
        &mut reader,
        &mut remote,
        &response,
        &approved,
        &view,
        &c.query,
        c.limit,
    )?;
    println!(
        "{}",
        json!({"root":prepared.path,"model":c.model_revision,"key":key,"recipient":identity.recipient,"authorized_view":view,"records":identity.records,"reused":prepared.reused})
    );
    Ok(())
}
fn main() {
    if run().is_err() {
        eprintln!("native preparation unavailable");
        std::process::exit(1);
    }
}
