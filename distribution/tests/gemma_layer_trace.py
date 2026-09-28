"""Read-only first-prefill activation trace via a supported worker extension.

Raw vectors remain private diagnostic artifacts; publish comparison metrics,
not these tensors. Forward hooks observe outputs without changing them.
"""
import json
from pathlib import Path


class LayerTrace:
    def install_gemma_trace(self):
        self.aimee_diagnostic_trace = {}
        model = self.model_runner.model.language_model.model
        def capture(name):
            def hook(module, args, output):
                if name in self.aimee_diagnostic_trace:
                    return
                value = output[0] if isinstance(output, tuple) else output
                self.aimee_diagnostic_trace[name] = value.detach().reshape(-1, value.shape[-1])[-1].float().cpu().tolist()
            return hook
        model.embed_tokens.register_forward_hook(capture('embedding'))
        for i, layer in enumerate(model.layers):
            layer.register_forward_hook(capture('layer.' + str(i)))
        model.norm.register_forward_hook(capture('norm'))
        return {'rank': self.rank, 'layers': len(model.layers)}

    def get_gemma_trace(self):
        return {'rank': self.rank, 'trace': self.aimee_diagnostic_trace}


def main():
    from vllm import LLM, SamplingParams
    output = Path('/evidence/gpu-trace.json')
    assert not output.exists(), 'preserve previous trace'
    model = LLM(model='/model', dtype='bfloat16', tensor_parallel_size=2,
              max_model_len=4096, max_num_seqs=2, max_num_batched_tokens=256,
              gpu_memory_utilization=.85, enforce_eager=True,
              enable_prefix_caching=False, async_scheduling=False,
              disable_custom_all_reduce=True, load_format='aimee_gguf_unified',
              quantization='gguf',
              model_loader_extra_config={'gguf_weights': '/weights/gemma4-26b-q8.gguf'},
              limit_mm_per_prompt={'image': 0, 'audio': 0, 'video': 0},
              worker_extension_cls='gemma_layer_trace.LayerTrace')
    model.collective_rpc('install_gemma_trace', timeout=120)
    result = model.chat([{'role': 'user', 'content': 'Compute 17 + 25. Return only the integer.'}],
        SamplingParams(temperature=0, max_tokens=1, skip_special_tokens=False),
        chat_template_kwargs={'enable_thinking': False})[0]
    trace = model.collective_rpc('get_gemma_trace', timeout=120)
    output.write_text(json.dumps({'input_token_ids': result.prompt_token_ids,
        'answer': result.outputs[0].text, 'token_ids': result.outputs[0].token_ids,
        'workers': trace}) + '\n')


if __name__ == '__main__':
    main()
