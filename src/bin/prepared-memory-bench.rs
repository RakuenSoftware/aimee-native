//! Focused prepared-store latency benchmark. Does not claim model readiness.
use aimee_qwen::prepared_memory::Store;
use anyhow::{Result, ensure};
use clap::Parser;
use serde_json::{Value, json};
use std::{os::fd::AsRawFd, path::PathBuf, time::Instant};
#[derive(Parser)]
struct Args {
    #[arg(long)]
    root: PathBuf,
    #[arg(long)]
    placement: Option<PathBuf>,
    #[arg(long, default_value_t = 0, conflicts_with = "cold")]
    host_cache_mib: usize,
    #[arg(long, default_value_t = 100)]
    repeats: usize,
    #[arg(long)]
    cold: bool,
    #[arg(long)]
    repack_to: Option<PathBuf>,
    #[arg(long)]
    verify_only: bool,
    #[arg(long, value_enum, default_value = "raw")]
    write_codec: aimee_qwen::native_compression::Codec,
}
fn evict_and_check(path: &std::path::Path) -> Result<()> {
    let f = std::fs::File::open(path)?;
    let size = f.metadata()?.len() as usize;
    let page = unsafe { libc::sysconf(libc::_SC_PAGESIZE) } as usize;
    ensure!(size > 0 && page > 0, "invalid page extent");
    unsafe {
        ensure!(
            libc::posix_fadvise(f.as_raw_fd(), 0, 0, libc::POSIX_FADV_DONTNEED) == 0,
            "file cache eviction failed"
        );
        let map = libc::mmap(
            std::ptr::null_mut(),
            size,
            libc::PROT_READ,
            libc::MAP_SHARED,
            f.as_raw_fd(),
            0,
        );
        ensure!(map != libc::MAP_FAILED, "residency mapping failed");
        let mut residency = vec![0u8; size.div_ceil(page)];
        let result = libc::mincore(map, size, residency.as_mut_ptr());
        libc::munmap(map, size);
        ensure!(
            result == 0 && residency.iter().all(|v| v & 1 == 0),
            "payload pages still resident; refusing cold label"
        );
    }
    Ok(())
}
fn main() -> Result<()> {
    let a = Args::parse();
    let index: Value = serde_json::from_slice(&std::fs::read(a.root.join("index.json"))?)?;
    let devices = a
        .placement
        .as_ref()
        .map(|p| -> Result<Vec<tch::Device>> {
            let placement: aimee_qwen::model::Placement =
                serde_json::from_slice(&std::fs::read(p)?)?;
            placement
                .layers
                .iter()
                .map(|s| aimee_qwen::model::device(s))
                .collect()
        })
        .transpose()?;
    let mut store = Store::open(&a.root, index["model"].as_str().unwrap(), false)?;
    store.set_host_cache_budget(a.host_cache_mib * 1024 * 1024);
    if a.verify_only {
        store.verify()?;
        println!("{}", json!({"verified":true}));
        return Ok(());
    }
    if let Some(destination) = &a.repack_to {
        store.verify()?;
        ensure!(!destination.exists(), "repack destination must be new");
        let mut writer = Store::open(destination, index["model"].as_str().unwrap(), true)?;
        writer.set_write_codec(a.write_codec);
        for key in index["entries"].as_object().unwrap().keys() {
            let original = store.load(key)?.unwrap();
            writer.put(key, &original.tokens, &original.banks)?;
            let reconstructed = writer.load(key)?.unwrap();
            ensure!(
                original.tokens == reconstructed.tokens
                    && original.banks.len() == reconstructed.banks.len(),
                "repack metadata mismatch"
            );
            for (layer, bank) in &original.banks {
                let next = &reconstructed.banks[layer];
                ensure!(
                    bank.keys.equal(&next.keys) && bank.values.equal(&next.values),
                    "repack changed native state"
                );
            }
            println!(
                "{}",
                json!({"key":key,"source_bytes":original.bytes,"intermediate_bytes":reconstructed.bytes,"expanded_bytes":reconstructed.expanded_bytes,"all_layers_equal":true})
            );
        }
        return Ok(());
    }
    for key in index["entries"].as_object().unwrap().keys() {
        store.activate(key)?; // File activation is outside active-store read timing; no verification.
        for repeat in 0..a.repeats {
            if a.cold {
                evict_and_check(&store.payload_path(key))?;
            }
            let started = Instant::now();
            let loaded = if let Some(ds) = &devices {
                store.load_to_devices(key, ds)?
            } else {
                store.load(key)?
            }
            .unwrap();
            let elapsed = started.elapsed().as_nanos();
            println!(
                "{}",
                json!({"key":key,"repeat":repeat,"mode":if a.cold{"os-page-cache-cold"}else{"os-cache-uncontrolled"},"bytes":loaded.bytes,"expanded_bytes":loaded.expanded_bytes,"tokens":loaded.tokens.len(),"layers":loaded.banks.len(),"read_ns":loaded.read_ns,"file_setup_ns":loaded.file_setup_ns,"file_opened":loaded.file_opened,"conversion_ns":loaded.conversion_ns,"total_ready_ns":elapsed,"readiness":if devices.is_some(){"device-synchronized"}else{"cpu-only"},"transfer_ns":loaded.transfer_ns,"transfer_operations":loaded.transfer_operations,"host_hit":loaded.host_hit})
            );
        }
    }
    Ok(())
}
