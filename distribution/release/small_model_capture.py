"""Model binding for Gemma's shared-K/V observation; Rust owns the layer mapping."""
from aimee_native_runtime.attention_capture import AttentionPrefixCapture as SharedCapture


class AttentionPrefixCapture(SharedCapture):
    def attention_chunk(self, layer, key, value, metadata):
        if key is None or value is None:
            if key is not None or value is not None:
                raise RuntimeError('partial shared K/V observation')
            sources = self.adapter.description['kv_source_layers']
            if not 0 <= layer < len(sources):
                raise RuntimeError('shared K/V layer outside dedicated adapter')
            source = sources[layer]
            if source == layer or source not in self.attention:
                raise RuntimeError('shared K/V source was not captured')
            starts = metadata.query_start_loc.tolist()
            if len(starts) != 2 or starts[0] != 0:
                raise RuntimeError('shared K/V request mapping mismatch')
            parent = self.attention[source]
            own = self.attention.get(layer, ([], []))
            count = starts[1]
            for captured, earlier in zip(parent, own):
                if (not captured or captured[-1].shape[0] != count
                    or sum(t.shape[0] for t in captured) != sum(t.shape[0] for t in earlier) + count):
                    raise RuntimeError('shared K/V source chunk mismatch')
            key, value = parent[0][-1], parent[1][-1]
        return super().attention_chunk(layer, key, value, metadata)


def install():
    from aimee_native_runtime import attention_capture
    attention_capture.AttentionPrefixCapture = AttentionPrefixCapture
