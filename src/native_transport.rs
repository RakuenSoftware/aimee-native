//! One owned, indexed transport arena per worker. Admission writes immutable
//! extents; activation only reads retained descriptors. No per-record files.
use crate::{
    native_store::{NativeStore, RankPlan},
    native_transport_codec::Encoded,
};
use anyhow::{Result, ensure};
use std::{
    fs::File,
    os::{fd::AsRawFd, unix::fs::FileExt},
    sync::{Arc, Mutex, OnceLock, Weak},
};
const ARENA_LIMIT: usize = 512 * 1024 * 1024;
struct Allocation {
    end: usize,
    free: Vec<(usize, usize)>,
}
struct Arena {
    file: File,
    allocation: Mutex<Allocation>,
}
fn arena() -> Result<Arc<Arena>> {
    static CURRENT: OnceLock<Mutex<Weak<Arena>>> = OnceLock::new();
    let mut current = CURRENT
        .get_or_init(|| Mutex::new(Weak::new()))
        .lock()
        .unwrap();
    if let Some(a) = current.upgrade() {
        return Ok(a);
    }
    let a = Arc::new(Arena {
        file: tempfile::tempfile()?,
        allocation: Mutex::new(Allocation {
            end: 0,
            free: Vec::new(),
        }),
    });
    *current = Arc::downgrade(&a);
    Ok(a)
}
struct Extent {
    arena: Arc<Arena>,
    offset: usize,
    reserved: usize,
}
impl Extent {
    fn write(bytes: &[u8]) -> Result<Option<Self>> {
        let arena = arena()?;
        let reserved = bytes.len().next_multiple_of(4096);
        let offset = {
            let mut a = arena.allocation.lock().unwrap();
            if let Some(i) = a.free.iter().position(|&(_, n)| n >= reserved) {
                let (offset, n) = a.free.remove(i);
                if n > reserved {
                    a.free.push((offset + reserved, n - reserved));
                }
                offset
            } else {
                if a.end.checked_add(reserved).is_none_or(|n| n > ARENA_LIMIT) {
                    return Ok(None);
                }
                let offset = a.end;
                a.end += reserved;
                arena.file.set_len(a.end as u64)?;
                offset
            }
        };
        let extent = Self {
            arena,
            offset,
            reserved,
        };
        extent.arena.file.write_all_at(bytes, offset as u64)?;
        extent.arena.file.sync_data()?;
        Ok(Some(extent))
    }
}
impl Drop for Extent {
    fn drop(&mut self) {
        let mut a = self.arena.allocation.lock().unwrap();
        a.free.push((self.offset, self.reserved));
        a.free.sort_unstable();
        let mut free: Vec<(usize, usize)> = Vec::new();
        for &(start, len) in &a.free {
            if let Some(last) = free.last_mut() {
                if last.0 + last.1 == start {
                    last.1 += len;
                    continue;
                }
            }
            free.push((start, len));
        }
        a.free = free;
    }
}
pub struct Transport {
    extent: Extent,
    pub file_bytes: usize,
    pub transfer_bytes: usize,
    pub index_offset: usize,
    pub words: usize,
    pub exception_offset: usize,
    pub exceptions: usize,
    pub table: [u8; 16],
    indices: Vec<u32>,
}
impl Transport {
    pub fn prepare(
        store: &NativeStore,
        plan: &RankPlan,
        device_budget: usize,
    ) -> Result<Option<Self>> {
        if !store.is_disk_backed() {
            return Ok(None);
        }
        // The compressed staging allocation coexists with the dense output.
        // Reject before authoring if even the best ratio cannot fit the budget.
        if plan
            .bytes
            .checked_mul(3)
            .map(|n| n / 4)
            .and_then(|n| plan.bytes.checked_add(n))
            .is_none_or(|n| n > device_budget)
        {
            return Ok(None);
        }
        let mut words = vec![0u16; plan.bytes / 2];
        let raw =
            unsafe { std::slice::from_raw_parts_mut(words.as_mut_ptr().cast::<u8>(), plan.bytes) };
        store.pack_rank(plan, raw)?;
        let encoded = Encoded::encode(&words);
        let index_offset = encoded.payload.len().next_multiple_of(4);
        let transfer_bytes = index_offset + encoded.exceptions * 4;
        if transfer_bytes >= plan.bytes
            || plan
                .bytes
                .checked_add(transfer_bytes)
                .is_none_or(|n| n > device_budget)
        {
            return Ok(None);
        }
        let Some(extent) = Extent::write(&encoded.payload)? else {
            return Ok(None);
        };
        Ok(Some(Self {
            extent,
            file_bytes: encoded.payload.len(),
            transfer_bytes,
            index_offset,
            words: encoded.words,
            exception_offset: encoded.exception_offset,
            exceptions: encoded.exceptions,
            table: encoded.table,
            indices: encoded
                .exception_positions
                .into_iter()
                .map(|i| i as u32)
                .collect(),
        }))
    }
    pub fn source(&self) -> serde_json::Value {
        serde_json::json!({"fd":self.extent.arena.file.as_raw_fd(),"offset":self.extent.offset,"bytes":self.file_bytes})
    }
    /// Valid writable pinned allocation of transfer_bytes bytes, exclusively held.
    pub unsafe fn fill(&self, target: *mut u8) -> Result<()> {
        let mut written = 0;
        while written < self.file_bytes {
            let n = unsafe {
                libc::pread(
                    self.extent.arena.file.as_raw_fd(),
                    target.add(written).cast(),
                    self.file_bytes - written,
                    (self.extent.offset + written) as libc::off_t,
                )
            };
            if n < 0 {
                let e = std::io::Error::last_os_error();
                if e.kind() == std::io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e.into());
            }
            ensure!(n > 0, "native transport read failed");
            written += n as usize;
        }
        unsafe {
            std::ptr::write_bytes(
                target.add(self.file_bytes),
                0,
                self.index_offset - self.file_bytes,
            );
            std::ptr::copy_nonoverlapping(
                self.indices.as_ptr().cast::<u8>(),
                target.add(self.index_offset),
                self.indices.len() * 4,
            );
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn arena_reuses_one_descriptor_and_reclaims_only_retired_extents() {
        let a = Extent::write(b"first").unwrap().unwrap();
        let b = Extent::write(b"second").unwrap().unwrap();
        assert!(Arc::ptr_eq(&a.arena, &b.arena));
        assert_ne!(a.offset, b.offset);
        let offset = a.offset;
        let arena = a.arena.clone();
        drop(a);
        let c = Extent::write(b"third").unwrap().unwrap();
        assert_eq!(c.offset, offset);
        let mut value = [0u8; 6];
        b.arena
            .file
            .read_exact_at(&mut value, b.offset as u64)
            .unwrap();
        assert_eq!(&value, b"second");
        let weak = Arc::downgrade(&arena);
        drop(arena);
        drop(b);
        drop(c);
        assert!(weak.upgrade().is_none());
    }
}
