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
    if std::env::var_os("CARGO_FEATURE_VLLM_PORTABLE").is_some() {
        let python = std::env::var_os("PYTHON_INCLUDE").expect("PYTHON_INCLUDE required for portable bridge build");
        println!("cargo:rerun-if-env-changed=PYTHON_INCLUDE");
        println!("cargo:rerun-if-changed=native/vllm_runtime_portable.cpp");
        cc::Build::new().cpp(true).file("native/vllm_runtime_portable.cpp").include(python)
            .flag_if_supported("-std=c++17").flag_if_supported("-fvisibility=hidden")
            .compile("aimee_vllm_runtime_portable");
    } else if std::env::var_os("CARGO_FEATURE_VLLM_RUNTIME").is_some() {
        let root = std::path::PathBuf::from(std::env::var_os("LIBTORCH").expect("LIBTORCH required for runtime bridge"));
        let python = std::env::var_os("PYTHON_INCLUDE").expect("PYTHON_INCLUDE required for runtime bridge");
        let codec = std::env::var_os("AIMEE_CODEC_OBJECT").expect("AIMEE_CODEC_OBJECT required for pinned GPU decoder");
        let hip = std::env::var_os("HIP_LIB_DIR").expect("HIP_LIB_DIR required for pinned GPU runtime");
        println!("cargo:rerun-if-env-changed=AIMEE_CODEC_OBJECT");
        println!("cargo:rerun-if-changed={}", std::path::PathBuf::from(&codec).display());
        println!("cargo:rerun-if-env-changed=HIP_LIB_DIR");
        println!("cargo:rustc-link-arg={}", std::path::PathBuf::from(codec).display());
        println!("cargo:rustc-link-search=native={}", std::path::PathBuf::from(hip).display());
        println!("cargo:rustc-link-lib=dylib=amdhip64");
        println!("cargo:rerun-if-env-changed=PYTHON_INCLUDE");
        println!("cargo:rerun-if-changed=native/vllm_runtime.cpp");
        cc::Build::new().cpp(true).file("native/vllm_runtime.cpp")
            .include(root.join("include")).include(root.join("include/torch/csrc/api/include")).include(python)
            .flag_if_supported("-std=c++20").flag_if_supported("-fvisibility=hidden")
            .define("_GLIBCXX_USE_CXX11_ABI", std::env::var("LIBTORCH_CXX11_ABI").unwrap_or_else(|_| "1".into()).as_str())
            .compile("aimee_vllm_runtime");
        println!("cargo:rustc-link-search=native={}", root.join("lib").display());
        for name in ["torch_python", "torch_cpu", "c10"] { println!("cargo:rustc-link-lib=dylib={name}"); }
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
