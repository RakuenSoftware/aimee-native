//! Dedicated Qwen 3.8 27B hybrid native-memory adapter.
//! Full attention and GDN state are one prefix, with live positions starting at M.
use anyhow::{Result, ensure};
use serde_json::{Value, json};
pub const ID: &str = "qwen3-8-27b";
pub fn validate(config: &Value) -> Result<()> {
    let c = config.get("text_config").unwrap_or(config);
    ensure!(c["model_type"] == "qwen3_5_text", "wrong model for Qwen 3.8 27B");
    for (key, expected) in [("num_hidden_layers",64), ("hidden_size",5120), ("num_attention_heads",24), ("num_key_value_heads",4), ("head_dim",256), ("linear_num_key_heads",16), ("linear_num_value_heads",48), ("linear_key_head_dim",128), ("linear_value_head_dim",128), ("linear_conv_kernel_dim",4)] {
        ensure!(c[key].as_u64() == Some(expected), "Qwen 3.8 27B: {key} mismatch");
    }
    let types = c["layer_types"].as_array().ok_or_else(|| anyhow::anyhow!("missing layer layout"))?;
    ensure!(types.len() == 64, "Qwen layer count mismatch");
    for (i, kind) in types.iter().enumerate() { ensure!(kind == if i % 4 == 3 { "full_attention" } else { "linear_attention" }, "Qwen layer {i} mismatch"); }
    ensure!(c["rope_parameters"]["rope_type"] == "default" && c["rope_parameters"]["rope_theta"].as_f64() == Some(10000000.0) && c["rope_parameters"]["partial_rotary_factor"].as_f64() == Some(0.25), "Qwen position implementation mismatch");
    Ok(())
}
pub fn request(input: &Value) -> Result<Value> {
    validate(&input["config"])?;
    match input["op"].as_str() {
        Some("describe") => Ok(json!({"adapter":ID,"positioning":"native-prefix-absolute-v1","recurrent":true,"layers":64,"capture_rpc":"aimee_capture_begin","capture_argument":"context","prefix_renderer":"adapter"})),
        Some("render_prefix") => {
            let context=input["context"].as_str().ok_or_else(||anyhow::anyhow!("missing Qwen system context"))?;
            let facts=input["facts"].as_array().ok_or_else(||anyhow::anyhow!("missing Qwen source facts"))?;
            ensure!((1..=32).contains(&facts.len()), "invalid Qwen source working set");
            let facts=facts.iter().map(|fact|fact.as_str().filter(|text|!text.is_empty()).ok_or_else(||anyhow::anyhow!("invalid Qwen source fact"))).collect::<Result<Vec<_>>>()?;
            ensure!(context.len()+facts.iter().map(|fact|fact.len()).sum::<usize>()<=1024*1024, "Qwen source working set exceeds limit");
            Ok(json!({"text":format!("<|im_start|>system\n{}\n\nAuthoritative memory:\n{}<|im_end|>\n",context.trim(),facts.join("\n"))}))
        },
        Some("validate_prefix_text") => {
            let context=input["context"].as_str().ok_or_else(||anyhow::anyhow!("missing Qwen system context"))?;
            let text=input["text"].as_str().ok_or_else(||anyhow::anyhow!("missing Qwen prefix text"))?;
            let expected=format!("<|im_start|>system\n{}\n\nAuthoritative memory:\n",context.trim());
            ensure!(text.starts_with(&expected) && text.ends_with("<|im_end|>\n"), "capture requires a closed authoritative Qwen system prefix");
            Ok(json!({"adapter":ID}))
        },
        Some("recurrent_layout") => {
            let layouts = input["layouts"].as_array().ok_or_else(||anyhow::anyhow!("missing Qwen recurrent layouts"))?;
            ensure!(layouts.len() == 96, "incomplete Qwen recurrent prefix");
            let mut seen=std::collections::BTreeSet::new();
            let mut end=0u64;
            for layout in layouts {
                let layer=layout["layer"].as_u64().ok_or_else(||anyhow::anyhow!("invalid Qwen layer"))?;
                let part=layout["part"].as_str().unwrap_or("");
                ensure!(layer<64 && layer%4!=3 && seen.insert((layer,part.to_string())), "invalid Qwen recurrent layer");
                let (shape,bytes)=match part {
                    "conv" => {ensure!(layout["dtype"]=="bf16", "Qwen conv dtype mismatch"); (json!([1,10240,4]),81920)},
                    "recurrent" => {ensure!(layout["dtype"]=="f32", "Qwen recurrent dtype mismatch"); (json!([1,48,128,128]),3145728)},
                    _ => anyhow::bail!("invalid Qwen recurrent part"),
                };
                ensure!(layout["shape"]==shape && layout["bytes"].as_u64()==Some(bytes) && layout["offset"].as_u64()==Some(end), "Qwen recurrent extent mismatch");
                end+=bytes;
            }
            ensure!(input["bytes"].as_u64()==Some(end), "Qwen recurrent payload mismatch");
            Ok(json!({"bytes":end}))
        },
        Some("seed_needed") => {
            let rows:Vec<(bool,u64,i64)>=serde_json::from_value(input["requests"].clone())?;
            Ok(json!(rows.iter().any(|(memory,computed,_)|*memory && *computed==0)))
        },
        Some("seed_plan") => {
            // vLLM slot IDs are runtime observations. The Qwen adapter alone
            // decides when a request initializes/reinitializes its GDN prefix.
            let rows:Vec<(bool,u64,i64)>=serde_json::from_value(input["requests"].clone())?;
            let capacity=input["capacity"].as_u64().ok_or_else(||anyhow::anyhow!("missing Qwen cache capacity"))?;
            let mut targets=std::collections::BTreeSet::new();
            let mut seed=Vec::new();
            for (i,(memory,computed,slot)) in rows.iter().enumerate() {
                ensure!(*slot>=0 && (*slot as u64)<capacity, "Qwen cache slot out of bounds");
                if *memory && *computed==0 { ensure!(targets.insert(*slot), "Qwen requests share a private cache slot"); seed.push(i); }
            }
            Ok(json!(seed))
        },
        Some("positions") => {
            let mut rows: Vec<Vec<i64>> = serde_json::from_value(input["positions"].clone())?;
            let ranges: Vec<(usize, usize, i64)> = serde_json::from_value(input["ranges"].clone())?;
            ensure!(!rows.is_empty() && rows.len() <= 3, "invalid Qwen position rows");
            let n = rows[0].len();
            ensure!(rows.iter().all(|r| r.len() == n && r.iter().all(|&p| p >= 0)), "invalid Qwen live positions");
            let mut end = 0;
            for (start, stop, memory) in ranges {
                ensure!(start == end && stop >= start && stop <= n && (0..=2048).contains(&memory), "invalid Qwen memory position mapping");
                for row in &mut rows { for position in &mut row[start..stop] { *position = position.checked_add(memory).ok_or_else(|| anyhow::anyhow!("position overflow"))?; } }
                end = stop;
            }
            ensure!(end == n, "incomplete Qwen position mapping");
            Ok(json!(rows))
        },
        Some("segments" | "publish") => {
            let segments = input["segments"].as_array().ok_or_else(|| anyhow::anyhow!("missing Qwen segments"))?;
            ensure!(segments.len() == 32, "incomplete Qwen attention memory");
            let mut seen = std::collections::BTreeSet::new();
            let count = input["positions"].as_u64().ok_or_else(|| anyhow::anyhow!("missing memory length"))?;
            ensure!((1..=2048).contains(&count), "invalid Qwen memory length");
            for s in segments {
                let layer = s["layer"].as_u64().ok_or_else(|| anyhow::anyhow!("invalid layer"))?;
                let value = s["value"].as_bool().ok_or_else(|| anyhow::anyhow!("invalid segment"))?;
                ensure!(layer < 64 && layer % 4 == 3 && seen.insert((layer,value)), "invalid Qwen attention layer");
                ensure!(s["heads"].as_u64() == Some(4) && s["width"].as_u64() == Some(256) && s["positions"].as_u64() == Some(count), "Qwen memory geometry mismatch");
            }
            if input["op"] == "publish" { return super::publication::publish(input, ID); }
            Ok(json!({"adapter":ID,"positioning":"native-prefix-absolute-v1"}))
        },
        _ => anyhow::bail!("unsupported Qwen 3.8 27B operation"),
    }
}
/// # Safety
/// Input is live NUL-terminated JSON; result belongs to the adapter free function.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn aimee_qwen3_8_27b_adapter(input: *const std::ffi::c_char) -> *mut std::ffi::c_char { unsafe { super::abi::call(input, request) } }
