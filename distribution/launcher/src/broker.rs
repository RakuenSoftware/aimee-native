//! Host-side selection broker. No private preparation or credentials enter vLLM.
use crate::{Config, atomic, delivery};
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{BufRead, BufReader, Read, Write},
    os::unix::{
        fs::PermissionsExt,
        net::{UnixListener, UnixStream},
    },
    path::Path,
    time::Duration,
};

fn control(path: &Path, request: Value) -> Result<Value> {
    let seconds = if request["op"] == "refresh" { 720 } else { 150 };
    control_with_timeout(path, request, Duration::from_secs(seconds))
}
fn control_with_timeout(path: &Path, request: Value, timeout: Duration) -> Result<Value> {
    let mut s = UnixStream::connect(path)?;
    s.set_read_timeout(Some(timeout))?;
    s.set_write_timeout(Some(Duration::from_secs(10)))?;
    serde_json::to_writer(&mut s, &request)?;
    s.write_all(b"\n")?;
    let mut line = String::new();
    BufReader::new(s).take(65537).read_line(&mut line)?;
    ensure!(
        line.len() <= 65536 && line.ends_with('\n'),
        "invalid control response"
    );
    let result: Value = serde_json::from_str(&line)?;
    ensure!(
        result.get("error").is_none(),
        "native activation unavailable"
    );
    Ok(result)
}
pub(crate) fn requires_restart(path: &Path) -> Result<bool> {
    let response = control_with_timeout(path, json!({"op":"status"}), Duration::from_secs(2))?;
    match response["state"].as_str() {
        Some("restart_required") => Ok(true),
        Some("active" | "paused") => Ok(false),
        _ => anyhow::bail!("invalid native health state"),
    }
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Query {
    query: String,
}

pub fn serve(
    http: reqwest::blocking::Client,
    connection: Config,
    serving: &Path,
    model: &str,
    disk_budget: u64,
) -> Result<()> {
    let c: Value = serde_json::from_slice(&fs::read(serving)?)?;
    let recipient = c["recipient"].as_str().context("missing recipient")?;
    let socket = Path::new(
        c["selection_socket"]
            .as_str()
            .context("missing selection socket")?,
    );
    let ctl = Path::new(
        c["control_socket"]
            .as_str()
            .context("missing control socket")?,
    );
    let catalog = Path::new(c["catalog"].as_str().context("missing catalog")?);
    let memory = fs::canonicalize(&connection.memory_root)?;
    for path in [socket, ctl, catalog] {
        ensure!(
            path.parent().map(fs::canonicalize).transpose()?.as_ref() == Some(&memory),
            "control paths must be in managed memory root"
        );
    }
    // A private parent and mode 0600 restrict this endpoint to the installation
    // owner. Refuse to replace another broker's socket or stale endpoint silently.
    ensure!(
        fs::metadata(&memory)?.permissions().mode() & 0o077 == 0,
        "memory directory must be private"
    );
    let listener = UnixListener::bind(socket)?;
    fs::set_permissions(socket, fs::Permissions::from_mode(0o600))?;
    struct Cleanup<'a>(&'a Path);
    impl Drop for Cleanup<'_> {
        fn drop(&mut self) {
            let _ = fs::remove_file(self.0);
        }
    }
    let _cleanup = Cleanup(socket);
    for incoming in listener.incoming() {
        let mut s = incoming?;
        s.set_read_timeout(Some(Duration::from_secs(10)))?;
        s.set_write_timeout(Some(Duration::from_secs(10)))?;
        let result = (|| -> Result<Value> {
            let mut line = String::new();
            BufReader::new(s.try_clone()?)
                .take(131073)
                .read_line(&mut line)?;
            ensure!(
                line.len() <= 131072 && line.ends_with('\n'),
                "invalid selection request"
            );
            let query: Query = serde_json::from_str(&line)?;
            let selection = delivery::select(
                &http,
                &connection,
                &query.query,
                recipient,
                model,
                disk_budget,
            )?;
            let raw = fs::read(catalog)?;
            let mut cat: Value = serde_json::from_slice(&raw)?;
            ensure!(cat["recipient"] == recipient, "catalog recipient mismatch");
            let (offer, root) = match selection {
                delivery::Selection::Memory(offer, root) => (offer, root),
                delivery::Selection::Empty(empty) => {
                    let status = control(ctl, json!({"op":"status"}))?;
                    ensure!(
                        status["state"] != "restart_required",
                        "worker restart required"
                    );
                    let bytes = if status["state"] == "active" {
                        raw
                    } else {
                        // Startup/recovery/withdrawal must never reactivate old grants.
                        let withdrawn = control(ctl, json!({"op":"withdraw"}))?;
                        cat["publications"] = json!({});
                        cat["selections"] = json!([]);
                        let bytes = serde_json::to_vec(&cat)?;
                        atomic(catalog, &bytes)?;
                        control(
                            ctl,
                            json!({"op":"refresh","generation":withdrawn["generation"]}),
                        )?;
                        // A cold activation can take time. Recheck authority after
                        // refresh, just as the nonempty publication path does.
                        let checked = delivery::select(
                            &http,
                            &connection,
                            &query.query,
                            recipient,
                            model,
                            disk_budget,
                        );
                        if !matches!(checked, Ok(delivery::Selection::Empty(ref current)) if current.authorized_view == empty.authorized_view)
                        {
                            let _ = control(ctl, json!({"op":"withdraw"}));
                            anyhow::bail!("empty selection changed during activation");
                        }
                        bytes
                    };
                    return Ok(
                        json!({"publication":null,"catalog_digest":hex::encode(Sha256::digest(&bytes))}),
                    );
                }
            };
            let desired = json!({"root":root,"model":offer.model,"key":offer.key});
            let binding = json!({"publication":offer.key,"authorized_view":offer.authorized_view,"records":offer.records});
            let matched = cat["publications"][&offer.key] == desired
                && cat["selections"]
                    .as_array()
                    .is_some_and(|a| a.contains(&binding));
            if matched && control(ctl, json!({"op":"status"}))?["state"] == "active" {
                return Ok(
                    json!({"publication":offer.key,"catalog_digest":hex::encode(Sha256::digest(&raw))}),
                );
            }
            let withdrawn = control(ctl, json!({"op":"withdraw"}))?;
            let mut retained = cat["selections"].as_array().cloned().unwrap_or_default();
            retained.retain(|b| {
                b["authorized_view"] == offer.authorized_view && b["publication"] != offer.key
            });
            let names: std::collections::HashSet<String> = retained
                .iter()
                .filter_map(|b| b["publication"].as_str().map(str::to_owned))
                .collect();
            let pubs = cat["publications"]
                .as_object_mut()
                .context("invalid catalog")?;
            pubs.retain(|k, _| names.contains(k));
            pubs.insert(offer.key.clone(), desired);
            retained.push(binding);
            cat["selections"] = json!(retained);
            let bytes = serde_json::to_vec(&cat)?;
            atomic(catalog, &bytes)?;
            control(
                ctl,
                json!({"op":"refresh","generation":withdrawn["generation"]}),
            )?;
            if let Err(e) = delivery::approve(&http, &connection, &offer) {
                let _ = control(ctl, json!({"op":"withdraw"}));
                return Err(e);
            }
            Ok(
                json!({"publication":offer.key,"catalog_digest":hex::encode(Sha256::digest(&bytes))}),
            )
        })();
        let response = result.unwrap_or_else(|error| {
            eprintln!("native selection unavailable: {error:#}");
            json!({"error":"native_selection_unavailable"})
        });
        // Disconnects do not kill the host broker or undo a completed installation.
        let _ = serde_json::to_writer(&mut s, &response);
        let _ = s.write_all(b"\n");
    }
    Ok(())
}

#[cfg(test)]
mod health_tests {
    use super::*;
    #[test]
    fn only_explicit_restart_state_requests_recovery() {
        for state in ["active", "paused", "restart_required", "unknown"] {
            let tmp = tempfile::tempdir().unwrap();
            let path = tmp.path().join("control.sock");
            let listener = UnixListener::bind(&path).unwrap();
            let worker = std::thread::spawn(move || {
                let (mut stream, _) = listener.accept().unwrap();
                let mut line = String::new();
                BufReader::new(stream.try_clone().unwrap())
                    .read_line(&mut line)
                    .unwrap();
                assert_eq!(
                    serde_json::from_str::<Value>(&line).unwrap(),
                    json!({"op":"status"})
                );
                writeln!(stream, "{}", json!({"state":state})).unwrap();
            });
            let response = requires_restart(&path);
            if state == "unknown" {
                assert!(response.is_err());
            } else {
                assert_eq!(response.unwrap(), state == "restart_required");
            }
            worker.join().unwrap();
        }
    }
}
