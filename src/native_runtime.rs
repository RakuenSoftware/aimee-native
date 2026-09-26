//! Rust-owned activation over the already installed ATen runtime. No encoder.
use crate::{
    native_store::{NativeStore, RankPlan},
    native_transport::Transport,
};
use anyhow::{Result, ensure};
use std::{
    ffi::{CString, c_void},
    time::Instant,
};
unsafe extern "C" {
    fn aimee_rt_host(bytes: usize) -> *mut c_void;
    fn aimee_rt_device(bytes: usize, device: i32) -> *mut c_void;
    fn aimee_rt_stream(tensor: *mut c_void, stream: *mut *mut c_void) -> bool;
    fn aimee_decode_bf16(
        input: *const u8,
        positions: *const u8,
        output: *mut u8,
        words: usize,
        exception_offset: usize,
        exceptions: usize,
        table0: u64,
        table1: u64,
        stream: *mut c_void,
        device: i32,
    ) -> i32;
    fn aimee_rt_data(tensor: *mut c_void) -> *mut u8;
    fn aimee_rt_upload(tensor: *mut c_void, device: i32) -> *mut c_void;
    fn aimee_rt_wait(tensor: *mut c_void) -> bool;
    fn aimee_rt_view(
        tensor: *mut c_void,
        heads: usize,
        positions: usize,
        width: usize,
        offset: usize,
    ) -> *mut c_void;
    fn aimee_rt_free(tensor: *mut c_void);
    fn aimee_rt_python(
        tensors: *const *mut c_void,
        layers: *const usize,
        values: *const bool,
        n: usize,
    ) -> *mut c_void;
}
struct Tensor(*mut c_void);
impl Tensor {
    fn new(pointer: *mut c_void) -> Result<Self> {
        ensure!(!pointer.is_null(), "native runtime operation failed");
        Ok(Self(pointer))
    }
}
impl Drop for Tensor {
    fn drop(&mut self) {
        unsafe { aimee_rt_free(self.0) }
    }
}
pub struct Activation {
    tensors: Vec<Tensor>,
    layers: Vec<usize>,
    values: Vec<bool>,
    pub profile: CString,
}
impl Activation {
    pub fn run(
        store: &NativeStore,
        plan: &RankPlan,
        transport: Option<&Transport>,
        device: i32,
        profile: bool,
    ) -> Result<Self> {
        ensure!(device >= 0 && device <= i16::MAX as i32, "invalid device");
        let mut marks = Vec::new();
        let mut mark = || {
            if profile {
                marks.push(Instant::now());
            }
        };
        mark();
        let transfer_bytes = transport.map_or(plan.bytes, |t| t.transfer_bytes);
        let host = Tensor::new(unsafe { aimee_rt_host(transfer_bytes) })?;
        mark();
        let pointer = unsafe { aimee_rt_data(host.0) };
        ensure!(
            !pointer.is_null() && transfer_bytes <= isize::MAX as usize,
            "invalid staging allocation"
        );
        if let Some(t) = transport {
            unsafe {
                t.fill(pointer)?;
            }
        } else {
            let target = unsafe {
                std::slice::from_raw_parts_mut(
                    pointer.cast::<std::mem::MaybeUninit<u8>>(),
                    plan.bytes,
                )
            };
            store.pack_rank_uninit(plan, target)?;
        }
        mark();
        let transferred = Tensor::new(unsafe { aimee_rt_upload(host.0, device) })?;
        let decoded = if let Some(t) = transport {
            let out = Tensor::new(unsafe { aimee_rt_device(plan.bytes, device) })?;
            let source = unsafe { aimee_rt_data(transferred.0) };
            let mut stream = std::ptr::null_mut();
            ensure!(
                unsafe { aimee_rt_stream(out.0, &mut stream) },
                "native stream unavailable"
            );
            let status = unsafe {
                aimee_decode_bf16(
                    source,
                    source.add(t.index_offset),
                    aimee_rt_data(out.0),
                    t.words,
                    t.exception_offset,
                    t.exceptions,
                    u64::from_le_bytes(t.table[..8].try_into().unwrap()),
                    u64::from_le_bytes(t.table[8..].try_into().unwrap()),
                    stream,
                    device,
                )
            };
            // Even on launch failure, complete queued work before source ownership ends.
            if status != 0 {
                unsafe {
                    aimee_rt_wait(out.0);
                }
                anyhow::bail!("native decoding failed");
            }
            Some(out)
        } else {
            None
        };
        let device_tensor = decoded.as_ref().unwrap_or(&transferred);
        mark();
        ensure!(
            unsafe { aimee_rt_wait(device_tensor.0) },
            "native GPU completion failed"
        );
        mark();
        let mut tensors = Vec::with_capacity(plan.segments.len());
        let mut layers = Vec::with_capacity(plan.segments.len());
        let mut values = Vec::with_capacity(plan.segments.len());
        for s in &plan.segments {
            tensors.push(Tensor::new(unsafe {
                aimee_rt_view(device_tensor.0, s.heads, s.positions, s.width, s.offset)
            })?);
            layers.push(s.layer);
            values.push(s.value);
        }
        mark();
        store.release_pages();
        mark();
        let names = [
            "pinned_allocation",
            "read_into_pinned",
            "device_submit",
            "device_wait",
            "views",
            "release",
        ];
        let phases: std::collections::BTreeMap<_, _> = names
            .into_iter()
            .zip(marks.windows(2).map(|m| (m[1] - m[0]).as_secs_f64() * 1e6))
            .collect();
        Ok(Self {
            tensors,
            layers,
            values,
            profile: CString::new(serde_json::to_string(&phases)?).unwrap(),
        })
    }
    /// Caller holds CPython GIL; returned object is a new reference.
    pub unsafe fn python(&self) -> *mut c_void {
        let pointers: Vec<_> = self.tensors.iter().map(|t| t.0).collect();
        unsafe {
            aimee_rt_python(
                pointers.as_ptr(),
                self.layers.as_ptr(),
                self.values.as_ptr(),
                pointers.len(),
            )
        }
    }
}

/// Initialize the compiled decoder during worker startup, using unrelated zeros.
pub fn warmup(device: i32) -> Result<()> {
    ensure!(device >= 0 && device <= i16::MAX as i32, "invalid device");
    let host = Tensor::new(unsafe { aimee_rt_host(16) })?;
    unsafe {
        std::ptr::write_bytes(aimee_rt_data(host.0), 0, 16);
    }
    let input = Tensor::new(unsafe { aimee_rt_upload(host.0, device) })?;
    let out = Tensor::new(unsafe { aimee_rt_device(16, device) })?;
    let mut stream = std::ptr::null_mut();
    ensure!(
        unsafe { aimee_rt_stream(out.0, &mut stream) },
        "native stream unavailable"
    );
    let status = unsafe {
        aimee_decode_bf16(
            aimee_rt_data(input.0),
            aimee_rt_data(input.0),
            aimee_rt_data(out.0),
            8,
            0,
            0,
            0,
            0,
            stream,
            device,
        )
    };
    ensure!(
        unsafe { aimee_rt_wait(out.0) },
        "native warmup completion failed"
    );
    ensure!(status == 0, "native warmup failed");
    Ok(())
}
