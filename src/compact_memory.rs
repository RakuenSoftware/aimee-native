//! Experimental shared-codebook intermediate. Offline construction only.
//! Codes identify contextual native states, NOT tokenizer IDs. Exact dictionaries
//! move dense state into shared RAM; bounded dictionaries are approximate and
//! MUST pass independent answer-quality evaluation before serving promotion.
use crate::native_format::Index;
#[cfg(not(feature = "native-client"))]
use crate::native_format::Record;
pub use crate::native_format::{Schema, Segment};
use crate::{model::Bank, prepared_files::Files};
use anyhow::{Context, Result, ensure};
use std::{
    collections::{BTreeMap, HashMap},
    os::unix::fs::FileExt,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};
#[cfg(not(feature = "native-client"))]
use std::{
    fs::{File, OpenOptions},
    io::Write,
};
use tch::{Device, Kind, Tensor};

impl Schema {
    pub fn from_banks(banks: &HashMap<usize, Bank>) -> Result<Self> {
        let mut layers: Vec<_> = banks.keys().copied().collect();
        layers.sort_unstable();
        let max_positions = banks
            .values()
            .map(|b| b.keys.size()[2])
            .max()
            .context("empty banks")?;
        let mut segments = vec![];
        let mut row_bytes = 0;
        for layer in layers {
            for (value, t) in [(false, &banks[&layer].keys), (true, &banks[&layer].values)] {
                let s = t.size();
                ensure!(
                    t.kind() == Kind::BFloat16
                        && s.len() == 4
                        && s[0] == 1
                        && s.iter().all(|&x| x > 0),
                    "compact prototype requires bf16 [1,H,T,D]"
                );
                row_bytes += s[1] as usize * s[3] as usize * 2;
                segments.push(Segment {
                    layer,
                    value,
                    heads: s[1] as usize,
                    width: s[3] as usize,
                    positions: if s[2] == max_positions {
                        None
                    } else {
                        Some(s[2] as usize)
                    },
                });
            }
        }
        ensure!(!segments.is_empty(), "empty native schema");
        Ok(Self {
            segments,
            row_bytes,
        })
    }
    fn output_bytes(&self, n: usize) -> usize {
        self.segments
            .iter()
            .map(|s| s.positions.unwrap_or(n) * s.heads * s.width * 2)
            .sum()
    }
    /// Offline transformation into contextual-token rows. Nothing is dropped.
    pub fn rows(&self, banks: &HashMap<usize, Bank>) -> Result<Tensor> {
        ensure!(self == &Self::from_banks(banks)?, "native schema changed");
        let mut parts = vec![];
        let mut n = None;
        for s in &self.segments {
            let b = &banks[&s.layer];
            let t = if s.value { &b.values } else { &b.keys };
            let count = t.size()[2];
            if let Some(n) = n {
                ensure!(n == count, "incomplete token coverage");
            }
            n = Some(count);
            parts.push(
                t.to_device(Device::Cpu)
                    .squeeze_dim(0)
                    .permute([1, 0, 2])
                    .contiguous()
                    .reshape([count, -1]),
            );
        }
        Ok(Tensor::cat(&parts, 1))
    }
}
#[cfg(not(feature = "native-client"))]
fn tensor_bytes(t: &Tensor) -> &[u8] {
    // All callers supply contiguous CPU tensors with live ownership.
    unsafe {
        std::slice::from_raw_parts(
            t.data_ptr().cast::<u8>(),
            t.numel() * t.kind().elt_size_in_bytes(),
        )
    }
}
/// Offline authoring owns one file containing shared state and every record.
/// Code bounds and layout are checked here/at admission, never by a hash scan
/// during application. Index metadata is activated into RAM.
#[cfg(not(feature = "native-client"))]
pub fn publish(
    root: &Path,
    model: &str,
    schema: &Schema,
    prototypes: &Tensor,
    records: &[(String, Vec<u32>, Vec<u32>)],
    approximate: bool,
    head_major: bool,
) -> Result<()> {
    use sha2::{Digest, Sha256};
    ensure!(!root.exists(), "compact destination already exists");
    ensure!(
        prototypes.kind() == Kind::BFloat16
            && prototypes.device() == Device::Cpu
            && prototypes.is_contiguous(),
        "dictionary must be contiguous CPU bf16"
    );
    let shape = prototypes.size();
    ensure!(
        shape.len() == 2 && shape[0] > 0 && shape[1] as usize * 2 == schema.row_bytes,
        "dictionary shape mismatch"
    );
    std::fs::create_dir_all(root)?;
    let reordered;
    let data = if head_major {
        let mut parts = vec![];
        let mut offset = 0;
        for seg in &schema.segments {
            let width = (seg.heads * seg.width) as i64;
            parts.push(
                prototypes
                    .narrow(1, offset, width)
                    .reshape([shape[0], seg.heads as i64, seg.width as i64])
                    .permute([1, 0, 2])
                    .contiguous()
                    .reshape([-1]),
            );
            offset += width;
        }
        reordered = Tensor::cat(&parts, 0);
        tensor_bytes(&reordered)
    } else {
        tensor_bytes(prototypes)
    };
    let count = shape[0] as usize;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(root.join("compact.pack"))?;
    file.write_all(&[0u8; 4096])?;
    file.write_all(data)?;
    let mut index = Index {
        version: 1,
        model: model.into(),
        schema: schema.clone(),
        prototypes: count,
        dictionary_bytes: data.len(),
        dictionary_sha256: format!("{:x}", Sha256::digest(data)),
        records: BTreeMap::new(),
        experimental_approximation: approximate,
        head_major,
        native_layout: false,
    };
    let mut offset = 4096 + data.len() as u64;
    for (key, tokens, codes) in records {
        ensure!(
            !tokens.is_empty()
                && tokens.len() == codes.len()
                && codes.iter().all(|&x| (x as usize) < count),
            "invalid compact record"
        );
        ensure!(!index.records.contains_key(key), "duplicate compact record");
        let aligned = (offset + 4095) & !4095;
        file.write_all(&vec![0u8; (aligned - offset) as usize])?;
        offset = aligned;
        for code in codes {
            file.write_all(&code.to_le_bytes())?;
        }
        index.records.insert(
            key.clone(),
            Record {
                offset,
                tokens: tokens.clone(),
            },
        );
        offset += codes.len() as u64 * 4;
    }
    file.sync_all()?;
    let mut out = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(root.join("index.json"))?;
    out.write_all(&serde_json::to_vec(&index)?)?;
    out.sync_all()?;
    File::open(root)?.sync_all()?;
    Ok(())
}

