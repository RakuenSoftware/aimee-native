//! Research binding to the same Rust native loader used by the device benchmark.
//! DLPack crosses language boundaries without serializing/copying GPU tensors.
//! Offline compilation is an explicit separate call; apply cannot encode a model.
use crate::{
    compact_memory::{Applied, DeviceWorkspace, Store},
    model,
};
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::json;
use std::{
    cell::RefCell,
    ffi::{CStr, CString, c_char, c_void},
    path::Path,
};
#[cfg(not(feature = "native-client"))]
use {
    crate::{compact_memory, model::Bank},
    std::collections::HashMap,
    tch::Tensor,
};
unsafe extern "C" {
    #[cfg(not(feature = "native-client"))]
    fn aimee_tensor_import_dlpack(p: *mut c_void) -> *mut c_void;
    fn aimee_tensor_export_dlpack(t: *const c_void) -> *mut c_void;
    #[cfg(not(feature = "native-client"))]
    fn aimee_transfer_error() -> *const c_char;
}
thread_local! {static ERROR:RefCell<CString>=RefCell::new(CString::new("").unwrap());}
fn invoke<T>(fail: T, f: impl FnOnce() -> Result<T>) -> T {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(Ok(v)) => v,
        other => {
            #[cfg(not(feature = "native-client"))]
            let msg = match other {
                Ok(Err(e)) => format!("{e:#}"),
                _ => "native FFI panic".into(),
            };
            #[cfg(feature = "native-client")]
            let msg = {
                let _ = other;
                "native operation failed".to_owned()
            };
            ERROR.with(|e| *e.borrow_mut() = CString::new(msg.replace('\0', " ")).unwrap());
            fail
        }
    }
}
unsafe fn string<'a>(p: *const c_char) -> Result<&'a str> {
    ensure!(!p.is_null(), "null string");
    unsafe { CStr::from_ptr(p).to_str().context("UTF-8 required") }
}
#[unsafe(no_mangle)]
pub extern "C" fn aimee_native_error() -> *const c_char {
    ERROR.with(|e| e.borrow().as_ptr())
}
#[cfg(not(feature = "native-client"))]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_import(p: *mut c_void) -> *mut c_void {
    invoke(std::ptr::null_mut(), || {
        ensure!(!p.is_null(), "null DLPack");
        let out = unsafe { aimee_tensor_import_dlpack(p) };
        ensure!(!out.is_null(), "DLPack import failed: {}", unsafe {
            CStr::from_ptr(aimee_transfer_error()).to_string_lossy()
        });
        Ok(out)
    })
}
#[cfg(not(feature = "native-client"))]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_tensor_free(p: *mut c_void) {
    if !p.is_null() {
        drop(unsafe { Tensor::from_ptr(p.cast()) });
    }
}
#[cfg(not(feature = "native-client"))]
#[derive(Deserialize)]
struct Publication {
    root: String,
    model: String,
    key: String,
    tokens: Vec<u32>,
    layers: Vec<usize>,
}
#[cfg(not(feature = "native-client"))]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_publish(
    spec: *const c_char,
    tensors: *const *mut c_void,
    count: usize,
) -> i32 {
    invoke(-1, || {
        let p: Publication = serde_json::from_str(unsafe { string(spec)? })?;
        ensure!(
            count == p.layers.len() * 2 && !tensors.is_null(),
            "native layer payload mismatch"
        );
        let inputs = unsafe { std::slice::from_raw_parts(tensors, count) };
        ensure!(inputs.iter().all(|p| !p.is_null()), "missing native tensor");
        let banks: HashMap<_, _> = p
            .layers
            .iter()
            .enumerate()
            .map(|(i, &layer)| {
                (
                    layer,
                    Bank {
                        keys: unsafe { Tensor::clone_from_ptr(inputs[2 * i].cast()) },
                        values: unsafe { Tensor::clone_from_ptr(inputs[2 * i + 1].cast()) },
                    },
                )
            })
            .collect();
        ensure!(banks.len() == p.layers.len(), "duplicate native layer");
        compact_memory::publish_native(Path::new(&p.root), &p.model, &p.key, &p.tokens, &banks)?;
        let store = Store::open(Path::new(&p.root), &p.model)?;
        let mut w = store.workspace(&p.key)?;
        store.expand(&p.key, &mut w)?;
        let recovered = store.banks(&p.key, &w)?;
        for (layer, b) in &banks {
            ensure!(
                b.keys
                    .to_device(tch::Device::Cpu)
                    .equal(&recovered[layer].keys)
                    && b.values
                        .to_device(tch::Device::Cpu)
                        .equal(&recovered[layer].values),
                "offline native roundtrip mismatch"
            );
        }
        Ok(0)
    })
}
struct Handle {
    store: Store,
    key: String,
    work: DeviceWorkspace,
    metadata: CString,
}
#[derive(Deserialize)]
struct Activation {
    root: String,
    model: String,
    key: String,
    placement: Vec<String>,
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_open(spec: *const c_char) -> *mut c_void {
    invoke(std::ptr::null_mut(), || {
        let p: Activation = serde_json::from_str(unsafe { string(spec)? })?;
        let mut store = Store::open(Path::new(&p.root), &p.model)?;
        store.set_threads(1)?;
        store.set_streaming(true)?;
        let placement = p
            .placement
            .iter()
            .map(|p| model::device(p))
            .collect::<Result<Vec<_>>>()?;
        let mut work = store.device_workspace(&p.key, &placement)?;
        store.initialize_device_pool(&mut work)?;
        #[cfg(not(feature = "native-client"))]
        let metadata=CString::new(json!({"tokens":store.tokens(&p.key)?,"dictionary_bytes":store.dictionary_bytes(),"representation":"exact-prepared-native-layout","resident_dictionary":true,"threads":1,"streaming_stores":true}).to_string())?;
        #[cfg(feature = "native-client")]
        let metadata = CString::new("{\"abi\":1}")?;
        Ok(Box::into_raw(Box::new(Handle {
            store,
            key: p.key,
            work,
            metadata,
        }))
        .cast())
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_metadata(handle: *mut c_void) -> *const c_char {
    if handle.is_null() {
        return std::ptr::null();
    }
    unsafe { (&*handle.cast::<Handle>()).metadata.as_ptr() }
}
struct Output {
    applied: Applied,
    metadata: CString,
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_apply(handle: *mut c_void) -> *mut c_void {
    invoke(std::ptr::null_mut(), || {
        ensure!(!handle.is_null(), "missing native handle");
        let h = unsafe { &mut *handle.cast::<Handle>() };
        let applied = h.store.apply_optimized(&h.key, &mut h.work)?;
        let mut layers: Vec<_> = applied.banks.keys().copied().collect();
        layers.sort_unstable();
        #[cfg(not(feature = "native-client"))]
        let metadata=CString::new(json!({"layers":layers,"read_ns":applied.read_ns,"expand_ns":applied.expand_ns,"transfer_ns":applied.transfer_ns,"total_ns":applied.total_ns,"transfer_operations":applied.transfer_operations,"model_encoding_passes":0}).to_string())?;
        #[cfg(feature = "native-client")]
        let metadata = CString::new(json!({"layers":layers}).to_string())?;
        Ok(Box::into_raw(Box::new(Output { applied, metadata })).cast())
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_result_metadata(output: *mut c_void) -> *const c_char {
    if output.is_null() {
        return std::ptr::null();
    }
    unsafe { (&*output.cast::<Output>()).metadata.as_ptr() }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_result_tensor(
    output: *mut c_void,
    layer: usize,
    value: bool,
) -> *mut c_void {
    invoke(std::ptr::null_mut(), || {
        ensure!(!output.is_null(), "missing native output");
        let o = unsafe { &*output.cast::<Output>() };
        let b = o
            .applied
            .banks
            .get(&layer)
            .context("missing native layer")?;
        let tensor = if value { &b.values } else { &b.keys };
        let p = unsafe { aimee_tensor_export_dlpack(tensor.as_ptr().cast()) };
        ensure!(!p.is_null(), "DLPack export failed");
        Ok(p)
    })
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_result_free(output: *mut c_void) {
    if !output.is_null() {
        drop(unsafe { Box::from_raw(output.cast::<Output>()) });
    }
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_native_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<Handle>()) });
    }
}

/// ABI version, independent of the private on-disk representation.
#[unsafe(no_mangle)]
pub extern "C" fn aimee_native_abi_version() -> u32 {
    1
}
