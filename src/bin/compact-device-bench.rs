//! Paired complete-loading control. Exact dense RAM dictionary, not sparse reconstruction.
use aimee_native::{
    compact_memory,
    model::{self, Bank, Placement},
    prepared_memory,
};
use anyhow::{Result, ensure};
use clap::Parser;
use serde_json::{Value, json};
use std::{collections::HashMap, os::fd::AsRawFd, path::PathBuf, time::Instant};
use tch::Device;
#[derive(Parser)]
struct Args {
    #[arg(long)]
    root: PathBuf,
    #[arg(long)]
    compact_root: PathBuf,
    #[arg(long)]
    placement: PathBuf,
    #[arg(long, default_value_t = 100)]
    repeats: usize,
    #[arg(long, default_value_t = 8)]
    threads: usize,
    #[arg(long)]
    cold: bool,
    #[arg(long)]
    optimized: bool,
    #[arg(long, requires = "optimized")]
    streaming_stores: bool,
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

fn check(expected: &HashMap<usize, Bank>, actual: &HashMap<usize, Bank>) -> Result<()> {
    ensure!(expected.len() == actual.len(), "native layer count changed");
    for (layer, bank) in expected {
        let got = &actual[layer];
        ensure!(
            bank.keys.equal(&got.keys.to_device(Device::Cpu))
                && bank.values.equal(&got.values.to_device(Device::Cpu)),
            "GPU native state changed at layer {layer}"
        );
    }
    Ok(())
}
fn main() -> Result<()> {
    let a = Args::parse();
    ensure!(a.repeats > 0, "positive repeat count required");
    let _guard = tch::no_grad_guard();
    let index: Value = serde_json::from_slice(&std::fs::read(a.root.join("index.json"))?)?;
    let model = index["model"].as_str().unwrap();
    let placement: Placement = serde_json::from_slice(&std::fs::read(&a.placement)?)?;
    let devices = placement
        .layers
        .iter()
        .map(|d| model::device(d))
        .collect::<Result<Vec<_>>>()?;
    let source = prepared_memory::Store::open(&a.root, model, false)?;
    source.verify()?;
    let mut compact = compact_memory::Store::open(&a.compact_root, model)?;
    compact.set_threads(a.threads)?;
    compact.set_streaming(a.streaming_stores)?;
    let keys: Vec<_> = index["entries"]
        .as_object()
        .unwrap()
        .keys()
        .cloned()
        .collect();
    let mut workspaces = vec![];
    let mut references = vec![];
    for key in &keys {
        let expected = source.load(key)?.unwrap();
        let mut work = compact.device_workspace(key, &devices)?;
        if a.optimized {
            compact.initialize_device_pool(&mut work)?;
        }
        let first = if a.optimized {
            compact.apply_optimized(key, &mut work)?
        } else {
            compact.apply(key, &mut work)?
        };
        check(&expected.banks, &first.banks)?;
        // A subsequent use must not overwrite previously returned GPU state.
        let mut alias = first.banks.values().next().unwrap().keys.narrow(2, 0, 1);
        let _ = alias.fill_(123.);
        let second = if a.optimized {
            compact.apply_optimized(key, &mut work)?
        } else {
            compact.apply(key, &mut work)?
        };
        ensure!(
            alias.eq(123.).all().int64_value(&[]) != 0,
            "live GPU bank overwritten"
        );
        check(&expected.banks, &second.banks)?;
        drop(first);
        drop(second);
        // A derived alias outlives the cached Bank TensorImpl. Storage ownership
        // must prevent reusing its underlying destination as well.
        let _ = alias.fill_(456.);
        let before_alias = alias.to_device(Device::Cpu);
        let third = if a.optimized {
            compact.apply_optimized(key, &mut work)?
        } else {
            compact.apply(key, &mut work)?
        };
        check(&expected.banks, &third.banks)?;
        ensure!(
            before_alias.equal(&alias.to_device(Device::Cpu)),
            "derived GPU alias overwritten"
        );
        let raw = source.load_to_devices(key, &devices)?.unwrap();
        check(&expected.banks, &raw.banks)?;
        println!(
            "{}",
            json!({"phase":"equality","key":key,"all_layers_equal":true,"tokens":expected.tokens.len(),"expanded_bytes":expected.expanded_bytes,"repeated_workspace_preserves_prior_gpu_state":true})
        );
        workspaces.push(work);
        references.push(expected);
    }
    println!(
        "{}",
        json!({"phase":"configuration","optimized":a.optimized,"streaming_stores":a.streaming_stores,"references_in_ram_index":a.optimized,"completion":if a.optimized{"current-stream-events"}else{"device-synchronize"},"threads":a.threads,"repeats":a.repeats,"shared_ram_bytes":compact.dictionary_bytes(),"dictionary_is_full_exact_state":true,"readiness":"device-synchronized","record_count":keys.len(),"cold":a.cold,"prepared_host_cache_enabled":false,"output_pinned":true,"activation_and_workspace_allocation_excluded":true})
    );
    for repeat in 0..a.repeats {
        for (i, key) in keys.iter().enumerate() {
            for method in if (repeat + i) % 2 == 0 {
                ["raw", "compact"]
            } else {
                ["compact", "raw"]
            } {
                let path = if method == "raw" {
                    source.payload_path(key)
                } else {
                    compact.path().to_owned()
                };
                if a.cold {
                    evict_and_check(&path)?;
                }
                let started = Instant::now();
                let (banks, read_ns, expand_ns, transfer_ns, operations) = if method == "raw" {
                    let v = source.load_to_devices(key, &devices)?.unwrap();
                    (
                        v.banks,
                        v.read_ns,
                        v.conversion_ns,
                        v.transfer_ns,
                        v.transfer_operations,
                    )
                } else {
                    let v = if a.optimized {
                        compact.apply_optimized(key, &mut workspaces[i])?
                    } else {
                        compact.apply(key, &mut workspaces[i])?
                    };
                    (
                        v.banks,
                        v.read_ns,
                        v.expand_ns,
                        v.transfer_ns,
                        v.transfer_operations,
                    )
                };
                let total_ns = started.elapsed().as_nanos();
                // Verification outside the timed path, after every paired result.
                check(&references[i].banks, &banks)?;
                println!(
                    "{}",
                    json!({"phase":"device-application","optimized":a.optimized,"streaming_stores":a.streaming_stores,"method":method,"key":key,"repeat":repeat,"tokens":references[i].tokens.len(),"read_bytes":if method=="raw"{references[i].expanded_bytes}else if a.optimized{0}else{references[i].tokens.len()*4},"expanded_bytes":references[i].expanded_bytes,"read_ns":read_ns,"expand_ns":expand_ns,"transfer_ns":transfer_ns,"total_ns":total_ns,"transfer_operations":operations,"all_layers_equal":true,"readiness":"device-synchronized","os_page_cache_cold":a.cold && (method=="raw" || !a.optimized),"references_in_ram_index":method=="compact" && a.optimized,"dictionary_in_ram":method=="compact"})
                );
            }
        }
    }
    Ok(())
}
