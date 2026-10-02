use aimee_native_launcher as native;
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
use sha2::{Digest, Sha256};
use std::os::unix::process::CommandExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::{
    fs,
    io::{self, Read},
    path::PathBuf,
    process::Command,
    time::Duration,
};

#[derive(Parser)]
#[command(version, about = "Aimee Native installation and runtime launcher")]
struct Cli {
    #[arg(long)]
    root: Option<PathBuf>,
    #[command(subcommand)]
    command: Action,
}
#[derive(Subcommand)]
enum Action {
    /// Save the Aimee endpoint. Read a scoped access token from standard input.
    Connect {
        endpoint: String,
        #[arg(long)]
        ca_file: Option<PathBuf>,
        /// PEM containing the enrolled client certificate and private key.
        #[arg(long)]
        client_identity: Option<PathBuf>,
        /// Dial this address while verifying the HTTPS endpoint hostname.
        #[arg(long)]
        connect_address: Option<std::net::SocketAddr>,
    },
    /// Connect using an existing, certificate-enrolled Aimee thin client.
    ConnectAimee {
        /// Aimee's client home; defaults to AIMEE_HOME, AIMEE_PROFILE, or ~/.config/aimee.
        #[arg(long)]
        aimee_home: Option<PathBuf>,
    },
    /// Run the private host-side native selection broker.
    MemoryAgent {
        #[arg(long)]
        serving: PathBuf,
        #[arg(long)]
        model: String,
        #[arg(long, default_value_t = 1073741824)]
        disk_budget: u64,
    },
    /// Fetch an approved complete native working set (control-plane diagnostic).
    FetchMemory {
        query: String,
        #[arg(long)]
        recipient: String,
        #[arg(long)]
        model: String,
        #[arg(long, default_value_t = 1073741824)]
        disk_budget: u64,
    },
    /// Check the enrolled Aimee source primitive on this inference host.
    FetchPrimitive {
        query: String,
        #[arg(long, default_value_t = 1024)]
        limit_tokens: u32,
    },
    #[command(hide = true)]
    PublishLocal {
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        identity: String,
        #[arg(long)]
        key: String,
    },
    /// Install a certified model/runtime from the configured release service.
    Install { model: String },
    /// Launch the installed native-memory runtime on loopback.
    Run {
        #[arg(long, default_value_t = 8080)]
        port: u16,
    },
    /// Serve an existing model in the current vLLM environment with live Aimee.
    Serve {
        #[arg(long)]
        config: PathBuf,
    },
    /// Restore the preceding installed release; does not downgrade memory.
    Rollback,
    /// Show installation/hardware information without reading credentials.
    Doctor,
}
struct AimeeCredentials {
    endpoint: String,
    token: String,
    ca: Option<Vec<u8>>,
    identity: Vec<u8>,
}
fn aimee_home(explicit: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(home) = explicit.or_else(|| std::env::var_os("AIMEE_HOME").map(PathBuf::from)) {
        ensure!(home.is_absolute(), "Aimee home must be an absolute path");
        return Ok(home);
    }
    let home = PathBuf::from(std::env::var_os("HOME").context("HOME or --aimee-home is required")?);
    let mut path = home.join(".config/aimee");
    if let Some(profile) = std::env::var_os("AIMEE_PROFILE") {
        let profile = profile.to_string_lossy();
        if !profile.trim().is_empty() {
            ensure!(profile != "." && profile != ".." && !profile.contains('/'), "invalid AIMEE_PROFILE");
            path = path.join("profiles").join(profile.as_ref());
        }
    }
    Ok(path)
}
fn private_aimee_file(path: &std::path::Path) -> Result<Vec<u8>> {
    let mut file = fs::OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path).with_context(|| format!("missing Aimee enrollment file: {}", path.display()))?;
    let metadata = file.metadata()?;
    ensure!(metadata.is_file() && metadata.uid() == unsafe { libc::geteuid() }
        && metadata.permissions().mode() & 0o077 == 0,
        "Aimee enrollment file must be a regular, owner-only file: {}", path.display());
    let mut contents = Vec::new();
    file.read_to_end(&mut contents)?;
    Ok(contents)
}
fn read_aimee_credentials(home: &std::path::Path) -> Result<AimeeCredentials> {
    let remote = String::from_utf8(private_aimee_file(&home.join("remote.conf"))?)?;
    let mut lines = remote.lines();
    let endpoint = lines.next().context("Aimee remote URL is missing")?.to_owned();
    let token = lines.next().context("Aimee enrollment bearer is missing")?.to_owned();
    ensure!(lines.next().is_none() && !token.is_empty(), "invalid Aimee remote configuration");
    native::validate_endpoint(&endpoint)?;
    // Aimee stores a pin for self-signed servers. Publicly trusted servers
    // need no local pin and use the runtime's normal trust roots instead.
    let ca = match fs::read(home.join("remote-ca.pem")) {
        Ok(pem) => Some(pem),
        Err(error) if error.kind() == io::ErrorKind::NotFound => None,
        Err(error) => return Err(error.into()),
    };
    if let Some(pem) = &ca {
        reqwest::Certificate::from_pem(pem)?;
    }
    let mut identity = private_aimee_file(&home.join("tls/client.crt"))?;
    identity.push(b'\n');
    identity.extend(private_aimee_file(&home.join("tls/client.key"))?);
    reqwest::Identity::from_pem(&identity)?;
    Ok(AimeeCredentials { endpoint, token, ca, identity })
}

