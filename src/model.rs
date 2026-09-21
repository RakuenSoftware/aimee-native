// Portions adapted from Transformers Qwen3.5, Apache-2.0.
// Copyright 2025 The Qwen Team and The HuggingFace Inc. team.
// See THIRD_PARTY_NOTICES.md and licenses/Apache-2.0.txt.
//! Frozen Qwen3.5/3.8 text forward pass using native libtorch kernels.
//! No Python runtime, model training, or memory text in the sequence cache.
//! Math follows the installed Transformers Qwen3.5 reference (Apache-2.0).
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::Value;
use std::{
    collections::{BTreeSet, HashMap},
    path::Path,
};
use tch::{Device, IndexOp, Kind, Tensor};

#[derive(Clone, Deserialize, Debug)]
pub struct Config {
    pub hidden_size: i64,
    pub num_hidden_layers: usize,
    pub num_attention_heads: i64,
    pub num_key_value_heads: i64,
    pub head_dim: i64,
    pub rms_norm_eps: f64,
    pub linear_num_key_heads: i64,
    pub linear_num_value_heads: i64,
    pub linear_key_head_dim: i64,
    pub linear_value_head_dim: i64,
    pub linear_conv_kernel_dim: i64,
    pub layer_types: Vec<String>,
    pub rope_parameters: Value,
}
#[derive(Deserialize)]
pub struct Placement {
    pub embedding: String,
    pub head: String,
    pub layers: Vec<String>,
}
pub fn device(s: &str) -> Result<Device> {
    if s == "cpu" {
        Ok(Device::Cpu)
    } else {
        Ok(Device::Cuda(
            s.strip_prefix("cuda:").context("invalid device")?.parse()?,
        ))
    }
}
// Match the reference's explicit host staging between different accelerators.
pub fn transfer(x: &Tensor, d: Device) -> Tensor {
    if x.device() != d && x.device() != Device::Cpu && d != Device::Cpu {
        x.to_device(Device::Cpu).to_device(d)
    } else {
        x.to_device(d)
    }
}
pub struct Bank {
    pub keys: Tensor,
    pub values: Tensor,
}
impl Bank {
    pub fn copy(&self) -> Self {
        Self {
            keys: self.keys.shallow_clone(),
            values: self.values.shallow_clone(),
        }
    }
}
#[derive(Default)]
pub struct LayerCache {
    pub kv: Option<Bank>,
    pub conv: Option<Tensor>,
    pub recurrent: Option<Tensor>,
}
pub struct Cache {
    pub layers: Vec<LayerCache>,
    pub length: i64,
}
impl Cache {
    pub fn new(n: usize) -> Self {
        Self {
            layers: (0..n).map(|_| LayerCache::default()).collect(),
            length: 0,
        }
    }
}
pub struct Model {
    pub config: Config,
    weights: HashMap<String, Tensor>,
    scales: HashMap<String, Tensor>,
    pub layers: Vec<Device>,
    pub embedding: Device,
    pub head: Device,
    pub kind: Kind,
}
pub type MemoryRead<'a> =
    dyn FnMut(&Model, usize, &Tensor, &Tensor, &Tensor, &Tensor) -> Result<Option<Bank>> + 'a;

