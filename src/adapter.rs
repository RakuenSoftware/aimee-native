//! The proven connection: native attention request -> Aimee -> separately
//! encoded frozen-Qwen K/V -> requesting attention. No trained adapter values.
use crate::{
    model::{Bank, Cache, Model, scores},
    tokens::Tokens,
    transport::MemorySource,
};
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::cell::{Cell, RefCell};
use std::collections::{HashMap, VecDeque};
use std::time::Instant;
use tch::{Device, Tensor};

struct PreparedLayer {
    offset: i64,
    prepositioned: bool,
    device: Device,
    sources: Vec<Bank>,
    bank: Bank,
}

pub struct State {
    prepared: RefCell<HashMap<usize, PreparedLayer>>,
    prepositioned: bool,
    pub bank_preparations: Cell<usize>,
    pub bank_reuses: Cell<usize>,
    pub bank_application_cpu_ns: Cell<u128>,
    pub cache_transition: Value,
    pub diagnostic_steps: usize,
    pub position_shift: i64,
    pub before_prompt: bool,
    pub attention_trace: Vec<Value>,
    pub encoding_format: String,
    pub record_encoding: bool,
    records: Vec<RecordBank>,
    pub binding: String,
    pub sequence: Vec<u32>,
    pub memory_ids: Vec<u32>,
    pub facts: Vec<Value>,
    pub banks: HashMap<usize, Bank>,
    pub events: Vec<Value>,
    pub native_reads: usize,
    pub encodings: usize,
    pub step: usize,
    pub decode_recall: bool,
    pub reuse: bool,
}
impl State {
    pub fn bank_position_offset(&self) -> i64 {
        if self.before_prompt {
            -(self.memory_ids.len() as i64)
        } else {
            self.position_shift
        }
    }
    /// Memory is encoded independently at positions 0..M. At both attention
    /// addressing and consumption it must occupy -M..-1, before the conversation.
    /// Keep the cached bank unshifted: repeated reads and reuse must not rotate it
    /// again, and a replacement bank must use its own length.
    /// Materialize every selected layer before generation, for a synchronized
    /// measurement from memory request to complete attention-ready state.
    pub fn prepare_ready(&self, model: &Model) -> Result<()> {
        for (i, kind) in model.config.layer_types.iter().enumerate() {
            if kind == "full_attention" {
                self.bank_for_read(model, i, model.layers[i])?;
            }
        }
        let devices: std::collections::BTreeSet<_> = model
            .layers
            .iter()
            .filter_map(|d| {
                if let Device::Cuda(i) = d {
                    Some(*i)
                } else {
                    None
                }
            })
            .collect();
        for i in devices {
            tch::Cuda::synchronize(i as i64);
        }
        Ok(())
    }
    fn bank_for_read(&self, model: &Model, index: usize, device: Device) -> Result<Option<Bank>> {
        let started = Instant::now();
        let sources: Vec<&Bank> = if self.record_encoding {
            if self.records.is_empty() {
                return Ok(None);
            }
            let mut count = 0;
            let mut sources = Vec::with_capacity(self.records.len());
            for record in &self.records {
                let bank = record
                    .banks
                    .get(&index)
                    .context("record missing native layer")?;
                ensure!(
                    bank.keys.size()[2] == record.tokens as i64
                        && bank.values.size()[2] == record.tokens as i64,
                    "native record/token address length differs"
                );
                count += record.tokens;
                sources.push(bank);
            }
            ensure!(
                count == self.memory_ids.len(),
                "native bank/token address length differs"
            );
            sources
        } else {
            let Some(bank) = self.banks.get(&index) else {
                return Ok(None);
            };
            ensure!(
                bank.keys.size()[2] == self.memory_ids.len() as i64
                    && bank.values.size()[2] == self.memory_ids.len() as i64,
                "native bank/token address length differs"
            );
            vec![bank]
        };
        let offset = self.bank_position_offset();
        if let Some(cached) = self.prepared.borrow().get(&index) {
            if cached.device == device
                && cached.prepositioned == self.prepositioned
                && cached.offset == offset
                && cached.sources.len() == sources.len()
                && cached.sources.iter().zip(&sources).all(|(a, b)| {
                    a.keys.data_ptr() == b.keys.data_ptr()
                        && a.values.data_ptr() == b.values.data_ptr()
                })
            {
                self.bank_reuses.set(self.bank_reuses.get() + 1);
                self.bank_application_cpu_ns
                    .set(self.bank_application_cpu_ns.get() + started.elapsed().as_nanos());
                return Ok(Some(cached.bank.copy()));
            }
        }
        // Placement and rotation happen once per layer/ordered bank, not once
        // per generated token. Both K and V remain on the consuming device.
        let mut start = offset;
        let mut keys = Vec::with_capacity(sources.len());
        let mut values = Vec::with_capacity(sources.len());
        for bank in &sources {
            keys.push(model.shift_memory_keys(
                &crate::model::transfer(&bank.keys, device),
                if self.prepositioned { 0 } else { start },
            ));
            values.push(crate::model::transfer(&bank.values, device));
            start += bank.keys.size()[2];
        }
        let bank = if keys.len() == 1 {
            Bank {
                keys: keys.pop().unwrap(),
                values: values.pop().unwrap(),
            }
        } else {
            Bank {
                keys: Tensor::cat(&keys, 2),
                values: Tensor::cat(&values, 2),
            }
        };
        ensure!(
            bank.keys.size()[2] == self.memory_ids.len() as i64
                && bank.values.size()[2] == self.memory_ids.len() as i64,
            "prepared native bank omitted records"
        );
        let answer = bank.copy();
        self.prepared.borrow_mut().insert(
            index,
            PreparedLayer {
                offset,
                prepositioned: self.prepositioned,
                device,
                sources: sources.iter().map(|b| b.copy()).collect(),
                bank,
            },
        );
        self.bank_preparations.set(self.bank_preparations.get() + 1);
        self.bank_application_cpu_ns
            .set(self.bank_application_cpu_ns.get() + started.elapsed().as_nanos());
        Ok(Some(answer))
    }
}
struct RecordBank {
    key: String,
    tokens: usize,
    banks: HashMap<usize, Bank>,
}

