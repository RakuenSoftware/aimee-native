import re
import torch
from vllm.v1.attention.backends.triton_attn import TritonAttentionBackend, TritonAttentionImpl, TritonAttentionMetadataBuilder
from vllm.v1.attention.backend import AttentionCGSupport, AttentionType
from . import state
import os
from .kernel import native_attention

class AimeeMetadataBuilder(TritonAttentionMetadataBuilder):
    _cudagraph_support = AttentionCGSupport.NEVER
    def build(self, common_prefix_len, common_attn_metadata, fast_build=False):
        # Cached text blocks remain usable, but the upstream cascade kernel
        # cannot combine a shared text prefix with separate native banks.
        # The normal paged path still reads prefix-cache hits from block_table.
        result = super().build(0, common_attn_metadata, fast_build)
        if (state.CURRENT is None or not state.CURRENT.requests or
                state.CURRENT.upstream_only_without_slots(common_attn_metadata)):
            result.aimee_ids = None  # upstream startup profiling, no real request
        else:
            result.aimee_ids = state.CURRENT.request_ids(common_attn_metadata)
        return result

class AimeeAttentionBackend(TritonAttentionBackend):
    supported_kv_cache_dtypes = ['auto', 'bfloat16']
    @staticmethod
    def get_name(): return 'CUSTOM'
    @staticmethod
    def get_impl_cls(): return AimeeAttentionImpl
    @staticmethod
    def get_builder_cls(): return AimeeMetadataBuilder
    @classmethod
    def supports_sink(cls): return False
    @classmethod
    def supports_rswa(cls): return False

class AimeeAttentionImpl(TritonAttentionImpl):
    def fused_rope_kvcache_supported(self): return False
    def forward(self, layer, query, key, value, kv_cache, attn_metadata, output,
                output_scale=None, output_block_scale=None):
        ids = getattr(attn_metadata, 'aimee_ids', None)
        table = None
        if ids is not None:
            name = layer.layer_name
            match = re.search(r'(?:^|\.)layers\.(\d+)\.', name)
            if not match:
                raise RuntimeError('native layer identity unavailable')
            table = state.CURRENT.memory_table(ids, int(match.group(1)), query.dtype,
                                              self.num_kv_heads, self.head_size)
        if table is None:
            return super().forward(layer,query,key,value,kv_cache,attn_metadata,output,
                                   output_scale,output_block_scale)
        if (self.attn_type != AttentionType.DECODER or self.alibi_slopes is not None
            or self.sinks is not None or output_scale is not None or output_block_scale is not None
            or self._is_per_token_head_quant or attn_metadata.use_cascade
            or bool(attn_metadata.mm_prefix_range)
            or not isinstance(attn_metadata.causal,bool) or not attn_metadata.causal):
            raise RuntimeError('unsupported native attention configuration')
        if kv_cache.dtype != query.dtype or query.dtype != torch.bfloat16:
            raise RuntimeError('native release currently requires BF16 attention/cache')
        kp,vp,lengths,_owners=table
        view=output.view(-1,self.num_heads,self.head_size)
        plan = state.CURRENT.owner.attention_plan({
            'requests': len(ids),
            'heads': self.num_heads,
            'kv_heads': self.num_kv_heads,
            'head_size': self.head_size,
            'block_size': kv_cache.shape[2],
            'max_query_len': attn_metadata.max_query_len,
            'scale': self.scale,
            'window': self.sliding_window[0],
            'soft_cap': self.logits_soft_cap,
        })
        args = (
            query,kv_cache,view,attn_metadata.query_start_loc,attn_metadata.seq_lens,
            attn_metadata.block_table,kp,vp,lengths,
            query.stride(0),query.stride(1),kv_cache.stride(0),kv_cache.stride(1),kv_cache.stride(2),
            view.stride(0),view.stride(1),attn_metadata.block_table.stride(0),
            plan['heads'],plan['kv_heads'],plan['head_size'],plan['block_size'],plan['scale'],
            plan['window'],plan['soft_cap'],plan['tile'],plan['width'],
            )
        kernel = native_attention[tuple(plan['grid'])](*args,num_warps=plan['num_warps'])
        if os.environ.get("AIMEE_EXPORT_KERNELS"):
            from .export_kernel import export
            export(os.environ["AIMEE_EXPORT_KERNELS"] + "/" + str(state.CURRENT.rank),kernel,args)
        return output
