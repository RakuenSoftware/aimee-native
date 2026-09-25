//! Signed local release lifecycle plus the real CLI/container invocation boundary.
//! The container executable is a capture fixture, not GPU/clean-host certification.
use aimee_native_launcher as native;
use ed25519_dalek::{Signer, SigningKey};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, fs, io::Cursor, os::unix::fs::PermissionsExt, process::Command};

fn release(sequence: u64) -> (Vec<u8>, Vec<u8>, [u8; 32], BTreeMap<String, Vec<u8>>) {
    let image = format!(
        "registry.example/aimee@sha256:{}",
        format!("{sequence:x}").repeat(64)
    );
    let files: BTreeMap<String, Vec<u8>> = BTreeMap::from([
        ("bin/aimee-vllm".into(), b"fixture".to_vec()),
        ("lib/libaimee_native.so".into(), b"fixture".to_vec()),
        ("models/config.json".into(), b"{}".to_vec()),
        (
            "models/model.gguf".into(),
            b"fixture weights, not a model".to_vec(),
        ),
        (
            "runtime/image.json".into(),
            serde_json::to_vec(&native::RuntimeImage {
                image,
                model_config: "models/config.json".into(),
            })
            .unwrap(),
        ),
    ]);
    let m = native::Manifest {
        schema: 1,
        sequence,
        version: format!("fixture-{sequence}"),
        platform: native::platform(),
        model: "fixture".into(),
        runtime: "vllm".into(),
        runtime_commit: "a".repeat(40),
        abi: native::ABI,
        engine: "bin/aimee-vllm".into(),
        model_file: "models/model.gguf".into(),
        library: "lib/libaimee_native.so".into(),
        gates: native::GATES.iter().map(|g| g.to_string()).collect(),
        artifacts: files
            .iter()
            .map(|(p, b)| native::Artifact {
                path: p.clone(),
                bytes: b.len() as u64,
                sha256: hex::encode(Sha256::digest(b)),
                executable: p == "bin/aimee-vllm",
            })
            .collect(),
    };
    let raw = serde_json::to_vec(&m).unwrap();
    let key = SigningKey::from_bytes(&[23; 32]); // ephemeral fixture identity only
    let signature = key.sign(&raw).to_bytes().to_vec();
    (raw, signature, key.verifying_key().to_bytes(), files)
}
#[test]
fn signed_install_upgrade_rollback_and_container_invocation() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("client");
    native::connect(&root, "https://aimee.example", "fixture-secret").unwrap();
    let config: native::Config =
        serde_json::from_slice(&fs::read(root.join("config.json")).unwrap()).unwrap();
    fs::create_dir_all(&config.memory_root).unwrap();
    let catalog = config.memory_root.join("catalog.json");
    fs::write(&catalog, b"{}").unwrap();
    fs::write(
        root.join("serving.json"),
        serde_json::to_vec(
            &serde_json::json!({"catalog":catalog,"recipient":"fixture","host_memory_budget":1024}),
        )
        .unwrap(),
    )
    .unwrap();
    let bin = temp.path().join("bin");
    fs::create_dir(&bin).unwrap();
    fs::write(
        bin.join("podman"),
        b"#!/bin/sh\nprintf '%s\\n' \"$@\" > \"$CAPTURE\"\ntest -z \"${AIMEE_TOKEN+x}\"\n",
    )
    .unwrap();
    fs::set_permissions(bin.join("podman"), fs::Permissions::from_mode(0o700)).unwrap();
    let capture = temp.path().join("argv");
    for seq in [1, 2] {
        let (raw, sig, key, files) = release(seq);
        native::install(&root, &raw, &sig, &key, |p| {
            Ok(Box::new(Cursor::new(files[p].clone())))
        })
        .unwrap();
    }
    let launch = || {
        let output = Command::new(env!("CARGO_BIN_EXE_aimee-native"))
            .args(["--root", root.to_str().unwrap(), "run", "--port", "8123"])
            .env("PATH", format!("{}:/usr/bin:/bin", bin.display()))
            .env("CAPTURE", &capture)
            .env("AIMEE_TOKEN", "must-not-inherit")
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        fs::read_to_string(&capture).unwrap()
    };
    let args = launch();
    assert!(args.contains(&format!("@sha256:{}", "2".repeat(64))));
    assert!(!args.contains("fixture-secret"));
    assert!(!args.contains(config.token_file.to_str().unwrap()));
    assert!(
        !args
            .lines()
            .any(|a| a == format!("{}:{}:rw", root.display(), root.display()))
    );
    let runtime: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("runtime.json")).unwrap()).unwrap();
    assert_eq!(runtime["serve"]["port"], 8123);
    assert_eq!(runtime["library"], "/opt/aimee/libaimee_native.so");
    assert!(
        runtime["gguf_weights"]
            .as_str()
            .unwrap()
            .ends_with("models/model.gguf")
    );
    native::rollback(&root).unwrap();
    assert!(launch().contains(&format!("@sha256:{}", "1".repeat(64))));
    let before = native::active(&root).unwrap();
    let (raw, mut sig, key, files) = release(3);
    sig[0] ^= 1;
    assert!(
        native::install(&root, &raw, &sig, &key, |p| Ok(Box::new(Cursor::new(
            files[p].clone()
        ))))
        .is_err()
    );
    assert_eq!(native::active(&root).unwrap().current, before.current);
    assert_eq!(native::active(&root).unwrap().high_water_sequence, 2);
}
