//! Safe wrappers for a minimal LibTorch event/copy bridge. GPU slots must not
//! be recycled while either their cached views or derived storage aliases live.
use anyhow::{Result, anyhow};
use std::ffi::{CStr, c_char, c_void};
use tch::Tensor;
unsafe extern "C" {
    fn aimee_transfer_error() -> *const c_char;
    fn aimee_event_new(t: *const c_void) -> *mut c_void;
    fn aimee_event_record(e: *mut c_void, t: *const c_void) -> i32;
    fn aimee_event_wait(e: *mut c_void) -> i32;
    fn aimee_event_free(e: *mut c_void);
    fn aimee_copy_async(dst: *mut c_void, src: *const c_void) -> i32;
    fn aimee_tensor_refs(t: *const c_void) -> usize;
    fn aimee_storage_refs(t: *const c_void) -> usize;
}
fn error() -> anyhow::Error {
    unsafe {
        anyhow!(
            "native transfer: {}",
            CStr::from_ptr(aimee_transfer_error()).to_string_lossy()
        )
    }
}
pub struct Event(*mut c_void);
impl Event {
    pub fn new(t: &Tensor) -> Result<Self> {
        let p = unsafe { aimee_event_new(t.as_ptr().cast()) };
        if p.is_null() {
            Err(error())
        } else {
            Ok(Self(p))
        }
    }
    pub fn record(&mut self, t: &Tensor) -> Result<()> {
        if unsafe { aimee_event_record(self.0, t.as_ptr().cast()) } == 0 {
            Ok(())
        } else {
            Err(error())
        }
    }
    pub fn wait(&self) -> Result<()> {
        if unsafe { aimee_event_wait(self.0) } == 0 {
            Ok(())
        } else {
            Err(error())
        }
    }
}
impl Drop for Event {
    fn drop(&mut self) {
        unsafe { aimee_event_free(self.0) }
    }
}
pub fn copy_async(dst: &mut Tensor, src: &Tensor) -> Result<()> {
    if unsafe { aimee_copy_async(dst.as_mut_ptr().cast(), src.as_ptr().cast()) } == 0 {
        Ok(())
    } else {
        Err(error())
    }
}
pub fn tensor_refs(t: &Tensor) -> usize {
    unsafe { aimee_tensor_refs(t.as_ptr().cast()) }
}
pub fn storage_refs(t: &Tensor) -> usize {
    unsafe { aimee_storage_refs(t.as_ptr().cast()) }
}