/// Offline publication for heterogeneous native layer shapes (e.g. local and
/// global attention). It stores the exact prepared working set; it does not claim
/// sparse compression. The same optimized device application code consumes it.
#[cfg(not(feature = "native-client"))]
pub fn publish_native(
    root: &Path,
    model: &str,
    key: &str,
    tokens: &[u32],
    banks: &HashMap<usize, Bank>,
) -> Result<()> {
    use sha2::{Digest, Sha256};
    ensure!(
        !root.exists() && !tokens.is_empty(),
        "new nonempty native snapshot required"
    );
    let schema = Schema::from_banks(banks)?;
    ensure!(
        banks.values().all(|b| b.keys.size() == b.values.size())
            && banks.values().map(|b| b.keys.size()[2] as usize).max() == Some(tokens.len()),
        "native token coverage mismatch"
    );
    let parts: Vec<_> = schema
        .segments
        .iter()
        .map(|s| {
            let b = &banks[&s.layer];
            (if s.value { &b.values } else { &b.keys })
                .to_device(Device::Cpu)
                .contiguous()
                .reshape([-1])
        })
        .collect();
    let packed = Tensor::cat(&parts, 0);
    let data = tensor_bytes(&packed);
    ensure!(
        data.len() == schema.output_bytes(tokens.len()),
        "native schema extent mismatch"
    );
    std::fs::create_dir_all(root)?;
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(root.join("compact.pack"))?;
    file.write_all(&[0u8; 4096])?;
    file.write_all(data)?;
    let end = 4096 + data.len() as u64;
    let offset = (end + 4095) & !4095;
    file.write_all(&vec![0; (offset - end) as usize])?;
    for code in 0..tokens.len() {
        file.write_all(&(code as u32).to_le_bytes())?;
    }
    file.sync_all()?;
    let index = Index {
        version: 1,
        model: model.into(),
        schema,
        prototypes: tokens.len(),
        dictionary_bytes: data.len(),
        dictionary_sha256: format!("{:x}", Sha256::digest(data)),
        records: BTreeMap::from([(
            key.into(),
            Record {
                offset,
                tokens: tokens.into(),
            },
        )]),
        experimental_approximation: false,
        head_major: false,
        native_layout: true,
    };
    let mut metadata = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(root.join("index.json"))?;
    metadata.write_all(&serde_json::to_vec(&index)?)?;
    metadata.sync_all()?;
    File::open(root)?.sync_all()?;
    Ok(())
}

