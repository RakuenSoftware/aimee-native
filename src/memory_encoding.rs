//! Serialization into the separate frozen encoder. Diagnostic variants are
//! gated by the serving command; none changes the main generation prompt.
use crate::tokens::Tokens;
use anyhow::{Result, ensure};
use serde_json::{Value, json};

pub fn encode(t: &Tokens, facts: &[Value], format: &str) -> Result<(Vec<u32>, Value)> {
    encode_with_context(t, facts, format, "")
}
pub fn encode_with_context(t: &Tokens, facts: &[Value], format: &str, context: &str) -> Result<(Vec<u32>, Value)> {
    let system_message = matches!(format, "system-message" | "system-message-keyed");
    let system_keyed = format == "system-message-keyed";
    let chat_framed = matches!(format, "chat-content" | "chat-keyed");
    let format = match format {
        "chat-content" => "content",
        "chat-keyed" => "keyed",
        "system-message" => "content",
        "system-message-keyed" => "keyed",
        other => other,
    };
    let mut text = String::new();
    let mut regions = vec![];
    if format == "json" {
        text = serde_json::to_string(
            &facts
                .iter()
                .map(|f| json!({"key":f["key"],"content":f["content"]}))
                .collect::<Vec<_>>(),
        )?;
    } else {
        text.push_str("Authoritative memory:\n");
        for (i, f) in facts.iter().enumerate() {
            if i > 0 {
                text.push('\n');
            }
            let record_start = text.len();
            let key = f["key"].as_str().unwrap_or("");
            let content = f["content"].as_str().unwrap();
            let mut key_range = None;
            if matches!(format, "keyed" | "keyed-neutral") && (!system_keyed || !key.is_empty()) {
                let start = text.len();
                text.push_str(key);
                key_range = Some((start, text.len()));
                text.push_str(": ");
            }
            let start = text.len();
            text.push_str(content);
            let content_range = (start, text.len());
            if format == "keyed-suffix" {
                text.push_str(" [");
                let start = text.len();
                text.push_str(key);
                key_range = Some((start, text.len()));
                text.push(']');
            }
            ensure!(
                matches!(
                    format,
                    "content" | "keyed" | "keyed-neutral" | "keyed-suffix"
                ),
                "unsupported memory encoding"
            );
            regions.push((
                f["memory_ref"].clone(),
                (record_start, text.len()),
                content_range,
                key_range,
            ));
        }
    }
    if chat_framed || system_message {
        let prefix = if system_message && !context.trim().is_empty() { format!("<|im_start|>system\n{}\n\n", context.trim()) } else { "<|im_start|>system\n".into() };
        text = format!("{}{}<|im_end|>\n", prefix, text);
        for (_, record, content, key) in &mut regions {
            record.0 += prefix.len();
            record.1 += prefix.len();
            content.0 += prefix.len();
            content.1 += prefix.len();
            if let Some((a, b)) = key {
                *a += prefix.len();
                *b += prefix.len();
            }
        }
    }
    let encoded = t
        .tokenizer
        .encode(text.as_str(), false)
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;
    let mut ids = encoded.get_ids().to_vec();
    let positions = |range: (usize, usize)| -> Vec<usize> {
        encoded
            .get_offsets()
            .iter()
            .enumerate()
            .filter(|(_, (a, b))| *a < range.1 && *b > range.0)
            .map(|(i, _)| i)
            .collect()
    };
    let mut details = vec![];
    for (reference, record, content, key) in regions {
        let key_positions = key.map(positions).unwrap_or_default();
        if format == "keyed-neutral" {
            let space = t.encode(" ")?;
            ensure!(space.len() == 1, "space control requires a single token");
            for p in &key_positions {
                ids[*p] = space[0];
            }
        }
        details.push(json!({"memory_ref":reference,"record_positions":positions(record),"content_positions":positions(content),"key_positions":key_positions}));
    }
    Ok((
        ids.clone(),
        json!({"text":t.decode(&ids,false)?,"token_ids":ids,"regions":details}),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn serialization_and_neutral_control_preserve_content_token_slots() {
        let Ok(path) = std::env::var("AIMEE_TEST_TOKENIZER") else {
            eprintln!("set AIMEE_TEST_TOKENIZER for checkpoint tokenizer test");
            return;
        };
        let t = Tokens::load(std::path::Path::new(&path)).unwrap();
        let facts = vec![
            json!({"key":"object primary","content":"Its value is 2.03446710000.","memory_ref":{"namespace":"test","id":"1","revision":"1"}}),
            json!({"key":"object secondary","content":"Its value is oolong.","memory_ref":{"namespace":"test","id":"2","revision":"1"}}),
        ];
        let (content, _) = encode(&t, &facts, "content").unwrap();
        let (prefix, info) = encode_with_context(&t, &facts, "system-message", "Caller instructions").unwrap();
        let prefix_text = "<|im_start|>system\nCaller instructions\n\nAuthoritative memory:\nIts value is 2.03446710000.\nIts value is oolong.<|im_end|>\n";
        assert_eq!(prefix, t.encode(prefix_text).unwrap());
        assert!(info["text"].as_str().unwrap().starts_with("<|im_start|>system\n"));
        assert!(info["text"].as_str().unwrap().ends_with("<|im_end|>\n"));
        let (keyed_prefix, _)=encode_with_context(&t,&facts,"system-message-keyed","Caller instructions").unwrap();
        assert_eq!(keyed_prefix,t.encode("<|im_start|>system\nCaller instructions\n\nAuthoritative memory:\nobject primary: Its value is 2.03446710000.\nobject secondary: Its value is oolong.<|im_end|>\n").unwrap());
        let mut missing_key=facts.clone();missing_key[0]["key"]=Value::Null;
        let (_,info)=encode_with_context(&t,&missing_key,"system-message-keyed","").unwrap();
        assert!(info["text"].as_str().unwrap().contains("Authoritative memory:\nIts value"));
        assert_eq!(
            content,
            t.encode("Authoritative memory:\nIts value is 2.03446710000.\nIts value is oolong.")
                .unwrap()
        );
        let (keyed, info) = encode(&t, &facts, "keyed").unwrap();
        assert_eq!(keyed,t.encode("Authoritative memory:\nobject primary: Its value is 2.03446710000.\nobject secondary: Its value is oolong.").unwrap());
        let (neutral, control) = encode(&t, &facts, "keyed-neutral").unwrap();
        assert_eq!(keyed.len(), neutral.len());
        assert_eq!(info["regions"], control["regions"]);
        let key_slots: std::collections::HashSet<usize> = info["regions"]
            .as_array()
            .unwrap()
            .iter()
            .flat_map(|r| {
                r["key_positions"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|p| p.as_u64().unwrap() as usize)
            })
            .collect();
        for i in 0..keyed.len() {
            if !key_slots.contains(&i) {
                assert_eq!(keyed[i], neutral[i]);
            }
        }
        let (suffix, _) = encode(&t, &facts, "keyed-suffix").unwrap();
        assert_eq!(suffix,t.encode("Authoritative memory:\nIts value is 2.03446710000. [object primary]\nIts value is oolong. [object secondary]").unwrap());
    }
}
