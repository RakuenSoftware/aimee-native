use aimee_qwen::transport::{ImageConfig, ImageReader, LocalFirst, MemorySource, unix_post};
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
#[cfg(any(feature = "torch", test))]
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{BufRead, Read},
    os::unix::fs::PermissionsExt,
    path::PathBuf,
    time::Duration,
};

#[derive(Parser)]
#[command(about = "Read-only native Qwen ↔ Aimee memory. No Python runtime.")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    Gateway(Gateway),
    /// Authorization-bound transport probe; input is JSON lines with op begin/search.
    ReadCheck(Connection),
    #[cfg(feature = "torch")]
    Serve(Serve),
    #[cfg(feature = "torch")]
    Probe(Probe),
    #[cfg(feature = "torch")]
    PrepareMemory(PrepareMemory),
}
#[derive(clap::Args)]
struct Connection {
    #[command(flatten)]
    image: ImageConfig,
    #[arg(long)]
    read_gateway: PathBuf,
    #[arg(long)]
    read_authority: String,
}
impl Connection {
    fn open(&self) -> Result<LocalFirst> {
        Ok(LocalFirst::new(
            ImageReader::start(&self.image)?,
            self.read_gateway.clone(),
            self.read_authority.clone(),
        ))
    }
}
#[derive(clap::Args)]
struct Gateway {
    #[command(flatten)]
    image: ImageConfig,
    #[arg(long)]
    socket: PathBuf,
    #[arg(long)]
    upstream_unix: Option<PathBuf>,
    /// Restrict Aimee candidates to this namespace in the verified grant.
    #[arg(long)]
    upstream_namespace: Option<String>,
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long)]
    ca: Option<PathBuf>,
    #[arg(long)]
    cert: Option<PathBuf>,
    #[arg(long)]
    key: Option<PathBuf>,
}
fn reply(r: tiny_http::Request, status: u16, body: Value) {
    let _ = r.respond(
        tiny_http::Response::from_string(body.to_string())
            .with_status_code(status)
            .with_header(
                tiny_http::Header::from_bytes("Content-Type", "application/json").unwrap(),
            ),
    );
}
fn body(r: &mut tiny_http::Request, max: usize) -> Result<Value> {
    ensure!(
        r.body_length().is_some_and(|n| n > 0 && n <= max),
        "invalid request size"
    );
    let mut raw = vec![];
    r.as_reader().take((max + 1) as u64).read_to_end(&mut raw)?;
    ensure!(raw.len() <= max, "oversize request");
    Ok(serde_json::from_slice(&raw)?)
}
fn gateway(g: Gateway) -> Result<()> {
    let mut guard = ImageReader::start(&g.image)?;
    // A published guard narrows an independently authenticated upstream read.
    // Its owner configures the recipient directory and upstream credentials.
    ensure!(
        !guard.published || g.upstream_namespace.is_some(),
        "published gateway requires restricted upstream"
    );
    let mut endpoint = String::new();
    let mut bearer = String::new();
    let mut https = None;
    if g.upstream_unix.is_some() {
        ensure!(
            g.config.is_none() && g.ca.is_none() && g.cert.is_none() && g.key.is_none(),
            "choose one upstream transport"
        );
    } else {
        let cfg = std::fs::read_to_string(g.config.context("HTTPS config required")?)?;
        let mut lines = cfg.lines();
        endpoint = lines
            .next()
            .context("endpoint required")?
            .trim()
            .trim_end_matches('/')
            .into();
        bearer = lines.next().context("bearer required")?.trim().into();
        ensure!(
            endpoint.starts_with("https://") && !bearer.is_empty(),
            "HTTPS identity required"
        );
        let ca = reqwest::Certificate::from_pem(&std::fs::read(g.ca.context("CA required")?)?)?;
        let mut identity = std::fs::read(g.cert.context("certificate required")?)?;
        identity.extend_from_slice(&std::fs::read(g.key.context("key required")?)?);
        https = Some(
            reqwest::blocking::Client::builder()
                .add_root_certificate(ca)
                .identity(reqwest::Identity::from_pem(&identity)?)
                .redirect(reqwest::redirect::Policy::none())
                .timeout(Duration::from_secs(60))
                .build()?,
        );
    }
    ensure!(!g.socket.exists(), "gateway socket already exists");
    let server =
        tiny_http::Server::http_unix(&g.socket).map_err(|e| anyhow::anyhow!(e.to_string()))?;
    std::fs::set_permissions(&g.socket, std::fs::Permissions::from_mode(0o660))?;
    for mut r in server.incoming_requests() {
        if r.method() != &tiny_http::Method::Post
            || !matches!(r.url(), "/identity" | "/search" | "/resolve")
        {
            reply(r, 403, json!({"error":"read-only gateway"}));
            continue;
        }
        let input = match body(&mut r, 65536) {
            Ok(v) => v,
            Err(_) => {
                reply(r, 400, json!({"error":"invalid read request"}));
                continue;
            }
        };
        let result = (|| -> Result<Value> {
            guard.pin()?;
            let binding = guard.binding.clone();
            if r.url() == "/identity" {
                ensure!(input == json!({}), "invalid identity request");
                return Ok(json!({"authorization":binding}));
            }
            let object = input.as_object().context("read object required")?;
            if r.url() == "/resolve" {
                ensure!(
                    object.len() == 2
                        && object.contains_key("response")
                        && input["authorization"] == binding,
                    "invalid resolution request"
                );
                return guard.call(json!({"op":"resolve_response", "response":input["response"]}));
            }

            ensure!(
                object.len() == 3
                    && object.contains_key("query")
                    && object.contains_key("limit")
                    && object.contains_key("authorization"),
                "invalid read fields"
            );
            ensure!(input["authorization"] == binding, "authorization differs");
            let query = input["query"]
                .as_str()
                .filter(|q| !q.trim().is_empty())
                .context("query required")?;
            let limit = input["limit"]
                .as_u64()
                .filter(|n| (1..=32).contains(n))
                .context("invalid limit")?;
            let restriction = match &g.upstream_namespace {
                Some(namespace) => {
                    Some(guard.call(json!({"op":"search_restriction","authority":namespace}))?)
                }
                None => None,
            };
            let mut request = json!({"keywords":[query],"limit":limit});
            if let Some(value) = &restriction {
                request["restriction"] = value.clone();
            }
            let result = if let Some(path) = &g.upstream_unix {
                unix_post(path, "/v1/memory/search", &request)?
            } else {
                let response = https
                    .as_ref()
                    .unwrap()
                    .post(format!("{endpoint}/v1/memory/search"))
                    .bearer_auth(&bearer)
                    .json(&request)
                    .send()?;
                ensure!(
                    response.status() == reqwest::StatusCode::OK,
                    "upstream rejected"
                );
                let mut raw = vec![];
                response.take((16 << 20) + 1).read_to_end(&mut raw)?;
                ensure!(raw.len() <= 16 << 20, "upstream response too large");
                serde_json::from_slice(&raw)?
            };
            if let Some(value) = &restriction {
                ensure!(
                    result.get("restriction") == Some(value),
                    "upstream did not enforce restriction"
                );
            }
            guard.call(json!({"op":"authorize_response","response":result}))?;
            guard.pin()?;
            ensure!(
                guard.binding == binding,
                "authorization changed during upstream read"
            );
            Ok(result)
        })();
        match result {
            Ok(v) => reply(r, 200, v),
            Err(_) => reply(r, 403, json!({"error":"authorized read unavailable"})),
        }
    }
    Ok(())
}
fn read_check(c: Connection) -> Result<()> {
    let mut source = c.open()?;
    for line in std::io::stdin().lock().lines() {
        let v: Value = serde_json::from_str(&line?)?;
        let result = match v["op"].as_str() {
            Some("begin") => source.begin().map(|b| json!({"authorization":b})),
            Some("native_search") => source.native_search(
                v["query"].as_str().context("query")?,
                v["limit"].as_u64().context("limit")? as usize,
            ),
            Some("search") => source.search(
                v["query"].as_str().context("query")?,
                v["limit"].as_u64().context("limit")? as usize,
            ),
            _ => Err(anyhow::anyhow!("unsupported operation")),
        };
        let value = match result {
            Ok(v) => v,
            Err(e) => {
                json!({"error":"read unavailable","denied":e.downcast_ref::<aimee_qwen::transport::Denied>().is_some()})
            }
        };
        let (admitted, local_ready) = source.state();
        println!(
            "{}",
            json!({"result":value,"admitted":admitted,"local_ready":local_ready})
        );
    }
    Ok(())
}