pub struct Store {
    index: Index,
    dictionary: Vec<u8>,
    path: PathBuf,
    files: Files,
    pool: Option<rayon::ThreadPool>,
    plans: BTreeMap<String, Vec<Run>>,
    streaming: Option<crate::streaming_copy::Streaming>,
}
pub struct Workspace {
    codes: Vec<u8>,
    pub dense: Vec<u8>,
}
pub struct Timings {
    pub read_ns: u128,
    pub expand_ns: u128,
    pub total_ns: u128,
}
#[derive(Clone)]
struct DeviceLayer {
    layer: usize,
    device: Device,
    offset: usize,
    elements: usize,
    shape: [i64; 4],
}
#[derive(Clone)]
struct Run {
    code: usize,
    token: usize,
    count: usize,
}
struct Span {
    host: Tensor,
    resident: Tensor,
    event: crate::prepared_transfer::Event,
    storage_refs: usize,
}
struct ResidentSlot {
    spans: Vec<Span>,
    banks: HashMap<usize, Bank>,
}
impl ResidentSlot {
    fn available(&self) -> bool {
        self.banks.values().all(|b| {
            crate::prepared_transfer::tensor_refs(&b.keys) == 1
                && crate::prepared_transfer::tensor_refs(&b.values) == 1
        }) && self
            .spans
            .iter()
            .all(|s| crate::prepared_transfer::storage_refs(&s.resident) == s.storage_refs)
    }
    fn new(work: &DeviceWorkspace) -> Result<Self> {
        let mut spans = vec![];
        let mut banks = HashMap::new();
        let mut begin = 0;
        while begin < work.layers.len() {
            let first = &work.layers[begin];
            let mut end = begin + 1;
            while end < work.layers.len() && work.layers[end].device == first.device {
                end += 1;
            }
            let last = &work.layers[end - 1];
            let count = last.offset + 2 * last.elements - first.offset;
            let host = work.packed.narrow(0, first.offset as i64, count as i64);
            let resident = Tensor::empty([count as i64], (Kind::BFloat16, first.device));
            let mut event = crate::prepared_transfer::Event::new(&resident)?;
            event.record(&resident)?;
            event.wait()?; // initialize the underlying event outside active use
            for l in &work.layers[begin..end] {
                let offset = l.offset - first.offset;
                banks.insert(
                    l.layer,
                    Bank {
                        keys: resident
                            .narrow(0, offset as i64, l.elements as i64)
                            .reshape(l.shape),
                        values: resident
                            .narrow(0, (offset + l.elements) as i64, l.elements as i64)
                            .reshape(l.shape),
                    },
                );
            }
            let storage_refs = crate::prepared_transfer::storage_refs(&resident);
            spans.push(Span {
                host,
                resident,
                event,
                storage_refs,
            });
            begin = end;
        }
        Ok(Self { spans, banks })
    }
}
/// Private pinned allocation stays alive until all submitted copies finish.
pub struct DeviceWorkspace {
    codes: Vec<u8>,
    packed: Tensor,
    layers: Vec<DeviceLayer>,
    devices: Vec<usize>,
    slots: Vec<ResidentSlot>,
}
pub struct Applied {
    pub banks: HashMap<usize, Bank>,
    pub read_ns: u128,
    pub expand_ns: u128,
    pub transfer_ns: u128,
    pub total_ns: u128,
    pub transfer_operations: usize,
}
impl Store {
    /// Activation, not the request path. Checks dictionary integrity once.
    pub fn open(root: &Path, model: &str) -> Result<Self> {
        use sha2::{Digest, Sha256};
        let index: Index = serde_json::from_slice(&std::fs::read(root.join("index.json"))?)?;
        ensure!(
            index.version == 1 && index.model == model && index.prototypes > 0,
            "compact model mismatch"
        );
        ensure!(
            index.schema.row_bytes > 0
                && index.schema.row_bytes % 2 == 0
                && (index.native_layout
                    || index.dictionary_bytes
                        == index
                            .prototypes
                            .checked_mul(index.schema.row_bytes)
                            .context("dictionary overflow")?),
            "invalid dictionary extent"
        );
        if index.native_layout {
            ensure!(
                index.records.len() == 1,
                "native-layout activation needs one prepared working set"
            );
            let record = index.records.values().next().unwrap();
            ensure!(
                index.dictionary_bytes == index.schema.output_bytes(record.tokens.len()),
                "native dictionary extent mismatch"
            );
        }
        let path = root.join("compact.pack");
        let files = Files::new(Duration::from_secs(60))?;
        let (file, _) = files.acquire(&path)?;
        let mut dictionary = vec![0; index.dictionary_bytes];
        file.read_exact_at(&mut dictionary, 4096)?;
        ensure!(
            format!("{:x}", Sha256::digest(&dictionary)) == index.dictionary_sha256,
            "dictionary checksum mismatch"
        );
        let segment_bytes: usize = index
            .schema
            .segments
            .iter()
            .map(|s| s.heads * s.width * 2)
            .sum();
        ensure!(
            segment_bytes == index.schema.row_bytes,
            "schema width mismatch"
        );
        let mut plans = BTreeMap::new();
        if index.head_major {
            for (key, record) in &index.records {
                let mut codes = vec![0; record.tokens.len() * 4];
                file.read_exact_at(&mut codes, record.offset)?;
                let mut runs: Vec<Run> = vec![];
                for (token, bytes) in codes.chunks_exact(4).enumerate() {
                    let code = u32::from_le_bytes(bytes.try_into().unwrap()) as usize;
                    ensure!(code < index.prototypes, "invalid offline reference");
                    if let Some(last) = runs.last_mut() {
                        if last.code + last.count == code {
                            last.count += 1;
                            continue;
                        }
                    }
                    runs.push(Run {
                        code,
                        token,
                        count: 1,
                    });
                }
                plans.insert(key.clone(), runs);
            }
        }
        Ok(Self {
            index,
            dictionary,
            path,
            files,
            pool: None,
            plans,
            streaming: None,
        })
    }
    pub fn set_streaming(&mut self, enabled: bool) -> Result<()> {
        self.streaming = if enabled {
            Some(
                crate::streaming_copy::Streaming::new()
                    .context("AVX2 streaming stores unavailable")?,
            )
        } else {
            None
        };
        Ok(())
    }
    pub fn set_threads(&mut self, threads: usize) -> Result<()> {
        ensure!(threads > 0, "thread count must be positive");
        if threads > 1 {
            ensure!(
                self.index.head_major
                    && self
                        .index
                        .schema
                        .segments
                        .iter()
                        .all(|s| s.width == self.index.schema.segments[0].width),
                "parallel expansion requires uniform head-major layout"
            );
            self.pool = Some(
                rayon::ThreadPoolBuilder::new()
                    .num_threads(threads)
                    .build()?,
            );
            self.pool.as_ref().unwrap().broadcast(|_| ());
        } else {
            self.pool = None;
        }
        Ok(())
    }
    pub fn workspace(&self, key: &str) -> Result<Workspace> {
        let n = self
            .index
            .records
            .get(key)
            .context("unknown compact record")?
            .tokens
            .len();
        Ok(Workspace {
            codes: vec![0; n * 4],
            dense: vec![0; self.index.schema.output_bytes(n)],
        })
    }
    pub fn tokens(&self, key: &str) -> Result<&[u32]> {
        Ok(&self
            .index
            .records
            .get(key)
            .context("missing record")?
            .tokens)
    }
    pub fn path(&self) -> &Path {
        &self.path
    }
    pub fn dictionary_bytes(&self) -> usize {
        self.dictionary.len()
    }
    /// One retained-file read into reusable code buffer, then only table gathers
    /// into the final layer-major layout. No encoder, tensor math, or GPU work.
    pub fn expand(&self, key: &str, work: &mut Workspace) -> Result<Timings> {
        self.expand_into(key, &mut work.codes, &mut work.dense)
    }
    fn expand_into(&self, key: &str, codes: &mut [u8], dense: &mut [u8]) -> Result<Timings> {
        let start = Instant::now();
        let record = self
            .index
            .records
            .get(key)
            .context("unknown compact record")?;
        let n = record.tokens.len();
        ensure!(
            codes.len() == n * 4 && dense.len() == self.index.schema.output_bytes(n),
            "workspace belongs to another extent"
        );
        let (file, _) = self.files.acquire(&self.path)?;
        let read = Instant::now();
        file.read_exact_at(codes, record.offset)?;
        let read_ns = read.elapsed().as_nanos();
        let expand = Instant::now();
        if self.index.native_layout {
            dense.copy_from_slice(&self.dictionary);
        } else if let Some(pool) = &self.pool {
            use rayon::prelude::*;
            let head_bytes = self.index.schema.segments[0].width * 2;
            pool.install(|| {
                dense
                    .par_chunks_mut(n * head_bytes)
                    .enumerate()
                    .try_for_each(|(head, dst)| {
                        expand_head(
                            &self.dictionary,
                            codes,
                            dst,
                            head * self.index.prototypes * head_bytes,
                            head_bytes,
                            head_bytes,
                        )
                    })
            })?;
        } else {
            expand_codes(
                &self.index.schema,
                &self.dictionary,
                codes,
                dense,
                self.index.head_major,
            )?;
        }
        Ok(Timings {
            read_ns,
            expand_ns: expand.elapsed().as_nanos(),
            total_ns: start.elapsed().as_nanos(),
        })
    }
    pub fn device_workspace(&self, key: &str, placement: &[Device]) -> Result<DeviceWorkspace> {
        let n = self
            .index
            .records
            .get(key)
            .context("unknown compact record")?
            .tokens
            .len();
        let mut layers = vec![];
        let mut offset = 0;
        for pair in self.index.schema.segments.chunks(2) {
            ensure!(
                pair.len() == 2
                    && !pair[0].value
                    && pair[1].value
                    && pair[0].layer == pair[1].layer
                    && pair[0].heads == pair[1].heads
                    && pair[0].width == pair[1].width,
                "invalid K/V pairing"
            );
            let s = &pair[0];
            let device = *placement.get(s.layer).context("missing GPU layer")?;
            ensure!(
                matches!(device, Device::Cuda(_)),
                "GPU benchmark requires all-native-layer GPU placement"
            );
            let positions = s.positions.unwrap_or(n);
            let elements = positions * s.heads * s.width;
            layers.push(DeviceLayer {
                layer: s.layer,
                device,
                offset,
                elements,
                shape: [1, s.heads as i64, positions as i64, s.width as i64],
            });
            offset += 2 * elements;
        }
        let packed = Tensor::empty([offset as i64], (Kind::BFloat16, Device::Cpu))
            .f_pin_memory(layers[0].device)?;
        let devices = layers
            .iter()
            .filter_map(|l| {
                if let Device::Cuda(i) = l.device {
                    Some(i)
                } else {
                    None
                }
            })
            .collect::<std::collections::BTreeSet<_>>()
            .into_iter()
            .collect();
        Ok(DeviceWorkspace {
            codes: vec![0; n * 4],
            packed,
            layers,
            devices,
            slots: vec![],
        })
    }
    pub fn initialize_device_pool(&self, work: &mut DeviceWorkspace) -> Result<()> {
        work.slots.push(ResidentSlot::new(work)?);
        Ok(())
    }
    #[cfg(all(test, not(feature = "native-client")))]
    fn expand_plan(&self, key: &str, dense: &mut [u8]) -> Result<()> {
        self.expand_plan_range(key, dense, 0)
    }
    fn expand_plan_range(&self, key: &str, dense: &mut [u8], first_head: usize) -> Result<()> {
        let runs = self
            .plans
            .get(key)
            .context("head-major copy plan required")?;
        let n = self
            .index
            .records
            .get(key)
            .context("missing compact record")?
            .tokens
            .len();
        let head_bytes = self.index.schema.segments[0].width * 2;
        ensure!(
            self.index
                .schema
                .segments
                .iter()
                .all(|s| s.width * 2 == head_bytes)
                && dense.len() % (n * head_bytes) == 0
                && first_head * n * head_bytes + dense.len() <= n * self.index.schema.row_bytes,
            "copy-plan output mismatch"
        );
        let copy = |(head, dst): (usize, &mut [u8])| {
            let base = (first_head + head) * self.index.prototypes * head_bytes;
            for r in runs {
                let src = base + r.code * head_bytes;
                let out = r.token * head_bytes;
                let bytes = r.count * head_bytes;
                if let Some(streaming) = &self.streaming {
                    streaming.copy(
                        &self.dictionary[src..src + bytes],
                        &mut dst[out..out + bytes],
                    );
                } else {
                    dst[out..out + bytes].copy_from_slice(&self.dictionary[src..src + bytes]);
                }
            }
            if let Some(streaming) = &self.streaming {
                streaming.finish();
            }
        };
        if let Some(pool) = &self.pool {
            use rayon::prelude::*;
            pool.install(|| {
                dense
                    .par_chunks_mut(n * head_bytes)
                    .enumerate()
                    .for_each(copy)
            });
        } else {
            dense.chunks_mut(n * head_bytes).enumerate().for_each(copy);
        }
        Ok(())
    }
    pub fn copy_plan_runs(&self, key: &str) -> usize {
        self.plans.get(key).map_or(0, Vec::len)
    }
    /// Planned references are part of activated RAM metadata. No payload read.
    /// Exact dense table storage remains explicit; this is a loading optimization.
    pub fn apply_optimized(&self, key: &str, work: &mut DeviceWorkspace) -> Result<Applied> {
        let started = Instant::now();
        let record = self
            .index
            .records
            .get(key)
            .context("missing compact record")?;
        let n = record.tokens.len();
        let head_bytes = self.index.schema.segments[0].width * 2;
        ensure!(
            (self.index.native_layout
                || self
                    .index
                    .schema
                    .segments
                    .iter()
                    .all(|s| s.width * 2 == head_bytes))
                && work.packed.numel() * 2 == self.index.schema.output_bytes(n),
            "optimized layout mismatch"
        );
        let mut expand_ns = 0;
        let mut transfer_ns = 0;
        let reusable = work.slots.iter().position(ResidentSlot::available);
        let mut temporary;
        let slot = if let Some(i) = reusable {
            &mut work.slots[i]
        } else if work.slots.len() < 2 {
            let next = ResidentSlot::new(work)?;
            work.slots.push(next);
            work.slots.last_mut().unwrap()
        } else {
            temporary = ResidentSlot::new(work)?;
            &mut temporary
        };
        let submitted = (|| -> Result<()> {
            let mut first_head = 0;
            let mut native_offset = 0;
            for span in &mut slot.spans {
                let expand = Instant::now();
                // Disjoint device spans: previous GPU copy never reads the region
                // being filled here. All copies drain before workspace reuse.
                let bytes = span.host.numel() * 2;
                let output = unsafe {
                    std::slice::from_raw_parts_mut(span.host.data_ptr().cast::<u8>(), bytes)
                };
                if self.index.native_layout {
                    let source = &self.dictionary[native_offset..native_offset + bytes];
                    if let Some(streaming) = &self.streaming {
                        streaming.copy(source, output);
                        streaming.finish();
                    } else {
                        output.copy_from_slice(source);
                    }
                } else {
                    self.expand_plan_range(key, output, first_head)?;
                    first_head += bytes / (n * head_bytes);
                }
                native_offset += bytes;
                expand_ns += expand.elapsed().as_nanos();
                let transfer = Instant::now();
                crate::prepared_transfer::copy_async(&mut span.resident, &span.host)?;
                span.event.record(&span.resident)?;
                transfer_ns += transfer.elapsed().as_nanos();
            }
            Ok(())
        })();
        if submitted.is_err() {
            // Error recovery only: drain even if recording the copy event failed.
            for &device in &work.devices {
                tch::Cuda::synchronize(device as i64);
            }
            submitted?;
        }
        let wait = Instant::now();
        let mut completion_error = None;
        for span in &slot.spans {
            if let Err(e) = span.event.wait() {
                completion_error = Some(e);
            }
        }
        if let Some(e) = completion_error {
            for &device in &work.devices {
                tch::Cuda::synchronize(device as i64);
            }
            return Err(e);
        }
        transfer_ns += wait.elapsed().as_nanos();
        let banks = slot
            .banks
            .iter()
            .map(|(&i, b)| {
                (
                    i,
                    Bank {
                        keys: b.keys.shallow_clone(),
                        values: b.values.shallow_clone(),
                    },
                )
            })
            .collect();
        Ok(Applied {
            banks,
            read_ns: 0,
            expand_ns,
            transfer_ns,
            total_ns: started.elapsed().as_nanos(),
            transfer_operations: slot.spans.len(),
        })
    }
    /// Complete reference-read -> CPU expansion -> device copy -> tensor views.
    /// Expand directly into pinned output; no intermediate dense CPU copy.
    pub fn apply(&self, key: &str, work: &mut DeviceWorkspace) -> Result<Applied> {
        let started = Instant::now();
        // SAFETY: private contiguous CPU tensor, exclusive workspace borrow, and
        // every prior call drains copies before returning. No host aliases escape.
        let dense = unsafe {
            std::slice::from_raw_parts_mut(
                work.packed.data_ptr().cast::<u8>(),
                work.packed.numel() * 2,
            )
        };
        let expanded = self.expand_into(key, &mut work.codes, dense)?;
        let transfer = Instant::now();
        let mut banks = HashMap::with_capacity(work.layers.len());
        let mut operations = 0;
        let result = (|| -> Result<()> {
            let mut begin = 0;
            while begin < work.layers.len() {
                let first = &work.layers[begin];
                let mut end = begin + 1;
                while end < work.layers.len() && work.layers[end].device == first.device {
                    end += 1;
                }
                let last = &work.layers[end - 1];
                let count = last.offset + 2 * last.elements - first.offset;
                let host = work.packed.narrow(0, first.offset as i64, count as i64);
                let resident = host.f_to_device_(first.device, Kind::BFloat16, true, false)?;
                operations += 1;
                for l in &work.layers[begin..end] {
                    let offset = l.offset - first.offset;
                    banks.insert(
                        l.layer,
                        Bank {
                            keys: resident
                                .narrow(0, offset as i64, l.elements as i64)
                                .reshape(l.shape),
                            values: resident
                                .narrow(0, (offset + l.elements) as i64, l.elements as i64)
                                .reshape(l.shape),
                        },
                    );
                }
                begin = end;
            }
            Ok(())
        })();
        // Drain on errors too; asynchronous reads must finish before CPU reuse.
        for &device in &work.devices {
            tch::Cuda::synchronize(device as i64);
        }
        result?;
        Ok(Applied {
            banks,
            read_ns: expanded.read_ns,
            expand_ns: expanded.expand_ns,
            transfer_ns: transfer.elapsed().as_nanos(),
            total_ns: started.elapsed().as_nanos(),
            transfer_operations: operations,
        })
    }
    /// Experimental evaluation bridge. Materializes every layer and record token.
    /// Timing this separately avoids hiding its allocations in CPU gather latency.
    pub fn banks(&self, key: &str, work: &Workspace) -> Result<HashMap<usize, Bank>> {
        let n = self
            .index
            .records
            .get(key)
            .context("unknown compact record")?
            .tokens
            .len();
        let mut offset = 0;
        let mut pairs: BTreeMap<usize, Vec<Tensor>> = BTreeMap::new();
        for s in &self.index.schema.segments {
            let positions = s.positions.unwrap_or(n);
            let bytes = positions * s.heads * s.width * 2;
            let t = Tensor::from_data_size(
                &work.dense[offset..offset + bytes],
                &[1, s.heads as i64, positions as i64, s.width as i64],
                Kind::BFloat16,
            );
            pairs.entry(s.layer).or_default().push(t);
            offset += bytes;
        }
        let mut banks = HashMap::new();
        for (layer, mut pair) in pairs {
            ensure!(pair.len() == 2, "missing K/V segment");
            let values = pair.pop().unwrap();
            let keys = pair.pop().unwrap();
            banks.insert(layer, Bank { keys, values });
        }
        Ok(banks)
    }
}
fn expand_head(
    dictionary: &[u8],
    codes: &[u8],
    out: &mut [u8],
    source: usize,
    stride: usize,
    head_bytes: usize,
) -> Result<()> {
    for (token, code) in codes.chunks_exact(4).enumerate() {
        let code = u32::from_le_bytes(code.try_into().unwrap()) as usize;
        let begin = code
            .checked_mul(stride)
            .and_then(|x| x.checked_add(source))
            .context("code overflow")?;
        let src = dictionary
            .get(begin..begin + head_bytes)
            .context("code outside dictionary")?;
        out[token * head_bytes..(token + 1) * head_bytes].copy_from_slice(src);
    }
    Ok(())
}
fn expand_codes(
    schema: &Schema,
    dictionary: &[u8],
    codes: &[u8],
    out: &mut [u8],
    head_major: bool,
) -> Result<()> {
    let n = codes.len() / 4;
    let count = dictionary.len() / schema.row_bytes;
    let mut source_segment = 0;
    let mut destination_segment = 0;
    for s in &schema.segments {
        let head_bytes = s.width * 2;
        for head in 0..s.heads {
            let source = source_segment + head * head_bytes;
            let destination = destination_segment + head * n * head_bytes;
            expand_head(
                dictionary,
                codes,
                &mut out[destination..destination + n * head_bytes],
                if head_major { source * count } else { source },
                if head_major {
                    head_bytes
                } else {
                    schema.row_bytes
                },
                head_bytes,
            )?;
        }
        source_segment += s.heads * head_bytes;
        destination_segment += n * s.heads * head_bytes;
    }
    Ok(())
}

