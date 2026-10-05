//! Read the installed Aimee thin client's enrollment at request time.
//! The plugin stores only the profile path, never a second bearer or key.
use crate::Config;
use anyhow::{Context, Result, ensure};
use reqwest::blocking::Client;
use std::{fs::{self, OpenOptions}, io::Read, os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt}, path::Path, time::Duration};

pub struct Authorization {
    pub http: Client,
    pub token: String,
}

fn secret(path: &Path) -> Result<Vec<u8>> {
    let file = OpenOptions::new().read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path).with_context(|| format!("missing Aimee thin-client credential: {}", path.display()))?;
    let meta = file.metadata()?;
    ensure!(meta.is_file() && meta.uid() == unsafe { libc::geteuid() }
        && meta.permissions().mode() & 0o077 == 0,
        "Aimee thin-client credential must be an owner-only regular file");
    let mut bytes = Vec::new();
    file.take(65537).read_to_end(&mut bytes)?;
    ensure!(bytes.len() <= 65536, "Aimee thin-client credential exceeds limit");
    Ok(bytes)
}

pub fn open(connection: &Config) -> Result<Authorization> {
    let home = connection.thinclient_home.as_ref().context("not a thin-client connection")?;
    let remote = String::from_utf8(secret(&home.join("remote.conf"))?)?;
    let mut lines = remote.lines();
    let endpoint = lines.next().context("Aimee thin-client endpoint missing")?;
    let token = lines.next().context("Aimee thin-client bearer missing")?.to_owned();
    ensure!(lines.next().is_none() && !token.is_empty() && token.len() <= 16384,
        "invalid Aimee thin-client remote configuration");
    ensure!(crate::validate_endpoint(endpoint)? == crate::validate_endpoint(&connection.endpoint)?,
        "Aimee thin-client endpoint changed; reconnect the plugin");
    let mut identity = secret(&home.join("tls/client.crt"))?;
    identity.push(b'\n');
    identity.extend(secret(&home.join("tls/client.key"))?);
    let mut builder = Client::builder().https_only(true)
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(15))
        .timeout(Duration::from_secs(3600))
        .identity(reqwest::Identity::from_pem(&identity)?);
    match fs::read(home.join("remote-ca.pem")) {
        Ok(ca) => {
            // Aimee's self-signed server enrollment pins the server leaf. Its
            // URL may be an IP while the leaf names only localhost. Trust only
            // this explicit pin, then allow that name mismatch.
            builder = builder.tls_built_in_root_certs(false)
                .danger_accept_invalid_hostnames(true)
                .add_root_certificate(reqwest::Certificate::from_pem(&ca)?);
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
        Err(error) => return Err(error.into()),
    }
    Ok(Authorization {http: builder.build()?, token})
}
