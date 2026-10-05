//! Shared connection and process supervisor. Model semantics belong to the
//! dedicated adapter supplied by the installed plugin's binding contract.
use aimee_native_launcher as native;
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{fs, path::PathBuf, process::Command};

#[derive(serde::Deserialize)]
struct PluginBinding {
    adapter: String,
    python_module: String,
    library_sha256: String,
}

#[derive(Parser)]
struct Cli {
    #[arg(long, global=true)] root: Option<PathBuf>,
    #[command(subcommand)] command: Action,
}
#[derive(Subcommand)]
enum Action {
    ConnectAimee { #[arg(long)] aimee_home: Option<PathBuf> },
    Serve { #[arg(long)] config: PathBuf },
    #[command(hide=true)]
    MemoryAgent { #[arg(long)] serving: PathBuf, #[arg(long)] model: String, #[arg(long)] disk_budget: u64 },
}

fn main() -> Result<()> {
    let options = Cli::parse();
    let contract = PathBuf::from(std::env::var_os("AIMEE_NATIVE_PLUGIN_CONTRACT")
        .context("launch through an installed dedicated model plugin")?);
    ensure!(contract.is_absolute(), "plugin contract must be absolute");
    let binding: PluginBinding = serde_json::from_slice(&fs::read(&contract)?)?;
    ensure!(native::component(&binding.adapter) && !binding.adapter.contains('.'), "invalid adapter binding");
    ensure!(!binding.python_module.is_empty() && binding.python_module.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_'), "invalid plugin module binding");
    let library = contract.parent().context("missing plugin directory")?.join("libaimee_native.so");
    ensure!(hex::encode(Sha256::digest(fs::read(&library)?)) == binding.library_sha256, "plugin library does not match binding contract");
    let model = (binding.adapter.as_str(), binding.python_module.as_str());
    let root = options.root.unwrap_or_else(|| PathBuf::from(std::env::var_os("HOME").expect("HOME required"))
        .join(".local/share/aimee").join(model.0));
    ensure!(root.is_absolute(), "plugin root must be absolute");
    native::private_dir(&root)?;
    let memory = root.join("memory");
    native::private_dir(&memory)?;
    let connection_path = root.join("connection.json");
    match options.command {
        Action::ConnectAimee { aimee_home } => {
            let home = aimee_home.or_else(|| std::env::var_os("AIMEE_HOME").map(PathBuf::from))
                .unwrap_or_else(|| {
                    let base = PathBuf::from(std::env::var_os("HOME").expect("HOME required")).join(".config/aimee");
                    match std::env::var_os("AIMEE_PROFILE").filter(|value| !value.is_empty()) {
                        Some(profile) => base.join("profiles").join(profile),
                        None => base,
                    }
                });
            ensure!(home.is_absolute(), "Aimee home must be absolute");
            // The shared thin-client reader checks ownership, mode, certificate
            // and endpoint on every request; only this profile path is stored.
            let remote = fs::read_to_string(home.join("remote.conf"))?;
            let connection = native::Config { schema:1,
                endpoint:remote.lines().next().context("missing enrolled endpoint")?.to_owned(),
                token_file:root.join("unused"), memory_root:memory,
                ca_file:None, client_identity:None, connect_address:None, thinclient_home:Some(home) };
            let auth = native::thin_client::open(&connection)?;
            native::primitive::fetch(&auth.http, &connection, "native memory connection", 64)?;
            native::atomic(&connection_path, &serde_json::to_vec(&connection)?)?;
            println!("Connected using the existing Aimee enrollment.");
        }
        Action::MemoryAgent { serving, model, disk_budget:_ } => {
            ensure!(model == binding.adapter, "selection broker belongs to a different model binding");
            let connection = serde_json::from_slice(&fs::read(connection_path)?)?;
            native::model_broker::serve(connection, &serving)?;
        }
        Action::Serve { config } => {
            ensure!(std::env::var("VLLM_API_KEY").is_ok_and(|key| !key.trim().is_empty()), "enrolled model serving requires VLLM_API_KEY");
            let _lock = native::runtime::lock(&root)?;
            let connection: native::Config = serde_json::from_slice(&fs::read(connection_path)?)?;
            ensure!(fs::canonicalize(&connection.memory_root)? == fs::canonicalize(&memory)?, "connection belongs to another managed memory root");
            native::thin_client::open(&connection)?;
            native::runtime::clean_sockets(&memory)?;
            let mut serving: Value = serde_json::from_slice(&fs::read(&config)?)?;
            ensure!(serving.is_object(), "invalid serving configuration");
            ensure!(serving.get("adapter").is_none() || serving["adapter"] == model.0, "different model adapter selected");
            let config_raw = fs::read(PathBuf::from(serving["model"].as_str().context("model required")?).join("config.json"))?;
            let identity = native::thin_client::open(&connection)?;
            // Recipient is bound to the actual enrolled identity, never supplied
            // by the HTTP caller or an operator-maintained account map.
            let home = connection.thinclient_home.as_ref().context("thin client required")?;
            let recipient = hex::encode(Sha256::digest([connection.endpoint.as_bytes(), &fs::read(home.join("tls/client.crt"))?].concat()));
            let actual = hex::encode(Sha256::digest(config_raw));
            native::primitive::fetch(&identity.http, &connection, "native memory connection", 64)?;
            serving["adapter"] = json!(model.0);
            serving["python_module"] = json!(model.1);
            serving["library"] = json!(library);
            serving["library_sha256"] = json!(binding.library_sha256);
            serving["native_runtime_version"] = json!(env!("CARGO_PKG_VERSION"));
            serving["recipient"] = json!(recipient);
            serving["model_config_sha256"] = json!(actual);
            serving["catalog"] = json!(memory.join("catalog.json"));
            serving["control_socket"] = json!(memory.join("control.sock"));
            serving["selection_socket"] = json!(memory.join("selection.sock"));
            serving["preparation_root"] = json!(memory.join("prepared-model"));
            serving["native_preparation_enabled"] = json!(true);
            serving["start_paused"] = json!(true);
            if serving.get("host_memory_budget").is_none() { serving["host_memory_budget"] = json!(8u64*1024*1024*1024); }
            if serving.get("device_memory_budget").is_none() { serving["device_memory_budget"] = json!(512u64*1024*1024); }
            if serving.get("native_system_context").is_none() { serving["native_system_context"] = json!(""); }
            ensure!(serving["serve"].get("host").is_none() || serving["serve"]["host"] == "127.0.0.1", "enrolled plugin serves one owner on loopback");
            if !serving["serve"].is_object() { serving["serve"] = json!({}); }
            serving["serve"]["host"] = json!("127.0.0.1");
            ensure!(serving["serve"].get("tensor_parallel_size").is_none() || serving["serve"]["tensor_parallel_size"] == 1, "enrolled preparation requires the certified single-GPU profile");
            for mode in ["async_scheduling","enable_prefix_caching","enable_model_compilation","enable_piecewise_graphs","v2_model_runner"] {
                ensure!(serving["serve"].get(mode).is_none() || serving["serve"][mode] == false, "enrolled preparation requires eager synchronous V1 serving");
            }
            native::atomic(&memory.join("catalog.json"), &serde_json::to_vec(&json!({
                "recipient":recipient,"model_config_sha256":actual,"publications":{}}))?)?;
            let serving_path = root.join("serving.json");
            native::atomic(&serving_path, &serde_json::to_vec(&serving)?)?;
            let python = std::env::var_os("AIMEE_VLLM_PYTHON").context("launch through the installed model plugin command")?;
            let mut runtime = Command::new(python);
            runtime.args(["-c", &format!("from {}.cli import main; main()", model.1), "--config"])
                .arg(&serving_path);
            native::runtime::supervise(&root, &mut runtime, model.0, 16*1024*1024*1024, memory.join("selection.sock"))?;
        }
    }
    Ok(())
}
