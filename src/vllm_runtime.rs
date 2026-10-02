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


#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AttentionPlanRequest {
    requests: usize,
    heads: usize,
    kv_heads: usize,
    head_size: usize,
    block_size: usize,
    max_query_len: usize,
    scale: f64,
    window: i64,
    soft_cap: f64,
}

fn next_power_of_two(value: usize) -> anyhow::Result<usize> {
    anyhow::ensure!(value > 0 && value <= 4096, "invalid attention width");
    value.checked_next_power_of_two()
        .ok_or_else(|| anyhow::anyhow!("attention width overflow"))
}

fn attention_plan(req: AttentionPlanRequest) -> anyhow::Result<Value> {
    anyhow::ensure!(req.requests > 0, "native attention requires requests");
    anyhow::ensure!(req.heads > 0 && req.kv_heads > 0, "invalid attention heads");
    anyhow::ensure!(req.heads % req.kv_heads == 0, "attention head ratio mismatch");
    anyhow::ensure!(req.head_size > 0 && req.block_size > 0, "invalid attention geometry");
    anyhow::ensure!(req.max_query_len > 0, "invalid query length");
    anyhow::ensure!(req.scale.is_finite() && req.scale > 0.0, "invalid attention scale");
    anyhow::ensure!(req.soft_cap.is_finite() && req.soft_cap >= 0.0, "invalid logits soft cap");
    anyhow::ensure!(req.window >= -1, "invalid sliding window");
    let width = next_power_of_two(req.head_size)?;
    let tile = 32usize;
    let num_warps = if width <= 64 { 2 } else { 4 };
    Ok(json!({
        "grid": [req.requests, req.heads, req.max_query_len],
        "num_warps": num_warps,
        "tile": tile,
        "width": width,
        "head_ratio": req.heads / req.kv_heads,
        "heads": req.heads,
        "kv_heads": req.kv_heads,
        "head_size": req.head_size,
        "block_size": req.block_size,
        "scale": req.scale,
        "window": req.window,
        "soft_cap": req.soft_cap,
    }))
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
pub unsafe extern "C" fn aimee_vllm_attention_plan(
    handle: *mut c_void,
    request: *const c_char,
) -> *const c_char {
    if handle.is_null() { return std::ptr::null(); }
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> anyhow::Result<*const c_char> {
        let runtime = unsafe { &mut *handle.cast::<Runtime>() };
        let plan = attention_plan(unsafe { json_arg(request)? })?;
        runtime.set_response(plan)
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
    #[test]
    fn attention_plan_owns_specialization_and_launch_geometry() {
        let plan = attention_plan(AttentionPlanRequest {
            requests: 3, heads: 32, kv_heads: 8, head_size: 128,
            block_size: 16, max_query_len: 7, scale: 0.0883883476,
            window: -1, soft_cap: 0.0,
        }).unwrap();
        assert_eq!(plan["grid"], json!([3, 32, 7]));
        assert_eq!(plan["head_ratio"], 4);
        assert_eq!(plan["tile"], 32);
        assert_eq!(plan["width"], 128);
        assert_eq!(plan["num_warps"], 4);
    }

    #[test]
    fn attention_plan_rejects_invalid_head_geometry() {
        assert!(attention_plan(AttentionPlanRequest {
            requests: 1, heads: 30, kv_heads: 8, head_size: 128,
            block_size: 16, max_query_len: 1, scale: 1.0,
            window: -1, soft_cap: 0.0,
        }).is_err());
    }

}
