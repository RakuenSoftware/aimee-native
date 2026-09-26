//! Store ABI with optional runtime-only ATen activation. Admission precedes serving.
use crate::native_store::{NativeStore, RankPlan};
use serde::Deserialize;
use serde_json::json;
use std::ffi::{CStr, CString, c_char, c_void};
use std::path::Path;
use std::sync::Arc;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Admission {
    root: String,
    model: String,
    key: String,
    byte_budget: usize,
    #[serde(default)]
    disk_backed: bool,
}
struct Handle {
    _store: Arc<NativeStore>,
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
        let store = NativeStore::admit_mode(
            Path::new(&spec.root),
            &spec.model,
            &spec.key,
            spec.byte_budget,
            spec.disk_backed,
        )?;
        let segments:Vec<_>=store.segments().map(|s|json!({"layer":s.layer,"value":s.value,"heads":s.heads,"positions":s.positions,"width":s.width,"pointer":s.bytes.as_ptr() as usize,"bytes":s.bytes.len()})).collect();
        let metadata=CString::new(json!({"abi":1,"positions":store.tokens().len(),"bytes":store.bytes(),"segments":segments}).to_string())?;
        Ok(Handle {
            _store: Arc::new(store),
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

#[unsafe(no_mangle)]
pub extern "C" fn aimee_admission_open(budget: usize) -> *mut c_void {
    Box::into_raw(Box::new(std::sync::Mutex::new(
        crate::device_cache::Admission::new(budget),
    )))
    .cast()
}
/// # Safety
/// Handle must be a live admission handle. Calls may be concurrent, but closing
/// the handle requires exclusive ownership after all calls/requests finish.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_admission_acquire(
    handle: *mut c_void,
    id: u64,
    bytes: usize,
) -> bool {
    if handle.is_null() {
        return false;
    }
    let mutex = unsafe { &*handle.cast::<std::sync::Mutex<crate::device_cache::Admission>>() };
    mutex
        .lock()
        .map(|mut a| a.acquire(id, bytes))
        .unwrap_or(false)
}
/// # Safety
/// Handle must be live; release exactly once per successful acquisition.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_admission_release(handle: *mut c_void, id: u64) {
    if !handle.is_null() {
        let mutex = unsafe { &*handle.cast::<std::sync::Mutex<crate::device_cache::Admission>>() };
        if let Ok(mut a) = mutex.lock() {
            a.release(id);
        }
    }
}
/// # Safety
/// Handle must be null or live and exclusively owned; close only once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_admission_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe {
            Box::from_raw(handle.cast::<std::sync::Mutex<crate::device_cache::Admission>>())
        });
    }
}

/// # Safety
/// Live store handle; no concurrent CPU consumers while releasing mapped pages.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_release_pages(handle: *const c_void) {
    if !handle.is_null() {
        unsafe {
            (&*handle.cast::<Handle>())._store.release_pages();
        }
    }
}

