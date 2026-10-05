#[cfg(any(all(feature="adapter-gemma4-12b",feature="adapter-gemma4-26b"),all(feature="adapter-gemma4-12b",feature="adapter-qwen3-8-27b"),all(feature="adapter-gemma4-26b",feature="adapter-qwen3-8-27b")))]
compile_error!("A release library contains exactly one model adapter");
// Three dedicated model adapters. Shared code here is ABI plumbing only.
#[cfg(any(feature="adapter-gemma4-12b", not(any(feature="adapter-gemma4-12b",feature="adapter-gemma4-26b",feature="adapter-qwen3-8-27b"))))]
pub mod gemma4_12b;
#[cfg(any(feature="adapter-gemma4-26b", not(any(feature="adapter-gemma4-12b",feature="adapter-gemma4-26b",feature="adapter-qwen3-8-27b"))))]
pub mod gemma4_26b;
#[cfg(any(feature="adapter-qwen3-8-27b", not(any(feature="adapter-gemma4-12b",feature="adapter-gemma4-26b",feature="adapter-qwen3-8-27b"))))]
pub mod qwen3_8_27b;
mod abi;
mod publication;

#[cfg(all(test,not(any(feature="adapter-gemma4-12b",feature="adapter-gemma4-26b",feature="adapter-qwen3-8-27b"))))]
mod tests {
    use super::*;
    use serde_json::{Value,json};
    fn config(name: &str) -> Value {
        serde_json::from_slice(&std::fs::read(format!("distribution/vllm/tests/model_configs/{name}.json")).unwrap()).unwrap()
    }
    #[test]
    fn qwen_closed_prefix_rendering_does_not_require_a_user_query() {
        let mut input=json!({"config":config("qwen3-8-27b"),"op":"render_prefix","context":"  Instructions.  ","facts":["Approved fact.","Another fact."]});
        let prefix=qwen3_8_27b::request(&input).unwrap()["text"].as_str().unwrap().to_owned();
        assert_eq!(prefix,"<|im_start|>system\nInstructions.\n\nAuthoritative memory:\nApproved fact.\nAnother fact.<|im_end|>\n");
        input["op"]=json!("validate_prefix_text");input["text"]=json!(prefix);
        qwen3_8_27b::request(&input).unwrap();
        input["text"]=json!("<|im_start|>system\nInstructions.");assert!(qwen3_8_27b::request(&input).is_err());
        input["op"]=json!("render_prefix");input["facts"]=json!([]);assert!(qwen3_8_27b::request(&input).is_err());
    }
    #[test]
    fn each_adapter_accepts_only_its_model() {
        let models=[config("gemma4-12b"),config("gemma4-26b"),config("qwen3-8-27b")];
        let validators:[fn(&Value)->anyhow::Result<()>;3]=[gemma4_12b::validate,gemma4_26b::validate,qwen3_8_27b::validate];
        for (i,validate) in validators.iter().enumerate() { for (j,c) in models.iter().enumerate() { assert_eq!(validate(c).is_ok(),i==j); } }
    }
    #[test]
    fn each_adapter_maps_prefill_decode_and_mixed_requests_without_mutation() {
        for (name,request) in [("gemma4-12b",gemma4_12b::request as fn(&Value)->anyhow::Result<Value>),("gemma4-26b",gemma4_26b::request),("qwen3-8-27b",qwen3_8_27b::request)] {
            let input=json!({"config":config(name),"op":"positions","positions":[[0,1,40,41,42]],"ranges":[[0,2,82],[2,5,0]]});
            assert_eq!(request(&input).unwrap(),json!([[82,83,40,41,42]]));
            assert_eq!(input["positions"],json!([[0,1,40,41,42]]));
            let decode=json!({"config":config(name),"op":"positions","positions":[[120],[120],[120]],"ranges":[[0,1,82]]});
            assert_eq!(request(&decode).unwrap(),json!([[202],[202],[202]]));
            for ranges in [json!([[1,5,82]]),json!([[0,2,82]]),json!([[0,5,-1]]),json!([[0,5,4096]])] {
                let mut invalid=input.clone();invalid["ranges"]=ranges;assert!(request(&invalid).is_err());
            }
        }
    }
    #[test]
    fn dedicated_memory_geometry_rejects_cross_model_and_partial_banks() {
        for (name,request,layers,global_heads) in [("gemma4-12b",gemma4_12b::request as fn(&Value)->anyhow::Result<Value>,48,1),("gemma4-26b",gemma4_26b::request,30,2),("qwen3-8-27b",qwen3_8_27b::request,64,4)] {
            let qwen=name.starts_with("qwen");
            let segments:Vec<_>=(0..layers).filter(|i| !qwen || i%4==3).flat_map(|i| [false,true].map(move |value| json!({"layer":i,"value":value,"heads":if qwen || i%6==5 {global_heads}else{8},"width":if qwen || i%6!=5 {256}else{512},"positions":82}))).collect();
            let input=json!({"config":config(name),"op":"segments","positions":82,"segments":segments});
            request(&input).unwrap();
            let mut invalid=input.clone();invalid["segments"][0]["heads"]=json!(3);assert!(request(&invalid).is_err());
            let mut invalid=input.clone();invalid["segments"].as_array_mut().unwrap().pop();assert!(request(&invalid).is_err());
            let mut invalid=input.clone();invalid["segments"][1]=invalid["segments"][0].clone();assert!(request(&invalid).is_err());
        }
    }
}
