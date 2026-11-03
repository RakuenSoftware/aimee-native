"""Lazy out-of-tree CPU platform registration for the explicit CPU profile."""
import os
def register():
    if os.environ.get('AIMEE_VLLM_CPU_CONFIG'):
        return 'aimee_vllm.cpu_platform.AimeeCPUPlatform'
    return None
