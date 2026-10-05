//! Dedicated gemma4 26b native-memory adapter.
//! Memory is encoded by the stock model at 0..M; live positions begin at M.
//! No model rotary cache is read or replaced. No other model is admitted.
use anyhow::{Result, ensure};
use serde_json::{Value, json};
pub const ID: &str = "gemma4-26b";
pub fn validate(config: &Value) -> Result<()> {
    let c = config.get("text_config").unwrap_or(config);
    ensure!(matches!(c["model_type"].as_str(), Some("gemma4_text" | "gemma4_unified_text")), "wrong model for {ID}");
    for (key, expected) in [("num_hidden_layers",30), ("hidden_size",2816), ("num_attention_heads",16), ("num_key_value_heads",8), ("num_global_key_value_heads",2), ("head_dim",256), ("global_head_dim",512)] {
        ensure!(c[key].as_u64() == Some(expected), "{ID}: {key} mismatch");
    }
    ensure!(c["enable_moe_block"] == true, "{ID}: expert architecture mismatch");
    ensure!(c["num_kv_shared_layers"].as_u64().unwrap_or(0) == 0, "shared KV layers unsupported for {ID}");
    ensure!(c["num_experts"].as_u64() == Some(128), "Gemma4 26B expert count mismatch");
    let types = c["layer_types"].as_array().ok_or_else(|| anyhow::anyhow!("missing layer layout"))?;
    ensure!(types.len() == 30, "{ID}: layer count mismatch");
    for (i, kind) in types.iter().enumerate() { ensure!(kind == if i % 6 == 5 { "full_attention" } else { "sliding_attention" }, "{ID}: layer {i} mismatch"); }
    ensure!(c["rope_parameters"]["sliding_attention"]["rope_type"] == "default"
        && c["rope_parameters"]["sliding_attention"]["rope_theta"].as_f64() == Some(10000.0)
        && c["rope_parameters"]["full_attention"]["rope_type"] == "proportional"
        && c["rope_parameters"]["full_attention"]["rope_theta"].as_f64() == Some(1000000.0)
        && c["rope_parameters"]["full_attention"]["partial_rotary_factor"].as_f64() == Some(0.25), "{ID}: position implementation mismatch");
    Ok(())
}
pub fn request(input: &Value) -> Result<Value> {
    validate(&input["config"])?;
    match input["op"].as_str() {
        Some("describe") => Ok(json!({"adapter":ID,"positioning":"native-prefix-absolute-v1","recurrent":false,"layers":30,"capture_rpc":"aimee_attention_capture_begin","capture_argument":"text","prefix_renderer":"stock"})),
        Some("memory_profile") => {
            let profile=&input["profile"];
            let root=std::path::Path::new(input["model_root"].as_str().ok_or_else(||anyhow::anyhow!("missing model root"))?);
            use sha2::{Digest,Sha256};
            let config=std::fs::read(root.join("config.json"))?;
            let tokenizer=std::fs::read(root.join("tokenizer.json"))?;
            ensure!(profile["adapter"]==ID && profile["positioning"]=="native-prefix-absolute-v1", "wrong dedicated Gemma publication");
            ensure!(profile["model_config_sha256"]==format!("{:x}",Sha256::digest(&config)) && profile["tokenizer_sha256"]==format!("{:x}",Sha256::digest(&tokenizer)), "Gemma checkpoint identity mismatch");
            let weights=input["weights_sha256"].as_str().ok_or_else(||anyhow::anyhow!("missing quantized checkpoint binding"))?;
            ensure!(weights.len()==64 && weights.bytes().all(|b|b.is_ascii_hexdigit() && !b.is_ascii_uppercase()), "invalid quantized checkpoint binding");
            ensure!(profile["weights_sha256"]==weights && profile["weight_profile"]==input["weight_profile"] && profile["versions"]==input["versions"], "Gemma precision/runtime mismatch");
            Ok(json!({"adapter":ID}))
        },
        Some("positions") => {
            let mut rows: Vec<Vec<i64>> = serde_json::from_value(input["positions"].clone())?;
            let ranges: Vec<(usize, usize, i64)> = serde_json::from_value(input["ranges"].clone())?;
            ensure!(!rows.is_empty() && rows.len() <= 3, "invalid position rows");
            let n = rows[0].len();
            ensure!(rows.iter().all(|r| r.len() == n && r.iter().all(|&p| p >= 0)), "invalid live positions");
            let mut end = 0;
            for (start, stop, memory) in ranges {
                ensure!(start == end && stop >= start && stop <= n && (0..=1024).contains(&memory), "invalid memory position mapping");
                for row in &mut rows { for position in &mut row[start..stop] { *position = position.checked_add(memory).ok_or_else(|| anyhow::anyhow!("position overflow"))?; } }
                end = stop;
            }
            ensure!(end == n, "incomplete position mapping");
            Ok(json!(rows))
        },
        Some("segments" | "publish") => {
            let segments = input["segments"].as_array().ok_or_else(|| anyhow::anyhow!("missing segments"))?;
            ensure!(segments.len() == 30 * 2, "incomplete {ID} memory");
            let mut seen = std::collections::BTreeSet::new();
            let count = input["positions"].as_u64().ok_or_else(|| anyhow::anyhow!("missing memory length"))?;
            ensure!((1..=1024).contains(&count), "invalid memory length");
            for s in segments {
                let layer = s["layer"].as_u64().ok_or_else(|| anyhow::anyhow!("invalid layer"))?;
                let value = s["value"].as_bool().ok_or_else(|| anyhow::anyhow!("invalid segment"))?;
                ensure!(layer < 30 && seen.insert((layer,value)), "duplicate or invalid layer");
                let global = layer % 6 == 5;
                ensure!(s["heads"].as_u64() == Some(if global { 2 } else { 8 }) && s["width"].as_u64() == Some(if global { 512 } else { 256 }) && s["positions"].as_u64() == Some(count), "{ID} memory geometry mismatch");
            }
            if input["op"] == "publish" { return super::publication::publish(input, ID); }
            Ok(json!({"adapter":ID,"positioning":"native-prefix-absolute-v1"}))
        },
        _ => anyhow::bail!("unsupported {ID} operation"),
    }
}
/// # Safety
/// Input is a live NUL-terminated JSON string; release result with the adapter free function.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_gemma4_26b_adapter(input: *const std::ffi::c_char) -> *mut std::ffi::c_char { unsafe { super::abi::call(input, request) } }
