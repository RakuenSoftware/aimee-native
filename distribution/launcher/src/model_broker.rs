//! Account-authorized selection for the dedicated installed model plugin.
//! Aimee owns source rows. The private model control endpoint derives banks;
//! model geometry and positioning remain in the model's one Rust adapter.
use crate::{Config, atomic, primitive, private_dir};
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs, io::{BufRead, BufReader, Read, Write}, os::unix::{fs::PermissionsExt, net::{UnixListener, UnixStream}}, path::Path, time::Duration};

fn digest(bytes: &[u8]) -> String { hex::encode(Sha256::digest(bytes)) }

fn control(path: &Path, request: Value) -> Result<Value> {
    let mut stream = UnixStream::connect(path)?;
    stream.set_read_timeout(Some(Duration::from_secs(1200)))?;
    stream.set_write_timeout(Some(Duration::from_secs(10)))?;
    serde_json::to_writer(&mut stream, &request)?;
    stream.write_all(b"\n")?;
    let mut line = String::new();
    BufReader::new(stream).take(65537).read_line(&mut line)?;
    ensure!(line.len() <= 65536 && line.ends_with('\n'), "invalid model control response");
    let response: Value = serde_json::from_str(&line)?;
    ensure!(response.get("error").is_none(), "model preparation or activation unavailable");
    Ok(response)
}

fn select(connection: &Config, serving: &Value, query: &str) -> Result<Value> {

    let ctl = Path::new(serving["control_socket"].as_str().context("control socket missing")?);
    let catalog = Path::new(serving["catalog"].as_str().context("catalog missing")?);
    let recipient = serving["recipient"].as_str().context("recipient missing")?;
    let source = primitive::fetch_for_recipient(connection, query, 1024, recipient)?;
    let view = digest(&serde_json::to_vec(&source)?);
    let cache_key = digest(&serde_json::to_vec(&json!([
        recipient, serving, source
    ]))?);
    let current: Value = serde_json::from_slice(&fs::read(catalog)?)?;
    ensure!(current["recipient"] == recipient, "catalog recipient mismatch");
    if current["authorized_view"] == view && control(ctl, json!({"op":"status"}))?["state"] == "active" {
        // Recheck authority even when immutable prepared bytes are already warm.
        ensure!(primitive::fetch_for_recipient(connection, query, 1024, recipient)? == source, "source changed during selection");
        return Ok(json!({"publication":current["selected_publication"],"catalog_digest":digest(&fs::read(catalog)?)}));
    }
    let withdrawn = control(ctl, json!({"op":"withdraw"}))?;
    let generation = withdrawn["generation"].as_u64().context("missing activation generation")?;
    let outcome = (|| -> Result<Value> {
        let mut next = json!({"recipient":recipient,"model_config_sha256":serving["model_config_sha256"],
            "publications":{},"authorized_view":view,"selected_publication":null});
        if !source.records.is_empty() {
            let prepared = connection.memory_root.join("prepared-model");
            private_dir(&prepared)?;
            let receipt = prepared.join(format!("{cache_key}.json"));
            let publication = if receipt.exists() {
                serde_json::from_slice::<Value>(&fs::read(&receipt)?)?
            } else {
                let destination = prepared.join(&cache_key);
                // A receipt is committed before catalogue activation. With the
                // supervisor lock and serialized broker, an unreceipted extent
                // from a crashed preparation has no active catalogue reference.
                if destination.exists() || destination.is_symlink() {
                    ensure!(fs::symlink_metadata(&destination)?.is_dir(), "invalid incomplete cache entry");
                    fs::remove_dir_all(&destination)?;
                }
                let mut used = 0u64;
                for directory in fs::read_dir(&prepared)? {
                    let directory = directory?;
                    if directory.file_type()?.is_dir() {
                        for artifact in fs::read_dir(directory.path())? {
                            let artifact = artifact?;
                            ensure!(artifact.file_type()?.is_file(), "unexpected prepared cache entry");
                            used = used.checked_add(artifact.metadata()?.len()).context("cache extent overflow")?;
                        }
                    }
                }
                let reserve = serving["host_memory_budget"].as_u64().context("host memory budget missing")?;
                let budget = serving["disk_budget"].as_u64().unwrap_or(16*1024*1024*1024);
                ensure!(used.checked_add(reserve).is_some_and(|total| total <= budget), "prepared cache disk budget exhausted");
                let facts: Vec<&str> = source.records.iter().map(|record| record.content.as_str()).collect();
                let response = control(ctl, json!({"op":"prepare","generation":generation,
                    "facts":facts,"context":serving["native_system_context"].as_str().unwrap_or(""),
                    "destination":destination}))?;
                let publication = response["publication"].clone();
                ensure!(publication.is_object(), "model did not publish a complete bank");
                atomic(&receipt, &serde_json::to_vec(&publication)?)?;
                publication
            };
            next["publications"][&cache_key] = publication;
            next["selected_publication"] = json!(cache_key);
        }
        ensure!(primitive::fetch_for_recipient(connection, query, 1024, recipient)? == source, "authority changed during preparation");
        atomic(catalog, &serde_json::to_vec(&next)?)?;
        control(ctl, json!({"op":"refresh","generation":generation}))?;
        ensure!(primitive::fetch_for_recipient(connection, query, 1024, recipient)? == source, "authority changed during activation");
        Ok(json!({"publication":next["selected_publication"],"catalog_digest":digest(&fs::read(catalog)?)}))
    })();
    if outcome.is_err() { let _ = control(ctl, json!({"op":"withdraw"})); }
    outcome
}

pub fn serve(connection: Config, serving_path: &Path) -> Result<()> {
    let serving: Value = serde_json::from_slice(&fs::read(serving_path)?)?;
    let socket = Path::new(serving["selection_socket"].as_str().context("selection socket missing")?);
    ensure!(fs::metadata(&connection.memory_root)?.permissions().mode() & 0o077 == 0, "memory root must be private");
    ensure!(socket.parent().map(fs::canonicalize).transpose()? == Some(fs::canonicalize(&connection.memory_root)?), "selection endpoint outside managed memory root");
    let listener = UnixListener::bind(socket)?;
    fs::set_permissions(socket, fs::Permissions::from_mode(0o600))?;
    for incoming in listener.incoming() {
        let mut stream = incoming?;
        stream.set_read_timeout(Some(Duration::from_secs(10)))?;
        stream.set_write_timeout(Some(Duration::from_secs(10)))?;
        let response = (|| -> Result<Value> {
            let mut line = String::new();
            BufReader::new(stream.try_clone()?).take(131073).read_line(&mut line)?;
            ensure!(line.len() <= 131072 && line.ends_with('\n'), "invalid selection request");
            let request: Value = serde_json::from_str(&line)?;
            ensure!(request.as_object().is_some_and(|object| object.len() == 1), "invalid selection fields");
            select(&connection, &serving, request["query"].as_str().context("missing query")?)
        })().unwrap_or_else(|_| json!({"error":"authorized native selection unavailable"}));
        serde_json::to_writer(&mut stream, &response)?;
        stream.write_all(b"\n")?;
    }
    Ok(())
}
