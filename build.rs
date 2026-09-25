fn main() {
    if std::env::var_os("CARGO_FEATURE_NATIVE_CLIENT").is_some() || std::env::var_os("CARGO_FEATURE_VLLM_CLIENT").is_some() {
        println!("cargo:rustc-cdylib-link-arg=-Wl,--exclude-libs,ALL");
    }
    println!("cargo:rerun-if-env-changed=LIBTORCH");
    println!("cargo:rerun-if-env-changed=LIBTORCH_CXX11_ABI");
    println!("cargo:rerun-if-changed=native/prepared_transfer.cpp");
    if std::env::var_os("CARGO_FEATURE_TORCH").is_some() {
        let root = std::path::PathBuf::from(
            std::env::var_os("LIBTORCH").expect("LIBTORCH is required for native transfer bridge"),
        );
        cc::Build::new()
            .cpp(true)
            .file("native/prepared_transfer.cpp")
            .include(root.join("include"))
            .include(root.join("include/torch/csrc/api/include"))
            .flag_if_supported("-std=c++20")
            .flag_if_supported("-fvisibility=hidden")
            .define(
                "_GLIBCXX_USE_CXX11_ABI",
                std::env::var("LIBTORCH_CXX11_ABI")
                    .unwrap_or_else(|_| "1".into())
                    .as_str(),
            )
            .compile("aimee_prepared_transfer");
    }
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
