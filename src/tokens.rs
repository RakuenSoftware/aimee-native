//! Byte-exact addressing for Qwen's byte-level tokenizer. Scores originate in
//! the model's attention query; this module only translates its addressed slots.
use anyhow::{Result, anyhow, ensure};
use serde_json::{Value, json};
use std::{
    collections::{HashMap, HashSet},
    path::Path,
};
use tokenizers::Tokenizer;
pub struct Tokens {
    pub tokenizer: Tokenizer,
    bytes: HashMap<char, u8>,
    special: HashSet<u32>,
}
impl Tokens {
    pub fn load(path: &Path) -> Result<Self> {
        let tokenizer = Tokenizer::from_file(path).map_err(|e| anyhow!(e.to_string()))?;
        let raw: Value = serde_json::from_slice(&std::fs::read(path)?)?;
        let special = raw["added_tokens"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|v| v["special"] == true)
            .filter_map(|v| v["id"].as_u64().map(|n| n as u32))
            .collect();
        let mut values: Vec<u8> = (33..=126).chain(161..=172).chain(174..=255).collect();
        let mut chars: Vec<u32> = values.iter().map(|x| *x as u32).collect();
        let mut extra = 0;
        for v in 0..=255u8 {
            if !values.contains(&v) {
                values.push(v);
                chars.push(256 + extra);
                extra += 1;
            }
        }
        Ok(Self {
            tokenizer,
            bytes: chars
                .into_iter()
                .zip(values)
                .map(|(c, v)| (char::from_u32(c).unwrap(), v))
                .collect(),
            special,
        })
    }
    pub fn encode(&self, text: &str) -> Result<Vec<u32>> {
        Ok(self
            .tokenizer
            .encode(text, false)
            .map_err(|e| anyhow!(e.to_string()))?
            .get_ids()
            .to_vec())
    }
    pub fn decode(&self, ids: &[u32], skip: bool) -> Result<String> {
        self.tokenizer
            .decode(ids, skip)
            .map_err(|e| anyhow!(e.to_string()))
    }
    pub fn addressed(
        &self,
        sources: &[(&str, &[u32])],
        scores: &[f32],
        max_words: usize,
    ) -> Result<(String, Vec<Value>)> {
        let regex = regex::Regex::new(r"\w+(?:[-.]\w+)*")?;
        let mut spans: Vec<(String, String, Vec<usize>, f64)> = vec![];
        let mut offset = 0;
        for (source, ids) in sources {
            let mut raw = vec![];
            let mut ranges = vec![];
            for id in *ids {
                let token = self
                    .tokenizer
                    .id_to_token(*id)
                    .ok_or_else(|| anyhow!("unknown token"))?;
                let start = raw.len();
                for c in token.chars() {
                    raw.push(
                        *self
                            .bytes
                            .get(&c)
                            .ok_or_else(|| anyhow!("unsupported token bytes"))?,
                    );
                }
                ranges.push((start, raw.len()));
            }
            let text = String::from_utf8_lossy(&raw);
            ensure!(
                text == self.decode(ids, false)?,
                "token address encoding differs"
            );
            ensure!(
                offset + ids.len() <= scores.len(),
                "attention address length differs"
            );
            for word in regex.find_iter(&text) {
                let positions: Vec<usize> = ranges
                    .iter()
                    .enumerate()
                    .filter(|(i, (a, b))| {
                        *a < word.end() && *b > word.start() && !self.special.contains(&ids[*i])
                    })
                    .map(|(i, _)| offset + i)
                    .collect();
                if !positions.is_empty() {
                    let score = positions.iter().map(|i| scores[*i] as f64).sum();
                    spans.push((word.as_str().into(), (*source).into(), positions, score));
                }
            }
            offset += ids.len();
        }
        ensure!(offset == scores.len(), "attention address length differs");
        spans.sort_by(|a, b| b.3.total_cmp(&a.3));
        spans.truncate(max_words);
        spans.sort_by_key(|s| s.2[0]);
        Ok((
            spans
                .iter()
                .map(|s| s.0.as_str())
                .collect::<Vec<_>>()
                .join(" "),
            spans
                .into_iter()
                .map(|s| json!({"text":s.0,"source":s.1,"positions":s.2,"score":s.3}))
                .collect(),
        ))
    }
}
