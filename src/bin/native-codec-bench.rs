use aimee_native::{native_store::NativeStore, native_transport_codec::Encoded};
use anyhow::{Result, ensure};
use std::{
    fs::File,
    io::Write,
    os::{fd::AsRawFd, unix::fs::FileExt},
    path::Path,
    time::Instant,
};
fn median(v: &[serde_json::Value], key: &str) -> f64 {
    let mut a: Vec<_> = v.iter().map(|x| x[key].as_f64().unwrap()).collect();
    a.sort_by(f64::total_cmp);
    a[a.len() / 2]
}
fn main() -> Result<()> {
    let a: Vec<_> = std::env::args().collect();
    ensure!(
        a.len() == 4 || (a.len() == 5 && a[4] == "--prepare-only"),
        "catalog publication output-directory"
    );
    let catalogue: serde_json::Value = serde_json::from_slice(&std::fs::read(&a[1])?)?;
    let s = &catalogue["publications"][&a[2]];
    let root = Path::new(&a[3]);
    std::fs::create_dir(root)?;
    let store = NativeStore::admit(
        Path::new(s["root"].as_str().unwrap()),
        s["model"].as_str().unwrap(),
        s["key"].as_str().unwrap(),
        512 * 1024 * 1024,
    )?;
    let plan = store.rank_plan(0, 2)?;
    let mut raw = vec![0u8; plan.bytes];
    store.pack_rank(&plan, &mut raw)?;
    let words: Vec<u16> = raw
        .chunks_exact(2)
        .map(|b| u16::from_le_bytes([b[0], b[1]]))
        .collect();
    let encoded = Encoded::encode(&words);
    let pool = rayon::ThreadPoolBuilder::new().num_threads(4).build()?;
    let simd = is_x86_feature_detected!("ssse3") && is_x86_feature_detected!("sse4.1");
    let mut decoded = vec![0u16; words.len()];
    unsafe { encoded.decode(&encoded.payload, &mut decoded, &pool, simd) };
    ensure!(decoded == words, "codec changed data");
    std::fs::write(
        root.join("format.json"),
        serde_json::to_vec(&serde_json::json!({
            "words":encoded.words,"table":encoded.table,"exceptions":encoded.exceptions,
            "exception_offset":encoded.exception_offset,"exception_positions":encoded.exception_positions
        }))?,
    )?;
    let raw_path = root.join("raw.pack");
    let code_path = root.join("encoded.pack");
    for (path, bytes) in [(&raw_path, &raw), (&code_path, &encoded.payload)] {
        let mut f = File::create(path)?;
        f.write_all(bytes)?;
        f.sync_all()?;
    }
    if a.len() == 5 {
        return Ok(());
    }
    let raw_f = File::open(&raw_path)?;
    let code_f = File::open(&code_path)?;
    let mut raw_buf = vec![0u8; raw.len()];
    let mut code_buf = vec![0u8; encoded.payload.len()];
    let mut rows = Vec::new();
    for trial in 0..30 {
        for mode in if trial % 2 == 0 {
            ["raw", "encoded"]
        } else {
            ["encoded", "raw"]
        } {
            let (file, buffer) = if mode == "raw" {
                (&raw_f, &mut raw_buf)
            } else {
                (&code_f, &mut code_buf)
            };
            unsafe {
                libc::posix_fadvise(file.as_raw_fd(), 0, 0, libc::POSIX_FADV_DONTNEED);
            }
            let start = Instant::now();
            file.read_exact_at(buffer, 0)?;
            let read_us = start.elapsed().as_secs_f64() * 1e6;
            if mode == "encoded" {
                unsafe { encoded.decode(buffer, &mut decoded, &pool, simd) };
            }
            let total_us = start.elapsed().as_secs_f64() * 1e6;
            rows.push(serde_json::json!({"trial":trial,"mode":mode,"read_us":read_us,"total_us":total_us,"decode_us":total_us-read_us}));
        }
    }
    let raw_rows: Vec<_> = rows
        .iter()
        .filter(|v| v["mode"] == "raw")
        .cloned()
        .collect();
    let code_rows: Vec<_> = rows
        .iter()
        .filter(|v| v["mode"] == "encoded")
        .cloned()
        .collect();
    let report = serde_json::json!({"status":"passed","scope":"CPU storage experiment, advisory page eviction; excludes GPU and is not certified cold activation","raw_bytes":raw.len(),"encoded_bytes":encoded.payload.len(),"exceptions":encoded.exceptions,"exception_index_ram_bytes":encoded.exception_positions.len()*std::mem::size_of::<usize>(),"simd":simd,"exact":decoded==words,"raw_total_median_us":median(&raw_rows,"total_us"),"encoded_total_median_us":median(&code_rows,"total_us"),"encoded_read_median_us":median(&code_rows,"read_us"),"decode_median_us":median(&code_rows,"decode_us"),"rows":rows});
    std::fs::write(
        root.join("report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    println!("{}", report);
    Ok(())
}
