"""Registration only. No upstream mutations, patches, or model-class replacement."""
def register():
    from .compatibility import check_interface
    check_interface()
    from vllm.v1.attention.backends.registry import AttentionBackendEnum, register_backend
    register_backend(AttentionBackendEnum.CUSTOM, "aimee_vllm.backend.AimeeAttentionBackend")
    import os
    if os.environ.get("AIMEE_GGUF_ENABLE") == "1":
        from .gguf_loader import register as register_gguf
        register_gguf()