fn encoding_key(
    binding: &str,
    ids: &[u32],
    refs: &[&Value],
    granularity: &str,
    format: &str,
) -> Result<String> {
    Ok(format!(
        "{}:{:x}",
        binding,
        Sha256::digest(serde_json::to_vec(&json!([
            granularity,
            format,
            ids,
            refs
        ]))?)
    ))
}

fn prepared_key(binding: &str, format: &str, records: bool, facts: &[Value]) -> Result<String> {
    let identity: Vec<_> = facts
        .iter()
        .map(|f| json!([f["memory_ref"], f["content"], f["memory_hash"]]))
        .collect();
    Ok(format!(
        "{:x}",
        Sha256::digest(serde_json::to_vec(&json!([
            "prepared-v1",
            binding,
            format,
            if records { "record" } else { "bank" },
            identity
        ]))?)
    ))
}

struct Cached {
    proof: Option<Value>,
    key: String,
    banks: HashMap<usize, Bank>,
    bytes: usize,
}

#[cfg(test)]
mod publication_tests {
    use super::*;

    struct Source(VecDeque<Option<String>>);
    impl MemorySource for Source {
        fn begin(&mut self) -> Result<String> {
            self.0
                .pop_front()
                .flatten()
                .context("publication withdrawn")
        }
        fn search(&mut self, _: &str, _: usize) -> Result<Value> {
            anyhow::bail!("unexpected search")
        }
        fn native_search(&mut self, _: &str, _: usize) -> Result<Value> {
            anyhow::bail!("unexpected search")
        }
    }

    #[test]
    fn strict_prepared_records_load_all_three_without_model_encoding() {
        let _guard = tch::no_grad_guard();
        let dir = tempfile::tempdir().unwrap();
        let token_path = dir.path().join("tokenizer.json");
        tokenizers::Tokenizer::new(tokenizers::models::wordlevel::WordLevel::default())
            .save(&token_path, false)
            .unwrap();
        let tokenizer = Tokens::load(&token_path).unwrap();
        // This model has no weights: any accidental model encoding cannot pass.
        let model = crate::model::position_tests::rotary_model();
        let facts: Vec<_> = (0..3).map(|i| json!({"id":format!("t:{i}"),
            "content":format!("record {i}"),"memory_ref":{"namespace":"t","id":i.to_string(),"revision":"1"}})).collect();
        let mut store = crate::prepared_memory::Store::open(dir.path(), "model-v1", true).unwrap();
        for (i, fact) in facts.iter().enumerate() {
            let key =
                prepared_key("publication", "content", true, std::slice::from_ref(fact)).unwrap();
            let banks = HashMap::from([(
                0,
                Bank {
                    keys: Tensor::ones([1, 2, 2, 8], (tch::Kind::Float, Device::Cpu)),
                    values: Tensor::full(
                        [1, 2, 2, 8],
                        i as f64 + 1.,
                        (tch::Kind::Float, Device::Cpu),
                    ),
                },
            )]);
            store
                .put(&key, &[10 + i as u32, 20 + i as u32], &banks)
                .unwrap();
            let shifted = HashMap::from([(
                0,
                Bank {
                    keys: model.shift_memory_keys(&banks[&0].keys, -2),
                    values: banks[&0].values.shallow_clone(),
                },
            )]);
            store
                .put(
                    &positioned_key(&key),
                    &[10 + i as u32, 20 + i as u32],
                    &shifted,
                )
                .unwrap();
        }
        drop(store);
        let source = Source(VecDeque::from([Some("publication".into())]));
        let mut adapter = Adapter::new(Box::new(source), 3, 100, 4096);
        adapter.prepared_store =
            Some(crate::prepared_memory::Store::open(dir.path(), "model-v1", false).unwrap());
        let mut state = adapter.begin(false, true).unwrap();
        state.record_encoding = true;
        adapter
            .recall_prepared(&model, &tokenizer, &mut state, facts.clone(), json!({}))
            .unwrap();
        assert_eq!(state.encodings, 0);
        assert_eq!(state.records.len(), 3);
        assert_eq!(state.memory_ids.len(), 6);
        let bank = state
            .bank_for_read(&model, 0, Device::Cpu)
            .unwrap()
            .unwrap();
        for i in 0..3 {
            assert_eq!(bank.values.double_value(&[0, 0, i * 2, 0]), i as f64 + 1.);
        }
        let reused = state
            .bank_for_read(&model, 0, Device::Cpu)
            .unwrap()
            .unwrap();
        assert_eq!(bank.keys.data_ptr(), reused.keys.data_ptr());
        assert_eq!(state.bank_preparations.get(), 1);
        assert_eq!(state.bank_reuses.get(), 1);
        adapter
            .recall_prepared(
                &model,
                &tokenizer,
                &mut state,
                facts[..1].to_vec(),
                json!({}),
            )
            .unwrap();
        assert!(state.prepositioned);
        let read = state
            .bank_for_read(&model, 0, Device::Cpu)
            .unwrap()
            .unwrap();
        let expected = model.shift_memory_keys(
            &Tensor::ones([1, 2, 2, 8], (tch::Kind::Float, Device::Cpu)),
            -2,
        );
        assert!(
            read.keys.equal(&expected),
            "offline position was applied twice"
        );
        adapter
            .recall_prepared(&model, &tokenizer, &mut state, facts.clone(), json!({}))
            .unwrap();
        assert!(!state.prepositioned);
        assert_eq!(state.memory_ids.len(), 6);
        let mut revised = facts.clone();
        revised[2]["memory_ref"]["revision"] = json!("2");
        assert!(
            adapter
                .recall_prepared(&model, &tokenizer, &mut state, revised, json!({}))
                .is_err()
        );
        assert_eq!(state.encodings, 0);
        let other_key = prepared_key("other-publication", "content", true, &facts[..1]).unwrap();
        assert!(
            adapter
                .prepared_store
                .as_ref()
                .unwrap()
                .entry(&other_key)
                .is_none()
        );
    }

