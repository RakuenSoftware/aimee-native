"""Validation instrumentation only; all attention math delegates unchanged."""
import os,json
from pathlib import Path

def register():
    import aimee_gemma4_12b
    selected=os.environ['VLLM_PLUGINS']
    try:
        os.environ['VLLM_PLUGINS']='aimee_gemma4_12b'
        aimee_gemma4_12b.register()
    finally:os.environ['VLLM_PLUGINS']=selected
    from vllm.v1.attention.backends.registry import AttentionBackendEnum,register_backend
    register_backend(AttentionBackendEnum.CUSTOM,'integration_trace.TracingBackend')

from aimee_native_runtime.backend import AimeeAttentionBackend,AimeeAttentionImpl
class TracingBackend(AimeeAttentionBackend):
    @staticmethod
    def get_impl_cls():return TracingImpl
class TracingImpl(AimeeAttentionImpl):
    def forward(self,layer,query,key,value,kv_cache,attn_metadata,output,output_scale=None,output_block_scale=None):
        from aimee_native_runtime import state
        ids=getattr(attn_metadata,'aimee_ids',None)
        pins=[]
        if ids is not None:
            for rid in ids:
                p=state.CURRENT.requests[rid]
                if p.store is not None:
                    pins.append({'request_id':rid,'publication':p.publication,'publication_key':p.store.spec['key'],'publication_model':p.store.spec['model']})
        result=super().forward(layer,query,key,value,kv_cache,attn_metadata,output,output_scale,output_block_scale)
        # The unchanged implementation invokes native_attention iff a store
        # is selected. Record only successful returns, never startup/capture.
        if pins:
            record={'pid':os.getpid(),'layer':layer.layer_name,'query_rows':query.shape[0],'catalog_digest':state.CURRENT.catalog_digest,'pins':pins,'native_kernel_returned':True}
            with open(os.environ['GEMMA_INTEGRATION_TRACE'],'a') as f:f.write(json.dumps(record)+'\n')
        return result