impl Model {
    pub fn load(root: &Path, placement: Option<&Path>, int8: bool) -> Result<Self> {
        let cfg: Value = serde_json::from_slice(&std::fs::read(root.join("config.json"))?)?;
        let raw = cfg.get("text_config").unwrap_or(&cfg);
        ensure!(
            raw["model_type"] == "qwen3_5_text",
            "unsupported text architecture"
        );
        ensure!(
            raw.get("attention_bias") != Some(&Value::Bool(true)),
            "attention bias unsupported"
        );
        ensure!(
            raw["rope_parameters"]["rope_type"] == "default",
            "only default text RoPE supported"
        );
        let config: Config = serde_json::from_value(raw.clone())?;
        ensure!(
            config.layer_types.len() == config.num_hidden_layers,
            "invalid layer count"
        );
        ensure!(
            config.num_attention_heads % config.num_key_value_heads == 0
                && config.linear_num_value_heads % config.linear_num_key_heads == 0,
            "invalid grouped heads"
        );
        let p = if let Some(path) = placement {
            serde_json::from_slice(&std::fs::read(path)?)?
        } else {
            Placement {
                embedding: "cpu".into(),
                head: "cpu".into(),
                layers: vec!["cpu".into(); config.num_hidden_layers],
            }
        };
        ensure!(
            p.layers.len() == config.num_hidden_layers,
            "placement length differs"
        );
        let mut m = Self {
            config,
            weights: HashMap::new(),
            scales: HashMap::new(),
            layers: p.layers.iter().map(|s| device(s)).collect::<Result<_>>()?,
            embedding: device(&p.embedding)?,
            head: device(&p.head)?,
            kind: Kind::Float,
        };
        let files: BTreeSet<String> = if root.join("model.safetensors.index.json").exists() {
            let index: Value =
                serde_json::from_slice(&std::fs::read(root.join("model.safetensors.index.json"))?)?;
            index["weight_map"]
                .as_object()
                .context("weight index")?
                .values()
                .map(|v| v.as_str().unwrap().to_string())
                .collect()
        } else {
            ["model.safetensors".into()].into_iter().collect()
        };
        for file in files {
            eprintln!("loading {file}");
            for (name, original) in Tensor::read_safetensors(root.join(file))? {
                let name = name.replace("model.language_model.", "model.");
                if !(name.starts_with("model.layers.")
                    || name == "model.embed_tokens.weight"
                    || name == "model.norm.weight"
                    || name == "lm_head.weight")
                {
                    continue;
                }
                let d = if let Some(rest) = name.strip_prefix("model.layers.") {
                    m.layers[rest.split('.').next().unwrap().parse::<usize>()?]
                } else if name == "model.embed_tokens.weight" {
                    m.embedding
                } else {
                    m.head
                };
                if name == "model.embed_tokens.weight" {
                    m.kind = original.kind();
                }
                if int8 && original.dim() == 2 && name != "model.embed_tokens.weight" {
                    let shape = original.size();
                    let q = Tensor::empty(&shape, (Kind::Int8, Device::Cpu));
                    let scale = Tensor::empty([shape[0], 1], (Kind::Float, Device::Cpu));
                    for start in (0..shape[0]).step_by(512) {
                        let n = (shape[0] - start).min(512);
                        let w = original.narrow(0, start, n).to_kind(Kind::Float);
                        let s = w.abs().amax([1], true).clamp_min(1e-12) / 127.;
                        q.narrow(0, start, n)
                            .copy_(&(&w / &s).round().clamp(-127., 127.).to_kind(Kind::Int8));
                        scale.narrow(0, start, n).copy_(&s);
                    }
                    m.weights.insert(name.clone(), q.to_device(d));
                    m.scales.insert(name, scale.to_device(d));
                } else {
                    m.weights.insert(name, original.to_device(d));
                }
            }
        }
        ensure!(
            m.weights.contains_key("lm_head.weight"),
            "untied LM head required"
        );
        Ok(m)
    }
    fn w(&self, n: &str) -> &Tensor {
        self.weights
            .get(n)
            .unwrap_or_else(|| panic!("missing model tensor {n}"))
    }
    fn linear(&self, x: &Tensor, name: &str) -> Tensor {
        let name = format!("{name}.weight");
        let w = self.w(&name);
        let weight = if let Some(s) = self.scales.get(&name) {
            w.to_kind(x.kind()) * s.to_kind(x.kind())
        } else {
            w.shallow_clone()
        };
        x.matmul(&weight.transpose(-1, -2))
    }
    fn norm(&self, x: &Tensor, name: &str) -> Tensor {
        let f = x.to_kind(Kind::Float);
        ((&f * ((&f * &f).mean_dim([-1].as_slice(), true, Kind::Float) + self.config.rms_norm_eps)
            .rsqrt())
            * (self.w(&format!("{name}.weight")).to_kind(Kind::Float) + 1.))
            .to_kind(x.kind())
    }
    fn mlp(&self, x: &Tensor, p: &str) -> Tensor {
        self.linear(
            &(self.linear(x, &format!("{p}.gate_proj")).silu()
                * self.linear(x, &format!("{p}.up_proj"))),
            &format!("{p}.down_proj"),
        )
    }
    fn rope(&self, x: &Tensor, start: i64) -> Tensor {
        let c = &self.config;
        let n = (c.head_dim as f64
            * c.rope_parameters
                .get("partial_rotary_factor")
                .and_then(Value::as_f64)
                .unwrap_or(1.)) as i64;
        let inv = Tensor::pow_scalar(
            c.rope_parameters["rope_theta"].as_f64().unwrap(),
            &(Tensor::arange_start_step(0, n, 2, (Kind::Float, x.device())) / (n as f64)),
        )
        .reciprocal();
        let pos = Tensor::arange_start(start, start + x.size()[2], (Kind::Float, x.device()));
        let f = pos.unsqueeze(-1) * inv.unsqueeze(0);
        let f = Tensor::cat(&[&f, &f], -1).unsqueeze(0).unsqueeze(0);
        let rot = x.narrow(-1, 0, n);
        let half = Tensor::cat(
            &[&(-rot.narrow(-1, n / 2, n / 2)), &rot.narrow(-1, 0, n / 2)],
            -1,
        );
        Tensor::cat(
            &[
                &(rot * f.cos().to_kind(x.kind()) + half * f.sin().to_kind(x.kind())),
                &x.narrow(-1, n, c.head_dim - n),
            ],
            -1,
        )
    }
    /// Rotary address translation for independently encoded memory. Source tokens stay
    /// unchanged. Zero is an exact no-op; nonzero shifts incur BF16 rounding.
    pub fn shift_memory_keys(&self, keys: &Tensor, offset: i64) -> Tensor {
        if offset == 0 {
            return keys.shallow_clone();
        }
        let c = &self.config;
        let n = (c.head_dim as f64
            * c.rope_parameters
                .get("partial_rotary_factor")
                .and_then(Value::as_f64)
                .unwrap_or(1.)) as i64;
        let inv = Tensor::pow_scalar(
            c.rope_parameters["rope_theta"].as_f64().unwrap(),
            &(Tensor::arange_start_step(0, n, 2, (Kind::Float, keys.device())) / (n as f64)),
        )
        .reciprocal();
        let f = &inv * (offset as f64);
        let f = Tensor::cat(&[&f, &f], -1).reshape([1, 1, 1, n]);
        let rot = keys.narrow(-1, 0, n).to_kind(Kind::Float);
        let half = Tensor::cat(
            &[&(-rot.narrow(-1, n / 2, n / 2)), &rot.narrow(-1, 0, n / 2)],
            -1,
        );
        Tensor::cat(
            &[
                &(rot * f.cos() + half * f.sin()).to_kind(keys.kind()),
                &keys.narrow(-1, n, c.head_dim - n),
            ],
            -1,
        )
    }
    pub fn forward(
        &self,
        ids: &[u32],
        cache: &mut Cache,
        mut memory: Option<&mut MemoryRead<'_>>,
    ) -> Result<Tensor> {
        ensure!(!ids.is_empty(), "empty forward");
        let c = &self.config;
        let n = ids.len() as i64;
        let start = cache.length;
        let tokens = Tensor::from_slice(&ids.iter().map(|i| *i as i64).collect::<Vec<_>>())
            .to_device(self.embedding);
        let mut hidden = self
            .w("model.embed_tokens.weight")
            .index_select(0, &tokens)
            .unsqueeze(0);
        for index in 0..c.num_hidden_layers {
            hidden = transfer(&hidden, self.layers[index]);
            let prefix = format!("model.layers.{index}");
            let x = self.norm(&hidden, &format!("{prefix}.input_layernorm"));
            let layer = &mut cache.layers[index];
            let mix = match c.layer_types[index].as_str() {
                "linear_attention" => self.delta(&x, &format!("{prefix}.linear_attn"), layer),
                "full_attention" => {
                    let p = format!("{prefix}.self_attn");
                    let qg = self.linear(&x, &format!("{p}.q_proj")).view([
                        1,
                        n,
                        c.num_attention_heads,
                        c.head_dim * 2,
                    ]);
                    let gate = qg.narrow(-1, c.head_dim, c.head_dim).reshape([1, n, -1]);
                    let q = self.rope(
                        &self
                            .norm(&qg.narrow(-1, 0, c.head_dim), &format!("{p}.q_norm"))
                            .transpose(1, 2),
                        start,
                    );
                    let k = self.rope(
                        &self
                            .norm(
                                &self.linear(&x, &format!("{p}.k_proj")).view([
                                    1,
                                    n,
                                    c.num_key_value_heads,
                                    c.head_dim,
                                ]),
                                &format!("{p}.k_norm"),
                            )
                            .transpose(1, 2),
                        start,
                    );
                    let v = self
                        .linear(&x, &format!("{p}.v_proj"))
                        .view([1, n, c.num_key_value_heads, c.head_dim])
                        .transpose(1, 2);
                    let (k, v) = if let Some(old) = &layer.kv {
                        (
                            Tensor::cat(&[&old.keys, &k], -2),
                            Tensor::cat(&[&old.values, &v], -2),
                        )
                    } else {
                        (k, v)
                    };
                    layer.kv = Some(Bank {
                        keys: k.shallow_clone(),
                        values: v.shallow_clone(),
                    });
                    let mask =
                        Tensor::ones([n, start + n], (Kind::Bool, x.device())).triu(start + 1);
                    let mask = Tensor::zeros([1, 1, n, start + n], (x.kind(), x.device()))
                        .masked_fill(&mask, f64::NEG_INFINITY);
                    let bank = if let Some(ref mut read) = memory {
                        read(self, index, &q, &k, &v, &mask)?
                    } else {
                        None
                    };
                    let (k, v, mask) = if let Some(bank) = bank {
                        let mk = bank.keys.to_device(x.device());
                        let mv = bank.values.to_device(x.device());
                        let zeros = Tensor::zeros([1, 1, n, mk.size()[2]], (x.kind(), x.device()));
                        (
                            Tensor::cat(&[mk, k], -2),
                            Tensor::cat(&[mv, v], -2),
                            Tensor::cat(&[zeros, mask], -1),
                        )
                    } else {
                        (k, v, mask)
                    };
                    let output = attention(
                        &q,
                        &k,
                        &v,
                        &mask,
                        c.num_attention_heads / c.num_key_value_heads,
                        (c.head_dim as f64).powf(-0.5),
                    )
                    .transpose(1, 2)
                    .contiguous()
                    .view([1, n, -1])
                        * gate.sigmoid();
                    self.linear(&output, &format!("{p}.o_proj"))
                }
                _ => anyhow::bail!("unsupported layer type"),
            };
            hidden += mix;
            let norm = self.norm(&hidden, &format!("{prefix}.post_attention_layernorm"));
            hidden += self.mlp(&norm, &format!("{prefix}.mlp"));
        }
        cache.length += n;
        hidden = transfer(&hidden, self.head);
        Ok(self.linear(&self.norm(&hidden, "model.norm"), "lm_head"))
    }
    pub fn encode(&self, ids: &[u32]) -> Result<HashMap<usize, Bank>> {
        let mut cache = Cache::new(self.config.num_hidden_layers);
        let _ = self.forward(ids, &mut cache, None)?;
        Ok(cache
            .layers
            .into_iter()
            .enumerate()
            .filter_map(|(i, l)| {
                l.kv.map(|b| {
                    (
                        i,
                        Bank {
                            keys: b.keys.to_device(Device::Cpu),
                            values: b.values.to_device(Device::Cpu),
                        },
                    )
                })
            })
            .collect())
    }
    fn delta(&self, x: &Tensor, p: &str, cache: &mut LayerCache) -> Tensor {
        let c = &self.config;
        let n = x.size()[1];
        let kd = c.linear_num_key_heads * c.linear_key_head_dim;
        let vd = c.linear_num_value_heads * c.linear_value_head_dim;
        let mixed = self.linear(x, &format!("{p}.in_proj_qkv")).transpose(1, 2);
        let z = self.linear(x, &format!("{p}.in_proj_z")).view([
            1,
            n,
            c.linear_num_value_heads,
            c.linear_value_head_dim,
        ]);
        let beta = self.linear(x, &format!("{p}.in_proj_b")).sigmoid();
        let a = self.linear(x, &format!("{p}.in_proj_a"));
        let g = -(self.w(&format!("{p}.A_log")).to_kind(Kind::Float).exp())
            * (a.to_kind(Kind::Float) + self.w(&format!("{p}.dt_bias"))).softplus();
        let k = c.linear_conv_kernel_dim;
        let mixed = if let Some(old) = &cache.conv {
            Tensor::cat(&[old, &mixed], -1)
        } else {
            mixed.constant_pad_nd([k - 1, 0])
        };
        // The reference cache stores k samples; the next valid convolution
        // drops its oldest output and keeps exactly the new sequence length.
        let conv_len = mixed.size()[2];
        cache.conv = Some(
            mixed
                .narrow(2, (conv_len - k).max(0), conv_len.min(k))
                .constant_pad_nd([(k - conv_len).max(0), 0]),
        );
        let weight = self.w(&format!("{p}.conv1d.weight"));
        let out = mixed
            .conv1d(weight, None::<&Tensor>, [1], [0], [1], kd * 2 + vd)
            .silu();
        let out = out.narrow(2, out.size()[2] - n, n).transpose(1, 2);
        let groups = c.linear_num_value_heads / c.linear_num_key_heads;
        let q = out
            .narrow(-1, 0, kd)
            .view([1, n, c.linear_num_key_heads, c.linear_key_head_dim])
            .repeat_interleave_self_int(groups, 2, None);
        let key = out
            .narrow(-1, kd, kd)
            .view([1, n, c.linear_num_key_heads, c.linear_key_head_dim])
            .repeat_interleave_self_int(groups, 2, None);
        let v = out.narrow(-1, kd * 2, vd).view([
            1,
            n,
            c.linear_num_value_heads,
            c.linear_value_head_dim,
        ]);
        let (out, state) = delta_rule(&q, &key, &v, &g, &beta, cache.recurrent.as_ref());
        cache.recurrent = Some(state);
        let f = out.to_kind(Kind::Float);
        let norm = (&f
            * ((&f * &f).mean_dim([-1].as_slice(), true, Kind::Float) + c.rms_norm_eps).rsqrt())
        .to_kind(x.kind())
            * self.w(&format!("{p}.norm.weight"));
        let out = (norm * z.to_kind(Kind::Float).silu())
            .to_kind(x.kind())
            .reshape([1, n, vd]);
        self.linear(&out, &format!("{p}.out_proj"))
    }
}
pub fn repeat(x: &Tensor, g: i64) -> Tensor {
    x.repeat_interleave_self_int(g, 1, None)
}
pub fn attention(
    q: &Tensor,
    k: &Tensor,
    v: &Tensor,
    mask: &Tensor,
    groups: i64,
    scale: f64,
) -> Tensor {
    ((q.matmul(&repeat(k, groups).transpose(-1, -2)) * scale) + mask)
        .softmax(-1, Kind::Float)
        .to_kind(q.kind())
        .matmul(&repeat(v, groups))
}
pub fn scores(q: &Tensor, k: &Tensor, mask: &Tensor, groups: i64, scale: f64) -> Result<Vec<f32>> {
    let last = q.narrow(2, q.size()[2] - 1, 1).to_kind(Kind::Float);
    let mask = mask.narrow(2, mask.size()[2] - 1, 1).to_kind(Kind::Float);
    let s = (last.matmul(&repeat(k, groups).to_kind(Kind::Float).transpose(-1, -2)) * scale + mask)
        .softmax(-1, Kind::Float)
        .mean_dim([1].as_slice(), false, Kind::Float)
        .view([-1])
        .to_device(Device::Cpu);
    Ok(Vec::<f32>::try_from(s)?)
}
fn normalize(x: &Tensor) -> Tensor {
    x * ((x * x).sum_dim_intlist([-1].as_slice(), true, Kind::Float) + 1e-6).rsqrt()
}
fn delta_rule(
    q: &Tensor,
    k: &Tensor,
    v: &Tensor,
    g: &Tensor,
    beta: &Tensor,
    initial: Option<&Tensor>,
) -> (Tensor, Tensor) {
    let dtype = q.kind();
    let seq = q.size()[1];
    let heads = v.size()[2];
    let kd = q.size()[3];
    let vd = v.size()[3];
    let d = q.device();
    let q = normalize(&q.transpose(1, 2).to_kind(Kind::Float));
    let k = normalize(&k.transpose(1, 2).to_kind(Kind::Float));
    let v = v.transpose(1, 2).to_kind(Kind::Float);
    let beta = beta.transpose(1, 2).to_kind(Kind::Float);
    let g = g.transpose(1, 2).to_kind(Kind::Float);
    let mut state = initial
        .map(Tensor::shallow_clone)
        .unwrap_or_else(|| Tensor::zeros([1, heads, kd, vd], (Kind::Float, d)));
    if seq == 1 && initial.is_some() {
        let q = q / (kd as f64).sqrt();
        let kt = k.i((.., .., 0));
        let qt = q.i((.., .., 0));
        let vt = v.i((.., .., 0));
        state *= g.i((.., .., 0)).exp().unsqueeze(-1).unsqueeze(-1);
        let predicted =
            (&state * kt.unsqueeze(-1)).sum_dim_intlist([-2].as_slice(), false, Kind::Float);
        let delta = (vt - predicted) * beta.i((.., .., 0)).unsqueeze(-1);
        state += kt.unsqueeze(-1) * delta.unsqueeze(-2);
        let out = (&state * qt.unsqueeze(-1))
            .sum_dim_intlist([-2].as_slice(), false, Kind::Float)
            .unsqueeze(1);
        return (out.to_kind(dtype), state);
    }
    let q = q * (kd as f64).powf(-0.5);
    let pad = (64 - seq % 64) % 64;
    let q = q.constant_pad_nd([0, 0, 0, pad]);
    let k = k.constant_pad_nd([0, 0, 0, pad]);
    let v = v.constant_pad_nd([0, 0, 0, pad]);
    let beta = beta.constant_pad_nd([0, pad]);
    let g = g.constant_pad_nd([0, pad]);
    let chunks = (seq + pad) / 64;
    let vb = &v * beta.unsqueeze(-1);
    let kb = &k * beta.unsqueeze(-1);
    let q = q.reshape([1, heads, chunks, 64, kd]);
    let k = k.reshape([1, heads, chunks, 64, kd]);
    let kb = kb.reshape([1, heads, chunks, 64, kd]);
    let vb = vb.reshape([1, heads, chunks, 64, vd]);
    let cum = g.reshape([1, heads, chunks, 64]).cumsum(3, Kind::Float);
    let upper = Tensor::ones([64, 64], (Kind::Bool, d)).triu(1);
    let decay = (cum.unsqueeze(4) - cum.unsqueeze(3))
        .masked_fill(&upper, f64::NEG_INFINITY)
        .exp();
    let ut = kb.matmul(&k.transpose(-1, -2)) * &decay;
    let intra = q.matmul(&k.transpose(-1, -2)) * &decay;
    let nv = ut.linalg_solve_triangular(&vb, false, true, true);
    let kc = ut.linalg_solve_triangular(&(kb * cum.exp().unsqueeze(-1)), false, true, true);
    let q = q * cum.exp().unsqueeze(-1);
    let k = k * (cum.narrow(3, 63, 1) - &cum).exp().unsqueeze(-1);
    let cd = cum.i((.., .., .., 63)).exp().unsqueeze(-1).unsqueeze(-1);
    let mut outputs = vec![];
    for i in 0..chunks {
        let newv = nv.i((.., .., i)) - kc.i((.., .., i)).matmul(&state);
        outputs.push(q.i((.., .., i)).matmul(&state) + intra.i((.., .., i)).matmul(&newv));
        state = &state * cd.i((.., .., i)) + k.i((.., .., i)).transpose(-1, -2).matmul(&newv);
    }
    (
        Tensor::cat(&outputs, 2)
            .narrow(2, 0, seq)
            .transpose(1, 2)
            .contiguous()
            .to_kind(dtype),
        state,
    )
}