    #[test]
    fn record_cache_reuses_unchanged_values_and_invalidates_exact_revisions() {
        let source = Source(VecDeque::from([Some("publication".into())]));
        let mut adapter = Adapter::new(Box::new(source), 4, 1024, 128);
        let make = |value| {
            HashMap::from([(
                0,
                Bank {
                    keys: Tensor::full([1, 1, 2, 4], value, (tch::Kind::Float, Device::Cpu)),
                    values: Tensor::zeros([1, 1, 2, 4], (tch::Kind::Float, Device::Cpu)),
                },
            )])
        }; // 64 bytes per record
        let a = json!({"namespace":"general","id":"a","revision":"1"});
        let b = json!({"namespace":"general","id":"b","revision":"1"});
        let key = |r: &Value, tokens: &[u32], binding: &str| {
            encoding_key(binding, tokens, &[r], "record", "content").unwrap()
        };
        let ka = key(&a, &[1, 2], "publication");
        let kb = key(&b, &[3, 4], "publication");
        adapter.remember(ka.clone(), &make(1.), true);
        adapter.remember(kb.clone(), &make(2.), true);
        assert!(adapter.cached(&ka, true).is_some());
        let changed = json!({"namespace":"general","id":"b","revision":"2"});
        let kc = key(&changed, &[3, 5], "publication");
        assert!(adapter.cached(&kc, true).is_none());
        assert!(
            adapter
                .cached(&key(&a, &[1, 9], "publication"), true)
                .is_none()
        );
        assert!(
            adapter
                .cached(&key(&a, &[1, 2], "other-recipient"), true)
                .is_none()
        );
        assert!(adapter.cached(&ka, false).is_none());
        adapter.remember(kc.clone(), &make(3.), true);
        assert!(
            adapter.cached(&ka, true).unwrap()[&0]
                .keys
                .equal(&make(1.)[&0].keys)
        );
        assert!(
            adapter.cached(&kb, true).is_none(),
            "LRU budget must evict the unused old revision"
        );
        assert!(adapter.cached(&kc, true).is_some());
        adapter.remember("disabled".into(), &make(4.), false);
        assert!(adapter.cached("disabled", true).is_none());
        adapter.cache_budget = 1;
        adapter.remember("too-large".into(), &make(4.), true);
        assert!(adapter.cached("too-large", true).is_none());
    }

    #[test]
    fn independent_records_have_disjoint_positions_without_mutating_cached_keys() {
        let model = crate::model::position_tests::rotary_model();
        let source = Source(VecDeque::from([Some("publication".into())]));
        let mut adapter = Adapter::new(Box::new(source), 4, 1024, 4096);
        let mut state = adapter.begin(true, true).unwrap();
        state.record_encoding = true;
        let make = |name: &str, count: usize, value: f64| RecordBank {
            key: name.into(),
            tokens: count,
            banks: HashMap::from([(
                0,
                Bank {
                    keys: Tensor::full(
                        [1, 2, count as i64, 8],
                        value,
                        (tch::Kind::Float, Device::Cpu),
                    ),
                    values: Tensor::full(
                        [1, 2, count as i64, 8],
                        value * 2.,
                        (tch::Kind::Float, Device::Cpu),
                    ),
                },
            )]),
        };
        state.records = vec![make("a", 3, 0.3), make("b", 5, 0.7)];
        for reordered in [false, true] {
            if reordered {
                state.records.swap(0, 1);
            }
            for grow in [false, true] {
                if grow {
                    state.records.push(make("c", 2, 0.9));
                }
                let count: usize = state.records.iter().map(|r| r.tokens).sum();
                state.memory_ids = vec![0; count];
                for step in [0, 1, 100] {
                    state.step = step;
                    let mut offset = -(count as i64);
                    let expected: Vec<Tensor> = state
                        .records
                        .iter()
                        .map(|r| {
                            let keys = model.shift_memory_keys(&r.banks[&0].keys, offset);
                            offset += r.tokens as i64;
                            keys
                        })
                        .collect();
                    let raw: Vec<Tensor> = state
                        .records
                        .iter()
                        .map(|r| r.banks[&0].keys.copy())
                        .collect();
                    let got = state
                        .bank_for_read(&model, 0, Device::Cpu)
                        .unwrap()
                        .unwrap();
                    assert!(got.keys.equal(&Tensor::cat(&expected, 2)));
                    for (record, before) in state.records.iter().zip(raw) {
                        assert!(record.banks[&0].keys.equal(&before));
                    }
                    assert_eq!(got.values.size()[2], count as i64);
                }
                if grow {
                    state.records.pop();
                }
            }
        }
        state.memory_ids.push(0);
        assert!(state.bank_for_read(&model, 0, Device::Cpu).is_err());
    }

    #[test]
    fn active_generation_failure_discards_shared_encodings() {
        struct Gone;
        impl MemorySource for Gone {
            fn begin(&mut self) -> Result<String> {
                Ok("old".into())
            }
            fn check_generation(&mut self, _: &str) -> Result<()> {
                anyhow::bail!("withdrawn")
            }
            fn search(&mut self, _: &str, _: usize) -> Result<Value> {
                unreachable!()
            }
            fn native_search(&mut self, _: &str, _: usize) -> Result<Value> {
                unreachable!()
            }
        }
        let mut a = Adapter::new(Box::new(Gone), 4, 2048, 1024);
        a.begin(false, true).unwrap();
        a.cache.push_back(Cached {
            key: "old:record".into(),
            proof: None,
            banks: HashMap::new(),
            bytes: 0,
        });
        assert!(a.check_generation("old").is_err());
        assert!(a.cache.is_empty());
        assert!(a.generation.is_none());
    }

    #[test]
    fn publication_change_preserves_only_revalidated_record_encodings() {
        struct Live {
            views: VecDeque<Option<String>>,
        }
        impl MemorySource for Live {
            fn begin(&mut self) -> Result<String> {
                self.views.pop_front().flatten().context("withdrawn")
            }
            fn retain_encodings(&mut self, p: &[Value]) -> Result<Vec<bool>> {
                Ok(p.iter()
                    .map(|v| v["memory_ref"]["id"] == "unchanged")
                    .collect())
            }
            fn search(&mut self, _: &str, _: usize) -> Result<Value> {
                unreachable!()
            }
            fn native_search(&mut self, _: &str, _: usize) -> Result<Value> {
                unreachable!()
            }
        }
        let mut a = Adapter::new(
            Box::new(Live {
                views: VecDeque::from([Some("old".into()), Some("new".into()), None]),
            }),
            4,
            2048,
            1024,
        );
        a.begin(false, true).unwrap();
        for id in ["unchanged", "changed", "removed"] {
            a.cache.push_back(Cached {
                key: format!("old:{id}"),
                proof: Some(json!({"memory_ref":{"id":id}})),
                banks: HashMap::new(),
                bytes: 0,
            });
        }
        a.cache.push_back(Cached {
            key: "old:joint-bank".into(),
            proof: None,
            banks: HashMap::new(),
            bytes: 0,
        });
        let s = a.begin(false, true).unwrap();
        assert_eq!(s.cache_transition, json!({"retained":1,"invalidated":3}));
        assert_eq!(a.cache.len(), 1);
        assert_eq!(a.cache[0].key, "new:unchanged");
        assert!(a.begin(false, true).is_err());
        assert!(a.cache.is_empty());
    }

