use aimee_native_launcher as native;
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
use std::os::unix::process::CommandExt;
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
    Connect { endpoint: String },
    /// Install a certified model/runtime from the configured release service.
    Install { model: String },
    /// Launch the installed native-memory runtime on loopback.
    Run {
        #[arg(long, default_value_t = 8080)]
        port: u16,
    },
    /// Restore the preceding installed release; does not downgrade memory.
    Rollback,
    /// Show installation/hardware information without reading credentials.
    Doctor,
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
    Ok(reqwest::blocking::Client::builder()
        .https_only(true)
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(3600))
        .build()?)
}
fn run() -> Result<()> {
    let cli = Cli::parse();
    let root = root(cli.root)?;
    match cli.command {
        Action::Connect { endpoint } => {
            let mut token = String::new();
            io::stdin().take(16385).read_to_string(&mut token)?;
            native::connect(&root, &endpoint, &token)?;
            println!("Aimee connection saved. Credentials are not sent to the release service.");
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
        Action::Run { port } => {
            let a = native::active(&root)?;
            let dir = root.join("releases").join(&a.current);
            let m: native::Manifest =
                serde_json::from_slice(&fs::read(dir.join("manifest.json"))?)?;
            native::validate(&m)?;
            let config_path = root.join("config.json");
            let _: native::Config = serde_json::from_slice(
                &fs::read(&config_path).context("connect Aimee before starting the runtime")?,
            )?;
            // Contract for the certified runtime build; upstream llama-server lacks these flags.
            // Do not forward bearer tokens through argv, logs, or release downloads.
            let e = Command::new(dir.join(&m.engine))
                .args([
                    "--host",
                    "127.0.0.1",
                    "--port",
                    &port.to_string(),
                    "--model",
                ])
                .arg(dir.join(&m.model_file))
                .arg("--aimee-config")
                .arg(config_path)
                .arg("--aimee-native-library")
                .arg(dir.join(&m.library))
                .env("LD_LIBRARY_PATH", dir.join("lib"))
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
