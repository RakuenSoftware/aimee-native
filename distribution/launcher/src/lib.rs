//! Installation/control plane only. Never called from native attention.
use anyhow::{Context, Result, ensure};
use ed25519_dalek::{Signature, VerifyingKey};
use fs2::FileExt;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use std::{
    collections::HashSet,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Component, Path, PathBuf},
};

pub mod broker;
pub mod delivery;
pub mod runtime;

pub const ABI: u32 = 1;
pub const GATES: &[&str] = &[
    "native_accuracy",
    "quantized_model",
    "all_selected_records",
    "long_conversation",
    "tenant_session_isolation",
    "revision_withdrawal",
    "cold_warm_latency",
    "reusable_preparation",
    "clean_install",
    "binary_disclosure_audit",
    "authenticated_delivery",
    "license_dependency_audit",
];
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Artifact {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
    pub executable: bool,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Manifest {
    pub schema: u32,
    pub sequence: u64,
    pub version: String,
    pub platform: String,
    pub model: String,
    pub runtime: String,
    pub runtime_commit: String,
    pub abi: u32,
    pub engine: String,
    pub model_file: String,
    pub library: String,
    pub gates: Vec<String>,
    pub artifacts: Vec<Artifact>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema: u32,
    pub endpoint: String,
    pub token_file: PathBuf,
    pub memory_root: PathBuf,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub ca_file: Option<PathBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub client_identity: Option<PathBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub connect_address: Option<std::net::SocketAddr>,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Active {
    pub current: String,
    pub previous: Option<String>,
    pub high_water_sequence: u64,
}

pub fn platform() -> String {
    format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH)
}
pub fn component(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"-_.".contains(&c))
        && s != "."
        && s != ".."
}
pub fn relative(s: &str) -> bool {
    !s.is_empty()
        && !s.contains('\\')
        && !s.contains(':')
        && Path::new(s)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
}
pub fn validate(m: &Manifest) -> Result<()> {
    ensure!(
        m.schema == 1 && m.abi == ABI,
        "unsupported release interface"
    );
    ensure!(
        m.platform == platform(),
        "release does not match this platform"
    );
    ensure!(
        m.runtime == "vllm",
        "runtime is not supported by this launcher"
    );
    ensure!(
        m.runtime_commit.len() == 40 && m.runtime_commit.bytes().all(|c| c.is_ascii_hexdigit()),
        "runtime must be pinned"
    );
    ensure!(
        component(&m.version) && component(&m.model),
        "invalid release identity"
    );
    if m.gates.iter().any(|g| g == "lab_only") {
        ensure!(
            cfg!(feature = "lab-release"),
            "lab release rejected by production launcher"
        );
        ensure!(
            m.model.starts_with("lab-"),
            "lab release must use a lab model identity"
        );
    } else {
        ensure!(
            GATES.iter().all(|g| m.gates.iter().any(|v| v == g)),
            "release has not passed every production gate"
        );
    }
    ensure!(
        !m.artifacts.is_empty() && m.artifacts.len() <= 128,
        "invalid release file count"
    );
    let mut names = HashSet::new();
    for a in &m.artifacts {
        ensure!(
            relative(&a.path) && names.insert(&a.path),
            "invalid or duplicate artifact path"
        );
        let allowed = matches!(
            a.path.as_str(),
            "runtime/image.json" | "runtime/profile.json"
        ) || a.path == "models/merges.txt"
            || a.path == "bin/aimee-vllm"
            || a.path == "lib/libaimee_native.so"
            || (a.path.starts_with("lib/")
                && a.path.split('/').count() == 2
                && a.path.contains(".so"))
            || (a.path.starts_with("models/")
                && a.path.split('/').count() == 2
                && (a.path.ends_with(".gguf")
                    || a.path.ends_with(".safetensors")
                    || a.path.ends_with(".json")
                    || a.path.ends_with(".jinja")
                    || a.path.ends_with(".model")))
            || (a.path.starts_with("licenses/")
                && a.path.split('/').count() == 2
                && a.path.ends_with(".txt"));
        ensure!(allowed, "artifact is outside the client allowlist");
        ensure!(
            a.bytes > 0 && a.bytes < (1u64 << 42),
            "invalid artifact extent"
        );
        ensure!(
            a.sha256.len() == 64 && a.sha256.bytes().all(|c| c.is_ascii_hexdigit()),
            "invalid digest"
        );
        ensure!(
            a.executable == (a.path == "bin/aimee-vllm"),
            "invalid executable permission"
        );
    }
    ensure!(
        m.engine == "bin/aimee-vllm" && m.library == "lib/libaimee_native.so",
        "invalid runtime layout"
    );
    ensure!(m.model_file.starts_with("models/"), "invalid model path");
    for p in [&m.engine, &m.library, &m.model_file] {
        ensure!(names.contains(p), "missing runtime artifact");
    }
    Ok(())
}
/// Signed runtime descriptor. Mutable image tags are never accepted.
#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeImage {
    pub image: String,
    pub model_config: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gguf_matrix_backend: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mm_proj: Option<String>,
}
impl RuntimeImage {
    pub fn validate(&self) -> Result<()> {
        let (repository, digest) = self
            .image
            .rsplit_once("@sha256:")
            .context("container runtime must use an immutable digest")?;
        ensure!(
            !repository.is_empty()
                && repository.contains('/')
                && repository
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"/._-:".contains(&b))
                && !repository.starts_with('-')
                && digest.len() == 64
                && digest.bytes().all(|b| b.is_ascii_hexdigit()),
            "invalid runtime image identity"
        );
        ensure!(
            relative(&self.model_config)
                && self.model_config.starts_with("models/")
                && self.model_config.ends_with("config.json"),
            "invalid model configuration sidecar"
        );
        ensure!(
            matches!(
                self.gguf_matrix_backend.as_deref(),
                None | Some("cuda") | Some("triton")
            ),
            "invalid GGUF matrix backend"
        );
        if let Some(path) = &self.mm_proj {
            ensure!(
                relative(path) && path.starts_with("models/") && path.ends_with(".gguf"),
                "invalid GGUF projector path"
            );
        }
        Ok(())
    }
}