    #[test]
    fn replacement_and_withdrawal_discard_cached_native_states() {
        let source = Source(VecDeque::from([
            Some("first".into()),
            Some("first".into()),
            Some("next".into()),
            None,
        ]));
        let mut adapter = Adapter::new(Box::new(source), 4, 1024, 4096);
        adapter.begin(false, true).unwrap();
        adapter.cache.push_back(Cached {
            proof: None,
            key: "old-bank".into(),
            banks: HashMap::new(),
            bytes: 0,
        });
        adapter.begin(false, true).unwrap();
        assert_eq!(adapter.cache.len(), 1);
        adapter.begin(false, true).unwrap();
        assert!(adapter.cache.is_empty());
        adapter.cache.push_back(Cached {
            proof: None,
            key: "new-bank".into(),
            banks: HashMap::new(),
            bytes: 0,
        });
        assert!(adapter.begin(false, true).is_err());
        assert!(adapter.cache.is_empty());
        assert!(adapter.generation.is_none());
    }

    #[test]
    fn bank_positions_are_disjoint_by_default_and_do_not_drift_on_reuse() {
        use tch::Kind;
        let model = crate::model::position_tests::rotary_model();
        let source = Source(VecDeque::from([Some("generation".into())]));
        let mut adapter = Adapter::new(Box::new(source), 4, 1024, 4096);
        let mut state = adapter.begin(true, true).unwrap();
        assert!(
            state.before_prompt,
            "default must separate memory and prompt positions"
        );
        assert!(
            state
                .bank_for_read(&model, 0, Device::Cpu)
                .unwrap()
                .is_none()
        );
        for count in [5, 17, 1] {
            state.memory_ids = vec![0; count];
            let keys = (Tensor::arange(count as i64 * 16, (Kind::Float, Device::Cpu)).reshape([
                1,
                2,
                count as i64,
                8,
            ]) * 0.11)
                .sin();
            let values = &keys * 0.5;
            state.banks.insert(
                0,
                Bank {
                    keys: keys.shallow_clone(),
                    values: values.shallow_clone(),
                },
            );
            let expected = model.shift_memory_keys(&keys, -(count as i64));
            for step in [0, 1, 16, 8192] {
                state.step = step;
                state.sequence.resize(step + 1, 0);
                let read = state
                    .bank_for_read(&model, 0, Device::Cpu)
                    .unwrap()
                    .unwrap();
                assert!(read.keys.equal(&expected));
                assert!(read.values.equal(&values));
                assert!(
                    state.banks[&0].keys.equal(&keys),
                    "cached keys were mutated"
                );
            }
            // The historical overlapping-coordinate control is opt-in only.
            state.before_prompt = false;
            assert!(
                state
                    .bank_for_read(&model, 0, Device::Cpu)
                    .unwrap()
                    .unwrap()
                    .keys
                    .equal(&keys)
            );
            state.before_prompt = true;
        }
        state.memory_ids.push(0);
        assert!(state.bank_for_read(&model, 0, Device::Cpu).is_err());
    }
}
struct CompactSnapshot {
    store: crate::compact_memory::Store,
    work: crate::compact_memory::DeviceWorkspace,
    key: String,
    identity: String,
    tokens: Vec<u32>,
    _directory: tempfile::TempDir,
}
pub struct Adapter {
    pub source: Box<dyn MemorySource>,
    pub limit: usize,
    pub max_tokens: usize,
    pub cache_budget: usize,
    cache: VecDeque<Cached>,
    generation: Option<String>,
    pub compact_root: Option<std::path::PathBuf>,
    compact: Option<CompactSnapshot>,
    pub prepared_store: Option<crate::prepared_memory::Store>,
    pub preparation_mode: bool,
    pub expected_preparation_refs: Option<Vec<Value>>,
}
impl Adapter {
    pub fn new(
        source: Box<dyn MemorySource>,
        limit: usize,
        max_tokens: usize,
        cache_budget: usize,
    ) -> Self {
        Self {
            source,
            limit,
            max_tokens,
            cache_budget,
            cache: VecDeque::new(),
            generation: None,
            compact_root: None,
            compact: None,
            prepared_store: None,
            preparation_mode: false,
            expected_preparation_refs: None,
        }
    }
    /// Explicit research preparation; never reachable as a serving-miss fallback.
    pub fn prepare_compact(
        &mut self,
        m: &Model,
        t: &Tokens,
        query: &str,
        expected: &[Value],
    ) -> Result<Value> {
        let root = self
            .compact_root
            .clone()
            .context("compact research mode disabled")?;
        self.compact = None;
        std::fs::create_dir_all(&root)?;
        let directory = tempfile::Builder::new()
            .prefix("active-native-")
            .tempdir_in(&root)?;
        let started = Instant::now();
        let mut state = self.begin(false, false)?;
        state.record_encoding = true;
        state.before_prompt = true;
        self.preparation_mode = true;
        self.expected_preparation_refs = Some(expected.to_vec());
        let result = self.recall(m, t, &mut state, query, "offline_preparation", vec![]);
        self.preparation_mode = false;
        self.expected_preparation_refs = None;
        result?;
        ensure!(!state.memory_ids.is_empty(), "empty offline preparation");
        let identity = prepared_key(&state.binding, &state.encoding_format, true, &state.facts)?;
        let mut banks = HashMap::new();
        for (i, kind) in m.config.layer_types.iter().enumerate() {
            if kind == "full_attention" {
                banks.insert(
                    i,
                    state
                        .bank_for_read(m, i, m.layers[i])?
                        .context("missing preparation layer")?,
                );
            }
        }
        let path = directory.path().join("snapshot");
        crate::compact_memory::publish_native(
            &path,
            &identity,
            "working-set",
            &state.memory_ids,
            &banks,
        )?;
        let mut store = crate::compact_memory::Store::open(&path, &identity)?;
        store.set_threads(1)?;
        store.set_streaming(true)?;
        let mut work = store.device_workspace("working-set", &m.layers)?;
        store.initialize_device_pool(&mut work)?;
        let loaded = store.apply_optimized("working-set", &mut work)?;
        ensure!(
            loaded.banks.len() == banks.len(),
            "offline layer coverage mismatch"
        );
        for (i, b) in &banks {
            ensure!(
                b.keys.equal(&loaded.banks[i].keys) && b.values.equal(&loaded.banks[i].values),
                "offline GPU roundtrip mismatch"
            );
        }
        let report = json!({"offline_model_encoding_passes":state.encodings,"offline_encoder_token_ids":state.memory_ids,
            "selected_facts":state.facts,"all_gpu_tensors_equal":true,"dictionary_bytes":store.dictionary_bytes(),
            "preparation_seconds":started.elapsed().as_secs_f64(),"source_record_encoding":true,
            "representation":"exact-prepared-native-layout","resident_dictionary":true});
        self.compact = Some(CompactSnapshot {
            store,
            work,
            key: "working-set".into(),
            identity,
            tokens: state.memory_ids,
            _directory: directory,
        });
        Ok(report)
    }
    fn recall_compact(&mut self, s: &mut State, next: Vec<Value>, mut event: Value) -> Result<()> {
        ensure!(
            s.record_encoding && s.before_prompt && s.position_shift == 0 && !s.decode_recall,
            "unsupported compact experiment configuration"
        );
        let identity = prepared_key(&s.binding, &s.encoding_format, true, &next)?;
        let snapshot = self
            .compact
            .as_mut()
            .context("explicit offline preparation required")?;
        ensure!(
            identity == snapshot.identity,
            "prepared source revision/content mismatch"
        );
        let applied = snapshot
            .store
            .apply_optimized(&snapshot.key, &mut snapshot.work)?;
        event["rust_native_load"] = json!({"total_ns":applied.total_ns,"read_ns":applied.read_ns,
            "expand_ns":applied.expand_ns,"transfer_ns":applied.transfer_ns,"transfer_operations":applied.transfer_operations});
        event["status"] = json!("bank_updated");
        event["source_record_encoding"] = json!(true);
        event["memory_encoding_tokens"] = json!(snapshot.tokens.len());
        event["bank_memory_ids"] = json!(next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>());
        s.prepared.borrow_mut().clear();
        s.records.clear();
        s.banks = applied.banks;
        s.prepositioned = true;
        s.record_encoding = false;
        s.memory_ids = snapshot.tokens.clone();
        s.facts = next;
        s.events.push(event);
        Ok(())
    }
    pub fn check_generation(&mut self, expected: &str) -> Result<()> {
        let result = self.source.check_generation(expected);
        if result.is_err() {
            self.cache.clear();
            self.generation = None;
        }
        result
    }