#[cfg(all(test, not(feature = "native-client")))]
mod tests {
    use super::*;
    #[test]
    fn exact_context_dictionary_preserves_all_layers_heads_tokens_and_both_banks() {
        let mut banks = HashMap::new();
        for layer in [3, 7] {
            let a = Tensor::arange(2 * 5 * 4, (Kind::Float, Device::Cpu)).reshape([1, 2, 5, 4])
                + layer as f64 * 100.;
            banks.insert(
                layer,
                Bank {
                    keys: a.to_kind(Kind::BFloat16),
                    values: (&a + 51.).to_kind(Kind::BFloat16),
                },
            );
        }
        let schema = Schema::from_banks(&banks).unwrap();
        let rows = schema.rows(&banks).unwrap();
        let dir = tempfile::tempdir().unwrap();
        for (head_major, threads) in [(false, 1), (true, 1), (true, 4)] {
            let dest = dir.path().join(format!("store-{head_major}-{threads}"));
            publish(
                &dest,
                "model",
                &schema,
                &rows,
                &[
                    ("first".into(), vec![10; 5], vec![0, 1, 2, 3, 4]),
                    ("second".into(), vec![20; 5], vec![4, 3, 2, 1, 0]),
                ],
                false,
                head_major,
            )
            .unwrap();
            let mut store = Store::open(&dest, "model").unwrap();
            store.set_threads(threads).unwrap();
            let mut work = store.workspace("first").unwrap();
            store.expand("first", &mut work).unwrap();
            let decoded = store.banks("first", &work).unwrap();
            for (layer, bank) in &banks {
                assert!(decoded[layer].keys.equal(&bank.keys));
                assert!(decoded[layer].values.equal(&bank.values));
            }
            store.expand("second", &mut work).unwrap();
            if head_major {
                let expected = work.dense.clone();
                let mut planned = vec![0; expected.len()];
                store.expand_plan("second", &mut planned).unwrap();
                assert_eq!(planned, expected);
                assert_eq!(store.copy_plan_runs("first"), 1);
                assert_eq!(store.copy_plan_runs("second"), 5);
            }
            let second = store.banks("second", &work).unwrap();
            for (layer, bank) in &banks {
                assert!(second[layer].keys.equal(&bank.keys.flip([2])));
                assert!(second[layer].values.equal(&bank.values.flip([2])));
            }
            assert!(Store::open(&dest, "other-model").is_err());
            assert!(store.workspace("missing").is_err());
        }
    }
    #[test]
    fn heterogeneous_window_lengths_and_head_widths_are_preserved() {
        let banks = HashMap::from([
            (
                0,
                Bank {
                    keys: Tensor::arange(2 * 6 * 4, (Kind::Float, Device::Cpu))
                        .reshape([1, 2, 6, 4])
                        .to_kind(Kind::BFloat16),
                    values: Tensor::ones([1, 2, 6, 4], (Kind::BFloat16, Device::Cpu)),
                },
            ),
            (
                1,
                Bank {
                    keys: Tensor::arange(10 * 8, (Kind::Float, Device::Cpu))
                        .reshape([1, 1, 10, 8])
                        .to_kind(Kind::BFloat16),
                    values: Tensor::full([1, 1, 10, 8], 7., (Kind::BFloat16, Device::Cpu)),
                },
            ),
        ]);
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("mixed");
        publish_native(&path, "model", "key", &vec![4; 10], &banks).unwrap();
        // The Torch-free consumer must read exactly the same prepared bytes,
        // including heterogeneous local/global layers, before replacing the bridge.
        let native = crate::native_store::NativeStore::admit(&path, "model", "key", 4096).unwrap();
        for segment in native.segments() {
            let bank = &banks[&segment.layer];
            let expected = if segment.value {
                &bank.values
            } else {
                &bank.keys
            };
            assert_eq!(segment.bytes, tensor_bytes(expected));
            assert_eq!(segment.positions, expected.size()[2] as usize);
        }
        let store = Store::open(&path, "model").unwrap();
        let mut work = store.workspace("key").unwrap();
        store.expand("key", &mut work).unwrap();
        let out = store.banks("key", &work).unwrap();
        for (layer, b) in banks {
            assert!(out[&layer].keys.equal(&b.keys));
            assert!(out[&layer].values.equal(&b.values));
        }
    }
    #[test]
    fn out_of_range_codes_do_not_read_arbitrary_memory() {
        let s = Schema {
            segments: vec![Segment {
                layer: 0,
                value: false,
                heads: 1,
                width: 2,
                positions: None,
            }],
            row_bytes: 4,
        };
        assert!(expand_codes(&s, &[0; 4], &1u32.to_le_bytes(), &mut [0; 4], false).is_err());
    }
}