/// Attention diagnostics use the same BF16 matmul / float softmax as generation,
/// but retain only the last query position and mean over heads. Not attribution.
pub fn native_attention_weights(
    q: &Tensor,
    k: &Tensor,
    memory: &Tensor,
    mask: &Tensor,
    groups: i64,
    scale: f64,
) -> Result<Vec<f32>> {
    let last = q.narrow(2, q.size()[2] - 1, 1);
    let keys = Tensor::cat(&[memory, k], -2);
    let mask = mask.narrow(2, mask.size()[2] - 1, 1);
    let zero = Tensor::zeros([1, 1, 1, memory.size()[2]], (mask.kind(), mask.device()));
    let mask = Tensor::cat(&[zero, mask], -1);
    let weights = ((last.matmul(&repeat(&keys, groups).transpose(-1, -2)) * scale) + mask)
        .softmax(-1, Kind::Float)
        .mean_dim([1].as_slice(), false, Kind::Float)
        .view([-1]);
    Ok(Vec::<f32>::try_from(weights.to_device(Device::Cpu))?)
}

#[cfg(test)]
pub(crate) mod position_tests {
    use super::*;
    pub(crate) fn rotary_model() -> Model {
        let config: Config = serde_json::from_value(serde_json::json!({
            "hidden_size":16,"num_hidden_layers":1,"num_attention_heads":2,
            "num_key_value_heads":2,"head_dim":8,"rms_norm_eps":0.000001,
            "linear_num_key_heads":1,"linear_key_head_dim":8,"linear_num_value_heads":1,
            "linear_value_head_dim":8,"linear_conv_kernel_dim":4,
            "layer_types":["full_attention"],
            "rope_parameters":{"rope_theta":10000.0,"partial_rotary_factor":0.5}
        }))
        .unwrap();
        Model {
            config,
            weights: HashMap::new(),
            scales: HashMap::new(),
            layers: vec![Device::Cpu],
            embedding: Device::Cpu,
            head: Device::Cpu,
            kind: Kind::Float,
        }
    }
    #[test]
    fn bank_shift_is_rotary_translation_and_preserves_unrotated_dimensions() {
        let model = rotary_model();
        let x = Tensor::arange(80, (Kind::Float, Device::Cpu)).reshape([1, 2, 5, 8]) / 80.;
        let original = model.rope(&x, 10);
        assert!(model.shift_memory_keys(&original, 0).equal(&original));
        let shifted = model.shift_memory_keys(&original, -7);
        let direct = model.rope(&x, 3);
        assert!((&shifted - direct).abs().max().double_value(&[]) < 1e-6);
        assert!(shifted.narrow(-1, 4, 4).equal(&original.narrow(-1, 4, 4)));
    }

