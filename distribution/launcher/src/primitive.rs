//! Model-neutral source rows from the enrolled Aimee server. Encoding belongs
//! to the inference host, which already has the selected model's weights.
use crate::Config;
use anyhow::{Context, Result, ensure};
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SourceVersion {
    pub schema_version: u32,
    pub owner_id: String,
    pub record_id: String,
    pub record_revision: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SourceRecord {
    pub id: u64,
    pub content: String,
    pub version: SourceVersion,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Primitive {
    pub schema: u32,
    pub records: Vec<SourceRecord>,
}

impl Primitive {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.schema == 1, "unsupported memory primitive");
        ensure!(self.records.len() <= 32, "memory working set exceeds limit");
        let mut seen = HashSet::new();
        for record in &self.records {
            let v = &record.version;
            ensure!(record.id > 0 && !record.content.is_empty(), "invalid source record");
            ensure!(record.content.len() <= 1 << 20, "source record exceeds limit");
            ensure!(v.schema_version == 1 && v.record_id == record.id.to_string(),
                "source revision does not match record");
            ensure!(v.owner_id.len() == 36 && v.owner_id.bytes().enumerate().all(|(i, b)| {
                if matches!(i, 8 | 13 | 18 | 23) { b == b'-' } else { b.is_ascii_hexdigit() && !b.is_ascii_uppercase() }
            }), "invalid source owner");
            ensure!(!v.record_revision.is_empty() && v.record_revision.bytes().all(|b| b.is_ascii_digit()),
                "invalid source revision");
            ensure!(seen.insert((v.owner_id.as_str(), v.record_id.as_str())), "duplicate source record");
        }
        Ok(())
    }
}

pub fn fetch(http: &Client, connection: &Config, query: &str, limit_tokens: u32) -> Result<Primitive> {
    let token = fs::read_to_string(&connection.token_file)?;
    fetch_with_token(http, &connection.endpoint, &token, query, limit_tokens)
}

pub fn fetch_with_token(http: &Client, endpoint: &str, token: &str, query: &str, limit_tokens: u32) -> Result<Primitive> {
    ensure!(!query.trim().is_empty() && query.len() <= 16384, "invalid memory query");
    ensure!((64..=8192).contains(&limit_tokens), "invalid memory budget");
    crate::validate_endpoint(endpoint)?;
    ensure!(!token.trim().is_empty(), "missing enrolled Aimee credential");
    let response = http.post(format!("{}/v1/native/primitive", endpoint.trim_end_matches('/')))
        .bearer_auth(token.trim())
        .header("Content-Type", "application/json")
        .body(serde_json::to_vec(&serde_json::json!({"task_hint": query, "limit_tokens": limit_tokens, "store": "user"}))?)
        .send()?
        .error_for_status()?;
    let bytes = response.bytes()?;
    ensure!(bytes.len() <= 1 << 20, "memory primitive exceeds limit");
    let primitive: Primitive = serde_json::from_slice(&bytes).context("invalid memory primitive")?;
    primitive.validate()?;
    Ok(primitive)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_missing_or_mismatched_source_versions() {
        let valid = r#"{"schema":1,"records":[{"id":7,"content":"fact","version":{"schema_version":1,"owner_id":"00000000-0000-0000-0000-000000000001","record_id":"7","record_revision":"3"}}]}"#;
        let p: Primitive = serde_json::from_str(valid).unwrap();
        p.validate().unwrap();
        assert!(serde_json::from_str::<Primitive>(&valid.replace("\"version\"", "\"missing\"")).is_err());
        let mut mismatch = p.clone();
        mismatch.records[0].version.record_id = "8".into();
        assert!(mismatch.validate().is_err());
        let mut duplicate = p.clone();
        duplicate.records.push(duplicate.records[0].clone());
        assert!(duplicate.validate().is_err());
    }
}