    pub fn begin(&mut self, decode_recall: bool, reuse: bool) -> Result<State> {
        let binding = match self.source.begin() {
            Ok(binding) => binding,
            Err(error) => {
                self.cache.clear();
                self.generation = None;
                return Err(error);
            }
        };
        let mut transition = json!({"retained":0,"invalidated":0});
        if self.generation.as_ref() != Some(&binding) {
            let before = self.cache.len();
            let proofs: Vec<Value> = self
                .cache
                .iter()
                .map(|c| c.proof.clone().unwrap_or(json!({})))
                .collect();
            let keep = match self.source.retain_encodings(&proofs) {
                Ok(keep) if keep.len() == proofs.len() => keep,
                _ => {
                    self.cache.clear();
                    self.generation = None;
                    anyhow::bail!("cache retention verification failed")
                }
            };
            let mut entries = VecDeque::new();
            for (mut cached, valid) in self.cache.drain(..).zip(keep) {
                if valid && cached.proof.is_some() {
                    if let Some((_, identity)) = cached.key.split_once(':') {
                        cached.key = format!("{}:{}", binding, identity);
                        entries.push_back(cached);
                    }
                }
            }
            self.cache = entries;
            transition = json!({"retained":self.cache.len(),"invalidated":before-self.cache.len()});
            self.generation = Some(binding.clone());
        }
        Ok(State {
            prepared: RefCell::new(HashMap::new()),
            prepositioned: false,
            bank_preparations: Cell::new(0),
            bank_reuses: Cell::new(0),
            bank_application_cpu_ns: Cell::new(0),
            cache_transition: transition,
            diagnostic_steps: 0,
            position_shift: 0,
            before_prompt: true,
            attention_trace: vec![],
            encoding_format: "content".into(),
            record_encoding: false,
            records: vec![],
            binding,
            sequence: vec![],
            memory_ids: vec![],
            facts: vec![],
            banks: HashMap::new(),
            events: vec![],
            native_reads: 0,
            encodings: 0,
            step: 0,
            decode_recall,
            reuse,
        })
    }
    pub fn recall(
        &mut self,
        m: &Model,
        t: &Tokens,
        s: &mut State,
        query: &str,
        origin: &str,
        spans: Vec<Value>,
    ) -> Result<()> {
        let source_started = Instant::now();
        let reply = match self.source.native_search(query, self.limit) {
            Ok(reply) => reply,
            Err(error) => {
                s.events.push(json!({"origin":origin,"query":query,"limit":self.limit,"step":s.step,"status":"read_failed","addressed_spans":spans}));
                return Err(error);
            }
        };
        ensure!(
            reply
                .get("windows")
                .and_then(Value::as_array)
                .is_none_or(Vec::is_empty),
            "episode codec unsupported"
        );
        ensure!(
            reply.get("active_context_missing") != Some(&Value::Bool(true)),
            "authority context incomplete"
        );
        let facts = reply["facts"].as_array().context("invalid fact response")?;
        let next = crate::knowledge::merge(&s.facts, facts)?;
        if let Some(expected) = &self.expected_preparation_refs {
            let actual: Vec<_> = next.iter().map(|f| f["memory_ref"].clone()).collect();
            ensure!(
                &actual == expected,
                "preparation record coverage mismatch before encoding"
            );
        }
        let mut event = json!({"origin":origin,"query":query,"limit":self.limit,"aimee_response":reply,"addressed_spans":spans,"step":s.step,"phase":if origin=="prompt_preload"{"preload"}else if s.step==0{"prefill"}else{"decode"}});
        if next.is_empty() {
            event["status"] = json!("empty");
            s.events.push(event);
            return Ok(());
        }
        event["source_selection_ns"] = json!(source_started.elapsed().as_nanos());
        if self.compact_root.is_some() && !self.preparation_mode {
            return self.recall_compact(s, next, event);
        }
        if self.prepared_store.is_some() {
            return self.recall_prepared(m, t, s, next, event);
        }
        if s.record_encoding {
            return self.recall_records(m, t, s, next, event);
        }
        let (ids, encoding) = crate::memory_encoding::encode(t, &next, &s.encoding_format)?;
        event["encoding_format"] = json!(s.encoding_format);
        if s.diagnostic_steps > 0 {
            event["encoding"] = encoding;
        }
        ensure!(
            ids.len() <= self.max_tokens,
            "memory exceeds capacity; refusing truncation"
        );
        event["memory_encoding_tokens"] = json!(ids.len());
        event["bank_memory_ids"] = json!(next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>());
        if ids == s.memory_ids {
            event["status"] = json!("bank_unchanged");
            s.facts = next;
            s.events.push(event);
            return Ok(());
        }
        let key = encoding_key(
            &s.binding,
            &ids,
            &next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>(),
            "bank",
            &s.encoding_format,
        )?;
        let encoding_started = Instant::now();
        let banks = if let Some(i) = self.cache.iter().position(|c| s.reuse && c.key == key) {
            let c = self.cache.remove(i).unwrap();
            let banks = copy_banks(&c.banks);
            self.cache.push_back(c);
            event["status"] = json!("bank_reused");
            banks
        } else {
            let banks = m.encode_native(&ids)?;
            s.encodings += 1;
            event["status"] = json!("bank_updated");
            let bytes = banks
                .values()
                .map(|b| (b.keys.numel() + b.values.numel()) * b.keys.kind().elt_size_in_bytes())
                .sum();
            if s.reuse && bytes <= self.cache_budget {
                while self.cache.iter().map(|c| c.bytes).sum::<usize>() + bytes > self.cache_budget
                {
                    self.cache.pop_front();
                }
                self.cache.push_back(Cached {
                    proof: None,
                    key,
                    banks: copy_banks(&banks),
                    bytes,
                });
            }
            banks
        };
        event["encoding_elapsed_ms"] = json!(encoding_started.elapsed().as_secs_f64() * 1000.);
        s.prepared.borrow_mut().clear();
        s.banks = banks;
        s.prepositioned = false;
        s.facts = next;
        s.memory_ids = ids;
        s.events.push(event);
        Ok(())
    }
    /// Strict persistent-state serving: missing prepared entries never invoke
    /// the model encoder. Only the explicit offline preparation mode may encode.
    fn recall_prepared(
        &mut self,
        m: &Model,
        t: &Tokens,
        s: &mut State,
        next: Vec<Value>,
        mut event: Value,
    ) -> Result<()> {
        let started = Instant::now();
        if next == s.facts && !s.memory_ids.is_empty() {
            event["status"] = json!("prepared_unchanged");
            event["bank_memory_ids"] =
                json!(next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>());
            event["memory_encoding_tokens"] = json!(s.memory_ids.len());
            s.events.push(event);
            return Ok(());
        }
        self.prepared_store.as_mut().unwrap().poll_updates();
        let groups: Vec<&[Value]> = if s.record_encoding {
            next.chunks(1).collect()
        } else {
            vec![next.as_slice()]
        };
        let eligible_positioned = !self.preparation_mode && s.before_prompt && groups.len() == 1;
        let mut prepositioned = false;
        let mut plan = Vec::with_capacity(groups.len());
        let mut total_tokens = 0;
        // Preflight every entry and the entire token budget before loading any
        // banks. This cannot degrade a three-record selection into one record.
        for group in groups {
            let base_key = prepared_key(&s.binding, &s.encoding_format, s.record_encoding, group)?;
            let positioned_key = positioned_key(&base_key);
            if eligible_positioned
                && self
                    .prepared_store
                    .as_ref()
                    .unwrap()
                    .entry(&positioned_key)
                    .is_none()
            {
                self.prepared_store.as_mut().unwrap().poll_updates();
            }
            let key = if eligible_positioned
                && self
                    .prepared_store
                    .as_ref()
                    .unwrap()
                    .entry(&positioned_key)
                    .is_some()
            {
                prepositioned = true;
                positioned_key
            } else {
                base_key
            };
            if !self.preparation_mode && self.prepared_store.as_ref().unwrap().entry(&key).is_none()
            {
                self.prepared_store.as_mut().unwrap().poll_updates();
            }
            let ids = if let Some(entry) = self.prepared_store.as_ref().unwrap().entry(&key) {
                entry.tokens.clone()
            } else {
                ensure!(
                    self.preparation_mode,
                    "prepared memory miss; offline preparation required"
                );
                crate::memory_encoding::encode(t, group, &s.encoding_format)?.0
            };
            total_tokens += ids.len();
            ensure!(
                total_tokens <= self.max_tokens,
                "prepared memory exceeds capacity; refusing truncation"
            );
            plan.push((key, ids));
        }
        let index_ns = started.elapsed().as_nanos();
        let mut records = vec![];
        let mut all_ids = vec![];
        let mut disk_reads = 0;
        let mut read_ns = 0;
        let mut conversion_ns = 0;
        let mut file_setup_ns = 0;
        let mut file_opens = 0;
        let mut transfer_ns = 0;
        let mut transfer_operations = 0;
        let mut host_hits = 0;
        self.prepared_store
            .as_mut()
            .unwrap()
            .set_host_cache_budget(if s.reuse { self.cache_budget } else { 0 });
        let mut read_bytes = 0;
        let mut cache_hits = 0;
        for (key, ids) in plan {
            let banks = if let Some(banks) = self.cached(&key, s.reuse) {
                cache_hits += 1;
                banks
            } else if let Some(loaded) = self
                .prepared_store
                .as_ref()
                .unwrap()
                .load_to_devices(&key, &m.layers)?
            {
                ensure!(loaded.tokens == ids, "prepared token identity changed");
                disk_reads += usize::from(!loaded.host_hit);
                read_ns += loaded.read_ns;
                file_setup_ns += loaded.file_setup_ns;
                file_opens += usize::from(loaded.file_opened);
                conversion_ns += loaded.conversion_ns;
                if !loaded.host_hit {
                    read_bytes += loaded.bytes;
                }
                transfer_ns += loaded.transfer_ns;
                host_hits += usize::from(loaded.host_hit);
                transfer_operations += loaded.transfer_operations;
                if loaded.transfer_operations == 0 {
                    self.remember(key.clone(), &loaded.banks, s.reuse);
                }
                loaded.banks
            } else {
                ensure!(
                    self.preparation_mode,
                    "prepared memory missing; encoding forbidden in serving"
                );
                let banks = m.encode_native(&ids)?;
                self.prepared_store
                    .as_mut()
                    .unwrap()
                    .put(&key, &ids, &banks)?;
                s.encodings += 1;
                banks
            };
            if self.preparation_mode {
                let ready_key = positioned_key(&key);
                if self
                    .prepared_store
                    .as_ref()
                    .unwrap()
                    .entry(&ready_key)
                    .is_none()
                {
                    let positioned = banks
                        .iter()
                        .map(|(&i, b)| {
                            (
                                i,
                                Bank {
                                    keys: m.shift_memory_keys(&b.keys, -(ids.len() as i64)),
                                    values: b.values.shallow_clone(),
                                },
                            )
                        })
                        .collect();
                    self.prepared_store
                        .as_mut()
                        .unwrap()
                        .put(&ready_key, &ids, &positioned)?;
                }
            }
            let expected: Vec<_> = m
                .config
                .layer_types
                .iter()
                .enumerate()
                .filter(|(_, kind)| kind.as_str() == "full_attention")
                .map(|(i, _)| i)
                .collect();
            ensure!(
                banks.len() == expected.len()
                    && expected.iter().all(|i| banks
                        .get(i)
                        .is_some_and(|b| b.keys.size()[2] == ids.len() as i64
                            && b.values.size()[2] == ids.len() as i64)),
                "incomplete prepared native layers"
            );
            all_ids.extend_from_slice(&ids);
            records.push(RecordBank {
                key,
                tokens: ids.len(),
                banks,
            });
        }
        ensure!(
            records.len() == if s.record_encoding { next.len() } else { 1 },
            "prepared record coverage mismatch"
        );
        s.prepared.borrow_mut().clear();
        if s.record_encoding {
            s.records = records;
            s.banks.clear();
        } else {
            s.banks = records.pop().unwrap().banks;
            s.records.clear();
        }
        s.memory_ids = all_ids;
        s.prepositioned = prepositioned;
        event["prepared_positioned_offline"] = json!(prepositioned);
        event["bank_memory_ids"] = json!(next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>());
        event["memory_encoding_tokens"] = json!(s.memory_ids.len());
        event["encoding_granularity"] = json!(if s.record_encoding { "record" } else { "bank" });
        event["status"] = json!(if self.preparation_mode {
            "offline_prepared"
        } else {
            "prepared_loaded"
        });
        event["prepared_index_ns"] = json!(index_ns);
        event["prepared_disk_reads"] = json!(disk_reads);
        event["prepared_read_bytes"] = json!(read_bytes);
        event["prepared_read_ns"] = json!(read_ns);
        event["prepared_file_setup_ns"] = json!(file_setup_ns);
        event["prepared_file_opens"] = json!(file_opens);
        event["prepared_cpu_conversion_ns"] = json!(conversion_ns);
        event["prepared_ram_hits"] = json!(cache_hits + host_hits);
        event["prepared_transfer_ns"] = json!(transfer_ns);
        event["prepared_transfer_operations"] = json!(transfer_operations);
        event["prepared_load_total_ns"] = json!(started.elapsed().as_nanos());
        s.facts = next;
        s.events.push(event);
        Ok(())
    }