struct PackHandle {
    store: Arc<NativeStore>,
    plan: RankPlan,
    #[cfg(feature = "vllm-runtime")]
    transport: Option<crate::native_transport::Transport>,
    metadata: CString,
}
/// # Safety
/// Store must be live for this call. The returned plan independently retains it.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_open(
    handle: *const c_void,
    rank: usize,
    world: usize,
) -> *mut c_void {
    if handle.is_null() {
        return std::ptr::null_mut();
    }
    let result = std::panic::catch_unwind(|| -> anyhow::Result<PackHandle> {
        let store = unsafe { &*handle.cast::<Handle>() }._store.clone();
        let plan = store.rank_plan(rank, world)?;
        let metadata =
            CString::new(json!({"bytes":plan.bytes,"segments":plan.segments}).to_string())?;
        Ok(PackHandle {
            store,
            plan,
            #[cfg(feature = "vllm-runtime")]
            transport: None,
            metadata,
        })
    });
    match result {
        Ok(Ok(h)) => Box::into_raw(Box::new(h)).cast(),
        _ => std::ptr::null_mut(),
    }
}
/// # Safety
/// Live pack handle; returned metadata is borrowed until close.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_metadata(handle: *const c_void) -> *const c_char {
    if handle.is_null() {
        return std::ptr::null();
    }
    unsafe { (&*handle.cast::<PackHandle>()).metadata.as_ptr() }
}
/// # Safety
/// Live pack handle and a writable, non-overlapping destination of `bytes` bytes.
/// Caller owns DMA synchronization; no concurrent release/close of this plan.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_copy(
    handle: *const c_void,
    destination: *mut u8,
    bytes: usize,
) -> bool {
    if handle.is_null() || destination.is_null() || bytes > isize::MAX as usize {
        return false;
    }
    let h = unsafe { &*handle.cast::<PackHandle>() };
    if bytes != h.plan.bytes {
        return false;
    }
    let destination = unsafe {
        std::slice::from_raw_parts_mut(destination.cast::<std::mem::MaybeUninit<u8>>(), bytes)
    };
    h.store.pack_rank_uninit(&h.plan, destination).is_ok()
}
/// # Safety
/// Null or exclusively owned live pack handle, closed exactly once.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_close(handle: *mut c_void) {
    if !handle.is_null() {
        drop(unsafe { Box::from_raw(handle.cast::<PackHandle>()) });
    }
}

/// # Safety
/// Live admitted plan; no concurrent mutation/close. Own and free the result.
#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_activate(handle: *const c_void, device: i32, profile: bool) -> *mut c_void {
    if handle.is_null() { return std::ptr::null_mut(); }
    match std::panic::catch_unwind(|| {
        let h = unsafe { &*handle.cast::<PackHandle>() };
        crate::native_runtime::Activation::run(&h.store, &h.plan, h.transport.as_ref(), device, profile)
    }) {
        Ok(Ok(a)) => Box::into_raw(Box::new(a)).cast(),
        _ => std::ptr::null_mut(),
    }
}
/// # Safety
/// Live activation and held CPython GIL. Result is a new Python reference.
#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_activation_python(handle: *const c_void) -> *mut c_void {
    if handle.is_null() { return std::ptr::null_mut(); }
    unsafe { (&*handle.cast::<crate::native_runtime::Activation>()).python() }
}
/// # Safety
/// Live activation. Returned string is borrowed until activation is freed.
#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_activation_profile(handle: *const c_void) -> *const c_char {
    if handle.is_null() { return std::ptr::null(); }
    unsafe { (&*handle.cast::<crate::native_runtime::Activation>()).profile.as_ptr() }
}
/// # Safety
/// Null or exclusively owned activation, freed exactly once.
#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_activation_free(handle: *mut c_void) {
    if !handle.is_null() { drop(unsafe { Box::from_raw(handle.cast::<crate::native_runtime::Activation>()) }); }
}

/// Admission-only optional lossless transport authoring. No runtime compilation.
/// Safety: live exclusively held plan, called before activation; no concurrent users.
#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_store_pack_prepare_transport(handle: *mut c_void, device_budget: usize) -> bool {
    if handle.is_null() { return false; }
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let h = unsafe { &mut *handle.cast::<PackHandle>() };
        h.transport = crate::native_transport::Transport::prepare(&h.store, &h.plan, device_budget).ok().flatten();
        let (transfer_bytes, reservation_bytes, source) = match &h.transport {
            Some(t) => (t.transfer_bytes, h.plan.bytes+t.transfer_bytes, t.source()),
            None => (h.plan.bytes, h.plan.bytes, serde_json::Value::Null),
        };
        h.metadata = CString::new(json!({"bytes":h.plan.bytes,"segments":h.plan.segments,
            "transfer_bytes":transfer_bytes,"reservation_bytes":reservation_bytes,
            "transport_source":source,"lossless_transport":h.transport.is_some()}).to_string()).unwrap();
        true
    })).unwrap_or(false)
}

#[cfg(feature = "vllm-runtime")]
#[unsafe(no_mangle)]
pub extern "C" fn aimee_store_runtime_warmup(device: i32) -> bool {
    matches!(std::panic::catch_unwind(|| crate::native_runtime::warmup(device)), Ok(Ok(())))
}
