"""Deterministic native reads from exact tokens observed by model.forward.

No chat-message parsing, generated command protocol, answer/entity rules, or
trainable parameters. Prefill uses the runtime prefix; decode uses a rolling
window of model-generated tokens. Aimee alone selects the returned records.
"""
import weakref

from torch import nn


class RuntimeCueRead(nn.Module):
    def __init__(self, adapter, after_block=1):
        super().__init__()
        self._adapter = weakref.ref(adapter)
        self.after_block = after_block

    def forward(self, hidden):
        adapter = self._adapter()
        state = adapter.active
        if state is None or adapter.encoding or state["recall_mode"] != "native_tokens":
            return hidden
        frame = state["runtime_frame"]
        if frame["step"] == state.get("last_read_step"):
            return hidden
        state["last_read_step"] = frame["step"]
        if frame["phase"] == "decode" and not state["decode_recall"]:
            return hidden
        # This is the token stream already consumed by the transformer, not
        # text reconstructed from activations or a query supplied by the caller.
        stream = state["runtime_prefill_ids"] if frame["phase"] == "prefill" else state["runtime_decode_ids"]
        ids = stream[-state["cue_window_tokens"]:]
        decoded = adapter.tokenizer.decode(ids, skip_special_tokens=True)
        # Do not search halfway through an identifier. This lexical boundary
        # applies to every word/domain equally and uses no expected answer.
        if (frame["phase"] == "decode" and state["decode_cue_boundary"] == "whitespace"
                and (not decoded or not decoded[-1].isspace())):
            return hidden
        query = decoded.strip()
        if not query:
            return hidden
        event = {"after_block": self.after_block, "phase": frame["phase"],
                 "step": frame["step"], "cue_token_ids": list(ids),
                 "forward_token_ids": list(frame["input_ids"]),
                 "hidden_shape": list(hidden.shape)}
        adapter.recall(query, origin="qwen_native_runtime_cues",
                       query_source="runtime_token_stream", event=event)
        return hidden
