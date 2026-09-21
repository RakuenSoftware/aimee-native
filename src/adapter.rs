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
use std::collections::{HashMap, VecDeque};
use std::time::Instant;
use tch::{Device, Tensor};

pub struct State {
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
    fn bank_for_read(&self, model: &Model, index: usize, device: Device) -> Result<Option<Bank>> {
        if self.record_encoding {
            if self.records.is_empty() {
                return Ok(None);
            }
            let mut start = self.bank_position_offset();
            let mut count = 0;
            let mut keys = Vec::new();
            let mut values = Vec::new();
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
                // Each cached record starts at its own encoder position zero.
                // Translate once into its disjoint slice of the virtual prefix.
                keys.push(model.shift_memory_keys(&bank.keys.to_device(device), start));
                values.push(bank.values.shallow_clone());
                start += record.tokens as i64;
                count += record.tokens;
            }
            ensure!(
                count == self.memory_ids.len(),
                "native bank/token address length differs"
            );
            return Ok(Some(Bank {
                keys: Tensor::cat(&keys, 2),
                values: Tensor::cat(&values, 2),
            }));
        }
        let Some(bank) = self.banks.get(&index) else {
            return Ok(None);
        };
        let count = self.memory_ids.len() as i64;
        ensure!(
            bank.keys.size()[2] == count && bank.values.size()[2] == count,
            "native bank/token address length differs"
        );
        let offset = self.bank_position_offset();
        Ok(Some(Bank {
            keys: model.shift_memory_keys(&bank.keys.to_device(device), offset),
            values: bank.values.shallow_clone(),
        }))
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
pub struct Adapter {
    pub source: Box<dyn MemorySource>,
    pub limit: usize,
    pub max_tokens: usize,
    pub cache_budget: usize,
    cache: VecDeque<Cached>,
    generation: Option<String>,
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
        }
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
        let mut event = json!({"origin":origin,"query":query,"limit":self.limit,"aimee_response":reply,"addressed_spans":spans,"step":s.step,"phase":if origin=="prompt_preload"{"preload"}else if s.step==0{"prefill"}else{"decode"}});
        if next.is_empty() {
            event["status"] = json!("empty");
            s.events.push(event);
            return Ok(());
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
            let banks = m.encode(&ids)?;
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
        s.banks = banks;
        s.facts = next;
        s.memory_ids = ids;
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
                let banks = m.encode(&ids)?;
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
        s.records = records;
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
