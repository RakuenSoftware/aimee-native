//! Torch-free admission and immutable views of exact prepared native memory.
//! Open on a preparation/publication worker, then pin with Arc for requests.
//! Runtime views perform no I/O, hashing, file opening, or content verification.
use crate::native_format::{Index, Segment};
use anyhow::{Context, Result, ensure};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet, fs::File, io::Read, ops::Range, os::fd::AsRawFd, os::unix::fs::FileExt,
    path::Path,
};

pub struct SegmentView<'a> {
    pub layer: usize,
    pub value: bool,
    pub heads: usize,
    pub positions: usize,
    pub width: usize,
    /// Contiguous BF16 little-endian [heads, positions, width].
    pub bytes: &'a [u8],
}
struct Plan {
    spec: Segment,
    positions: usize,
    range: Range<usize>,
}
enum Payload {
    Owned(Vec<u8>),
    Mapped {
        pointer: *mut libc::c_void,
        bytes: usize,
        _file: File,
    },
}
impl Payload {
    fn bytes(&self) -> &[u8] {
        match self {
            Self::Owned(v) => v,
            Self::Mapped { pointer, bytes, .. } => unsafe {
                // Immutable publisher-owned inode, retained for this mapping's lifetime.
                std::slice::from_raw_parts(pointer.cast::<u8>(), *bytes)
            },
        }
    }
    fn release_pages(&self) {
        if let Self::Mapped { pointer, bytes, .. } = self {
            // Residency hint only, after synchronous H2D. No verification or reopen.
            unsafe {
                libc::madvise(*pointer, *bytes, libc::MADV_DONTNEED);
            }
        }
    }
}
impl Drop for Payload {
    fn drop(&mut self) {
        if let Self::Mapped { pointer, bytes, .. } = self {
            unsafe {
                libc::munmap(*pointer, *bytes);
            }
        }
    }
}
pub struct NativeStore {
    data: Payload,
    plans: Vec<Plan>,
    tokens: Vec<u32>,
}
impl NativeStore {
    pub fn admit(root: &Path, expected_model: &str, key: &str, byte_budget: usize) -> Result<Self> {
        Self::admit_mode(root, expected_model, key, byte_budget, false)
    }
    /// Disk-backed admission requires immutable, publisher-owned inodes. Updates
    /// replace paths atomically; in-place writes/truncation are forbidden.
    pub fn admit_mode(
        root: &Path,
        expected_model: &str,
        key: &str,
        byte_budget: usize,
        disk_backed: bool,
    ) -> Result<Self> {
        let mut metadata = Vec::new();
        File::open(root.join("index.json"))?
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut metadata)?;
        ensure!(
            metadata.len() <= 16 * 1024 * 1024,
            "native index exceeds admission budget"
        );
        let mut index: Index = serde_json::from_slice(&metadata)?;
        ensure!(
            index.version == 1 && index.model == expected_model,
            "native model/format mismatch"
        );
        ensure!(
            index.native_layout && !index.experimental_approximation && !index.head_major,
            "native representation unsupported"
        );
        ensure!(
            index.records.len() == 1,
            "expected an exact prepared working set"
        );
        let record = index
            .records
            .remove(key)
            .context("prepared selection unavailable")?;
        ensure!(
            !record.tokens.is_empty() && index.prototypes == record.tokens.len(),
            "native position coverage mismatch"
        );
        ensure!(
            index.dictionary_bytes > 0 && index.dictionary_bytes <= byte_budget,
            "native memory budget exceeded"
        );
        let mut plans = Vec::new();
        let mut seen = HashSet::new();
        let mut total = 0usize;
        let mut row_bytes = 0usize;
        for spec in index.schema.segments {
            ensure!(
                seen.insert((spec.layer, spec.value)),
                "duplicate native segment"
            );
            let positions = spec.positions.unwrap_or(record.tokens.len());
            ensure!(
                spec.heads > 0
                    && spec.width > 0
                    && positions > 0
                    && positions <= record.tokens.len(),
                "invalid native dimensions"
            );
            let row = spec
                .heads
                .checked_mul(spec.width)
                .and_then(|v| v.checked_mul(2))
                .context("native extent overflow")?;
            let size = row
                .checked_mul(positions)
                .context("native extent overflow")?;
            row_bytes = row_bytes
                .checked_add(row)
                .context("native extent overflow")?;
            let end = total.checked_add(size).context("native extent overflow")?;
            ensure!(
                end <= index.dictionary_bytes,
                "native extent exceeds payload"
            );
            plans.push(Plan {
                spec,
                positions,
                range: total..end,
            });
            total = end;
        }
        ensure!(
            !plans.is_empty()
                && total == index.dictionary_bytes
                && row_bytes == index.schema.row_bytes,
            "native coverage mismatch"
        );
        for plan in &plans {
            let peer = plans
                .iter()
                .find(|p| p.spec.layer == plan.spec.layer && p.spec.value != plan.spec.value)
                .context("missing K/V pair")?;
            ensure!(
                peer.spec.heads == plan.spec.heads
                    && peer.spec.width == plan.spec.width
                    && peer.positions == plan.positions,
                "incompatible K/V pair"
            );
        }
        let file = File::open(root.join("compact.pack"))?;
        let data = if disk_backed {
            ensure!(total <= isize::MAX as usize, "native mapping exceeds slice limit");
            ensure!(
                file.metadata()?.len() >= 4096 + total as u64,
                "native payload truncated"
            );
            // Fixed-size verification scratch; never allocate the full catalogue.
            let mut scratch = vec![0u8; total.min(256 * 1024)];
            let mut hash = Sha256::new();
            let mut offset = 0;
            while offset < total {
                let size = scratch.len().min(total - offset);
                file.read_exact_at(&mut scratch[..size], 4096 + offset as u64)?;
                hash.update(&scratch[..size]);
                offset += size;
            }
            ensure!(
                format!("{:x}", hash.finalize()) == index.dictionary_sha256,
                "native publication integrity rejected"
            );
            let pointer = unsafe {
                libc::mmap(
                    std::ptr::null_mut(),
                    total,
                    libc::PROT_READ,
                    libc::MAP_PRIVATE,
                    file.as_raw_fd(),
                    4096,
                )
            };
            ensure!(pointer != libc::MAP_FAILED, "native mapping failed");
            Payload::Mapped {
                pointer,
                bytes: total,
                _file: file,
            }
        } else {
            let mut data = vec![0u8; total];
            file.read_exact_at(&mut data, 4096)?;
            ensure!(
                format!("{:x}", Sha256::digest(&data)) == index.dictionary_sha256,
                "native publication integrity rejected"
            );
            Payload::Owned(data)
        };
        Ok(Self {
            data,
            plans,
            tokens: record.tokens,
        })
    }
    pub fn bytes(&self) -> usize {
        self.data.bytes().len()
    }
    pub fn release_pages(&self) {
        self.data.release_pages();
    }
    pub fn tokens(&self) -> &[u32] {
        &self.tokens
    }
    pub fn segments(&self) -> impl ExactSizeIterator<Item = SegmentView<'_>> {
        self.plans.iter().map(|p| SegmentView {
            layer: p.spec.layer,
            value: p.spec.value,
            heads: p.spec.heads,
            positions: p.positions,
            width: p.spec.width,
            bytes: &self.data.bytes()[p.range.clone()],
        })
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};
    fn fixture(root: &Path) -> Value {
        // Global layer has three positions; local layer has two, different width.
        let data: Vec<u8> = (0..56).collect();
        let mut packed = vec![0; 4096];
        packed.extend(&data);
        std::fs::write(root.join("compact.pack"), packed).unwrap();
        let index = json!({"version":1,"model":"revision","schema":{"row_bytes":24,"segments":[
            {"layer":0,"value":false,"heads":1,"width":2}, {"layer":0,"value":true,"heads":1,"width":2},
            {"layer":1,"value":false,"heads":2,"width":2,"positions":2}, {"layer":1,"value":true,"heads":2,"width":2,"positions":2}]},
            "prototypes":3,"dictionary_bytes":56,"dictionary_sha256":format!("{:x}",Sha256::digest(&data)),
            "records":{"selection":{"offset":8192,"tokens":[11,22,33]}},"experimental_approximation":false,"head_major":false,"native_layout":true});
        std::fs::write(root.join("index.json"), serde_json::to_vec(&index).unwrap()).unwrap();
        index
    }
    #[test]
    fn heterogeneous_views_preserve_every_byte_without_files() {
        let tmp = tempfile::tempdir().unwrap();
        fixture(tmp.path());
        let store = NativeStore::admit(tmp.path(), "revision", "selection", 56).unwrap();
        std::fs::remove_file(tmp.path().join("compact.pack")).unwrap();
        std::fs::remove_file(tmp.path().join("index.json")).unwrap();
        let views: Vec<_> = store.segments().collect();
        assert_eq!(views.len(), 4);
        assert_eq!(
            views.iter().map(|s| s.positions).collect::<Vec<_>>(),
            [3, 3, 2, 2]
        );
        assert_eq!(
            views
                .iter()
                .flat_map(|s| s.bytes.iter().copied())
                .collect::<Vec<_>>(),
            (0..56).collect::<Vec<u8>>()
        );
        assert_eq!(store.tokens(), [11, 22, 33]);
    }
    #[test]
    fn disk_mapping_pins_old_inode_across_replacement_and_page_release() {
        let tmp = tempfile::tempdir().unwrap();
        fixture(tmp.path());
        let store = NativeStore::admit_mode(tmp.path(), "revision", "selection", 56, true).unwrap();
        std::fs::rename(tmp.path().join("compact.pack"), tmp.path().join("old.pack")).unwrap();
        std::fs::write(tmp.path().join("compact.pack"), vec![255; 4152]).unwrap();
        std::fs::remove_file(tmp.path().join("old.pack")).unwrap();
        for _ in 0..3 {
            assert_eq!(
                store
                    .segments()
                    .flat_map(|s| s.bytes.iter().copied())
                    .collect::<Vec<_>>(),
                (0..56).collect::<Vec<u8>>()
            );
            store.release_pages();
        }
    }
    #[test]
    fn admission_rejects_wrong_identity_budget_corruption_and_incomplete_pairs() {
        let tmp = tempfile::tempdir().unwrap();
        let mut index = fixture(tmp.path());
        assert!(NativeStore::admit(tmp.path(), "different", "selection", 56).is_err());
        assert!(NativeStore::admit(tmp.path(), "revision", "selection", 55).is_err());
        assert!(NativeStore::admit(tmp.path(), "revision", "first-record-only", 56).is_err());
        index["schema"]["segments"][3]["value"] = json!(false);
        std::fs::write(
            tmp.path().join("index.json"),
            serde_json::to_vec(&index).unwrap(),
        )
        .unwrap();
        assert!(NativeStore::admit(tmp.path(), "revision", "selection", 56).is_err());
        fixture(tmp.path());
        let file = std::fs::OpenOptions::new()
            .write(true)
            .open(tmp.path().join("compact.pack"))
            .unwrap();
        file.write_all_at(&[255], 4096).unwrap();
        assert!(NativeStore::admit(tmp.path(), "revision", "selection", 56).is_err());
    }
}
