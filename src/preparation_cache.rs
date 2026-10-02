//! Private preparation-worker cache. Not compiled into the native client.
//! Inputs must come from Aimee's authorized publication path. This module does
//! not issue authority, select records, or turn client-supplied IDs into access.
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    fs::{self, File, OpenOptions},
    os::{
        fd::AsRawFd,
        unix::fs::{OpenOptionsExt, PermissionsExt},
    },
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RecordRevision {
    pub namespace: String,
    pub id: String,
    pub revision: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PreparationIdentity {
    pub recipient: String,
    pub authorized_view: String,
    pub model_revision: String,
    pub runtime_profile: String,
    pub encoding_revision: String,
    pub position_policy: String,
    /// Preserve selection order. Never key only on the first returned record.
    pub records: Vec<RecordRevision>,
}
impl PreparationIdentity {
    pub fn key(&self) -> Result<String> {
        for s in [
            &self.recipient,
            &self.authorized_view,
            &self.model_revision,
            &self.runtime_profile,
            &self.encoding_revision,
            &self.position_policy,
        ] {
            ensure!(!s.is_empty(), "incomplete preparation identity");
        }
        ensure!(!self.records.is_empty(), "no selected records");
        let mut seen = HashSet::new();
        for r in &self.records {
            ensure!(
                !r.namespace.is_empty() && !r.id.is_empty() && !r.revision.is_empty(),
                "incomplete record revision"
            );
            ensure!(
                seen.insert((&r.namespace, &r.id)),
                "duplicate selected record"
            );
        }
        let mut h = Sha256::new();
        h.update(b"aimee-preparation-cache-v1\0");
        h.update(serde_json::to_vec(self)?);
        Ok(format!("{:x}", h.finalize()))
    }
}
pub struct Prepared {
    pub path: PathBuf,
    pub reused: bool,
}
pub struct Cache {
    root: PathBuf,
}
impl Cache {
    pub fn open(root: &Path) -> Result<Self> {
        fs::create_dir_all(root)?;
        ensure!(
            !fs::symlink_metadata(root)?.file_type().is_symlink(),
            "cache root must be owned"
        );
        fs::set_permissions(root, fs::Permissions::from_mode(0o700))?;
        Ok(Self {
            root: root.to_owned(),
        })
    }
    /// Background worker only. Per-key interprocess locking coalesces concurrent
    /// requests. Compiler writes a new `payload` directory and validates it fully
    /// before returning. Failed preparation is never visible as a cache hit.
    pub fn prepare(
        &self,
        identity: &PreparationIdentity,
        compile: impl FnOnce(&Path) -> Result<()>,
    ) -> Result<Prepared> {
        let key = identity.key()?;
        let guard = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .mode(0o600)
            .open(self.root.join(format!("{key}.lock")))?;
        ensure!(
            unsafe { libc::flock(guard.as_raw_fd(), libc::LOCK_EX) } == 0,
            "preparation lock failed"
        );
        // flock is released by closing the descriptor, including on error/unwind.
        let path = self.root.join(&key);
        if path.is_dir() {
            return Ok(Prepared {
                path: path.join("payload"),
                reused: true,
            });
        }
        let stage = tempfile::Builder::new()
            .prefix(".preparing-")
            .tempdir_in(&self.root)?;
        let payload = stage.path().join("payload");
        compile(&payload)?;
        ensure!(
            payload.is_dir(),
            "compiler did not publish a payload directory"
        );
        fs::write(
            stage.path().join("identity.json"),
            serde_json::to_vec(identity)?,
        )?;
        sync_tree(stage.path())?;
        fs::rename(stage.path(), &path)?;
        File::open(&self.root)?.sync_all()?;
        Ok(Prepared {
            path: path.join("payload"),
            reused: false,
        })
    }
}
fn sync_tree(root: &Path) -> Result<()> {
    for entry in fs::read_dir(root)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        ensure!(!ty.is_symlink(), "compiler output cannot contain symlinks");
        if ty.is_dir() {
            sync_tree(&entry.path())?;
        } else {
            ensure!(ty.is_file(), "compiler output must be regular files");
            File::open(entry.path())
                .context("open prepared output")?
                .sync_all()?;
        }
    }
    File::open(root)?.sync_all()?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    fn identity() -> PreparationIdentity {
        PreparationIdentity {
            recipient: "tenant/user".into(),
            authorized_view: "view1".into(),
            model_revision: "model1".into(),
            runtime_profile: "bf16-runtime1".into(),
            encoding_revision: "encoder1".into(),
            position_policy: "policy1".into(),
            records: (0..3)
                .map(|i| RecordRevision {
                    namespace: "personal".into(),
                    id: format!("{i}"),
                    revision: "1".into(),
                })
                .collect(),
        }
    }
    fn compile(path: &Path) -> Result<()> {
        fs::create_dir(path)?;
        fs::write(path.join("store"), b"fixture only")?;
        Ok(())
    }
    #[test]
    fn exact_selection_reuses_without_reencoding() {
        let tmp = tempfile::tempdir().unwrap();
        let c = Cache::open(tmp.path()).unwrap();
        let i = identity();
        assert!(!c.prepare(&i, compile).unwrap().reused);
        assert!(
            c.prepare(&i, |_| panic!("cache hit must not compile"))
                .unwrap()
                .reused
        );
    }
    #[test]
    fn every_record_order_revision_recipient_and_model_affect_reuse() {
        let original = identity();
        let key = original.key().unwrap();
        for idx in 0..3 {
            let mut i = identity();
            i.records[idx].revision = "2".into();
            assert_ne!(i.key().unwrap(), key);
        }
        let mut i = identity();
        i.records.swap(0, 2);
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.records.pop();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.recipient = "other/user".into();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.authorized_view = "view2".into();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.model_revision = "model2".into();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.runtime_profile = "q4".into();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.encoding_revision = "encoder2".into();
        assert_ne!(i.key().unwrap(), key);
        let mut i = identity();
        i.position_policy = "policy2".into();
        assert_ne!(i.key().unwrap(), key);
    }
    #[test]
    fn failed_compilation_never_becomes_visible() {
        let tmp = tempfile::tempdir().unwrap();
        let c = Cache::open(tmp.path()).unwrap();
        let i = identity();
        assert!(
            c.prepare(&i, |p| {
                compile(p)?;
                anyhow::bail!("failed roundtrip")
            })
            .is_err()
        );
        assert!(!c.prepare(&i, compile).unwrap().reused);
    }
    #[test]
    fn concurrent_preparation_is_coalesced() {
        let tmp = tempfile::tempdir().unwrap();
        let c = std::sync::Arc::new(Cache::open(tmp.path()).unwrap());
        let calls = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let jobs: Vec<_> = (0..6)
            .map(|_| {
                let c = c.clone();
                let calls = calls.clone();
                std::thread::spawn(move || {
                    c.prepare(&identity(), |p| {
                        calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                        compile(p)
                    })
                    .unwrap()
                    .reused
                })
            })
            .collect();
        let hits = jobs
            .into_iter()
            .filter_map(|j| if j.join().unwrap() { Some(()) } else { None })
            .count();
        assert_eq!(hits, 5);
        assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 1);
    }
    #[test]
    fn missing_identity_or_duplicate_records_rejected() {
        let mut i = identity();
        i.records.push(i.records[0].clone());
        assert!(i.key().is_err());
        let mut i = identity();
        i.authorized_view.clear();
        assert!(i.key().is_err());
    }
}
