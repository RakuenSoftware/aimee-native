"""CPU platform extension selects the owner-bound backend without upstream edits."""
from vllm.platforms.cpu import CpuPlatform
from vllm.v1.attention.backends.registry import AttentionBackendEnum
class AimeeCPUPlatform(CpuPlatform):
    @classmethod
    def get_attn_backend_cls(cls,selected_backend,attn_selector_config,num_heads=None):
        if selected_backend==AttentionBackendEnum.CUSTOM:
            return 'aimee_vllm.cpu_backend.AimeeCPUBackend'
        return super().get_attn_backend_cls(selected_backend,attn_selector_config,num_heads)
