//! Opaque vLLM runtime ownership: catalogue identity, publication revisions and request pins.
//! Python/vLLM supplies request IDs and receives opaque publication keys; policy/state lives here.
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::ffi::{CStr, CString, c_char, c_void};
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeConfig {
    catalog: PathBuf,
    model: PathBuf,
    recipient: String,
}

#[derive(Deserialize)]
struct Catalog {
    model_config_sha256: String,
    recipient: String,
    publications: BTreeMap<String, Value>,
}

#[derive(Clone, Serialize)]
struct Publication {
    name: String,
    key: String,
    spec: Value,
}

#[derive(Clone)]
struct Pin {
    publication: Option<String>,
    key: Option<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct NewRequest {
    id: String,
    publication: Option<String>,
    catalog_digest: Option<String>,
}

struct Runtime {
    config: RuntimeConfig,
    catalog_digest: String,
    publications: BTreeMap<String, Publication>,
    requests: BTreeMap<String, Pin>,
    response: CString,
}

fn hex_sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn canonical_key(value: &Value) -> anyhow::Result<String> {
    Ok(hex_sha(&serde_json::to_vec(value)?))
}

impl Runtime {
    fn load(config: RuntimeConfig) -> anyhow::Result<Self> {
        let (catalog_digest, publications) = Self::read_catalog(&config)?;
        Ok(Self {
            config,
            catalog_digest,
            publications,
            requests: BTreeMap::new(),
            response: CString::default(),
        })
    }

    fn read_catalog(config: &RuntimeConfig) -> anyhow::Result<(String, BTreeMap<String, Publication>)> {
        let raw = fs::read(&config.catalog)?;
        let catalog: Catalog = serde_json::from_slice(&raw)?;
        anyhow::ensure!(catalog.recipient == config.recipient, "publication catalogue recipient mismatch");
        let model = fs::read(Path::new(&config.model).join("config.json"))?;
        anyhow::ensure!(
            catalog.model_config_sha256 == hex_sha(&model),
            "publication catalogue model mismatch"
        );
        let mut publications = BTreeMap::new();
        for (name, spec) in catalog.publications {
            let key = canonical_key(&spec)?;
            publications.insert(name.clone(), Publication { name, key, spec });
        }
        Ok((hex_sha(&raw), publications))
    }

    fn snapshot(&self) -> Value {
        json!({
            "catalog_digest": self.catalog_digest,
            "publications": self.publications.values().collect::<Vec<_>>(),
            "pins": self.requests.iter().map(|(id, pin)| json!({
                "id": id,
                "publication": pin.publication,
                "key": pin.key,
            })).collect::<Vec<_>>(),
        })
    }

    fn begin(&mut self, finished: Vec<String>, new: Vec<NewRequest>) -> anyhow::Result<()> {
        for id in finished {
            self.requests.remove(&id);
        }
        for req in new {
            if let Some(expected) = &req.catalog_digest {
                anyhow::ensure!(expected == &self.catalog_digest, "frontend/worker publication mismatch");
            }
            let pin = match &req.publication {
                Some(name) => {
                    let publication = self.publications.get(name)
                        .ok_or_else(|| anyhow::anyhow!("native publication unavailable"))?;
                    Pin { publication: Some(name.clone()), key: Some(publication.key.clone()) }
                }
                None => Pin { publication: None, key: None },
            };
            if let Some(old) = self.requests.get(&req.id) {
                anyhow::ensure!(
                    old.publication == pin.publication && old.key == pin.key,
                    "cannot change memory within a pinned request"
                );
            } else {
                self.requests.insert(req.id, pin);
            }
        }
        Ok(())
    }

    fn refresh(&mut self) -> anyhow::Result<()> {
        let (digest, publications) = Self::read_catalog(&self.config)?;
        self.catalog_digest = digest;
        self.publications = publications;
        Ok(())
    }