    #[test]
    fn memory_before_prompt_matches_disjoint_virtual_prefix_attention() {
        let model = rotary_model();
        // Independent memory and a prefill/decode query must have the same
        // relative distances as one disjoint virtual sequence. Check grouped
        // heads, multiple bank lengths, prefill and later decode positions.
        for memory_len in [1, 5, 17] {
            let raw_memory = (Tensor::arange(2 * memory_len * 8, (Kind::Float, Device::Cpu))
                .reshape([1, 2, memory_len, 8])
                * 0.13)
                .sin();
            let memory = model.rope(&raw_memory, 0);
            let shifted = model.shift_memory_keys(&memory, -memory_len);
            for start in [0, 3, 31, 128] {
                for count in [1, 4] {
                    let raw_q = (Tensor::arange(4 * count * 8, (Kind::Float, Device::Cpu))
                        .reshape([1, 4, count, 8])
                        * 0.17)
                        .cos();
                    let raw_k =
                        (Tensor::arange(2 * (start + count) * 8, (Kind::Float, Device::Cpu))
                            .reshape([1, 2, start + count, 8])
                            * 0.19)
                            .sin();
                    let values = (Tensor::arange(
                        2 * (memory_len + start + count) * 8,
                        (Kind::Float, Device::Cpu),
                    )
                    .reshape([1, 2, memory_len + start + count, 8])
                        * 0.23)
                        .cos();
                    let causal = Tensor::ones([count, start + count], (Kind::Bool, Device::Cpu))
                        .triu(start + 1);
                    let main_mask =
                        Tensor::zeros([1, 1, count, start + count], (Kind::Float, Device::Cpu))
                            .masked_fill(&causal, f64::NEG_INFINITY);
                    let mask = Tensor::cat(
                        &[
                            Tensor::zeros([1, 1, count, memory_len], (Kind::Float, Device::Cpu)),
                            main_mask,
                        ],
                        -1,
                    );
                    let actual = attention(
                        &model.rope(&raw_q, start),
                        &Tensor::cat(&[&shifted, &model.rope(&raw_k, 0)], -2),
                        &values,
                        &mask,
                        2,
                        8f64.powf(-0.5),
                    );
                    let expected = attention(
                        &model.rope(&raw_q, memory_len + start),
                        &Tensor::cat(&[&memory, &model.rope(&raw_k, memory_len)], -2),
                        &values,
                        &mask,
                        2,
                        8f64.powf(-0.5),
                    );
                    assert!(
                        (&actual - expected).abs().max().double_value(&[]) < 2e-6,
                        "memory={memory_len}, start={start}, count={count}"
                    );
                }
            }
        }
    }
}
