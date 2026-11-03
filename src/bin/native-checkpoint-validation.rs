//! Full-checkpoint replay and withdrawal gate, using facts exported by the real
//! published reader. The controlled source models a bank change and withdrawal;
//! it does not claim to implement production authorization policy.
#[cfg(feature = "torch")]
mod validation {
    use aimee_native::{adapter::Adapter, model::{Bank, Cache, Model}, tokens::Tokens,
        transport::MemorySource};
    use anyhow::{Result, ensure};
    use clap::Parser;
    use serde_json::{Value, json};
    use std::{cell::Cell, path::PathBuf, rc::Rc};

    #[derive(Parser)]
    struct Args {
        #[arg(long)] model: PathBuf,
        #[arg(long)] placement: PathBuf,
        #[arg(long)] facts: PathBuf,
    }
    struct Source { binding: String, initial: Value, next: Value, reads: usize, withdrawn: Rc<Cell<bool>> }
    impl MemorySource for Source {
        fn begin(&mut self) -> Result<String> { Ok(self.binding.clone()) }
        fn check_generation(&mut self, expected: &str) -> Result<()> {
            ensure!(!self.withdrawn.get() && expected==self.binding,"publication withdrawn");Ok(())
        }
        fn search(&mut self, _: &str, _: usize) -> Result<Value> {
            self.reads+=1;Ok(if self.reads==1 {self.initial.clone()} else {self.next.clone()})
        }
        fn native_search(&mut self, query: &str, limit: usize) -> Result<Value> {self.search(query,limit)}
    }
    pub fn run() -> Result<()> {
        let args=Args::parse();let _guard=tch::no_grad_guard();tch::set_num_threads(8);
        let raw=std::fs::read(&args.facts)?;let source:Value=serde_json::from_slice(&raw)?;
        let withdrawn=Rc::new(Cell::new(false));
        let source=Source{binding:source["view"].as_str().unwrap().to_owned(),
            initial:source["initial"].clone(),next:source["next"].clone(),reads:0,withdrawn:withdrawn.clone()};
        let model=Model::load(&args.model,Some(&args.placement),true)?;
        let tokens=Tokens::load(&args.model.join("tokenizer.json"))?;
        let mut adapter=Adapter::new(Box::new(source),6,256,64*1024*1024);
        let mut state=adapter.begin(true,false)?;state.hybrid_native=true;
        state.encoding_format="system-message".into();
        state.encoding_context="Answer with the requested value using the available memory.".into();
        adapter.recall(&model,&tokens,&mut state,"initial","published-fixture",vec![])?;
        let original=state.memory_ids.clone();
        let ids=tokens.tokenizer.encode("<|im_start|>user\nWhich station code is reachable from Osreth outpost?<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n",false)
            .map_err(|e|anyhow::anyhow!(e.to_string()))?.get_ids().to_vec();
        let mut actual_cache=Cache::new(model.config.num_hidden_layers);
        let actual=adapter.forward(&model,&tokens,&ids,&mut actual_cache,&mut state)?;
        ensure!(state.native_replays==1 && state.source_reads==2 && state.memory_ids!=original,"bank replay/read gate failed");
        let (banks,states)=model.encode_native_complete(&state.memory_ids)?;
        let mut expected_cache=Cache::new(model.config.num_hidden_layers);
        expected_cache.position_offset=state.memory_ids.len() as i64;
        for (i,(conv,recurrent)) in states {expected_cache.layers[i].conv=Some(conv.copy());expected_cache.layers[i].recurrent=Some(recurrent.copy());}
        let expected=model.forward(&ids,&mut expected_cache,Some(&mut |_,i,_,_,_,_| {
            Ok(banks.get(&i).map(|b|Bank{keys:b.keys.shallow_clone(),values:b.values.shallow_clone()}))
        }))?;
        ensure!(actual.equal(&expected),"replayed logits differ from fixed-bank execution");
        for (a,b) in actual_cache.layers.iter().zip(&expected_cache.layers) {
            if let (Some(x),Some(y))=(&a.recurrent,&b.recurrent){ensure!(x.equal(y),"replayed recurrence differs");}
            if let (Some(x),Some(y))=(&a.conv,&b.conv){ensure!(x.equal(y),"replayed convolution differs");}
        }
        withdrawn.set(true);
        ensure!(adapter.forward(&model,&tokens,&[ids[0]],&mut actual_cache,&mut state).is_err(),"withdrawn publication emitted output");
        ensure!(state.memory_ids.is_empty() && state.banks.is_empty() && state.native_metrics()["active_recurrent_bytes"]==0
            && actual_cache.length==0 && actual_cache.position_offset==0
            && actual_cache.layers.iter().all(|l|l.kv.is_none() && l.conv.is_none() && l.recurrent.is_none()),"withdrawn state retained");
        println!("{}",json!({"full_checkpoint_layers":model.config.num_hidden_layers,"replay_equal":true,
            "recurrent_equal":true,"source_reads":state.source_reads,"withdrawal_rejected":true,
            "conversation_and_native_caches_cleared":true,"scope":"controlled transitions over real published-reader public facts"}));
        Ok(())
    }
}
#[cfg(feature = "torch")]
fn main() -> anyhow::Result<()> { validation::run() }
#[cfg(not(feature = "torch"))]
fn main() { panic!("checkpoint validation requires the torch feature"); }