    fn set_response(&mut self, value: Value) -> anyhow::Result<*const c_char> {
        self.response = CString::new(serde_json::to_vec(&value)?)?;
        Ok(self.response.as_ptr())
    }
}

unsafe fn json_arg<T: for<'de> Deserialize<'de>>(ptr: *const c_char) -> anyhow::Result<T> {
    anyhow::ensure!(!ptr.is_null(), "missing JSON argument");
    Ok(serde_json::from_str(unsafe { CStr::from_ptr(ptr) }.to_str()?)?)
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_vllm_runtime_open(config: *const c_char) -> *mut c_void {
    let result = std::panic::catch_unwind(|| -> anyhow::Result<Runtime> {
        Runtime::load(unsafe { json_arg(config)? })
    });
    match result {
        Ok(Ok(runtime)) => Box::into_raw(Box::new(runtime)).cast(),
        _ => std::ptr::null_mut(),
    }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_vllm_runtime_snapshot(handle: *mut c_void) -> *const c_char {
    if handle.is_null() { return std::ptr::null(); }
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> anyhow::Result<*const c_char> {
        let runtime = unsafe { &mut *handle.cast::<Runtime>() };
        let snapshot = runtime.snapshot();
        runtime.set_response(snapshot)
    }));
    match result { Ok(Ok(p)) => p, _ => std::ptr::null() }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_vllm_runtime_begin(
    handle: *mut c_void,
    finished: *const c_char,
    new_requests: *const c_char,
) -> *const c_char {
    if handle.is_null() { return std::ptr::null(); }
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> anyhow::Result<*const c_char> {
        let runtime = unsafe { &mut *handle.cast::<Runtime>() };
        runtime.begin(unsafe { json_arg(finished)? }, unsafe { json_arg(new_requests)? })?;
        let snapshot = runtime.snapshot();
        runtime.set_response(snapshot)
    }));
    match result { Ok(Ok(p)) => p, _ => std::ptr::null() }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_vllm_runtime_refresh(handle: *mut c_void) -> *const c_char {
    if handle.is_null() { return std::ptr::null(); }
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> anyhow::Result<*const c_char> {
        let runtime = unsafe { &mut *handle.cast::<Runtime>() };
        runtime.refresh()?;
        let snapshot = runtime.snapshot();
        runtime.set_response(snapshot)
    }));
    match result { Ok(Ok(p)) => p, _ => std::ptr::null() }
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_vllm_runtime_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<Runtime>()) });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn fixture() -> (tempfile::TempDir, RuntimeConfig) {
        let root = tempdir().unwrap();
        let model = root.path().join("model");
        fs::create_dir(&model).unwrap();
        fs::write(model.join("config.json"), b"{\"model\":1}").unwrap();
        let digest = hex_sha(b"{\"model\":1}");
        let catalog = root.path().join("catalog.json");
        fs::write(&catalog, serde_json::to_vec(&json!({
            "model_config_sha256": digest,
            "recipient": "r",
            "publications": {"a": {"root":"/x","model":"m","key":"k"}}
        })).unwrap()).unwrap();
        (root, RuntimeConfig { catalog, model, recipient: "r".into() })
    }

    #[test]
    fn pins_exact_revision_across_refresh() {
        let (_root, cfg) = fixture();
        let mut runtime = Runtime::load(cfg).unwrap();
        runtime.begin(vec![], vec![NewRequest {
            id: "1".into(), publication: Some("a".into()),
            catalog_digest: Some(runtime.catalog_digest.clone())
        }]).unwrap();
        let old = runtime.requests["1"].key.clone();
        runtime.publications.get_mut("a").unwrap().key = "changed".into();
        assert_eq!(runtime.requests["1"].key, old);
    }

    #[test]
    fn request_cannot_change_publication() {
        let (_root, cfg) = fixture();
        let mut runtime = Runtime::load(cfg).unwrap();
        runtime.begin(vec![], vec![NewRequest { id:"1".into(), publication:Some("a".into()), catalog_digest:None }]).unwrap();
        assert!(runtime.begin(vec![], vec![NewRequest { id:"1".into(), publication:None, catalog_digest:None }]).is_err());
    }
}
