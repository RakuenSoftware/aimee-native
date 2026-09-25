//! Signed runtime defaults and owned broker/container process lifecycle.
use crate::{Config, atomic, delivery::Profile};
use anyhow::{Context, Result, ensure};
use fs2::FileExt;
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    fs,
    os::unix::{fs::FileTypeExt, process::CommandExt},
    path::{Path, PathBuf},
    process::{Child, Command},
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Defaults {
    pub schema: u32,
    pub native_model: String,
    pub model_config_sha256: String,
    pub host_memory_budget: u64,
    pub device_memory_budget: u64,
    pub disk_budget: u64,
    pub serve: Value,
}
pub fn initialize(
    root: &Path,
    release: &Path,
    connection: &Config,
    profile: &Profile,
) -> Result<(Value, Defaults)> {
    let d: Defaults = serde_json::from_slice(&fs::read(release.join("runtime/profile.json"))?)?;
    ensure!(
        d.schema == 1
            && d.native_model == profile.model
            && d.model_config_sha256 == profile.model_config_sha256,
        "connected memory profile does not match installed runtime"
    );
    ensure!(
        d.host_memory_budget > 0
            && d.device_memory_budget > 0
            && d.disk_budget >= d.host_memory_budget
            && d.serve.is_object(),
        "invalid runtime defaults"
    );
    ensure!(
        hex::encode(Sha256::digest(fs::read(
            release.join("models/config.json")
        )?)) == d.model_config_sha256,
        "installed model configuration mismatch"
    );
    let memory = fs::canonicalize(&connection.memory_root)?;
    let catalog = memory.join("catalog.json");
    // Every start discards cached authorization state, but retains immutable bytes.
    // Selection obtains a fresh grant even for an already downloaded artifact.
    atomic(
        &catalog,
        &serde_json::to_vec(
            &json!({"recipient":profile.recipient,"model_config_sha256":profile.model_config_sha256,"publications":{},"selections":[]}),
        )?,
    )?;
    let serving = json!({"recipient":profile.recipient,"catalog":catalog,"selection_socket":memory.join("selection.sock"),"control_socket":memory.join("control.sock"),"start_paused":true,"host_memory_budget":d.host_memory_budget,"device_memory_budget":d.device_memory_budget,"disk_backed":true,"serve":d.serve});
    atomic(&root.join("serving.json"), &serde_json::to_vec(&serving)?)?;
    Ok((serving, d))
}
static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn stop(_: libc::c_int) {
    STOP.store(true, Ordering::Relaxed);
}
fn terminate(child: &mut Child) {
    if child.try_wait().ok().flatten().is_some() {
        return;
    }
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    let deadline = Instant::now() + Duration::from_secs(15);
    while Instant::now() < deadline {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
}
fn death_signal(cmd: &mut Command) {
    // The direct children stop even if this supervisor is killed without cleanup.
    let parent = unsafe { libc::getpid() };
    unsafe {
        cmd.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            if libc::getppid() != parent {
                return Err(std::io::Error::other("supervisor exited"));
            }
            Ok(())
        });
    }
}
pub fn lock(root: &Path) -> Result<fs::File> {
    let f = fs::OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(root.join("serving.lock"))?;
    f.try_lock_exclusive()
        .context("native runtime is already running")?;
    Ok(f)
}
pub fn clean_sockets(memory: &Path) -> Result<()> {
    // Only call with the serving lock held. Remove socket nodes, never files/links.
    for name in ["selection.sock", "control.sock"] {
        let p = memory.join(name);
        match fs::symlink_metadata(&p) {
            Ok(m) => {
                ensure!(m.file_type().is_socket(), "unexpected control endpoint");
                fs::remove_file(p)?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}
pub fn supervise(
    root: &Path,
    runtime: &mut Command,
    model: &str,
    disk_budget: u64,
    socket: PathBuf,
) -> Result<()> {
    STOP.store(false, Ordering::Relaxed);
    let old_term = unsafe { libc::signal(libc::SIGTERM, stop as *const () as libc::sighandler_t) };
    let old_int = unsafe { libc::signal(libc::SIGINT, stop as *const () as libc::sighandler_t) };
    let mut broker = Command::new(std::env::current_exe()?);
    broker
        .arg("--root")
        .arg(root)
        .arg("memory-agent")
        .arg("--serving")
        .arg(root.join("serving.json"))
        .arg("--model")
        .arg(model)
        .arg("--disk-budget")
        .arg(disk_budget.to_string());
    death_signal(&mut broker);
    death_signal(runtime);
    let mut broker = broker.spawn()?;
    let outcome = (|| -> Result<()> {
        let deadline = Instant::now() + Duration::from_secs(10);
        while !socket.exists() {
            ensure!(
                !STOP.load(Ordering::Relaxed)
                    && broker.try_wait()?.is_none()
                    && Instant::now() < deadline,
                "native broker did not start"
            );
            std::thread::sleep(Duration::from_millis(20));
        }
        let mut model = runtime.spawn()?;
        let result = (|| -> Result<()> {
            loop {
                if STOP.load(Ordering::Relaxed) {
                    return Ok(());
                }
                if let Some(status) = model.try_wait()? {
                    ensure!(status.success(), "native runtime exited unsuccessfully");
                    return Ok(());
                }
                ensure!(
                    broker.try_wait()?.is_none(),
                    "native broker exited; stopping runtime"
                );
                std::thread::sleep(Duration::from_millis(100));
            }
        })();
        terminate(&mut model);
        result
    })();
    terminate(&mut broker);
    unsafe {
        libc::signal(libc::SIGTERM, old_term);
        libc::signal(libc::SIGINT, old_int);
    }
    let _ = fs::remove_file(socket);
    outcome
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn bootstrap_binds_recipient_model_and_clears_old_authority() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path();
        crate::connect(root, "https://example.invalid", "fixture").unwrap();
        let c: Config =
            serde_json::from_slice(&fs::read(root.join("config.json")).unwrap()).unwrap();
        let release = root.join("release");
        fs::create_dir_all(release.join("models")).unwrap();
        fs::create_dir_all(release.join("runtime")).unwrap();
        fs::write(release.join("models/config.json"), b"{}").unwrap();
        let sha = hex::encode(Sha256::digest(b"{}"));
        let defaults = json!({"schema":1,"native_model":"gemma","model_config_sha256":sha,"host_memory_budget":100,"device_memory_budget":100,"disk_budget":1000,"serve":{"tensor_parallel_size":2}});
        fs::write(
            release.join("runtime/profile.json"),
            serde_json::to_vec(&defaults).unwrap(),
        )
        .unwrap();
        let mut p = Profile {
            schema: 1,
            recipient: "alice".into(),
            model: "gemma".into(),
            model_config_sha256: sha,
        };
        let (serving, _) = initialize(root, &release, &c, &p).unwrap();
        assert_eq!(serving["start_paused"], true);
        fs::write(
            c.memory_root.join("catalog.json"),
            br#"{"recipient":"old-user","publications":{"stale":{}}}"#,
        )
        .unwrap();
        initialize(root, &release, &c, &p).unwrap();
        let cat: Value =
            serde_json::from_slice(&fs::read(c.memory_root.join("catalog.json")).unwrap()).unwrap();
        assert_eq!(cat["recipient"], "alice");
        assert_eq!(cat["publications"], json!({}));
        p.model = "another-model".into();
        assert!(initialize(root, &release, &c, &p).is_err());
    }
    #[test]
    fn exclusive_runtime_lock_and_socket_cleanup_reject_files() {
        let tmp = tempfile::tempdir().unwrap();
        let guard = lock(tmp.path()).unwrap();
        assert!(lock(tmp.path()).is_err());
        drop(guard);
        assert!(lock(tmp.path()).is_ok());
        fs::write(tmp.path().join("control.sock"), b"keep").unwrap();
        assert!(clean_sockets(tmp.path()).is_err());
        assert_eq!(fs::read(tmp.path().join("control.sock")).unwrap(), b"keep");
    }
}
