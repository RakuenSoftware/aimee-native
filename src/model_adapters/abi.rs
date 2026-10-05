use std::ffi::{CStr, CString, c_char};
/// ABI input/output ownership only; model implementations own all semantics.
pub(super) unsafe fn call(input: *const c_char, f: fn(&serde_json::Value) -> anyhow::Result<serde_json::Value>) -> *mut c_char {
    if input.is_null() { return std::ptr::null_mut(); }
    let result = std::panic::catch_unwind(|| -> anyhow::Result<CString> {
        let raw = unsafe { CStr::from_ptr(input) }.to_bytes();
        anyhow::ensure!(raw.len() <= 4 * 1024 * 1024, "adapter request too large");
        Ok(CString::new(serde_json::to_vec(&f(&serde_json::from_slice(raw)?)?)?)?)
    });
    match result { Ok(Ok(result)) => result.into_raw(), _ => std::ptr::null_mut() }
}
/// # Safety
/// Pointer must be null or an unreleased result from one of the adapter calls.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_model_adapter_result_free(result: *mut c_char) {
    if !result.is_null() { drop(unsafe { CString::from_raw(result) }); }
}
