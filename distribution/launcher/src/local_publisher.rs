//! Portable Rust writer for locally prepared native banks. The private encoder
//! supplies BF16 tensor bytes; no LibTorch ABI or GPU-specific library is linked.
use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{fs::{self, File, OpenOptions}, io::{Read, Write}, os::unix::fs::OpenOptionsExt, path::Path};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Segment {
    layer: usize,
    value: bool,
    heads: usize,
    width: usize,
    positions: usize,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Header {
    tokens: Vec<u32>,
    segments: Vec<Segment>,
}

pub fn publish(mut input: impl Read, output: &Path, model: &str, key: &str) -> Result<()> {
    ensure!(!model.is_empty() && key.len() == 64
        && key.bytes().all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
        "invalid local bank identity");
    ensure!(!output.exists(), "local bank destination already exists");
    let mut length = [0u8; 8];
    input.read_exact(&mut length)?;
    let size = u64::from_le_bytes(length);
    ensure!((1..=1<<20).contains(&size), "invalid native tensor header");
    let mut raw = vec![0u8; size as usize];
    input.read_exact(&mut raw)?;
    let header: Header = serde_json::from_slice(&raw)?;
    ensure!(!header.tokens.is_empty() && header.tokens.len() <= 8192
        && !header.segments.is_empty() && header.segments.len() <= 512,
        "invalid native tensor geometry");
    let mut previous: Option<(usize, bool)> = None;
    let mut row_bytes = 0usize;
    let mut dictionary_bytes = 0usize;
    let mut index_segments = Vec::new();
    for segment in &header.segments {
        ensure!(segment.heads > 0 && segment.width > 0
            && segment.positions == header.tokens.len(), "incomplete native positions");
        ensure!(previous.is_none_or(|(layer, value)|
            segment.layer > layer || segment.layer == layer && !value && segment.value),
            "native layer order changed");
        previous = Some((segment.layer, segment.value));
        let row = segment.heads.checked_mul(segment.width).and_then(|n| n.checked_mul(2))
            .context("native row extent overflow")?;
        row_bytes = row_bytes.checked_add(row).context("native row extent overflow")?;
        dictionary_bytes = dictionary_bytes.checked_add(row.checked_mul(segment.positions)
            .context("native tensor extent overflow")?).context("native tensor extent overflow")?;
        index_segments.push(json!({"layer":segment.layer,"value":segment.value,
            "heads":segment.heads,"width":segment.width}));
    }
    ensure!(dictionary_bytes > 0 && dictionary_bytes <= 1<<30,
        "native tensor payload exceeds limit");
    fs::create_dir(output)?;
    let mut payload = OpenOptions::new().write(true).create_new(true).mode(0o600)
        .open(output.join("compact.pack"))?;
    payload.write_all(&[0u8;4096])?;
    let mut digest = Sha256::new();
    let mut remaining = dictionary_bytes;
    let mut chunk = [0u8; 256*1024];
    while remaining > 0 {
        let n = remaining.min(chunk.len());
        input.read_exact(&mut chunk[..n])?;
        digest.update(&chunk[..n]);
        payload.write_all(&chunk[..n])?;
        remaining -= n;
    }
    let mut extra = [0u8; 1];
    ensure!(input.read(&mut extra)? == 0, "extra native tensor bytes");
    let end = 4096 + dictionary_bytes as u64;
    let offset = (end + 4095) & !4095;
    payload.write_all(&vec![0u8; (offset-end) as usize])?;
    for code in 0..header.tokens.len() {
        payload.write_all(&(code as u32).to_le_bytes())?;
    }
    payload.sync_all()?;
    let index = json!({"version":1,"model":model,
        "schema":{"segments":index_segments,"row_bytes":row_bytes},
        "prototypes":header.tokens.len(),"dictionary_bytes":dictionary_bytes,
        "dictionary_sha256":hex::encode(digest.finalize()),
        "records":{key:{"offset":offset,"tokens":header.tokens}},
        "experimental_approximation":false,"head_major":false,"native_layout":true});
    let mut file = OpenOptions::new().write(true).create_new(true).mode(0o600)
        .open(output.join("index.json"))?;
    file.write_all(&serde_json::to_vec(&index)?)?;
    file.sync_all()?;
    File::open(output)?.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn writes_exact_native_layout_and_rejects_incomplete_tensor() {
        let temp=tempfile::tempdir().unwrap();
        let header=json!({"tokens":[4,5],"segments":[
            {"layer":0,"value":false,"heads":1,"width":2,"positions":2},
            {"layer":0,"value":true,"heads":1,"width":2,"positions":2}]});
        let raw=serde_json::to_vec(&header).unwrap();
        let mut wire=(raw.len() as u64).to_le_bytes().to_vec();
        wire.extend(raw); wire.extend([1u8;16]);
        publish(wire.as_slice(),&temp.path().join("bank"),"model",&"a".repeat(64)).unwrap();
        let index:serde_json::Value=serde_json::from_slice(&fs::read(temp.path().join("bank/index.json")).unwrap()).unwrap();
        assert_eq!(index["dictionary_bytes"],16);
        assert_eq!(index["records"]["a".repeat(64)]["tokens"],json!([4,5]));
        let mut truncated=wire.clone();truncated.pop();
        assert!(publish(truncated.as_slice(),&temp.path().join("incomplete"),"model",&"b".repeat(64)).is_err());
    }
}
