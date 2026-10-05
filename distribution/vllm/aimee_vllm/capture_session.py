"""Offline runtime observation and request ownership only; no model adapter."""
import torch
CURRENT = None

def raw_tensor(tensor):
    return tensor.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()


class CaptureSession:
    def begin(self, scheduler_output):
        if not scheduler_output.num_scheduled_tokens and not scheduler_output.scheduled_new_reqs:
            return  # Scheduler cleanup has no model forward or cache mutation.
        for req in scheduler_output.scheduled_new_reqs:
            if self.request is not None or list(req.prompt_token_ids) != self.tokens:
                raise RuntimeError('capture prompt/request identity mismatch')
            self.request = req.req_id
        if (self.request is None or set(scheduler_output.num_scheduled_tokens) != {self.request}
            or self.request in scheduler_output.finished_req_ids):
            raise RuntimeError('capture requires one uninterrupted prefill')

    def attention_chunk(self, layer, key, value, metadata):
        starts = metadata.query_start_loc.tolist()
        if len(starts) != 2 or starts[0] != 0:
            raise RuntimeError('capture attention request mapping mismatch')
        count = starts[1]
        parts = self.attention.setdefault(layer, ([], []))
        if sum(x.shape[0] for x in parts[0])+count > len(self.tokens):
            raise RuntimeError('capture crossed the prefix boundary')
        for target, tensor in zip(parts, (key, value)):
            if tensor.dtype != torch.bfloat16:
                raise RuntimeError('capture requires BF16 attention tensors')
            target.append(tensor[:count].detach().cpu().clone())

    def close(self):
        for hook in self.hooks:hook.remove()
        self.hooks.clear()