    /// Independently encoded records are experimental: their frozen-model
    /// encoder context differs from the complete-bank baseline. Selection and
    /// canonical revisions are still supplied exclusively by the memory source.
    fn recall_records(
        &mut self,
        m: &Model,
        t: &Tokens,
        s: &mut State,
        next: Vec<Value>,
        mut event: Value,
    ) -> Result<()> {
        let mut plan = Vec::new();
        let mut all_ids = Vec::new();
        for fact in &next {
            let (ids, diagnostic) =
                crate::memory_encoding::encode(t, std::slice::from_ref(fact), &s.encoding_format)?;
            let key = encoding_key(
                &s.binding,
                &ids,
                &[&fact["memory_ref"]],
                "record",
                &s.encoding_format,
            )?;
            all_ids.extend_from_slice(&ids);
            let proof = if fact["memory_hash"].as_str().is_some_and(|h| h.len() == 64) {
                Some(json!({"memory_ref":fact["memory_ref"],"memory_hash":fact["memory_hash"]}))
            } else {
                None
            };
            plan.push((key, ids, diagnostic, proof));
        }
        // Validate the entire bank before any encoder work or cache mutation.
        ensure!(
            all_ids.len() <= self.max_tokens,
            "memory exceeds capacity; refusing truncation"
        );
        event["encoding_format"] = json!(s.encoding_format);
        event["encoding_granularity"] = json!("record");
        event["memory_encoding_tokens"] = json!(all_ids.len());
        event["bank_memory_ids"] = json!(next.iter().map(|f| &f["memory_ref"]).collect::<Vec<_>>());
        if s.diagnostic_steps > 0 {
            event["record_encodings"] = json!(plan.iter().map(|p| &p.2).collect::<Vec<_>>());
        }
        let started = Instant::now();
        let mut current_hits = 0;
        let mut cache_hits = 0;
        let mut encoded = 0;
        let mut encoded_tokens = 0;
        let mut records = Vec::new();
        for (key, ids, _, proof) in plan {
            let banks = if let Some(record) = s.records.iter().find(|r| r.key == key) {
                current_hits += 1;
                copy_banks(&record.banks)
            } else if let Some(banks) = self.cached(&key, s.reuse) {
                cache_hits += 1;
                banks
            } else {
                let banks = m.encode_native(&ids)?;
                s.encodings += 1;
                encoded += 1;
                encoded_tokens += ids.len();
                self.remember(key.clone(), &banks, s.reuse);
                if let Some(cached) = self.cache.iter_mut().find(|c| c.key == key) {
                    cached.proof = proof;
                }
                banks
            };
            records.push(RecordBank {
                key,
                tokens: ids.len(),
                banks,
            });
        }
        event["encoding_elapsed_ms"] = json!(started.elapsed().as_secs_f64() * 1000.);
        event["record_working_set_hits"] = json!(current_hits);
        event["record_cache_hits"] = json!(cache_hits);
        event["records_encoded"] = json!(encoded);
        event["tokens_encoded"] = json!(encoded_tokens);
        event["status"] = json!(if encoded > 0 {
            "bank_updated"
        } else if cache_hits > 0 {
            "bank_reused"
        } else {
            "bank_unchanged"
        });
        s.prepared.borrow_mut().clear();
        s.records = records;
        s.prepositioned = false;
        s.facts = next;
        s.memory_ids = all_ids;
        s.events.push(event);
        Ok(())
    }