fn local_model_fingerprint(model: &std::path::Path, gguf: Option<&str>) -> Result<String> {
    let mut files = Vec::new();
    for entry in fs::read_dir(model)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().into_owned();
        let relevant = name.ends_with(".safetensors")
            || matches!(name.as_str(), "config.json" | "tokenizer.json" | "tokenizer.model"
                | "tokenizer_config.json" | "special_tokens_map.json" | "added_tokens.json"
                | "vocab.json" | "merges.txt" | "chat_template.jinja");
        if relevant {
            ensure!(entry.metadata()?.is_file(), "model artifact must be a regular file: {name}");
            files.push((name, entry.path()));
        }
    }
    ensure!(files.iter().any(|(name, _)| name.ends_with(".safetensors")) || gguf.is_some(),
        "local native preparation requires model safetensors or GGUF on the inference host");
    if let Some(path) = gguf {
        let path = fs::canonicalize(path)?;
        ensure!(path.is_file(), "GGUF weights must be a regular file");
        files.push(("serving.gguf".into(), path));
    }
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut digest = Sha256::new();
    digest.update(b"aimee-local-model-v1\0");
    let mut buffer = [0u8; 1024 * 1024];
    for (name, path) in files {
        digest.update((name.len() as u64).to_le_bytes());
        digest.update(name.as_bytes());
        let mut file = fs::File::open(path)?;
        loop {
            let count = file.read(&mut buffer)?;
            if count == 0 { break; }
            digest.update(&buffer[..count]);
        }
    }
    Ok(hex::encode(digest.finalize()))
}
fn connect_from_aimee(root: &std::path::Path, home: &std::path::Path) -> Result<()> {
    let credentials = read_aimee_credentials(home)?;
    native::primitive::fetch_with_token(
        &tls_client(credentials.ca.as_deref(), Some(&credentials.identity),
            Some(&credentials.endpoint), None)?,
        &credentials.endpoint, &credentials.token, "native memory connection", 64,
    )?;
    native::connect_with_thinclient(root, &credentials.endpoint, home)?;
    println!("Authenticated Aimee native-memory connection established.");
    Ok(())
}
fn root(explicit: Option<PathBuf>) -> Result<PathBuf> {
    if let Some(p) = explicit {
        return Ok(std::path::absolute(p)?);
    }
    if let Some(p) = std::env::var_os("XDG_DATA_HOME") {
        return Ok(PathBuf::from(p).join("aimee-native"));
    }
    Ok(
        PathBuf::from(std::env::var_os("HOME").context("HOME or --root is required")?)
            .join(".local/share/aimee-native"),
    )
}
fn release_key() -> Result<[u8; 32]> {
    let value = option_env!("AIMEE_RELEASE_PUBLIC_KEY")
        .context("development launcher: release trust root has not been provisioned")?;
    hex::decode(value)?
        .try_into()
        .map_err(|_| anyhow::anyhow!("invalid embedded release key"))
}
fn client() -> Result<reqwest::blocking::Client> {
    tls_client(
        option_env!("AIMEE_RELEASE_CA_PEM").map(str::as_bytes),
        None,
        None,
        None,
    )
}
fn tls_client(
    ca: Option<&[u8]>,
    identity: Option<&[u8]>,
    endpoint: Option<&str>,
    address: Option<std::net::SocketAddr>,
) -> Result<reqwest::blocking::Client> {
    let builder = reqwest::blocking::Client::builder()
        .https_only(true)
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(3600));
    #[cfg(feature = "lab-release")]
    let builder = builder.add_root_certificate(reqwest::Certificate::from_pem(include_bytes!(
        env!("AIMEE_LAB_CA_FILE")
    ))?);
    let builder = if let Some(pem) = ca {
        builder.add_root_certificate(reqwest::Certificate::from_pem(pem)?)
    } else {
        builder
    };
    let builder = if let Some(pem) = identity {
        builder.identity(reqwest::Identity::from_pem(pem)?)
    } else {
        builder
    };
    let builder = if let Some(address) = address {
        let url =
            native::validate_endpoint(endpoint.context("dial override requires an endpoint")?)?;
        native::validate_connect_address(&url, address)?;
        builder.no_proxy().resolve(url.host_str().unwrap(), address)
    } else {
        builder
    };
    Ok(builder.build()?)
}
fn run() -> Result<()> {
    let cli = Cli::parse();
    if cfg!(feature = "lab-release") {
        eprintln!("Aimee Native: isolated LAB release build; not for production distribution");
    }
    let root = root(cli.root)?;
    match cli.command {
        Action::Connect {
            endpoint,
            ca_file,
            client_identity,
            connect_address,
        } => {
            let mut token = String::new();
            io::stdin().take(16385).read_to_string(&mut token)?;
            let ca = ca_file.map(fs::read).transpose()?;
            let identity = client_identity.map(fs::read).transpose()?;
            let profile = native::delivery::bootstrap(
                &tls_client(
                    ca.as_deref(),
                    identity.as_deref(),
                    Some(&endpoint),
                    connect_address,
                )?,
                &endpoint,
                &token,
            )?;
            native::connect_with_address(
                &root,
                &endpoint,
                &token,
                ca.as_deref(),
                identity.as_deref(),
                connect_address,
            )?;
            native::atomic(
                &root.join("native-profile.json"),
                &serde_json::to_vec(&profile)?,
            )?;
            println!("Authenticated Aimee native-memory connection established.");
        }
        Action::ConnectAimee { aimee_home: explicit } => {
            connect_from_aimee(&root, &aimee_home(explicit)?)?;
        }
        Action::MemoryAgent {
            serving,
            model,
            disk_budget,
        } => {
            let connection: native::Config =
                serde_json::from_slice(&fs::read(root.join("config.json"))?)?;
            let ca = connection.ca_file.as_ref().map(fs::read).transpose()?;
            let identity = connection
                .client_identity
                .as_ref()
                .map(fs::read)
                .transpose()?;
            native::broker::serve(
                tls_client(
                    ca.as_deref(),
                    identity.as_deref(),
                    Some(&connection.endpoint),
                    connection.connect_address,
                )?,
                connection,
                &serving,
                &model,
                disk_budget,
            )?;
        }
        Action::FetchMemory {
            query,
            recipient,
            model,
            disk_budget,
        } => {
            let connection: native::Config =
                serde_json::from_slice(&fs::read(root.join("config.json"))?)?;
            let ca = connection.ca_file.as_ref().map(fs::read).transpose()?;
            let identity = connection
                .client_identity
                .as_ref()
                .map(fs::read)
                .transpose()?;
            let (offer, path) = native::delivery::fetch(
                &tls_client(
                    ca.as_deref(),
                    identity.as_deref(),
                    Some(&connection.endpoint),
                    connection.connect_address,
                )?,
                &connection,
                &query,
                &recipient,
                &model,
                disk_budget,
            )?;
            println!(
                "{}",
                serde_json::json!({"publication":offer.key,"root":path,"records":offer.records.len(),"authorized_view":offer.authorized_view})
            );
        }
        Action::FetchPrimitive { query, limit_tokens } => {
            let connection: native::Config =
                serde_json::from_slice(&fs::read(root.join("config.json"))?)?;
            let ca = connection.ca_file.as_ref().map(fs::read).transpose()?;
            let identity = connection.client_identity.as_ref().map(fs::read).transpose()?;
            let primitive = native::primitive::fetch(
                &tls_client(ca.as_deref(), identity.as_deref(),
                    Some(&connection.endpoint), connection.connect_address)?,
                &connection, &query, limit_tokens)?;
            println!("{}", serde_json::json!({"records":primitive.records.len(),"schema":primitive.schema}));
        }
        Action::PublishLocal { output, identity, key } => {
            native::local_publisher::publish(io::stdin().lock(), &output, &identity, &key)?;
        }
        Action::Install { model } => {
            ensure!(native::component(&model), "invalid model identifier");
            let key = release_key()?;
            let base = option_env!("AIMEE_RELEASE_URL")
                .context("development launcher: release service has not been provisioned")?;
            let base = format!(
                "{}/{}/{}/",
                base.trim_end_matches('/'),
                native::platform(),
                model
            );
            let http = client()?;
            let mut raw = Vec::new();
            http.get(format!("{base}manifest.json"))
                .send()?
                .error_for_status()?
                .take(1048577)
                .read_to_end(&mut raw)?;
            let mut signature = Vec::new();
            http.get(format!("{base}manifest.sig"))
                .send()?
                .error_for_status()?
                .take(65)
                .read_to_end(&mut signature)?;
            let m = native::authenticate(&raw, &signature, &key)?;
            ensure!(m.model == model, "release model mismatch");
            let a = native::install(&root, &raw, &signature, &key, |path| {
                Ok(Box::new(
                    http.get(format!("{base}{path}"))
                        .send()?
                        .error_for_status()?,
                ))
            })?;
            println!("Installed {} ({})", m.model, a.current);
        }
        Action::Rollback => {
            native::rollback(&root)?;
            println!("Previous runtime restored.");
        }
        Action::Doctor => {
            println!("Platform: {}", native::platform());
            println!(
                "Release service configured: {}",
                option_env!("AIMEE_RELEASE_URL").is_some()
                    && option_env!("AIMEE_RELEASE_PUBLIC_KEY").is_some()
            );
            println!(
                "Aimee connection configured: {}",
                root.join("config.json").is_file()
            );
            match native::active(&root) {
                Ok(a) => println!("Active release: {}", a.current),
                Err(_) => println!("No usable release installed"),
            }
            println!(
                "GPU device nodes: AMD={}, NVIDIA={}",
                std::path::Path::new("/dev/kfd").exists(),
                std::path::Path::new("/dev/nvidiactl").exists()
            );
            println!(
                "GPU availability and model compatibility are certified by the runtime, not inferred from device nodes."
            );
        }
        Action::Serve { config } => {
            let connection: native::Config = serde_json::from_slice(
                &fs::read(root.join("config.json")).context("connect Aimee before serving")?,
            )?;
            let _runtime_lock = native::runtime::lock(&root)?;
            let mut settings: serde_json::Value = serde_json::from_slice(&fs::read(config)?)?;
            ensure!(settings.is_object(), "serving configuration must be an object");
            let model = fs::canonicalize(settings["model"].as_str().context("model directory required")?)?;
            if settings["gguf_weights"].is_null() {
                let candidates: Vec<PathBuf> = fs::read_dir(&model)?
                    .filter_map(|entry| entry.ok())
                    .filter(|entry| {
                        let name = entry.file_name().to_string_lossy().into_owned();
                        name.ends_with(".gguf") && !name.to_ascii_lowercase().contains("mmproj")
                            && entry.metadata().is_ok_and(|metadata| metadata.is_file())
                    })
                    .map(|entry| entry.path()).collect();
                if candidates.len() == 1 {
                    settings["gguf_weights"] = serde_json::json!(candidates[0]);
                }
            }
            let model_config_sha256 = hex::encode(Sha256::digest(fs::read(model.join("config.json"))?));
            let fingerprint = local_model_fingerprint(&model, settings["gguf_weights"].as_str())?;
            let native_model = format!("local-{}", &fingerprint[..24]);
            let ca = connection.ca_file.as_ref().map(fs::read).transpose()?;
            let identity = connection.client_identity.as_ref().map(fs::read).transpose()?;
            let (http, token) = if connection.thinclient_home.is_some() {
                let authorization = native::thin_client::open(&connection)?;
                (authorization.http, authorization.token)
            } else {
                (tls_client(ca.as_deref(), identity.as_deref(),
                    Some(&connection.endpoint), connection.connect_address)?,
                 fs::read_to_string(&connection.token_file)?)
            };
            native::primitive::fetch_with_token(&http, &connection.endpoint, &token,
                "native memory connection", 64)?;
            let mut recipient_identity = Sha256::new();
            recipient_identity.update(b"aimee-local-recipient-v1\0");
            recipient_identity.update(connection.endpoint.as_bytes());
            if let Some(home) = &connection.thinclient_home {
                recipient_identity.update(home.as_os_str().as_encoded_bytes());
            } else {
                recipient_identity.update(token.as_bytes());
                if let Some(identity) = &identity { recipient_identity.update(identity); }
            }
            let profile = native::delivery::Profile { schema:1,
                recipient:format!("self-{}", hex::encode(recipient_identity.finalize())),
                model:native_model.clone(), model_config_sha256 };
            let d: native::runtime::Defaults = serde_json::from_value(serde_json::json!({
                "schema":1, "native_model":native_model, "model_config_sha256":profile.model_config_sha256,
                "host_memory_budget":settings.get("host_memory_budget").cloned().unwrap_or(serde_json::json!(1073741824u64)),
                "device_memory_budget":settings.get("device_memory_budget").cloned().unwrap_or(serde_json::json!(268435456u64)),
                "disk_budget":settings.get("disk_budget").cloned().unwrap_or(serde_json::json!(2147483648u64)),
                "serve":settings.get("serve").cloned().unwrap_or(serde_json::json!({}))
            }))?;
            native::runtime::clean_sockets(&connection.memory_root)?;
            let (mut serving, defaults) = native::runtime::initialize_profile(&root, &model.join("config.json"), &connection, &profile, d)?;
            serving["model"] = serde_json::json!(model);
            let library = std::env::var_os("AIMEE_NATIVE_LIBRARY").map(PathBuf::from)
                .or_else(|| settings["library"].as_str().map(PathBuf::from))
                .context("install the complete Aimee plugin wheel")?;
            serving["library"] = serde_json::json!(fs::canonicalize(library)?);
            let python = std::env::var_os("AIMEE_VLLM_PYTHON").context("use the installed plugin entry point")?;
            let limit_tokens: u32 = settings["max_memory_tokens"].as_u64().unwrap_or(1024).try_into()?;
            let compiler: Vec<String> = match settings.get("local_compiler") {
                Some(value) => serde_json::from_value(value.clone())?,
                None => {
                    // Keep the venv interpreter path: canonicalizing its symlink
                    // switches to the base Python and loses installed extensions.
                    let mut command = vec![PathBuf::from(&python).to_string_lossy().into_owned(),
                    "-c".into(), "from aimee_vllm.native_compiler._c5 import main; main()".into(),
                    "--model".into(), model.to_string_lossy().into_owned(),
                    "--max-memory-tokens".into(), limit_tokens.to_string()];
                    if let Some(gguf) = settings["gguf_weights"].as_str() {
                        command.extend(["--gguf".into(), fs::canonicalize(gguf)?.to_string_lossy().into_owned()]);
                    }
                    command
                },
            };
            let model_config: serde_json::Value = serde_json::from_slice(&fs::read(model.join("config.json"))?)?;
            let position_policy = if model_config["model_type"] == "qwen3_5" { "nonnegative" } else { "negative" };
            let local = native::local_delivery::Settings {
                compiler,
                model_config_sha256:profile.model_config_sha256.clone(),
                runtime_profile:format!("{}-vllm", native_model),
                encoding_revision:"local-primitive-v1".into(),
                position_policy:position_policy.into(),
                limit_tokens,
            };
            local.validate()?;
            serving["local_preparation"] = serde_json::to_value(&local)?;
            for key in ["gguf_weights", "mm_proj", "gguf_matrix_backend"] {
                if let Some(value) = settings.as_object_mut().and_then(|s| s.remove(key)) {
                    serving[key] = value;
                }
            }
            serving["serve"]["host"] = serde_json::json!("127.0.0.1");
            native::atomic(&root.join("serving.json"), &serde_json::to_vec(&serving)?)?;
            let runtime_config = root.join("runtime.json");
            native::atomic(&runtime_config, &serde_json::to_vec(&serving)?)?;
            let mut cmd = Command::new(python);
            cmd.args(["-c", "from aimee_vllm.cli import main; main()", "--config"]).arg(runtime_config).env_remove("AIMEE_TOKEN");
            return native::runtime::supervise(&root, &mut cmd, &defaults.native_model,
                defaults.disk_budget, connection.memory_root.join("selection.sock"));
        }
        Action::Run { port } => {
            let a = native::active(&root)?;
            let dir = root.join("releases").join(&a.current);
            let m: native::Manifest =
                serde_json::from_slice(&fs::read(dir.join("manifest.json"))?)?;
            native::validate(&m)?;
            let config_path = root.join("config.json");
            let connection: native::Config = serde_json::from_slice(
                &fs::read(&config_path).context("connect Aimee before starting the runtime")?,
            )?;
            let _runtime_lock = native::runtime::lock(&root)?;
            let automatic = m.artifacts.iter().any(|a| a.path == "runtime/profile.json");
            let (mut serving, defaults) = if automatic {
                let ca = connection.ca_file.as_ref().map(fs::read).transpose()?;
                let identity = connection
                    .client_identity
                    .as_ref()
                    .map(fs::read)
                    .transpose()?;
                let http = tls_client(
                    ca.as_deref(),
                    identity.as_deref(),
                    Some(&connection.endpoint),
                    connection.connect_address,
                )?;
                let token = fs::read_to_string(&connection.token_file)?;
                let defaults: native::runtime::Defaults =
                    serde_json::from_slice(&fs::read(dir.join("runtime/profile.json"))?)?;
                let profile = native::delivery::bootstrap_for_model(
                    &http,
                    &connection.endpoint,
                    &token,
                    Some(&defaults.native_model),
                )?;
                native::runtime::clean_sockets(&connection.memory_root)?;
                let (serving, defaults) =
                    native::runtime::initialize(&root, &dir, &connection, &profile)?;
                (serving, Some(defaults))
            } else {
                (
                    serde_json::from_slice(
                        &fs::read(root.join("serving.json"))
                            .context("native publication serving configuration is not installed")?,
                    )?,
                    None,
                )
            };
            if m.artifacts.iter().any(|a| a.path == "runtime/image.json") {
                let image: native::RuntimeImage =
                    serde_json::from_slice(&fs::read(dir.join("runtime/image.json"))?)?;
                image.validate()?;
                anyhow::ensure!(
                    m.artifacts.iter().any(|a| a.path == image.model_config),
                    "missing model configuration sidecar"
                );
                let memory_root = fs::canonicalize(&connection.memory_root)?;
                let catalog =
                    fs::canonicalize(serving["catalog"].as_str().context("missing catalog")?)?;
                anyhow::ensure!(
                    catalog.starts_with(&memory_root),
                    "catalog must reside in managed memory root"
                );
                let model_dir = fs::canonicalize(
                    dir.join(&image.model_config)
                        .parent()
                        .context("missing model directory")?,
                )?;
                serving["catalog"] = serde_json::json!(catalog);
                serving["model"] = serde_json::json!(model_dir);
                serving["library"] = serde_json::json!("/opt/aimee/libaimee_native.so");
                if m.model_file.ends_with(".gguf") {
                    serving["gguf_weights"] =
                        serde_json::json!(fs::canonicalize(dir.join(&m.model_file))?);
                }
                // Runtime choices are part of the signed release, not user tuning.
                serving["gguf_matrix_backend"] =
                    serde_json::json!(image.gguf_matrix_backend.as_deref().unwrap_or("cuda"));
                serving
                    .as_object_mut()
                    .context("invalid serving configuration")?
                    .remove("mm_proj");
                if let Some(projector) = &image.mm_proj {
                    ensure!(
                        m.artifacts.iter().any(|a| &a.path == projector),
                        "missing signed GGUF projector artifact"
                    );
                    serving["mm_proj"] = serde_json::json!(fs::canonicalize(dir.join(projector))?);
                }
                serving["serve"]["port"] = serde_json::json!(port);
                serving["serve"]["host"] = serde_json::json!("127.0.0.1");
                let runtime_config = root.join("runtime.json");
                native::atomic(&runtime_config, &serde_json::to_vec(&serving)?)?;
                let runtime_config = fs::canonicalize(runtime_config)?;
                // Pulls are digest-pinned by the signed descriptor. Preparation and
                // account credentials are not mounted into the client container.
                // Keep private registry trust local to this installation. The
                // model container never receives account TLS identities.
                if let Some(ca) = option_env!("AIMEE_RELEASE_CA_PEM") {
                    let present = Command::new("podman")
                        .args(["image", "exists", &image.image])
                        .env_remove("AIMEE_TOKEN")
                        .status()?;
                    ensure!(
                        present.success() || present.code() == Some(1),
                        "cannot inspect container image"
                    );
                    if !present.success() {
                        let trust = root.join("release-trust");
                        native::private_dir(&trust)?;
                        native::atomic(&trust.join("ca.crt"), ca.as_bytes())?;
                        ensure!(
                            Command::new("podman")
                                .args(["pull", "--cert-dir"])
                                .arg(&trust)
                                .arg(&image.image)
                                .env_remove("AIMEE_TOKEN")
                                .status()?
                                .success(),
                            "verified runtime image download failed"
                        );
                    }
                }
                let mut cmd = Command::new("podman");
                cmd.args([
                    "run",
                    "--rm",
                    "--ipc=host",
                    "--network=host",
                    "--device",
                    "/dev/kfd",
                ]);
                if let Some(defaults) = &defaults {
                    cmd.arg("--memory")
                        .arg(defaults.system_memory_budget.to_string())
                        .arg("--memory-swap")
                        .arg(defaults.system_memory_budget.to_string());
                }
                for device in ["/dev/dri/renderD128", "/dev/dri/renderD129"] {
                    if std::path::Path::new(device).exists() {
                        cmd.args(["--device", device]);
                    }
                }
                for (path, mode) in [
                    (&model_dir, "ro"),
                    (&memory_root, "rw"),
                    (&runtime_config, "ro"),
                ] {
                    anyhow::ensure!(
                        !path.as_os_str().as_encoded_bytes().contains(&b':'),
                        "unsupported mount path"
                    );
                    cmd.arg("--volume").arg(format!(
                        "{}:{}:{}",
                        path.display(),
                        path.display(),
                        mode
                    ));
                }
                cmd.arg(&image.image)
                    .arg("--config")
                    .arg(runtime_config)
                    .env_remove("AIMEE_TOKEN");
                if let Some(defaults) = defaults {
                    return native::runtime::supervise(
                        &root,
                        &mut cmd,
                        &defaults.native_model,
                        defaults.disk_budget,
                        connection.memory_root.join("selection.sock"),
                    );
                }
                return Err(cmd.exec()).context("could not start certified container; Podman and matching GPU driver are required");
            }
            ensure!(
                !automatic,
                "automatic native delivery requires the certified container runtime"
            );
            let model_path = dir.join(&m.model_file);
            serving["model"] = serde_json::json!(if m.model_file.ends_with("config.json") {
                model_path
                    .parent()
                    .context("invalid model directory")?
                    .to_path_buf()
            } else {
                model_path
            });
            serving["library"] = serde_json::json!(dir.join(&m.library));
            serving["serve"]["port"] = serde_json::json!(port);
            serving["serve"]["host"] = serde_json::json!("127.0.0.1");
            let runtime_config = root.join("runtime.json");
            native::atomic(&runtime_config, &serde_json::to_vec(&serving)?)?;
            let e = Command::new(dir.join(&m.engine))
                .arg("--config")
                .arg(runtime_config)
                .env_remove("AIMEE_TOKEN")
                .current_dir(&dir)
                .exec();
            return Err(e).context("could not start the certified runtime");
        }
    }
    Ok(())
}
fn main() {
    if let Err(e) = run() {
        eprintln!("Aimee Native: {e}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod aimee_enrollment_tests {
    use super::*;

    #[test]
    fn incomplete_or_exposed_enrollment_fails_closed() {
        let dir = tempfile::tempdir().unwrap();
        let remote = dir.path().join("remote.conf");
        fs::write(&remote, "https://memory.example:8743\ninvitation\n").unwrap();
        fs::set_permissions(&remote, fs::Permissions::from_mode(0o600)).unwrap();
        assert!(read_aimee_credentials(dir.path()).is_err()); // no certificate
        fs::set_permissions(&remote, fs::Permissions::from_mode(0o644)).unwrap();
        assert!(private_aimee_file(&remote).is_err());
    }

    #[test]
    fn reads_existing_aimee_client_identity() {
        let dir = tempfile::tempdir().unwrap();
        let tls = dir.path().join("tls");
        fs::create_dir(&tls).unwrap();
        let cert = tls.join("client.crt");
        let key = tls.join("client.key");
        let output = Command::new("openssl")
            .args(["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                "-subj", "/CN=thin-client", "-keyout", key.to_str().unwrap(),
                "-out", cert.to_str().unwrap()])
            .output().unwrap();
        assert!(output.status.success());
        fs::set_permissions(&key, fs::Permissions::from_mode(0o600)).unwrap();
        fs::set_permissions(&cert, fs::Permissions::from_mode(0o600)).unwrap();
        let remote = dir.path().join("remote.conf");
        fs::write(&remote, "https://memory.example:8743\ninvitation\n").unwrap();
        fs::set_permissions(&remote, fs::Permissions::from_mode(0o600)).unwrap();
        fs::copy(&cert, dir.path().join("remote-ca.pem")).unwrap();
        let credentials = read_aimee_credentials(dir.path()).unwrap();
        assert_eq!(credentials.endpoint, "https://memory.example:8743");
        assert_eq!(credentials.token, "invitation");
        assert!(credentials.identity.windows(17).any(|v| v == b"BEGIN PRIVATE KEY"));
        fs::remove_file(dir.path().join("remote-ca.pem")).unwrap();
        assert!(read_aimee_credentials(dir.path()).unwrap().ca.is_none());
    }

    #[test]
    fn local_bank_identity_changes_with_checkpoint_bytes() {
        let dir = tempfile::tempdir().unwrap();
        fs::write(dir.path().join("config.json"), b"model").unwrap();
        let checkpoint = dir.path().join("model.safetensors");
        assert!(local_model_fingerprint(dir.path(), None).is_err());
        fs::write(&checkpoint, b"first weights").unwrap();
        let first = local_model_fingerprint(dir.path(), None).unwrap();
        fs::write(&checkpoint, b"other weights").unwrap();
        assert_ne!(first, local_model_fingerprint(dir.path(), None).unwrap());
        let gguf = dir.path().join("model.gguf");
        fs::write(&gguf, b"served weights").unwrap();
        assert_ne!(first, local_model_fingerprint(dir.path(), gguf.to_str()).unwrap());
        fs::remove_file(&checkpoint).unwrap();
        let gguf_only = local_model_fingerprint(dir.path(), gguf.to_str()).unwrap();
        fs::write(&gguf, b"updated served weights").unwrap();
        assert_ne!(gguf_only, local_model_fingerprint(dir.path(), gguf.to_str()).unwrap());
    }

}
