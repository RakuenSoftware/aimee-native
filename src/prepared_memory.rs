//! Immutable model-bound native states. RAM metadata index, one packed SSD
//! payload per encoding, no model forward pass in the reader.
use crate::model::Bank;
use crate::native_compression::Codec;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::os::fd::AsRawFd;
use std::{
    collections::{BTreeMap, HashMap},
    fs::{File, OpenOptions},
    io::Write,
    os::unix::fs::{FileExt, OpenOptionsExt},
    path::{Path, PathBuf},
    time::Instant,
};
use tch::{Device, Kind, Tensor};
const PACK_HEADER_BYTES: u64 = 4096;
const PACK_MAGIC: &[u8; 8] = b"AIMEENM1";
fn check_pack(file: &File, model: &str) -> Result<()> {
    let mut header = [0u8; 40];
    file.read_exact_at(&mut header, 0)?;
    ensure!(
        &header[..8] == PACK_MAGIC && header[8..40] == Sha256::digest(model.as_bytes())[..],
        "native container identity mismatch"
    );
    Ok(())
}

#[derive(Clone, Serialize, Deserialize)]
struct Layout {
    layer: usize,
    shape: Vec<i64>,
    offset: usize,
    elements: usize,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Entry {
    pub tokens: Vec<u32>,
    dtype: String,
    #[serde(default)]
    codec: Codec,
    #[serde(default)]
    offset: Option<u64>,
    #[serde(default)]
    intermediate: bool,
    bytes: usize,
    sha256: String,
    layouts: Vec<Layout>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    recurrent: Option<crate::prepared_recurrent::Metadata>,
}
impl Entry {
    pub fn recurrent_bytes(&self) -> usize {
        self.recurrent.as_ref().map_or(0, |m| m.bytes())
    }
}
#[derive(Clone, Serialize, Deserialize)]
struct Index {
    version: u32,
    model: String,
    entries: BTreeMap<String, Entry>,
}
// Publication I/O, parsing and reclamation stay on this worker, not serving.
struct IndexWatch {
    latest: std::sync::Arc<std::sync::Mutex<std::sync::Arc<Index>>>,
    stop: std::sync::mpsc::Sender<()>,
    worker: Option<std::thread::JoinHandle<()>>,
}
impl IndexWatch {
    fn new(path: PathBuf, initial: std::sync::Arc<Index>) -> Result<Self> {
        use std::os::unix::fs::MetadataExt;
        use std::sync::{Arc, Mutex, mpsc};
        let latest = Arc::new(Mutex::new(initial.clone()));
        let published = latest.clone();
        let (stop, rx) = mpsc::channel();
        let worker = std::thread::Builder::new()
            .name("prepared-index-update".into())
            .spawn(move || {
                let model = initial.model.clone();
                drop(initial);
                let mut fingerprint = None;
                let mut retired: Vec<Arc<Index>> = Vec::new();
                while matches!(
                    rx.recv_timeout(std::time::Duration::from_millis(250)),
                    Err(mpsc::RecvTimeoutError::Timeout)
                ) {
                    let update = (|| -> Result<()> {
                        let file = File::open(&path)?;
                        let meta = file.metadata()?;
                        let version = (
                            meta.dev(),
                            meta.ino(),
                            meta.len(),
                            meta.mtime(),
                            meta.mtime_nsec(),
                        );
                        if fingerprint == Some(version) {
                            return Ok(());
                        }
                        let next: Index = serde_json::from_reader(file)?;
                        ensure!(
                            next.version == 1 && next.model == model,
                            "prepared index identity changed"
                        );
                        for (key, e) in &next.entries {
                            ensure!(key_ok(key), "invalid prepared key");
                            validate(e)?;
                        }
                        let old =
                            std::mem::replace(&mut *published.lock().unwrap(), Arc::new(next));
                        retired.push(old);
                        fingerprint = Some(version);
                        Ok(())
                    })();
                    if let Err(error) = update {
                        eprintln!("prepared index update deferred: {error}");
                    }
                    retired.retain(|old| Arc::strong_count(old) > 1);
                }
            })?;
        Ok(Self {
            latest,
            stop,
            worker: Some(worker),
        })
    }
}
impl Drop for IndexWatch {
    fn drop(&mut self) {
        let _ = self.stop.send(());
        if let Some(w) = self.worker.take() {
            let _ = w.join();
        }
    }
}
pub struct Store {
    root: PathBuf,
    index: std::sync::Arc<Index>,
    watcher: Option<IndexWatch>,
    writable: bool,
    write_codec: Codec,
    encoded_scratch: std::cell::RefCell<Vec<u8>>,
    decode_scratch: std::cell::RefCell<Vec<u8>>,
    staging: std::cell::RefCell<Option<Tensor>>,
    host_staging_key: std::cell::RefCell<Option<String>>,
    host_cache_budget: usize,
    files: crate::prepared_files::Files,
}
pub struct Loaded {
    pub tokens: Vec<u32>,
    pub banks: HashMap<usize, Bank>,
    pub recurrent: HashMap<usize, (Tensor, Tensor)>,
    pub recurrent_load_wall_ns: u128,
    pub recurrent_read_bytes: usize,
    pub read_ns: u128,
    pub file_setup_ns: u128,
    pub file_opened: bool,
    pub conversion_ns: u128,
    pub bytes: usize,
    pub expanded_bytes: usize,
    pub transfer_ns: u128,
    pub transfer_operations: usize,
    pub host_hit: bool,
}
fn kind(name: &str) -> Result<Kind> {
    Ok(match name {
        "bf16" => Kind::BFloat16,
        "f16" => Kind::Half,
        "f32" => Kind::Float,
        _ => anyhow::bail!("unsupported prepared dtype"),
    })
}
fn key_ok(key: &str) -> bool {
    key.len() == 64
        && key
            .bytes()
            .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
}
impl Store {
    pub fn open(root: &Path, model: &str, writable: bool) -> Result<Self> {
        Self::open_with_idle(root, model, writable, std::time::Duration::from_secs(60))
    }
    pub fn open_with_idle(
        root: &Path,
        model: &str,
        writable: bool,
        idle: std::time::Duration,
    ) -> Result<Self> {
        ensure!(!model.is_empty(), "model identity required");
        if writable {
            std::fs::create_dir_all(root)?;
        }
        let path = root.join("index.json");
        let index: Index = if path.exists() {
            serde_json::from_slice(&std::fs::read(path)?)?
        } else {
            ensure!(writable, "prepared index missing");
            Index {
                version: 1,
                model: model.into(),
                entries: BTreeMap::new(),
            }
        };
        ensure!(
            index.version == 1 && index.model == model,
            "prepared model/codec identity mismatch"
        );

        for (key, e) in &index.entries {
            ensure!(key_ok(key), "invalid prepared key");
            validate(e)?;
        }
        crate::native_compression::initialize();
        let index = std::sync::Arc::new(index);
        let watcher = if writable {
            None
        } else {
            Some(IndexWatch::new(root.join("index.json"), index.clone())?)
        };
        Ok(Self {
            root: root.into(),
            index,
            watcher,
            writable,
            write_codec: Codec::Raw,
            encoded_scratch: std::cell::RefCell::new(Vec::new()),
            decode_scratch: std::cell::RefCell::new(Vec::new()),
            staging: std::cell::RefCell::new(None),
            host_staging_key: std::cell::RefCell::new(None),
            host_cache_budget: 0,
            files: crate::prepared_files::Files::new(idle)?,
        })
    }
    pub fn set_write_codec(&mut self, codec: Codec) {
        self.write_codec = codec;
    }
    /// Reload a newly published prepared index without replacing the model.
    /// Called on a publication transition or a preparation miss, not each hit.
    pub fn refresh(&mut self) -> Result<()> {
        let next = Self::open(&self.root, &self.index.model, self.writable)?;
        self.index = next.index;
        self.watcher = next.watcher;

        self.host_staging_key.borrow_mut().take();
        Ok(())
    }
    /// Nonblocking snapshot adoption only: no I/O, parsing, validation, or large
    /// index reclamation. The publication worker owns old snapshots until unused.
    pub fn poll_updates(&mut self) {
        let next = self
            .watcher
            .as_ref()
            .and_then(|w| w.latest.try_lock().ok().map(|s| s.clone()));
        if let Some(next) = next {
            if !std::sync::Arc::ptr_eq(&self.index, &next) {
                self.index = next;
                self.host_staging_key.borrow_mut().take();
            }
        }
    }
    /// Optional bounded reuse of the last verified pinned artifact. Authorization
    /// and source revision checks still happen before each call from the adapter.
    pub fn set_host_cache_budget(&mut self, bytes: usize) {
        self.host_cache_budget = bytes;
        if bytes == 0 {
            self.host_staging_key.borrow_mut().take();
        }
    }
    /// Open the owned file ahead of use; no integrity checks.
    /// Explicit offline maintenance. Never called by serving loads or idle reopen.
    pub fn verify(&self) -> Result<()> {
        if self.root.join("native.pack").exists() {
            check_pack(
                &File::open(self.root.join("native.pack"))?,
                &self.index.model,
            )?;
        }
        for (key, e) in &self.index.entries {
            if let Some(meta) = &e.recurrent {
                let _ = crate::prepared_recurrent::load(&self.root, key, meta, None)?;
            }
            let file = File::open(self.payload_path(key))?;
            let offset = e.offset.unwrap_or(0);
            ensure!(
                file.metadata()?.len() >= offset + e.bytes as u64,
                "prepared extent mismatch"
            );
            let mut hash = Sha256::new();
            let mut scratch = vec![0u8; e.bytes.min(256 * 1024)];
            let mut done = 0;
            while done < e.bytes {
                let n = scratch.len().min(e.bytes - done);
                file.read_exact_at(&mut scratch[..n], offset + done as u64)?;
                hash.update(&scratch[..n]);
                done += n;
            }
            ensure!(
                format!("{:x}", hash.finalize()) == e.sha256,
                "prepared checksum mismatch"
            );
        }
        Ok(())
    }
    pub fn payload_path(&self, key: &str) -> PathBuf {
        if self
            .index
            .entries
            .get(key)
            .is_some_and(|e| e.offset.is_some())
        {
            self.root.join("native.pack")
        } else {
            self.root.join(format!("{key}.bin"))
        }
    }
    pub fn activate(&self, key: &str) -> Result<()> {
        ensure!(
            self.index.entries.contains_key(key),
            "prepared entry missing"
        );
        self.files.acquire(&self.payload_path(key))?;
        Ok(())
    }
    pub fn entry(&self, key: &str) -> Option<&Entry> {
        self.index.entries.get(key)
    }
    pub fn load(&self, key: &str) -> Result<Option<Loaded>> {
        self.load_impl(key, None)
    }
    /// Direct SSD -> reusable pinned host buffer -> contiguous layer-device spans.
    /// All copies finish before returning or allowing staging-buffer reuse.
    pub fn load_to_devices(&self, key: &str, devices: &[Device]) -> Result<Option<Loaded>> {
        self.load_impl(key, Some(devices))
    }
    fn load_impl(&self, key: &str, devices: Option<&[Device]>) -> Result<Option<Loaded>> {
        let Some(e) = self.index.entries.get(key) else {
            return Ok(None);
        };
        let admitted = Instant::now();
        let (file, file_opened) = self.files.acquire(&self.payload_path(key))?;
        let file_setup_ns = admitted.elapsed().as_nanos();
        let dtype = kind(&e.dtype)?;
        let expanded_bytes = expanded_bytes(e)?;
        let gpu = devices.filter(|ds| {
            e.layouts.iter().all(|l| {
                ds.get(l.layer)
                    .is_some_and(|d| matches!(d, Device::Cuda(_)))
            })
        });
        if let Some(ds) = devices {
            ensure!(
                e.layouts.iter().all(|l| ds.get(l.layer).is_some()),
                "missing native layer placement"
            );
        }
        let host_hit = gpu.is_some()
            && expanded_bytes <= self.host_cache_budget
            && self
                .host_staging_key
                .borrow()
                .as_ref()
                .is_some_and(|k| k == key);
        if !host_hit {
            self.host_staging_key.borrow_mut().take();
        }
        let mut staging = self.staging.borrow_mut();
        let elements = expanded_bytes / dtype.elt_size_in_bytes();
        let packed = if let Some(ds) = gpu {
            if staging
                .as_ref()
                .is_none_or(|t| t.kind() != dtype || t.numel() < elements)
            {
                *staging = Some(
                    Tensor::empty([elements as i64], (dtype, Device::Cpu))
                        .f_pin_memory(ds[e.layouts[0].layer])?,
                );
            }
            staging.as_ref().unwrap().narrow(0, 0, elements as i64)
        } else {
            Tensor::empty([elements as i64], (dtype, Device::Cpu))
        };
        // SAFETY: owned contiguous CPU allocation, fully initialized by read_exact
        // before any tensor view is exposed. Its byte extent is checked at open.
        let dense = unsafe {
            std::slice::from_raw_parts_mut(packed.data_ptr().cast::<u8>(), expanded_bytes)
        };
        let encoded = e.intermediate || e.codec != Codec::Raw;
        let mut intermediate = self.encoded_scratch.borrow_mut();
        if encoded && !host_hit {
            intermediate.resize(e.bytes, 0);
        }
        let data = if encoded {
            intermediate.as_mut_slice()
        } else {
            &mut *dense
        };
        let (read_ns, conversion_ns) = if host_hit {
            (0, 0)
        } else {
            let started = Instant::now();
            file.read_exact_at(data, e.offset.unwrap_or(0))?;
            let read_ns = started.elapsed().as_nanos();
            let convert = Instant::now();
            if e.intermediate {
                // SAFETY: tensor allocation is aligned for u16 and sized by validated layouts.
                let words = unsafe {
                    std::slice::from_raw_parts_mut(
                        packed.data_ptr().cast::<u16>(),
                        expanded_bytes / 2,
                    )
                };
                crate::native_packing::unpack(&intermediate, words)?;
            }
            if e.codec != Codec::Raw {
                crate::native_compression::decode(
                    e.codec,
                    &intermediate,
                    dense,
                    &mut self.decode_scratch.borrow_mut(),
                )?;
            }
            let conversion_ns = convert.elapsed().as_nanos();
            (read_ns, conversion_ns)
        };
        if gpu.is_some() && expanded_bytes <= self.host_cache_budget {
            *self.host_staging_key.borrow_mut() = Some(key.into());
        }
        let transfer_started = Instant::now();
        let mut operations = 0;
        let mut banks = HashMap::with_capacity(e.layouts.len());
        let result = (|| -> Result<()> {
            let mut begin = 0;
            while begin < e.layouts.len() {
                let device = gpu.map_or(Device::Cpu, |ds| ds[e.layouts[begin].layer]);
                let mut end = begin + 1;
                while end < e.layouts.len()
                    && gpu.map_or(Device::Cpu, |ds| ds[e.layouts[end].layer]) == device
                {
                    end += 1;
                }
                let offset = e.layouts[begin].offset;
                let last = &e.layouts[end - 1];
                let count = last.offset + 2 * last.elements - offset;
                let host = packed.narrow(0, offset as i64, count as i64);
                let resident = if device == Device::Cpu {
                    host
                } else {
                    operations += 1;
                    host.f_to_device_(device, dtype, true, false)?
                };
                for l in &e.layouts[begin..end] {
                    let keys = resident
                        .narrow(0, (l.offset - offset) as i64, l.elements as i64)
                        .reshape(&l.shape);
                    let values = resident
                        .narrow(
                            0,
                            (l.offset - offset + l.elements) as i64,
                            l.elements as i64,
                        )
                        .reshape(&l.shape);
                    banks.insert(l.layer, Bank { keys, values });
                }
                begin = end;
            }
            Ok(())
        })();
        // Also drain submitted copies on an error before the host buffer can be reused.
        if let Some(ds) = gpu {
            let used: std::collections::BTreeSet<_> = e
                .layouts
                .iter()
                .filter_map(|l| {
                    if let Device::Cuda(i) = ds[l.layer] {
                        Some(i)
                    } else {
                        None
                    }
                })
                .collect();
            for i in used {
                tch::Cuda::synchronize(i as i64);
            }
        }
        result?;
        let transfer_ns = transfer_started.elapsed().as_nanos();
        let recurrent_started = Instant::now();
        let recurrent = match &e.recurrent {
            Some(meta) => crate::prepared_recurrent::load(&self.root, key, meta, devices)?,
            None => HashMap::new(),
        };
        Ok(Some(Loaded {
            tokens: e.tokens.clone(),
            banks,
            recurrent,
            recurrent_load_wall_ns: recurrent_started.elapsed().as_nanos(),
            recurrent_read_bytes: e.recurrent_bytes(),
            read_ns,
            file_setup_ns,
            file_opened,
            conversion_ns,
            transfer_ns,
            transfer_operations: operations,
            host_hit,
            bytes: e.bytes + e.recurrent.as_ref().map_or(0, |m| m.bytes()),
            expanded_bytes: expanded_bytes + e.recurrent.as_ref().map_or(0, |m| m.bytes()),
        }))
    }
    pub fn put(&mut self, key: &str, tokens: &[u32], banks: &HashMap<usize, Bank>) -> Result<()> {
        self.put_complete(key, tokens, banks, &HashMap::new())
    }
    pub fn put_complete(
        &mut self,
        key: &str,
        tokens: &[u32],
        banks: &HashMap<usize, Bank>,
        recurrent: &HashMap<usize, (Tensor, Tensor)>,
    ) -> Result<()> {
        ensure!(
            self.writable && key_ok(key),
            "prepared store not writable or invalid key"
        );
        ensure!(
            !tokens.is_empty() && !banks.is_empty(),
            "empty prepared encoding"
        );
        if self.index.entries.contains_key(key) {
            anyhow::bail!("prepared entry already exists");
        }
        let mut layers: Vec<_> = banks.keys().copied().collect();
        layers.sort_unstable();
        let dtype = banks[&layers[0]].keys.kind();
        let name = match dtype {
            Kind::BFloat16 => "bf16",
            Kind::Half => "f16",
            Kind::Float => "f32",
            _ => anyhow::bail!("unsupported prepared dtype"),
        };
        let mut parts = vec![];
        let mut layouts = vec![];
        let mut offset = 0;
        for layer in layers {
            let b = &banks[&layer];
            let shape = b.keys.size();
            ensure!(
                shape.len() == 4
                    && shape[0] == 1
                    && shape[2] == tokens.len() as i64
                    && b.values.size() == shape,
                "invalid prepared bank shape"
            );
            ensure!(
                b.keys.kind() == dtype && b.values.kind() == dtype,
                "mixed prepared dtypes"
            );
            let elements = b.keys.numel();
            layouts.push(Layout {
                layer,
                shape,
                offset,
                elements,
            });
            offset += 2 * elements;
            parts.push(b.keys.to_device(Device::Cpu).contiguous().reshape([-1]));
            parts.push(b.values.to_device(Device::Cpu).contiguous().reshape([-1]));
        }
        let packed = Tensor::cat(&parts, 0);
        let bytes = offset
            .checked_mul(dtype.elt_size_in_bytes())
            .context("prepared size overflow")?;
        let data = unsafe { std::slice::from_raw_parts(packed.data_ptr().cast::<u8>(), bytes) };
        let encoded;
        let data = if self.write_codec != Codec::Raw {
            ensure!(
                !matches!(
                    self.write_codec,
                    Codec::Lz4Byteplane
                        | Codec::Lz4ByteplaneParallel
                        | Codec::Lz4ByteplaneHc
                        | Codec::Lz4ByteplaneHcParallel
                ) || dtype.elt_size_in_bytes() == 2,
                "byte-plane codec requires 16-bit tensors"
            );
            encoded = crate::native_compression::encode(self.write_codec, data)?;
            encoded.as_slice()
        } else {
            data
        };
        let bytes = data.len();
        let mut e = Entry {
            offset: None,
            tokens: tokens.into(),
            dtype: name.into(),
            codec: self.write_codec,
            intermediate: false,
            bytes,
            sha256: format!("{:x}", Sha256::digest(data)),
            layouts,
            recurrent: crate::prepared_recurrent::write(&self.root, key, recurrent)?,
        };
        validate(&e)?;
        // Append-only ranges keep old readers valid while a new index is published.
        let mut file = OpenOptions::new()
            .read(true)
            .append(true)
            .create(true)
            .mode(0o600)
            .open(self.root.join("native.pack"))?;
        ensure!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX) } == 0,
            "prepared publication lock failed"
        );
        // Reload under the backing-file lock to preserve another publisher's entries.
        if self.root.join("index.json").exists() {
            let latest: Index =
                serde_json::from_slice(&std::fs::read(self.root.join("index.json"))?)?;
            ensure!(
                latest.version == 1 && latest.model == self.index.model,
                "prepared publication identity changed"
            );
            for (k, entry) in &latest.entries {
                ensure!(key_ok(k), "invalid prepared key");
                validate(entry)?;
            }
            self.index = std::sync::Arc::new(latest);
            ensure!(
                !self.index.entries.contains_key(key),
                "prepared entry already exists"
            );
        }
        let size = file.metadata()?.len();
        if size == 0 {
            let mut header = vec![0u8; PACK_HEADER_BYTES as usize];
            header[..8].copy_from_slice(PACK_MAGIC);
            header[8..40].copy_from_slice(&Sha256::digest(self.index.model.as_bytes()));
            file.write_all(&header)?;
        } else {
            check_pack(&file, &self.index.model)?;
        }
        let end = file.metadata()?.len();
        let aligned = end.checked_add(4095).context("container size overflow")? & !4095;
        if aligned > end {
            file.write_all(&vec![0u8; (aligned - end) as usize])?;
        }
        e.offset = Some(aligned);
        validate(&e)?;
        file.write_all(data)?;
        file.sync_all()?;
        std::sync::Arc::make_mut(&mut self.index)
            .entries
            .insert(key.into(), e);
        let temp = self.root.join("index.tmp");
        let mut index = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .mode(0o600)
            .open(&temp)?;
        index.write_all(&serde_json::to_vec(self.index.as_ref())?)?;
        index.sync_all()?;
        std::fs::rename(temp, self.root.join("index.json"))?;
        File::open(&self.root)?.sync_all()?;
        Ok(())
    }
}
fn expanded_bytes(e: &Entry) -> Result<usize> {
    let last = e.layouts.last().context("empty prepared layout")?;
    (last.offset + 2 * last.elements)
        .checked_mul(kind(&e.dtype)?.elt_size_in_bytes())
        .context("prepared overflow")
}
fn validate(e: &Entry) -> Result<()> {
    if let Some(meta) = &e.recurrent {
        crate::prepared_recurrent::validate(meta)?;
    }
    if let Some(offset) = e.offset {
        ensure!(
            offset >= PACK_HEADER_BYTES
                && offset % 4096 == 0
                && offset.checked_add(e.bytes as u64).is_some(),
            "invalid prepared container extent"
        );
    }
    let dtype = kind(&e.dtype)?;
    ensure!(
        !e.tokens.is_empty() && e.tokens.len() <= 32768 && !e.layouts.is_empty(),
        "invalid prepared metadata"
    );
    ensure!(
        e.bytes > 0 && e.bytes <= 2usize.pow(30) && key_ok(&e.sha256),
        "invalid prepared byte extent"
    );
    let mut offset = 0usize;
    let mut seen = std::collections::HashSet::new();
    for l in &e.layouts {
        ensure!(
            l.shape.len() == 4
                && l.shape[0] == 1
                && l.shape[2] == e.tokens.len() as i64
                && l.shape.iter().all(|&x| x > 0),
            "invalid prepared shape"
        );
        let elements = l
            .shape
            .iter()
            .try_fold(1usize, |n, &x| n.checked_mul(x as usize))
            .context("prepared shape overflow")?;
        ensure!(
            elements == l.elements && l.offset == offset && seen.insert(l.layer),
            "invalid prepared layout"
        );
        offset = offset
            .checked_add(elements.checked_mul(2).context("prepared overflow")?)
            .context("prepared overflow")?;
    }
    let dense = offset
        .checked_mul(dtype.elt_size_in_bytes())
        .context("prepared extent overflow")?;
    ensure!(
        dense <= 2usize.pow(30),
        "expanded prepared extent too large"
    );
    if e.codec != Codec::Raw {
        ensure!(
            !e.intermediate
                && (!matches!(
                    e.codec,
                    Codec::Lz4Byteplane
                        | Codec::Lz4ByteplaneParallel
                        | Codec::Lz4ByteplaneHc
                        | Codec::Lz4ByteplaneHcParallel
                ) || dtype.elt_size_in_bytes() == 2),
            "invalid native codec layout"
        );
        ensure!(
            e.bytes <= dense + dense / 255 + 64 + dense.div_ceil(64 * 1024) * 32,
            "invalid compressed extent"
        );
    } else if e.intermediate {
        ensure!(
            dtype.elt_size_in_bytes() == 2
                && e.bytes <= dense + dense.div_ceil(2 * crate::native_packing::BLOCK),
            "invalid intermediate extent"
        );
    } else {
        ensure!(dense == e.bytes, "prepared payload extent mismatch");
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shared_container_append_refresh_and_stale_publishers_preserve_all_records() {
        let dir = tempfile::tempdir().unwrap();
        let mut a = Store::open(dir.path(), "model", true).unwrap();
        let mut b = Store::open(dir.path(), "model", true).unwrap();
        let banks = HashMap::from([(
            0,
            Bank {
                keys: Tensor::ones([1, 1, 1, 4], (Kind::Float, Device::Cpu)),
                values: Tensor::ones([1, 1, 1, 4], (Kind::Float, Device::Cpu)),
            },
        )]);
        let k1 = "1".repeat(64);
        let k2 = "2".repeat(64);
        a.put(&k1, &[1], &banks).unwrap();
        let mut reader = Store::open(dir.path(), "model", false).unwrap();
        reader.load(&k1).unwrap();
        // Another publisher opened before the first append must not lose that entry.
        b.put(&k2, &[2], &banks).unwrap();
        reader.refresh().unwrap();
        assert_eq!(reader.load(&k1).unwrap().unwrap().tokens, vec![1]);
        assert_eq!(reader.load(&k2).unwrap().unwrap().tokens, vec![2]);
        assert!(
            !reader.load(&k1).unwrap().unwrap().file_opened,
            "publication refresh reopened unchanged backing file"
        );
        assert_eq!(reader.payload_path(&k1), reader.payload_path(&k2));
        assert!(reader.entry(&k2).unwrap().offset > reader.entry(&k1).unwrap().offset);
        assert!(!dir.path().join(format!("{k1}.bin")).exists());
        assert!(b.put(&k1, &[1], &banks).is_err());
    }
    #[test]
    fn background_publication_is_adopted_without_request_file_access() {
        let dir = tempfile::tempdir().unwrap();
        let mut writer = Store::open(dir.path(), "model", true).unwrap();
        let banks = HashMap::from([(
            0,
            Bank {
                keys: Tensor::ones([1, 1, 1, 4], (Kind::Float, Device::Cpu)),
                values: Tensor::ones([1, 1, 1, 4], (Kind::Float, Device::Cpu)),
            },
        )]);
        let first = "1".repeat(64);
        let second = "2".repeat(64);
        writer.put(&first, &[1], &banks).unwrap();
        let mut reader = Store::open(dir.path(), "model", false).unwrap();
        writer.put(&second, &[2], &banks).unwrap();
        let deadline = Instant::now() + std::time::Duration::from_secs(3);
        while !reader
            .watcher
            .as_ref()
            .unwrap()
            .latest
            .lock()
            .unwrap()
            .entries
            .contains_key(&second)
        {
            assert!(
                Instant::now() < deadline,
                "background publication timed out"
            );
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        // Adoption must use the completed RAM snapshot even with the disk index absent.
        std::fs::rename(
            dir.path().join("index.json"),
            dir.path().join("index.offline"),
        )
        .unwrap();
        reader.poll_updates();
        assert!(reader.entry(&second).is_some());
        assert_eq!(reader.load(&second).unwrap().unwrap().tokens, vec![2]);
    }
    #[test]
    fn direct_layout_preserves_bf16_layers() {
        let dir = tempfile::tempdir().unwrap();
        let key = "c".repeat(64);
        let banks = HashMap::from_iter((0..3).map(|i| {
            (
                i,
                Bank {
                    keys: Tensor::full(
                        [1, 2, 33, 64],
                        i as f64 + 1.,
                        (Kind::BFloat16, Device::Cpu),
                    ),
                    values: Tensor::full(
                        [1, 2, 33, 64],
                        i as f64 + 11.,
                        (Kind::BFloat16, Device::Cpu),
                    ),
                },
            )
        }));
        let tokens = vec![17; 33];
        let mut writer = Store::open(dir.path(), "model", true).unwrap();
        writer.put(&key, &tokens, &banks).unwrap();
        let reader = Store::open(dir.path(), "model", false).unwrap();
        let loaded = reader.load(&key).unwrap().unwrap();
        assert!(!reader.entry(&key).unwrap().intermediate);
        assert_eq!(loaded.bytes, loaded.expanded_bytes);
        for (i, b) in &banks {
            assert!(loaded.banks[i].keys.equal(&b.keys));
            assert!(loaded.banks[i].values.equal(&b.values));
        }
    }
    #[test]
    fn persistent_banks_preserve_every_layer_and_reject_corruption_and_wrong_model() {
        let dir = tempfile::tempdir().unwrap();
        let key = "a".repeat(64);
        let banks = HashMap::from_iter((0..3).map(|i| {
            (
                i,
                Bank {
                    keys: Tensor::full([1, 2, 3, 4], i as f64 + 1., (Kind::Float, Device::Cpu)),
                    values: Tensor::full([1, 2, 3, 4], i as f64 + 11., (Kind::Float, Device::Cpu)),
                },
            )
        }));
        Store::open(dir.path(), "pinned-model-bf16", true)
            .unwrap()
            .put(&key, &[1, 2, 3], &banks)
            .unwrap();
        assert!(Store::open(dir.path(), "other-model", false).is_err());
        let mut reader = Store::open(dir.path(), "pinned-model-bf16", false).unwrap();
        assert!(reader.load(&"b".repeat(64)).unwrap().is_none());
        let result = reader.load(&key).unwrap().unwrap();
        assert_eq!(result.tokens, vec![1, 2, 3]);
        assert_eq!(result.banks.len(), 3);
        for (i, b) in &banks {
            assert!(result.banks[i].keys.equal(&b.keys));
            assert!(result.banks[i].values.equal(&b.values));
        }
        let new_key = "b".repeat(64);
        Store::open(dir.path(), "pinned-model-bf16", true)
            .unwrap()
            .put(&new_key, &[4, 5, 6], &banks)
            .unwrap();
        assert!(reader.entry(&new_key).is_none());
        reader.refresh().unwrap();
        assert_eq!(
            reader.load(&new_key).unwrap().unwrap().tokens,
            vec![4, 5, 6]
        );
        use std::os::unix::fs::FileExt;
        let corrupt = OpenOptions::new()
            .write(true)
            .open(reader.payload_path(&key))
            .unwrap();
        corrupt
            .write_all_at(
                &vec![0; result.bytes],
                reader.entry(&key).unwrap().offset.unwrap(),
            )
            .unwrap();
        reader.files.clear(); // Integrity verification is an offline maintenance operation.
        assert!(reader.verify().is_err());
    }
}