    fn cached(&mut self, key: &str, reuse: bool) -> Option<HashMap<usize, Bank>> {
        let index = self.cache.iter().position(|c| reuse && c.key == key)?;
        let cached = self.cache.remove(index).unwrap();
        let banks = copy_banks(&cached.banks);
        self.cache.push_back(cached);
        Some(banks)
    }

    fn remember(&mut self, key: String, banks: &HashMap<usize, Bank>, reuse: bool) {
        let bytes: usize = banks
            .values()
            .map(|b| {
                b.keys.numel() * b.keys.kind().elt_size_in_bytes()
                    + b.values.numel() * b.values.kind().elt_size_in_bytes()
            })
            .sum();
        if !reuse || bytes > self.cache_budget {
            return;
        }
        self.cache.retain(|c| c.key != key);
        while self.cache.iter().map(|c| c.bytes).sum::<usize>() + bytes > self.cache_budget {
            self.cache.pop_front();
        }
        self.cache.push_back(Cached {
            proof: None,
            key,
            banks: copy_banks(banks),
            bytes,
        });
    }

    pub fn forward(
        &mut self,
        m: &Model,
        t: &Tokens,
        ids: &[u32],
        cache: &mut Cache,
        s: &mut State,
    ) -> Result<Tensor> {
        if let Err(e) = self.check_generation(&s.binding) {
            s.prepared.borrow_mut().clear();
            s.banks.clear();
            s.records.clear();
            s.memory_ids.clear();
            s.facts.clear();
            return Err(e);
        }
        s.sequence.extend_from_slice(ids);
        let request_layer = m
            .config
            .layer_types
            .iter()
            .position(|x| x == "full_attention")
            .context("no full attention layer")?;
        let result = m.forward(
            ids,
            cache,
            Some(&mut |model, index, q, k, _v, mask| {
                if index == request_layer && (s.step == 0 || s.decode_recall) {
                    let groups =
                        model.config.num_attention_heads / model.config.num_key_value_heads;
                    let scale = (model.config.head_dim as f64).powf(-0.5);
                    let mut sources = vec![("sequence", s.sequence.as_slice())];
                    let score = if let Some(bank) = s.bank_for_read(model, index, k.device())? {
                        let mk = bank.keys;
                        let zeros = Tensor::zeros(
                            [1, 1, mask.size()[2], mk.size()[2]],
                            (mask.kind(), mask.device()),
                        );
                        sources.insert(0, ("aimee", s.memory_ids.as_slice()));
                        scores(
                            q,
                            &Tensor::cat(&[mk, k.shallow_clone()], -2),
                            &Tensor::cat(&[zeros, mask.shallow_clone()], -1),
                            groups,
                            scale,
                        )?
                    } else {
                        scores(q, k, mask, groups, scale)?
                    };
                    let (query, spans) = t.addressed(&sources, &score, 12)?;
                    if !query.is_empty() {
                        self.recall(model, t, s, &query, "qwen_attention_query", spans)?;
                    }
                }
                let offset = s.bank_position_offset();
                // Recall above may have replaced the bank. Recompute placement
                // from the current bank, using the same rule as native addressing.
                let bank = s.bank_for_read(model, index, k.device())?;
                if s.step < s.diagnostic_steps {
                    if let Some(b) = &bank {
                        let groups = model.config.num_attention_heads / model.config.num_key_value_heads;
                        let weights = crate::model::native_attention_weights(q,k,&b.keys,mask,groups,(model.config.head_dim as f64).powf(-0.5))?;
                        s.attention_trace.push(json!({"step":s.step,"layer":index,"position_shift":offset,"memory_tokens":s.memory_ids.len(),"weights":weights}));
                    }
                }
                if bank.is_some() {
                    s.native_reads += 1;
                }
                Ok(bank)
            }),
        );
        if result.is_err() {
            s.prepared.borrow_mut().clear();
            s.banks.clear();
            s.records.clear();
            s.memory_ids.clear();
            s.facts.clear();
        }
        s.step += 1;
        result
    }
}
fn copy_banks(b: &HashMap<usize, Bank>) -> HashMap<usize, Bank> {
    b.iter().map(|(i, b)| (*i, b.copy())).collect()
}
pub fn tensor_values(t: &Tensor) -> Result<Vec<f32>> {
    Ok(Vec::<f32>::try_from(
        t.to_kind(tch::Kind::Float)
            .to_device(Device::Cpu)
            .reshape([-1]),
    )?)
}

// A separate artifact permits exact offline positioning without rounding twice.
// Multi-record combinations retain canonical keys and receive their actual offsets.
fn positioned_key(base: &str) -> String {
    let mut h = Sha256::new();
    h.update(b"native-before-prompt-v1:");
    h.update(base.as_bytes());
    format!("{:x}", h.finalize())
}
