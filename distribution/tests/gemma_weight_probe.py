"""Private read-only inspection through vLLM's supported worker extension.

Run against the failed Gemma Q8 artifact. No runtime weights or upstream code
are changed. This is a loading diagnostic, not a release-quality benchmark.
"""
import json
import hashlib
from pathlib import Path
import time


class WeightProbe:
    def inspect_gemma_weights(self):
        import torch
        model = self.model_runner.model
        rows = {}
        with torch.inference_mode():
            tensors = dict(model.named_parameters())
            tensors.update(dict(model.named_buffers()))
            for name, tensor in tensors.items():
                scalar = name.endswith('layer_scalar')
                selected = any(f'.layers.{i}.' in name for i in (0, 5, 29))
                embedding = name == 'language_model.model.embed_tokens.weight'
                if not scalar and not selected and not embedding:
                    continue
                if torch.nn.parameter.is_lazy(tensor):
                    rows[name] = {'uninitialized': True, 'class': type(tensor).__name__,
                                  'weight_type': getattr(tensor, 'weight_type', None)}
                    continue
                row = {'shape': list(tensor.shape), 'dtype': str(tensor.dtype),
                       'sample': tensor.detach().reshape(-1)[:8].cpu().tolist()}
                if tensor.dtype == torch.uint8 and name.endswith(('weight', '_weight')):
                    row['sha256'] = hashlib.sha256(tensor.detach().cpu().contiguous().numpy()).hexdigest()
                if tensor.numel() <= 8192 and tensor.is_floating_point():
                    value = tensor.detach().float()
                    row.update(finite=bool(torch.isfinite(value).all()),
                               mean=float(value.mean()), min=float(value.min()),
                               max=float(value.max()))
                if hasattr(tensor, 'weight_type'):
                    row['weight_type'] = tensor.weight_type
                rows[name] = row
        return {'rank': self.rank, 'tensors': rows}


def main():
    from vllm import LLM, SamplingParams
    output = Path('/evidence')
    assert not (output / 'weights.json').exists(), 'preserve earlier diagnostic'
    started = time.monotonic()
    llm = LLM(model='/model', dtype='bfloat16', tensor_parallel_size=2,
              max_model_len=4096, max_num_seqs=2, max_num_batched_tokens=256,
              gpu_memory_utilization=.85, enforce_eager=True,
              enable_prefix_caching=False, async_scheduling=False,
              disable_custom_all_reduce=True, load_format='aimee_gguf_unified',
              quantization='gguf',
              model_loader_extra_config={'gguf_weights': '/weights/gemma4-26b-q8.gguf'},
              limit_mm_per_prompt={'image': 0, 'audio': 0, 'video': 0},
              worker_extension_cls='gemma_weight_probe.WeightProbe')
    rows = llm.collective_rpc('inspect_gemma_weights', timeout=120)
    (output / 'weights.json').write_text(json.dumps(rows, indent=2) + '\n')
    result = llm.chat([{'role': 'user', 'content': 'Compute 17 + 25. Return only the integer.'}],
                      SamplingParams(temperature=0, max_tokens=16, skip_special_tokens=False),
                      chat_template_kwargs={'enable_thinking': False})
    answers = [{'text': r.outputs[0].text, 'token_ids': r.outputs[0].token_ids} for r in result]
    (output / 'result.json').write_text(json.dumps({'status': 'complete',
        'scope': 'Read-only Q8 loading diagnostic; no native memory',
        'seconds': time.monotonic() - started, 'answers': answers}, indent=2) + '\n')


if __name__ == '__main__':
    main()