#[cfg(feature = "torch")]
#[derive(clap::Args)]
struct Serve {
    /// Research-only bounded native snapshot; enables explicit offline preparation.
    #[arg(long, conflicts_with = "prepared_memory")]
    compact_working_root: Option<PathBuf>,
    /// Synchronize complete native bank readiness for latency measurement.
    #[arg(long)]
    measure_native_ready: bool,
    /// Strict ahead-of-time native store; no model encoding on a serving miss.
    #[arg(long, requires = "prepared_model_revision")]
    prepared_memory: Option<PathBuf>,
    /// Close unused prepared artifact handles after this many idle seconds.
    #[arg(long, default_value_t = 60)]
    prepared_idle_seconds: u64,
    /// Immutable checkpoint revision used when preparing this store.
    #[arg(long, requires = "prepared_memory")]
    prepared_model_revision: Option<String>,
    /// Enable bounded research-only encoding/position diagnostics.
    #[arg(long)]
    enable_memory_diagnostics: bool,
    /// Permit experimental independently encoded memory records.
    #[arg(long)]
    enable_record_encoding: bool,
    #[command(flatten)]
    connection: Connection,
    #[arg(long)]
    model: PathBuf,
    #[arg(long)]
    placement: Option<PathBuf>,
    #[arg(long, default_value_t = 18793)]
    port: u16,
    #[arg(long, default_value_t = 4)]
    memory_limit: usize,
    #[arg(long, default_value_t = 2048)]
    max_memory_tokens: usize,
    #[arg(long, default_value_t = 0)]
    encoding_cache_mib: usize,
    #[arg(long)]
    trace_dir: PathBuf,
    #[arg(long)]
    int8: bool,
}
#[cfg(feature = "torch")]
#[derive(clap::Args)]
struct Probe {
    #[arg(long)]
    model: PathBuf,
    #[arg(long)]
    input: PathBuf,
    #[arg(long)]
    output: PathBuf,
    #[arg(long)]
    int8: bool,
}
#[cfg(feature = "torch")]
#[derive(clap::Args)]
struct PrepareMemory {
    #[command(flatten)]
    runtime: Serve,
    /// JSON array of {query, expected_refs}; records are read through Aimee.
    #[arg(long)]
    requests: PathBuf,
    #[arg(long)]
    record_encoding: bool,
}
#[cfg(feature = "torch")]
fn prepared_identity(args: &Serve) -> Result<String> {
    use sha2::{Digest, Sha256};
    let revision = args
        .prepared_model_revision
        .as_ref()
        .context("pinned model revision required")?;
    ensure!(
        revision.len() >= 40 && revision.bytes().all(|x| x.is_ascii_hexdigit()),
        "immutable model revision required"
    );
    let mut hash = Sha256::new();
    hash.update(b"aimee-native-codec-v1");
    hash.update(revision.as_bytes());
    hash.update([u8::from(args.int8)]);
    for file in ["config.json", "tokenizer.json"] {
        hash.update(std::fs::read(args.model.join(file))?);
    }
    Ok(format!("{:x}", hash.finalize()))
}
#[cfg(feature = "torch")]
fn prepare_memory(args: PrepareMemory) -> Result<()> {
    use aimee_qwen::{adapter::Adapter, model::Model, prepared_memory::Store, tokens::Tokens};
    let runtime = &args.runtime;
    let identity = prepared_identity(runtime)?;
    let path = runtime
        .prepared_memory
        .as_ref()
        .context("prepared-memory store required")?;
    let _guard = tch::no_grad_guard();
    tch::set_num_threads(8);
    let model = Model::load(&runtime.model, runtime.placement.as_deref(), runtime.int8)?;
    let tokenizer = Tokens::load(&runtime.model.join("tokenizer.json"))?;
    let mut adapter = Adapter::new(
        Box::new(runtime.connection.open()?),
        runtime.memory_limit,
        runtime.max_memory_tokens,
        0,
    );
    adapter.prepared_store = Some(Store::open(path, &identity, true)?);
    adapter.preparation_mode = true;
    let requests: Vec<Value> = serde_json::from_slice(&std::fs::read(&args.requests)?)?;
    for request in requests {
        let query = request["query"]
            .as_str()
            .context("preparation query required")?;
        let expected = request["expected_refs"]
            .as_array()
            .context("expected record refs required")?;
        ensure!(!expected.is_empty(), "empty preparation selection");
        adapter.expected_preparation_refs = Some(expected.clone());
        let mut state = adapter.begin(false, false)?;
        state.record_encoding = args.record_encoding;
        adapter.recall(
            &model,
            &tokenizer,
            &mut state,
            query,
            "offline_preparation",
            vec![],
        )?;
        let refs: Vec<_> = state
            .facts
            .iter()
            .map(|f| f["memory_ref"].clone())
            .collect();
        ensure!(
            &refs == expected,
            "offline preparation omitted or changed selected records"
        );
        adapter.check_generation(&state.binding)?;
        println!(
            "{}",
            json!({"query":query,"records":refs,"encodings":state.encodings,"events":state.events})
        );
    }
    Ok(())
}

