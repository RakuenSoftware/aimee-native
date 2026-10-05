//! Lossless immutable hybrid prefix states, admitted with the attention entry.
//! Convolution and recurrent tensors retain their individual dtypes (in
//! particular FP32 recurrence); no pickle or model execution occurs at load.
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::{BTreeMap, HashMap},
    fs::OpenOptions,
    io::Write,
    os::unix::fs::OpenOptionsExt,
    path::Path,
};
use tch::{Device, Kind, Tensor};
#[derive(Clone, Serialize, Deserialize)]
struct Layout {
    layer: usize,
    part: String,
    dtype: String,
    shape: Vec<i64>,
    offset: usize,
    bytes: usize,
}
#[derive(Clone, Serialize, Deserialize)]
pub struct Metadata {
    version: u32,
    bytes: usize,
    sha256: String,
    layouts: Vec<Layout>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    payload: Option<String>,
}
impl Metadata {
    pub fn bytes(&self) -> usize {
        self.bytes
    }
}
fn kind(s: &str) -> Result<Kind> {
    Ok(match s {
        "f32" => Kind::Float,
        "bf16" => Kind::BFloat16,
        "f16" => Kind::Half,
        _ => anyhow::bail!("invalid recurrent dtype"),
    })
}
pub fn validate(m: &Metadata) -> Result<()> {
    ensure!(m.payload.as_ref().is_none_or(|p| p == &format!("{}.rnn.bin", m.sha256)), "invalid recurrent payload identity");
    ensure!(
        m.version == 1
            && m.bytes > 0
            && m.bytes <= 1 << 30
            && m.sha256.len() == 64
            && m.sha256
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()),
        "invalid recurrent metadata"
    );
    let mut end = 0usize;
    let mut pairs = BTreeMap::new();
    for l in &m.layouts {
        ensure!(
            l.layer < 4096
                && matches!(l.part.as_str(), "conv" | "recurrent")
                && l.shape.len() <= 4
                && !l.shape.is_empty()
                && l.shape.iter().all(|x| *x > 0),
            "invalid recurrent layout"
        );
        let elements = l
            .shape
            .iter()
            .try_fold(1usize, |n, x| n.checked_mul(*x as usize))
            .context("recurrent shape overflow")?;
        ensure!(
            elements.checked_mul(kind(&l.dtype)?.elt_size_in_bytes()) == Some(l.bytes)
                && l.offset == end,
            "invalid recurrent extent"
        );
        ensure!(
            l.part != "recurrent" || l.dtype == "f32",
            "recurrent state must remain FP32"
        );
        ensure!(
            pairs
                .entry(l.layer)
                .or_insert(std::collections::HashSet::new())
                .insert(l.part.clone()),
            "duplicate recurrent component"
        );
        end = end
            .checked_add(l.bytes)
            .context("recurrent extent overflow")?;
    }
    ensure!(
        end == m.bytes && !pairs.is_empty() && pairs.values().all(|p| p.len() == 2),
        "incomplete recurrent state"
    );
    Ok(())
}
pub fn write(
    root: &Path,
    _key: &str,
    states: &HashMap<usize, (Tensor, Tensor)>,
) -> Result<Option<Metadata>> {
    if states.is_empty() {
        return Ok(None);
    }
    let mut layers: Vec<_> = states.keys().copied().collect();
    layers.sort_unstable();
    let mut data = Vec::new();
    let mut layouts = Vec::new();
    for layer in layers {
        for (part, t) in [
            ("conv", &states[&layer].0),
            ("recurrent", &states[&layer].1),
        ] {
            let dtype = match t.kind() {
                Kind::Float => "f32",
                Kind::BFloat16 => "bf16",
                Kind::Half => "f16",
                _ => anyhow::bail!("unsupported recurrent dtype"),
            };
            let cpu = t.to_device(Device::Cpu).contiguous();
            let bytes = cpu.numel() * cpu.kind().elt_size_in_bytes();
            layouts.push(Layout {
                layer,
                part: part.into(),
                dtype: dtype.into(),
                shape: cpu.size(),
                offset: data.len(),
                bytes,
            });
            data.extend_from_slice(unsafe {
                std::slice::from_raw_parts(cpu.data_ptr().cast::<u8>(), bytes)
            });
        }
    }
    let sha256 = format!("{:x}", Sha256::digest(&data));
    let m = Metadata {
        version: 1,
        bytes: data.len(),
        payload: Some(format!("{sha256}.rnn.bin")),
        sha256,
        layouts,
    };
    validate(&m)?;
    let path = root.join(m.payload.as_ref().unwrap());
    // A failed attention publication may leave this immutable payload behind.
    // Only an identical retry may adopt it; never overwrite another encoding.
    static SERIAL: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let temporary = root.join(format!(".recurrent-{}-{}-{}.tmp", std::process::id(), std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_nanos(), SERIAL.fetch_add(1, std::sync::atomic::Ordering::Relaxed)));
    let mut f = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&temporary)?;
    let publication = (|| -> Result<()> {
      f.write_all(&data)?;
      f.sync_all()?;
      match std::fs::hard_link(&temporary, &path) {
        Ok(()) => {},
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => ensure!(
            std::fs::read(&path)? == data,
            "recurrent publication collision"
        ),
        Err(e) => return Err(e.into()),
      }
      std::fs::File::open(root)?.sync_all()?;
      Ok(())
    })();
    drop(f);
    let _ = std::fs::remove_file(&temporary);
    publication?;
    Ok(Some(m))
}
pub fn load(
    root: &Path,
    key: &str,
    m: &Metadata,
    devices: Option<&[Device]>,
) -> Result<HashMap<usize, (Tensor, Tensor)>> {
    validate(m)?;
    let path = root.join(m.payload.clone().unwrap_or_else(|| format!("{key}.rnn.bin")));
    ensure!(
        std::fs::metadata(&path)?.len() == m.bytes as u64,
        "recurrent payload size mismatch"
    );
    let data = std::fs::read(path)?;
    ensure!(
        format!("{:x}", Sha256::digest(&data)) == m.sha256,
        "recurrent checksum mismatch"
    );
    let mut parts = HashMap::new();
    for l in &m.layouts {
        let dtype = kind(&l.dtype)?;
        let t = Tensor::empty(&l.shape[..], (dtype, Device::Cpu));
        unsafe {
            std::ptr::copy_nonoverlapping(
                data[l.offset..l.offset + l.bytes].as_ptr(),
                t.data_ptr().cast::<u8>(),
                l.bytes,
            );
        }
        let device = match devices {
            Some(ds) => *ds
                .get(l.layer)
                .context("missing recurrent layer placement")?,
            None => Device::Cpu,
        };
        parts.insert((l.layer, l.part.as_str()), t.to_device(device));
    }
    let layers: Vec<_> = parts
        .keys()
        .filter(|(_, p)| *p == "conv")
        .map(|(l, _)| *l)
        .collect();
    Ok(layers
        .into_iter()
        .map(|l| {
            (
                l,
                (
                    parts.remove(&(l, "conv")).unwrap(),
                    parts.remove(&(l, "recurrent")).unwrap(),
                ),
            )
        })
        .collect())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn identical_payloads_share_storage_and_legacy_entries_still_load() {
        let root = tempfile::tempdir().unwrap();
        let source = HashMap::from([(2, (Tensor::ones([1, 4, 4], (Kind::BFloat16, Device::Cpu)), Tensor::ones([1, 1, 4, 4], (Kind::Float, Device::Cpu))))]);
        let first = write(root.path(), &"1".repeat(64), &source).unwrap().unwrap();
        let second = write(root.path(), &"2".repeat(64), &source).unwrap().unwrap();
        assert_eq!(first.payload, second.payload);
        assert_eq!(std::fs::read_dir(root.path()).unwrap().count(), 1);
        assert!(load(root.path(), &"2".repeat(64), &second, None).unwrap()[&2].1.equal(&source[&2].1));
        let legacy_key = "3".repeat(64);
        std::fs::copy(root.path().join(first.payload.as_ref().unwrap()), root.path().join(format!("{legacy_key}.rnn.bin"))).unwrap();
        let mut legacy = first.clone();
        legacy.payload = None;
        assert!(load(root.path(), &legacy_key, &legacy, None).unwrap()[&2].0.equal(&source[&2].0));
        let mut invalid = second;
        invalid.payload = Some("../outside.rnn.bin".into());
        assert!(validate(&invalid).is_err());
    }
    #[test]
    fn lossless_mixed_dtype_and_corruption_rejection() {
        let root = tempfile::tempdir().unwrap();
        let key = "1".repeat(64);
        let conv = Tensor::arange(24, (Kind::Float, Device::Cpu))
            .reshape([1, 6, 4])
            .to_kind(Kind::BFloat16);
        let state =
            (Tensor::arange(16, (Kind::Float, Device::Cpu)) * 0.000123).reshape([1, 1, 4, 4]);
        let source = HashMap::from([(2, (conv, state))]);
        let meta = write(root.path(), &key, &source).unwrap().unwrap();
        let loaded = load(root.path(), &key, &meta, None).unwrap();
        assert_eq!(loaded[&2].0.kind(), Kind::BFloat16);
        assert_eq!(loaded[&2].1.kind(), Kind::Float);
        assert_eq!(
            (&loaded[&2].1 - &source[&2].1)
                .abs()
                .max()
                .double_value(&[]),
            0.
        );
        let _ = loaded[&2].1.shallow_clone().fill_(42.);
        assert_ne!(source[&2].1.double_value(&[0, 0, 0, 0]), 42.);
        let path = root.path().join(meta.payload.as_ref().unwrap());
        let mut data = std::fs::read(&path).unwrap();
        data[0] ^= 1;
        std::fs::write(path, data).unwrap();
        assert!(load(root.path(), &key, &meta, None).is_err());
    }
    #[test]
    fn incomplete_or_lossy_layout_rejected() {
        let root = tempfile::tempdir().unwrap();
        let key = "2".repeat(64);
        let source = HashMap::from([(
            1,
            (
                Tensor::zeros([1, 4, 4], (Kind::Float, Device::Cpu)),
                Tensor::zeros([1, 1, 4, 4], (Kind::BFloat16, Device::Cpu)),
            ),
        )]);
        assert!(write(root.path(), &key, &source).is_err());
    }
}
