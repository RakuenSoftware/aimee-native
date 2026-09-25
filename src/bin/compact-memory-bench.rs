//! Isolated CPU expansion experiment. Exact-table control is explicitly a dense
//! RAM dictionary, not proof of sparse-state reconstruction or serving latency.
use aimee_qwen::{
    compact_memory::{self, Schema},
    prepared_memory,
};
use anyhow::{Result, ensure};
use clap::Parser;
use serde_json::{Value, json};
use std::{path::PathBuf, time::Instant};
use tch::Tensor;
#[derive(Parser)]
struct Args {
    #[arg(long)]
    root: PathBuf,
    #[arg(long)]
    output: PathBuf,
    #[arg(long, default_value_t = 100)]
    repeats: usize,
    #[arg(long)]
    head_major: bool,
    #[arg(long, default_value_t = 1)]
    threads: usize,
}
fn main() -> Result<()> {
    let a = Args::parse();
    ensure!(a.repeats > 0, "positive repeat count required");
    let _guard = tch::no_grad_guard();
    let index: Value = serde_json::from_slice(&std::fs::read(a.root.join("index.json"))?)?;
    let model = index["model"].as_str().unwrap();
    let source = prepared_memory::Store::open(&a.root, model, false)?;
    source.verify()?; // Explicit offline admission, not part of reconstruction.
    let mut schema = None;
    let mut rows = vec![];
    let mut records = vec![];
    let mut count = 0;
    for key in index["entries"].as_object().unwrap().keys() {
        let native = source.load(key)?.unwrap();
        let s = Schema::from_banks(&native.banks)?;
        if let Some(schema) = &schema {
            ensure!(schema == &s, "mixed native schemas");
        } else {
            schema = Some(s.clone());
        }
        let matrix = s.rows(&native.banks)?;
        let n = native.tokens.len();
        records.push((
            key.clone(),
            native.tokens,
            (count..count + n as u32).collect(),
        ));
        count += n as u32;
        rows.push(matrix);
    }
    let dictionary = Tensor::cat(&rows, 0).contiguous();
    let schema = schema.unwrap();
    compact_memory::publish(
        &a.output,
        model,
        &schema,
        &dictionary,
        &records,
        false,
        a.head_major,
    )?;
    drop(rows);
    drop(dictionary);
    let activated = Instant::now();
    let mut store = compact_memory::Store::open(&a.output, model)?;
    store.set_threads(a.threads)?;
    println!(
        "{}",
        json!({"phase":"activation","ns":activated.elapsed().as_nanos(),"shared_ram_bytes":store.dictionary_bytes(),"record_count":records.len(),"dictionary_is_full_exact_state":true,"tokenizer_ids_are_not_dictionary_codes":true})
    );
    // Equality and bridge allocation are outside the timed CPU-only loop.
    for (key, tokens, _) in &records {
        let original = source.load(key)?.unwrap();
        let mut work = store.workspace(key)?;
        store.expand(key, &mut work)?;
        let recovered = store.banks(key, &work)?;
        for (layer, bank) in &original.banks {
            ensure!(
                bank.keys.equal(&recovered[layer].keys)
                    && bank.values.equal(&recovered[layer].values),
                "native state changed"
            );
        }
        println!(
            "{}",
            json!({"phase":"equality","key":key,"all_layers_equal":true,"tokens":tokens.len(),"record_payload_bytes":tokens.len()*4,"expanded_bytes":work.dense.len()})
        );
    }
    let mut workspaces = records
        .iter()
        .map(|(k, _, _)| store.workspace(k))
        .collect::<Result<Vec<_>>>()?;
    // Round robin prevents reporting only repetitions of one most recent record.
    for repeat in 0..a.repeats {
        for ((key, tokens, _), work) in records.iter().zip(&mut workspaces) {
            let t = store.expand(key, work)?;
            std::hint::black_box(&work.dense);
            println!(
                "{}",
                json!({"phase":"cpu-expansion","head_major":a.head_major,"threads":a.threads,"key":key,"repeat":repeat,"tokens":tokens.len(),"record_payload_bytes":tokens.len()*4,"expanded_bytes":work.dense.len(),"shared_ram_bytes":store.dictionary_bytes(),"read_ns":t.read_ns,"expand_ns":t.expand_ns,"total_ns":t.total_ns,"gpu_included":false,"output_preallocated":true,"code_read_cache":"uncontrolled"})
            );
        }
    }
    Ok(())
}