#[cfg(any(feature = "torch", test))]
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Message {
    role: String,
    content: String,
}
#[cfg(any(feature = "torch", test))]
fn memory_before_prompt(input: &Value) -> bool {
    // Explicit false is a diagnostic-only legacy control, checked by the server
    // before execution. Normal requests always use disjoint native positions.
    input["memory_before_prompt"].as_bool().unwrap_or(true)
}
// Exact text-only, no-tools, enable_thinking=false subset of this checkpoint's
// installed template. Memory never enters this formatter. Its hash is pinned.
#[cfg(any(feature = "torch", test))]
fn chat(messages: &[Message]) -> Result<String> {
    let mut s = String::new();
    ensure!(!messages.is_empty(), "messages required");
    let mut user = false;
    for (i, m) in messages.iter().enumerate() {
        let text = m.content.trim();
        match m.role.as_str() {
            "system" => {
                ensure!(i == 0, "system must be first");
                if !text.is_empty() {
                    s += &format!("<|im_start|>system\n{text}<|im_end|>\n");
                }
            }
            "user" => {
                user = true;
                s += &format!("<|im_start|>user\n{text}<|im_end|>\n");
            }
            "assistant" => {
                s += &format!("<|im_start|>assistant\n<think>\n\n</think>\n\n{text}<|im_end|>\n");
            }
            _ => anyhow::bail!("text chat role unsupported"),
        }
    }
    ensure!(user, "user required");
    s += "<|im_start|>assistant\n<think>\n\n</think>\n\n";
    Ok(s)
}
#[cfg(feature = "torch")]
fn write_private(path: &std::path::Path, value: &Value) -> Result<()> {
    use std::{io::Write, os::unix::fs::OpenOptionsExt};
    let mut f = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .mode(0o600)
        .open(path)?;
    f.write_all(&serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

#[cfg(feature = "torch")]
fn serve(args: Serve) -> Result<()> {
    use aimee_qwen::{
        adapter::Adapter,
        model::{Cache, Model},
        tokens::Tokens,
    };
    use sha2::{Digest, Sha256};
    use tch::IndexOp;
    let mut source = args.connection.open()?;
    source.begin()?;
    ensure!(
        (1..=32).contains(&args.memory_limit),
        "memory limit outside 1..32"
    );
    let template = std::fs::read(args.model.join("chat_template.jinja"))?;
    ensure!(
        format!("{:x}", Sha256::digest(template))
            == "c3cf9e34abf4f9e36c2d72165aa9c132d3e2a725b6c2586aaa3a8af9d7a81041",
        "unsupported chat template; validate its Rust formatting before use"
    );
    let _guard = tch::no_grad_guard();
    tch::set_num_threads(8);
    let model = Model::load(&args.model, args.placement.as_deref(), args.int8)?;
    let tokenizer = Tokens::load(&args.model.join("tokenizer.json"))?;
    let gen_cfg: Value =
        serde_json::from_slice(&std::fs::read(args.model.join("generation_config.json"))?)?;
    let eos: Vec<u32> = if let Some(a) = gen_cfg["eos_token_id"].as_array() {
        a.iter()
            .filter_map(|x| x.as_u64().map(|i| i as u32))
            .collect()
    } else {
        vec![gen_cfg["eos_token_id"].as_u64().context("EOS required")? as u32]
    };
    let mut adapter = Adapter::new(
        Box::new(source),
        args.memory_limit,
        args.max_memory_tokens,
        args.encoding_cache_mib
            .checked_mul(1 << 20)
            .context("cache budget overflow")?,
    );
    adapter.compact_root = args.compact_working_root.clone();
    if let Some(path) = &args.prepared_memory {
        adapter.prepared_store = Some(aimee_qwen::prepared_memory::Store::open_with_idle(
            path,
            &prepared_identity(&args)?,
            false,
            std::time::Duration::from_secs(args.prepared_idle_seconds),
        )?);
    }
    std::fs::create_dir_all(&args.trace_dir)?;
    std::fs::set_permissions(&args.trace_dir, std::fs::Permissions::from_mode(0o700))?;
    let server = tiny_http::Server::http(("127.0.0.1", args.port))
        .map_err(|e| anyhow::anyhow!(e.to_string()))?;
    println!(
        "{}",
        json!({"event":"ready","runtime":"rust-libtorch","adapter_trainable_parameters":0,"port":args.port})
    );
    let mut counter = 0u64;
    for mut request in server.incoming_requests() {
        if request.method() == &tiny_http::Method::Get && request.url() == "/health" {
            reply(
                request,
                200,
                json!({"status":"ready","runtime":"rust","adapter_trainable_parameters":0}),
            );
            continue;
        }
        if request.method() == &tiny_http::Method::Post
            && request.url() == "/aimee/prepare"
            && args.compact_working_root.is_some()
        {
            let result = (|| -> Result<Value> {
                let input = body(&mut request, 1_000_000)?;
                let query = input["query"].as_str().context("query required")?;
                let expected = input["expected_refs"]
                    .as_array()
                    .context("expected refs required")?;
                ensure!(!expected.is_empty(), "empty expected records");
                adapter.prepare_compact(&model, &tokenizer, query, expected)
            })();
            match result {
                Ok(v) => reply(request, 200, v),
                Err(e) => reply(request, 400, json!({"error":format!("{e:#}")})),
            }
            continue;
        }
        if request.method() != &tiny_http::Method::Post || request.url() != "/v1/chat/completions" {
            reply(request, 404, json!({"error":"not found"}));
            continue;
        }
        let input = match body(&mut request, 1_000_000) {
            Ok(v) => v,
            Err(_) => {
                reply(request, 400, json!({"error":"invalid request"}));
                continue;
            }
        };
        let parsed = (|| -> Result<(Vec<Message>, usize, bool, bool, bool, bool)> {
            let object = input.as_object().context("request object required")?;
            let allowed = [
                "model",
                "messages",
                "max_tokens",
                "temperature",
                "stream",
                "aimee_memory",
                "preload_memory",
                "decode_recall",
                "recall_mode",
                "reuse_encoding",
                "memory_encoding",
                "memory_encoding_granularity",
                "memory_diagnostics",
                "memory_position_shift",
                "memory_before_prompt",
                "diagnostic_candidates",
            ];
            ensure!(
                object.keys().all(|k| allowed.contains(&k.as_str())),
                "unsupported request fields"
            );
            ensure!(
                input.get("recall_mode").is_none_or(|v| v == "attention"),
                "only proven attention mode is supported"
            );
            ensure!(
                input
                    .get("temperature")
                    .is_none_or(|v| v.as_f64() == Some(0.)),
                "only greedy decoding supported"
            );
            ensure!(
                input.get("stream").is_none_or(|v| v == false),
                "streaming unsupported"
            );
            let flag = |name: &str, default: bool| -> Result<bool> {
                match input.get(name) {
                    None => Ok(default),
                    Some(v) => v.as_bool().context("boolean flag required"),
                }
            };
            ensure!(
                input.get("memory_encoding").is_none_or(|v| matches!(
                    v.as_str(),
                    Some("content" | "keyed" | "json" | "keyed-neutral" | "keyed-suffix")
                )),
                "unsupported memory encoding"
            );
            ensure!(
                input
                    .get("memory_encoding_granularity")
                    .is_none_or(|v| matches!(v.as_str(), Some("bank" | "record"))),
                "unsupported encoding granularity"
            );
            ensure!(
                input["memory_encoding_granularity"] != "record" || args.enable_record_encoding,
                "record encoding disabled"
            );
            let diagnostic_request = [
                "memory_diagnostics",
                "memory_position_shift",
                "memory_before_prompt",
                "diagnostic_candidates",
            ]
            .iter()
            .any(|k| input.get(*k).is_some())
                || matches!(
                    input["memory_encoding"].as_str(),
                    Some("keyed-neutral" | "keyed-suffix")
                );
            ensure!(
                !diagnostic_request || args.enable_memory_diagnostics,
                "memory diagnostics disabled"
            );
            ensure!(
                input
                    .get("memory_diagnostics")
                    .is_none_or(|v| v.as_u64().is_some_and(|n| n <= 32)),
                "invalid diagnostic step limit"
            );
            ensure!(
                input
                    .get("memory_position_shift")
                    .is_none_or(|v| v.as_i64().is_some_and(|n| (-8192..=8192).contains(&n))),
                "invalid rotary shift"
            );
            flag("memory_before_prompt", true)?;
            if let Some(candidates) = input.get("diagnostic_candidates") {
                let candidates = candidates.as_array().context("candidate array required")?;
                ensure!(
                    candidates.len() <= 16
                        && candidates
                            .iter()
                            .all(|x| x.as_str().is_some_and(|s| !s.is_empty() && s.len() <= 128)),
                    "invalid diagnostic candidates"
                );
            }
            let messages: Vec<Message> = serde_json::from_value(input["messages"].clone())?;
            chat(&messages)?;
            let max = input
                .get("max_tokens")
                .map(|v| v.as_u64().context("integer max_tokens required"))
                .transpose()?
                .unwrap_or(128);
            ensure!((1..=512).contains(&max), "invalid max_tokens");
            Ok((
                messages,
                max as usize,
                flag("aimee_memory", true)?,
                flag("preload_memory", true)?,
                flag("decode_recall", true)?,
                flag("reuse_encoding", true)?,
            ))
        })();
        let (messages, max, enabled, preload, decode, reuse) = match parsed {
            Ok(v) => v,
            Err(_) => {
                reply(request, 400, json!({"error":"unsupported chat request"}));
                continue;
            }
        };
        counter += 1;
        let started = std::time::Instant::now();
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos();
        let id = format!("rust-{stamp}-{counter}");
        let mut state = None;
        let result = (|| -> Result<(String, Value)> {
            let prompt_text = chat(&messages)?;
            let prompt = tokenizer.encode(&prompt_text)?;
            ensure!(prompt.len() <= 8192, "prompt exceeds experimental bound");
            let native_ready_started = std::time::Instant::now();
            let mut native_ready_ns = None;
            state = if enabled {
                Some(adapter.begin(decode, reuse)?)
            } else {
                None
            };
            if let Some(s) = state.as_mut() {
                s.record_encoding = input["memory_encoding_granularity"] == "record";
                s.diagnostic_steps = input["memory_diagnostics"].as_u64().unwrap_or(0) as usize;
                s.position_shift = input["memory_position_shift"].as_i64().unwrap_or(0);
                s.before_prompt = memory_before_prompt(&input);
                s.encoding_format = input
                    .get("memory_encoding")
                    .and_then(Value::as_str)
                    .unwrap_or("content")
                    .to_owned();
            }
            if enabled && preload {
                let query = &messages
                    .iter()
                    .rev()
                    .find(|m| m.role == "user")
                    .unwrap()
                    .content;
                adapter.recall(
                    &model,
                    &tokenizer,
                    state.as_mut().unwrap(),
                    query,
                    "prompt_preload",
                    vec![],
                )?;
            }
            if args.measure_native_ready && enabled && preload {
                state.as_ref().unwrap().prepare_ready(&model)?;
                native_ready_ns = Some(native_ready_started.elapsed().as_nanos());
            }
            let mut cache = Cache::new(model.config.num_hidden_layers);
            let mut next = prompt.clone();
            let mut generated = vec![];
            let mut finish_reason = "length";
            let mut logit_trace = vec![];
            for _ in 0..max {
                let logits = if let Some(s) = state.as_mut() {
                    adapter.forward(&model, &tokenizer, &next, &mut cache, s)?
                } else {
                    model.forward(&next, &mut cache, None)?
                };
                if generated.len() < input["memory_diagnostics"].as_u64().unwrap_or(0) as usize {
                    let lp = logits
                        .i((0, -1, ..))
                        .to_kind(tch::Kind::Float)
                        .log_softmax(-1, tch::Kind::Float);
                    let (values, indices) = lp.topk(10, -1, true, true);
                    let values = Vec::<f32>::try_from(values.to_device(tch::Device::Cpu))?;
                    let indices = Vec::<i64>::try_from(indices.to_device(tch::Device::Cpu))?;
                    let top:Vec<Value>=indices.iter().zip(values).map(|(id,logp)|json!({"id":id,"text":tokenizer.decode(&[*id as u32],false).unwrap_or_default(),"logp":logp})).collect();
                    let mut candidates = vec![];
                    for candidate in input["diagnostic_candidates"]
                        .as_array()
                        .into_iter()
                        .flatten()
                    {
                        let ids = tokenizer.encode(candidate.as_str().unwrap())?;
                        if let Some(id) = ids.first() {
                            candidates.push(json!({"text":candidate,"first_token":id,"logp":lp.double_value(&[*id as i64])}));
                        }
                    }
                    logit_trace
                        .push(json!({"step":generated.len(),"top":top,"candidates":candidates}));
                }
                let token = logits.i((0, -1, ..)).argmax(-1, false).int64_value(&[]) as u32;
                if eos.contains(&token) {
                    finish_reason = "stop";
                    break;
                }
                generated.push(token);
                next = vec![token];
            }
            let answer = tokenizer.decode(&generated, true)?;
            if let Some(s) = state.as_ref() {
                adapter.check_generation(&s.binding)?;
            }
            let trace = json!({"native_ready_ns":native_ready_ns,"cache_transition":state.as_ref().map(|s|&s.cache_transition),"runtime":"rust-libtorch","id":id,"logit_trace":logit_trace,"attention_trace":state.as_ref().map(|s|&s.attention_trace),"generation_prompt":prompt_text,"prompt_token_ids":prompt,"generated_token_ids":generated,"memory_prompt_tokens":0,"publication":state.as_ref().map(|s|&s.binding),"memory_encoding":state.as_ref().map(|s|&s.encoding_format),"memory_encoding_granularity":state.as_ref().map(|s|if s.record_encoding {"record"} else {"bank"}),"memory_before_prompt":state.as_ref().map(|s|s.before_prompt),"memory_position_offset":state.as_ref().map(|s|s.bank_position_offset()),"answer":answer,"finish_reason":finish_reason,"elapsed_ms":started.elapsed().as_secs_f64()*1000.,"memory_encoding_passes":state.as_ref().map(|s|s.encodings).unwrap_or(0),"native_reads":state.as_ref().map(|s|s.native_reads).unwrap_or(0),"bank_residence":"layer_devices","native_bank_preparations":state.as_ref().map(|s|s.bank_preparations.get()),"native_bank_reuses":state.as_ref().map(|s|s.bank_reuses.get()),"native_bank_application_cpu_ns":state.as_ref().map(|s|s.bank_application_cpu_ns.get()),"recall_events":state.as_ref().map(|s|&s.events),"main_cache_length":cache.length});
            Ok((answer, trace))
        })();
        match result {
            Ok((answer, trace)) => {
                let counts = (
                    trace["prompt_token_ids"].as_array().unwrap().len(),
                    trace["generated_token_ids"].as_array().unwrap().len(),
                );
                write_private(&args.trace_dir.join(format!("{id}.json")), &trace)?;
                reply(
                    request,
                    200,
                    json!({"id":id,"object":"chat.completion","model":"qwen-aimee-rust","choices":[{"index":0,"message":{"role":"assistant","content":answer},"finish_reason":trace["finish_reason"]}],"usage":{"prompt_tokens":counts.0,"completion_tokens":counts.1,"total_tokens":counts.0+counts.1}}),
                );
            }
            Err(e) => {
                write_private(
                    &args.trace_dir.join(format!("{id}-failed.json")),
                    &json!({"id":id,"status":"failed","recall_events":state.as_ref().map(|s|&s.events)}),
                )?;
                eprintln!("request failed: {e}");
                reply(
                    request,
                    502,
                    json!({"error":"native memory request failed"}),
                );
            }
        }
    }
    Ok(())
}

#[cfg(feature = "torch")]
fn probe(p: Probe) -> Result<()> {
    use aimee_qwen::{
        adapter::tensor_values,
        model::{Bank, Cache, Model},
    };
    let _guard = tch::no_grad_guard();
    tch::set_num_threads(2);
    let m = Model::load(&p.model, None, p.int8)?;
    let v: Value = serde_json::from_slice(&std::fs::read(&p.input)?)?;
    let ids: Vec<u32> = serde_json::from_value(v["prompt"].clone())?;
    let memory: Vec<u32> = serde_json::from_value(v["memory"].clone())?;
    let mut cache = Cache::new(m.config.num_hidden_layers);
    let baseline = m.forward(&ids, &mut cache, None)?;
    let mut main = Cache::new(m.config.num_hidden_layers);
    let bank = m.encode(&memory)?;
    let native = m.forward(
        &ids,
        &mut main,
        Some(&mut |_, i, _, _, _, _| Ok(bank.get(&i).map(Bank::copy))),
    )?;
    let decode: Vec<u32> = serde_json::from_value(v["decode"].clone())?;
    let next = m.forward(
        &decode,
        &mut main,
        Some(&mut |_, i, _, _, _, _| Ok(bank.get(&i).map(Bank::copy))),
    )?;
    write_private(
        &p.output,
        &json!({"baseline":tensor_values(&baseline)?,"native":tensor_values(&native)?,"decode":tensor_values(&next)?,"main_cache_length":main.length,"bank_layers":bank.keys().collect::<Vec<_>>()}),
    )
}
fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Gateway(g) => gateway(g),
        Command::ReadCheck(c) => read_check(c),
        #[cfg(feature = "torch")]
        Command::Serve(s) => serve(s),
        #[cfg(feature = "torch")]
        Command::Probe(p) => probe(p),
        #[cfg(feature = "torch")]
        Command::PrepareMemory(p) => prepare_memory(p),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn normal_request_uses_disjoint_native_memory_positions() {
        assert!(memory_before_prompt(&json!({})));
        assert!(memory_before_prompt(&json!({"aimee_memory": true})));
        assert!(!memory_before_prompt(
            &json!({"memory_before_prompt": false})
        ));
    }
    #[test]
    fn chat_memory_never_added() {
        let m = vec![Message {
            role: "user".into(),
            content: " hi ".into(),
        }];
        assert_eq!(
            chat(&m).unwrap(),
            "<|im_start|>user\nhi<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
        );
    }
    #[test]
    fn misplaced_system_rejected() {
        let m = vec![
            Message {
                role: "user".into(),
                content: "hi".into(),
            },
            Message {
                role: "system".into(),
                content: "later".into(),
            },
        ];
        assert!(chat(&m).is_err());
    }
}
