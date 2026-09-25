"""Registration only. No upstream mutations, patches, or model-class replacement."""
def register():
    from importlib.metadata import version
    from packaging.version import Version
    if Version(version("vllm")).base_version != "0.30.0":
        raise RuntimeError("Aimee requires the validated vLLM 0.30.0 interface")
    from vllm.v1.attention.backends.registry import AttentionBackendEnum, register_backend
    register_backend(AttentionBackendEnum.CUSTOM, "aimee_vllm.backend.AimeeAttentionBackend")
    import os
    if os.environ.get("AIMEE_GGUF_ENABLE") == "1":
        from .gguf_loader import register as register_gguf
        register_gguf()