pub fn authenticate(raw: &[u8], signature: &[u8], public_key: &[u8; 32]) -> Result<Manifest> {
    ensure!(raw.len() <= 1024 * 1024, "manifest is too large");
    VerifyingKey::from_bytes(public_key)?
        .verify_strict(raw, &Signature::from_slice(signature)?)
        .context("release signature rejected")?;
    let m: Manifest = serde_json::from_slice(raw)?;
    validate(&m)?;
    Ok(m)
}
pub fn private_dir(path: &Path) -> Result<()> {
    fs::create_dir_all(path)?;
    ensure!(
        !fs::symlink_metadata(path)?.file_type().is_symlink(),
        "managed directory is a symlink"
    );
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    Ok(())
}
pub fn atomic(path: &Path, data: &[u8]) -> Result<()> {
    let parent = path.parent().context("missing parent")?;
    let mut f = tempfile::NamedTempFile::new_in(parent)?;
    f.as_file()
        .set_permissions(fs::Permissions::from_mode(0o600))?;
    f.write_all(data)?;
    f.as_file().sync_all()?;
    f.persist(path).map_err(|e| e.error)?;
    File::open(parent)?.sync_all()?;
    Ok(())
}
pub fn lock(root: &Path) -> Result<File> {
    private_dir(root)?;
    let f = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .mode(0o600)
        .open(root.join("update.lock"))?;
    f.lock_exclusive()?;
    Ok(f)
}
pub fn active(root: &Path) -> Result<Active> {
    let a: Active = serde_json::from_slice(&fs::read(root.join("active.json"))?)?;
    ensure!(
        component(&a.current) && a.previous.as_ref().is_none_or(|p| component(p)),
        "invalid active release"
    );
    Ok(a)
}
pub fn verify_file(mut input: impl Read, out: &Path, a: &Artifact) -> Result<()> {
    fs::create_dir_all(out.parent().context("missing artifact parent")?)?;
    let mut f = OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(out)?;
    let mut hash = Sha256::new();
    let mut total = 0u64;
    let mut buf = [0u8; 128 * 1024];
    loop {
        let n = input.read(&mut buf).map_err(|error| {
            anyhow::anyhow!(
                "release artifact {} read failed after {} of {} bytes: {:?}",
                a.path,
                total,
                a.bytes,
                error
            )
        })?;
        if n == 0 {
            break;
        }
        total += n as u64;
        ensure!(total <= a.bytes, "artifact exceeds declared extent");
        hash.update(&buf[..n]);
        f.write_all(&buf[..n])?;
    }
    ensure!(
        total == a.bytes && hex::encode(hash.finalize()).eq_ignore_ascii_case(&a.sha256),
        "artifact integrity rejected"
    );
    f.set_permissions(fs::Permissions::from_mode(if a.executable {
        0o700
    } else {
        0o600
    }))?;
    f.sync_all()?;
    Ok(())
}
/// Installer takes a streaming fetcher. No archive extraction and no remote shell.
pub fn install(
    root: &Path,
    raw: &[u8],
    signature: &[u8],
    key: &[u8; 32],
    mut fetch: impl FnMut(&str) -> Result<Box<dyn Read>>,
) -> Result<Active> {
    let m = authenticate(raw, signature, key)?;
    let _guard = lock(root)?;
    let old = if root.join("active.json").exists() {
        Some(active(root)?)
    } else {
        None
    };
    let id = hex::encode(Sha256::digest(raw));
    if let Some(a) = &old {
        if a.current == id {
            return Ok(a.clone());
        }
        ensure!(
            m.sequence > a.high_water_sequence,
            "release sequence rollback rejected"
        );
    }
    let releases = root.join("releases");
    private_dir(&releases)?;
    let stage = tempfile::Builder::new()
        .prefix(".stage-")
        .tempdir_in(&releases)?;
    for a in &m.artifacts {
        verify_file(fetch(&a.path)?, &stage.path().join(&a.path), a)?;
    }
    atomic(&stage.path().join("manifest.json"), raw)?;
    atomic(&stage.path().join("manifest.sig"), signature)?;
    sync_directories(stage.path())?;
    let final_path = releases.join(&id);
    if final_path.exists() {
        // A crash may leave a complete directory before the active pointer was
        // committed. This ID cannot be current (handled above), or an older
        // installed revision (sequence guard). Replace only this owned orphan.
        fs::remove_dir_all(&final_path)?;
    }
    fs::rename(stage.path(), &final_path)?;
    File::open(&releases)?.sync_all()?;
    let next = Active {
        current: id,
        previous: old.map(|a| a.current),
        high_water_sequence: m.sequence,
    };
    atomic(
        &root.join("active.json"),
        &serde_json::to_vec_pretty(&next)?,
    )?;
    Ok(next)
}
fn sync_directories(path: &Path) -> Result<()> {
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        if entry.file_type()?.is_dir() {
            sync_directories(&entry.path())?;
        }
    }
    File::open(path)?.sync_all()?;
    Ok(())
}
pub fn rollback(root: &Path) -> Result<Active> {
    let _guard = lock(root)?;
    let old = active(root)?;
    let previous = old.previous.context("no previous release")?;
    ensure!(
        root.join("releases")
            .join(&previous)
            .join("manifest.json")
            .is_file(),
        "previous release unavailable"
    );
    let next = Active {
        current: previous,
        previous: Some(old.current),
        high_water_sequence: old.high_water_sequence,
    };
    atomic(
        &root.join("active.json"),
        &serde_json::to_vec_pretty(&next)?,
    )?;
    Ok(next)
}
pub fn connect(root: &Path, endpoint: &str, token: &str) -> Result<()> {
    connect_with_tls(root, endpoint, token, None, None)
}
pub fn validate_endpoint(endpoint: &str) -> Result<reqwest::Url> {
    let u = reqwest::Url::parse(endpoint)?;
    ensure!(
        u.scheme() == "https"
            && u.username().is_empty()
            && u.password().is_none()
            && u.query().is_none()
            && u.fragment().is_none(),
        "Aimee endpoint must be HTTPS without embedded credentials or query"
    );
    Ok(u)
}
pub fn validate_connect_address(url: &reqwest::Url, address: std::net::SocketAddr) -> Result<()> {
    let host = url.host_str().context("endpoint hostname required")?;
    ensure!(
        host.parse::<std::net::IpAddr>().is_err() && !host.starts_with('['),
        "connect address requires a DNS-name endpoint"
    );
    ensure!(
        url.port_or_known_default() == Some(address.port()),
        "connect address port must match the endpoint"
    );
    Ok(())
}
pub fn connect_with_tls(
    root: &Path,
    endpoint: &str,
    token: &str,
    ca: Option<&[u8]>,
    identity: Option<&[u8]>,
) -> Result<()> {
    connect_with_address(root, endpoint, token, ca, identity, None)
}
pub fn connect_with_address(
    root: &Path,
    endpoint: &str,
    token: &str,
    ca: Option<&[u8]>,
    identity: Option<&[u8]>,
    connect_address: Option<std::net::SocketAddr>,
) -> Result<()> {
    let u = validate_endpoint(endpoint)?;
    if let Some(address) = connect_address {
        validate_connect_address(&u, address)?;
    }
    if let Some(pem) = ca {
        reqwest::Certificate::from_pem(pem)?;
    }
    if let Some(pem) = identity {
        reqwest::Identity::from_pem(pem)?;
    }
    ensure!(
        !token.trim().is_empty() && token.len() <= 16384 && !token.trim().contains(['\r', '\n']),
        "invalid credential"
    );
    let _guard = lock(root)?;
    let credentials = root.join("credentials");
    private_dir(&credentials)?;
    // Immutable credential files make config replacement atomic for running readers.
    let mut secret = tempfile::Builder::new()
        .prefix("credential-")
        .tempfile_in(&credentials)?;
    secret
        .as_file()
        .set_permissions(fs::Permissions::from_mode(0o600))?;
    secret.write_all(token.trim().as_bytes())?;
    secret.as_file().sync_all()?;
    let (_, token_file) = secret.keep().map_err(|e| e.error)?;
    let memory_root = root.join("memory");
    private_dir(&memory_root)?;
    let save_tls = |prefix: &str, data: Option<&[u8]>| -> Result<Option<PathBuf>> {
        data.map(|bytes| {
            let mut f = tempfile::Builder::new()
                .prefix(prefix)
                .tempfile_in(&credentials)?;
            f.as_file()
                .set_permissions(fs::Permissions::from_mode(0o600))?;
            f.write_all(bytes)?;
            f.as_file().sync_all()?;
            Ok(f.keep().map_err(|e| e.error)?.1)
        })
        .transpose()
    };
    let config = Config {
        schema: 1,
        endpoint: u.to_string(),
        token_file,
        memory_root,
        ca_file: save_tls("ca-", ca)?,
        client_identity: save_tls("identity-", identity)?,
        connect_address,
    };
    atomic(
        &root.join("config.json"),
        &serde_json::to_vec_pretty(&config)?,
    )?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};
    use std::io::Cursor;
    #[test]
    fn connect_address_preserves_named_tls_endpoint_and_port() {
        let address = "192.0.2.10:8743".parse().unwrap();
        assert!(
            validate_connect_address(
                &validate_endpoint("https://memory.example:8743").unwrap(),
                address
            )
            .is_ok()
        );
        assert!(
            validate_connect_address(
                &validate_endpoint("https://memory.example").unwrap(),
                address
            )
            .is_err()
        );
        assert!(
            validate_connect_address(
                &validate_endpoint("https://192.0.2.10:8743").unwrap(),
                address
            )
            .is_err()
        );
        let root = tempfile::tempdir().unwrap();
        connect_with_address(
            root.path(),
            "https://memory.example:8743",
            "test-token",
            None,
            None,
            Some(address),
        )
        .unwrap();
        let config: Config =
            serde_json::from_slice(&fs::read(root.path().join("config.json")).unwrap()).unwrap();
        assert_eq!(config.connect_address, Some(address));
        assert_eq!(config.endpoint, "https://memory.example:8743/");
    }
    #[test]
    fn signed_tokenizer_merges_are_allowed() {
        let (mut m, _, _, _) = fixture(1);
        m.artifacts.push(Artifact {
            path: "models/merges.txt".into(),
            bytes: 10,
            sha256: "a".repeat(64),
            executable: false,
        });
        assert!(validate(&m).is_ok());
        m.artifacts.last_mut().unwrap().path = "models/arbitrary.txt".into();
        assert!(validate(&m).is_err());
    }
    #[test]
    fn container_descriptor_rejects_mutable_tags_and_escape_paths() {
        let mut d = RuntimeImage {
            image: format!("registry.example/aimee@sha256:{}", "a".repeat(64)),
            model_config: "models/config.json".into(),
            gguf_matrix_backend: None,
            mm_proj: None,
        };
        assert!(d.validate().is_ok());
        d.gguf_matrix_backend = Some("triton".into());
        d.mm_proj = Some("models/projector.gguf".into());
        assert!(d.validate().is_ok());
        d.mm_proj = Some("models/../projector.gguf".into());
        assert!(d.validate().is_err());
        d.mm_proj = None;
        d.gguf_matrix_backend = Some("typo".into());
        assert!(d.validate().is_err());
        d.gguf_matrix_backend = None;
        d.image = "registry.example/aimee:latest".into();
        assert!(d.validate().is_err());
        d.image = format!("registry.example/aimee@sha256:{}", "a".repeat(64));
        d.model_config = "models/../config.json".into();
        assert!(d.validate().is_err());
    }
    #[test]
    fn production_launcher_rejects_lab_release_marker() {
        let (mut m, _, _, _) = fixture(1);
        m.gates = vec!["lab_only".into()];
        m.model = "lab-fixture".into();
        assert_eq!(validate(&m).is_ok(), cfg!(feature = "lab-release"));
        m.model = "customer-model".into();
        assert!(validate(&m).is_err());
    }
    fn fixture(sequence: u64) -> (Manifest, Vec<u8>, Vec<u8>, [u8; 32]) {
        let files = [
            "bin/aimee-vllm",
            "lib/libaimee_native.so",
            "models/config.json",
        ];
        let m = Manifest {
            schema: 1,
            sequence,
            version: format!("test-{sequence}"),
            platform: platform(),
            model: "test".into(),
            runtime: "vllm".into(),
            runtime_commit: "a".repeat(40),
            abi: ABI,
            engine: files[0].into(),
            library: files[1].into(),
            model_file: files[2].into(),
            gates: GATES.iter().map(|s| s.to_string()).collect(),
            artifacts: files
                .iter()
                .map(|p| Artifact {
                    path: p.to_string(),
                    bytes: 4,
                    sha256: hex::encode(Sha256::digest(b"test")),
                    executable: *p == files[0],
                })
                .collect(),
        };
        let raw = serde_json::to_vec(&m).unwrap();
        // Ephemeral test-only key, never a release trust root.
        let key = SigningKey::from_bytes(&[7u8; 32]);
        let sig = key.sign(&raw).to_bytes().to_vec();
        (m, raw, sig, key.verifying_key().to_bytes())
    }
    fn fetch(_: &str) -> Result<Box<dyn Read>> {
        Ok(Box::new(Cursor::new(b"test".to_vec())))
    }
    #[test]
    fn authenticated_install_update_and_explicit_rollback() {
        let d = tempfile::tempdir().unwrap();
        let (_, raw, sig, key) = fixture(1);
        let a = install(d.path(), &raw, &sig, &key, fetch).unwrap();
        assert_eq!(
            install(d.path(), &raw, &sig, &key, fetch).unwrap().current,
            a.current
        );
        let (_, raw2, sig2, _) = fixture(2);
        let b = install(d.path(), &raw2, &sig2, &key, fetch).unwrap();
        assert_eq!(b.previous, Some(a.current.clone()));
        assert!(install(d.path(), &raw, &sig, &key, fetch).is_err());
        let c = rollback(d.path()).unwrap();
        assert_eq!(c.current, a.current);
        assert_eq!(c.high_water_sequence, 2);
        assert_eq!(rollback(d.path()).unwrap().current, b.current);
    }
    #[test]
    fn corruption_does_not_change_active_release() {
        let d = tempfile::tempdir().unwrap();
        let (_, raw, sig, key) = fixture(1);
        let a = install(d.path(), &raw, &sig, &key, fetch).unwrap();
        let (_, raw2, sig2, _) = fixture(2);
        assert!(
            install(d.path(), &raw2, &sig2, &key, |_| Ok(Box::new(Cursor::new(
                b"oops".to_vec()
            ))))
            .is_err()
        );
        assert_eq!(active(d.path()).unwrap().current, a.current);
        assert_eq!(fs::read_dir(d.path().join("releases")).unwrap().count(), 1);
    }
    #[test]
    fn interrupted_download_keeps_active_release_and_reports_progress() {
        struct Interrupted(bool);
        impl Read for Interrupted {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                if !self.0 {
                    self.0 = true;
                    buf[0] = b'x';
                    return Ok(1);
                }
                Err(std::io::Error::new(
                    std::io::ErrorKind::ConnectionReset,
                    "peer reset",
                ))
            }
        }
        let d = tempfile::tempdir().unwrap();
        let (_, raw, sig, key) = fixture(1);
        let first = install(d.path(), &raw, &sig, &key, fetch).unwrap();
        let (_, raw2, sig2, _) = fixture(2);
        let error = install(d.path(), &raw2, &sig2, &key, |_| {
            Ok(Box::new(Interrupted(false)))
        })
        .unwrap_err();
        let message = error.to_string();
        assert!(message.contains("read failed after 1 of"), "{message}");
        assert!(message.contains("peer reset"), "{message}");
        assert_eq!(active(d.path()).unwrap().current, first.current);
        assert_eq!(fs::read_dir(d.path().join("releases")).unwrap().count(), 1);
    }
    #[test]
    fn forged_manifests_and_wrong_keys_rejected_before_fetch() {
        let d = tempfile::tempdir().unwrap();
        let (_, mut raw, sig, key) = fixture(1);
        raw.push(b' ');
        assert!(install(d.path(), &raw, &sig, &key, |_| panic!("must not fetch")).is_err());
        let (_, raw, sig, _) = fixture(1);
        assert!(authenticate(&raw, &sig, &[0; 32]).is_err());
    }
    #[test]
    fn client_package_excludes_preparation_and_source() {
        let (mut m, _, _, _) = fixture(1);
        for path in [
            "../secret",
            "/absolute",
            "bin/aimee-prepare",
            "src/encoder.rs",
            "models/private.safetensors",
            "lib/nested/x.so",
        ] {
            m.artifacts[0].path = path.into();
            assert!(validate(&m).is_err(), "{path}");
        }
        let (mut m, _, _, _) = fixture(1);
        m.gates.retain(|s| s != "reusable_preparation");
        assert!(validate(&m).is_err());
    }
    #[test]
    fn connect_keeps_secrets_private_and_rejects_url_credentials() {
        let d = tempfile::tempdir().unwrap();
        connect(d.path(), "https://example.invalid/aimee", "scoped-token\n").unwrap();
        let raw = fs::read(d.path().join("config.json")).unwrap();
        assert!(!String::from_utf8_lossy(&raw).contains("scoped-token"));
        let c: Config = serde_json::from_slice(&raw).unwrap();
        assert_eq!(
            fs::metadata(&c.token_file).unwrap().permissions().mode() & 0o777,
            0o600
        );
        assert_eq!(fs::read_to_string(c.token_file).unwrap(), "scoped-token");
        assert!(connect(d.path(), "https://secret@example.invalid", "x").is_err());
        assert!(connect(d.path(), "http://example.invalid", "x").is_err());
        assert!(connect(d.path(), "https://example.invalid?token=x", "x").is_err());
    }
    #[test]
    fn duplicate_and_traversal_paths_fail() {
        let (mut m, _, _, _) = fixture(1);
        m.artifacts.push(m.artifacts[0].clone());
        assert!(validate(&m).is_err());
        for p in ["../x", "x/../y", "/x", "x\\y", "x:evil"] {
            assert!(!relative(p));
        }
    }
    #[test]
    fn interrupted_pointer_commit_is_recovered_without_user_cleanup() {
        let d = tempfile::tempdir().unwrap();
        let (_, raw, sig, key) = fixture(1);
        let old = install(d.path(), &raw, &sig, &key, fetch).unwrap();
        let (_, raw2, sig2, _) = fixture(2);
        let next = install(d.path(), &raw2, &sig2, &key, fetch).unwrap();
        // Simulate the second release's rename landing, but not its pointer.
        atomic(
            &d.path().join("active.json"),
            &serde_json::to_vec(&old).unwrap(),
        )
        .unwrap();
        assert_eq!(
            install(d.path(), &raw2, &sig2, &key, fetch)
                .unwrap()
                .current,
            next.current
        );
    }
}
