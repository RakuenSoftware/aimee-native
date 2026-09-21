fn main() {
    println!("cargo:rerun-if-env-changed=LIBTORCH");
    // torch-sys detects NVIDIA libraries but does not retain ROCm's kernel
    // registration library. Keep its constructors when linking a ROCm build.
    if std::env::var_os("CARGO_FEATURE_TORCH").is_some()
        && let Some(root) = std::env::var_os("LIBTORCH")
    {
        let hip = std::path::PathBuf::from(root).join("lib/libtorch_hip.so");
        if hip.exists() {
            println!("cargo:rustc-link-arg=-Wl,--push-state,--no-as-needed");
            println!("cargo:rustc-link-arg={}", hip.display());
            println!("cargo:rustc-link-arg=-Wl,--pop-state");
        }
    }
}
