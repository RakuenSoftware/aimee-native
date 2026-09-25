//! Torch-independent client ABI. Publication admission precedes serving.
use crate::native_store::NativeStore;
use serde::Deserialize;
use serde_json::json;
use std::ffi::{CStr, CString, c_char, c_void};
use std::path::Path;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Admission {
    root: String,
    model: String,
    key: String,
    byte_budget: usize,
}
struct Handle {
    _store: NativeStore,
    metadata: CString,
}
#[unsafe(no_mangle)]
pub extern "C" fn aimee_store_abi_version() -> u32 {
    1
}
/// # Safety
/// `spec` must be null or point to a live, NUL-terminated UTF-8 JSON string.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_open(spec: *const c_char) -> *mut c_void {
    let result = std::panic::catch_unwind(|| -> anyhow::Result<Handle> {
        anyhow::ensure!(!spec.is_null(), "missing admission");
        let spec: Admission = serde_json::from_str(unsafe { CStr::from_ptr(spec) }.to_str()?)?;
        let store = NativeStore::admit(
            Path::new(&spec.root),
            &spec.model,
            &spec.key,
            spec.byte_budget,
        )?;
        let segments:Vec<_>=store.segments().map(|s|json!({"layer":s.layer,"value":s.value,"heads":s.heads,"positions":s.positions,"width":s.width,"pointer":s.bytes.as_ptr() as usize,"bytes":s.bytes.len()})).collect();
        let metadata=CString::new(json!({"abi":1,"positions":store.tokens().len(),"bytes":store.bytes(),"segments":segments}).to_string())?;
        Ok(Handle {
            _store: store,
            metadata,
        })
    });
    match result {
        Ok(Ok(h)) => Box::into_raw(Box::new(h)).cast(),
        _ => std::ptr::null_mut(),
    }
}
/// # Safety
/// The handle must be null or a live handle from `aimee_store_open`.
/// The returned string is borrowed until that handle is closed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_metadata(handle: *const c_void) -> *const c_char {
    if handle.is_null() {
        return std::ptr::null();
    }
    unsafe { (&*handle.cast::<Handle>()).metadata.as_ptr() }
}
/// # Safety
/// The handle must be null or an open handle, and must be closed only once.
/// No caller may use its metadata or buffers after closing.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<Handle>()) });
    }
}

struct CacheHandle {
    cache: crate::device_cache::DeviceCache,
    response: CString,
}
#[unsafe(no_mangle)]
pub extern "C" fn aimee_cache_open(budget: usize) -> *mut c_void {
    match crate::device_cache::DeviceCache::new(budget) {
        Ok(cache) => Box::into_raw(Box::new(CacheHandle {
            cache,
            response: CString::default(),
        }))
        .cast(),
        Err(_) => std::ptr::null_mut(),
    }
}
/// # Safety
/// `handle` must be a live cache handle exclusively owned for this call, and
/// `required` a NUL-terminated JSON bank array. The response is borrowed until
/// the next call or close. Null response means rejection without mutation.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_cache_plan(
    handle: *mut c_void,
    required: *const c_char,
) -> *const c_char {
    if handle.is_null() || required.is_null() {
        return std::ptr::null();
    }
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(
        || -> anyhow::Result<*const c_char> {
            let h = unsafe { &mut *handle.cast::<CacheHandle>() };
            let banks: Vec<crate::device_cache::Bank> =
                serde_json::from_str(unsafe { CStr::from_ptr(required) }.to_str()?)?;
            let plan = h.cache.reconcile(&banks)?;
            h.response = CString::new(serde_json::to_string(&plan)?)?;
            Ok(h.response.as_ptr())
        },
    ));
    match result {
        Ok(Ok(p)) => p,
        _ => std::ptr::null(),
    }
}
/// # Safety
/// A non-null handle must be live, exclusively owned, and closed only once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_cache_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<CacheHandle>()) });
    }
}
