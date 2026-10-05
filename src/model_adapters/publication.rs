//! Byte publication utility. Dedicated adapters validate their own geometry first.
use anyhow::{Result, ensure};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs::{self, OpenOptions}, io::Write, path::Path};
fn hash(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
pub(super) fn publish(input: &Value, adapter: &str) -> Result<Value> {
    let tokens: Vec<u32> = serde_json::from_value(input["tokens"].clone())?;
    let segments = input["segments"].as_array().ok_or_else(|| anyhow::anyhow!("missing segments"))?;
    ensure!(tokens.len() as u64 == input["positions"].as_u64().unwrap_or(0), "token count mismatch");
    let bytes = segments.iter().try_fold(0usize, |sum, s| -> Result<usize> {
        let words = s["heads"].as_u64().unwrap_or(0).checked_mul(s["width"].as_u64().unwrap_or(0)).and_then(|v|v.checked_mul(tokens.len() as u64)).and_then(|v|v.checked_mul(2)).ok_or_else(||anyhow::anyhow!("geometry overflow"))?;
        sum.checked_add(usize::try_from(words)?).ok_or_else(||anyhow::anyhow!("size overflow"))
    })?;
    ensure!(bytes <= 128*1024*1024, "publication exceeds adapter budget");
    let source = Path::new(input["payload"].as_str().ok_or_else(||anyhow::anyhow!("missing payload"))?);
    ensure!(fs::metadata(source)?.len() == bytes as u64, "payload extent mismatch");
    let data = fs::read(source)?;
    let mut profile = input["profile"].clone();
    ensure!(profile.is_object(), "missing preparation identity");
    profile["adapter"] = json!(adapter);
    profile["positioning"] = json!("native-prefix-absolute-v1");
    let model = hash(&[b"dedicated-model-prefix-v1\0".as_slice(), &serde_json::to_vec(&profile)?].concat());
    let key = hash(&[model.as_bytes(), &serde_json::to_vec(&tokens)?].concat());
    let offset = (4096 + data.len() + 4095) & !4095;
    let row_bytes = bytes / tokens.len();
    let index = json!({"version":1,"model":model,"schema":{"segments":segments,"row_bytes":row_bytes},"prototypes":tokens.len(),"dictionary_bytes":data.len(),"dictionary_sha256":hash(&data),"records":{key.clone():{"offset":offset,"tokens":tokens}},"experimental_approximation":false,"head_major":false,"native_layout":true});
    let destination = Path::new(input["destination"].as_str().ok_or_else(||anyhow::anyhow!("missing destination"))?);
    fs::create_dir(destination)?;
    let result = (|| -> Result<()> {
        for (name, raw) in [("index.json",serde_json::to_vec(&index)?),("profile.json",serde_json::to_vec(&profile)?)] {
            let mut f=OpenOptions::new().write(true).create_new(true).open(destination.join(name))?;
            f.write_all(&raw)?; f.sync_all()?;
        }
        let mut f=OpenOptions::new().write(true).create_new(true).open(destination.join("compact.pack"))?;
        f.write_all(&[0;4096])?; f.write_all(&data)?; f.write_all(&vec![0;offset-4096-data.len()])?;
        for i in 0..tokens.len() { f.write_all(&(i as u32).to_le_bytes())?; }
        f.sync_all()?; Ok(())
    })();
    if let Err(error)=result { let _=fs::remove_dir_all(destination); return Err(error); }
    Ok(json!({"root":destination,"model":model,"key":key}))
}
