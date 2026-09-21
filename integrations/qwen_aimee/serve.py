#!/usr/bin/env python3
"""Serial experimental Qwen serving process directly connected to Aimee.

Normal /v1/chat/completions requests, no benchmark fixture or trained adapter.
Private loopback listener; expose only through authenticated infrastructure.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import time
import uuid

import torch
from transformers import AutoConfig, AutoTokenizer, Qwen3_5ForCausalLM, Qwen3_5ForConditionalGeneration

from profiling import TokenClock, synchronize
from aimee_client import AimeeClient, AimeeError
from local_image import AimeeImageClient
from local_first import LocalFirstClient
from gateway_client import ReadGatewayClient
from frozen_int8 import quantize_frozen_linears
from placement import place
from qwen_adapter import QwenAimeeAdapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--placement", type=Path, required=True)
    parser.add_argument("--aimee-config", type=Path)
    parser.add_argument("--aimee-ca", type=Path)
    parser.add_argument("--memory-image", type=Path)
    parser.add_argument("--image-reader", type=Path)
    parser.add_argument("--image-scope", action="append", default=[])
    parser.add_argument("--image-view")
    parser.add_argument("--aimee-client-cert", type=Path)
    parser.add_argument("--aimee-client-key", type=Path)
    parser.add_argument("--port", type=int, default=18792)
    parser.add_argument("--memory-limit", type=int, default=4)
    parser.add_argument("--trace-dir", type=Path, required=True)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--host-memory", action="store_true")
    parser.add_argument("--keepalive", action="store_true")
    parser.add_argument("--compare-backends", action="store_true",
                        help="explicit serial research comparison: allow both configured readers")
    parser.add_argument("--read-gateway", type=Path)
    parser.add_argument("--local-first", action="store_true")
    parser.add_argument("--read-authority")
    parser.add_argument("--encoding-cache-mib", type=int, default=0)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--authority-key", type=Path)
    parser.add_argument("--subject")
    parser.add_argument("--policy-epoch")
    args = parser.parse_args()
    if not args.memory_image or not args.read_gateway or any((args.aimee_config,args.aimee_ca,args.aimee_client_cert,args.aimee_client_key)):
        parser.error("native serving requires an authorized image and read gateway; no authority credentials in the model process")
    args.trace_dir.mkdir(parents=True, exist_ok=True)
    clients = {}
    if args.memory_image:
        if not args.image_reader or ((args.aimee_config or args.aimee_ca) and not (args.compare_backends or args.local_first)):
            parser.error("local image requires --image-reader and excludes remote Aimee credentials")
        client = AimeeImageClient(args.image_reader, args.memory_image,
                                  scopes=args.image_scope, view=args.image_view, authorization=args.authorization,
                                  authority_key=args.authority_key, subject=args.subject, policy_epoch=args.policy_epoch)
        client.begin_request()  # Verify the signed image before loading model weights.
        clients["local"] = client
    if args.read_gateway:
        if args.aimee_config or args.aimee_ca:
            parser.error("read gateway excludes direct Aimee credentials")
        client = ReadGatewayClient(args.read_gateway, expected_authorization=clients["local"].authorization_id)
        clients["remote"] = client
    elif not args.memory_image or args.compare_backends or args.local_first:
        if not args.aimee_config or not args.aimee_ca:
            parser.error("provide --memory-image/--image-reader or remote Aimee config/CA")
        client = AimeeClient(args.aimee_config, args.aimee_ca,
                            cert_file=args.aimee_client_cert, key_file=args.aimee_client_key, keepalive=args.keepalive)
        clients["remote"] = client
    if args.local_first:
        if "local" not in clients or "remote" not in clients or not args.read_authority:
            parser.error("local-first requires an image, an Aimee read connection, and --read-authority")
        client = LocalFirstClient(clients["local"], clients["remote"], args.read_authority)
        clients = {"local_first": client, **({"remote": clients["remote"]} if args.compare_backends else {})}
    if args.memory_image and not args.read_gateway:
        parser.error("authorized local memory requires the authorization-bound read gateway")
    config = AutoConfig.from_pretrained(args.model, trust_remote_code=False)
    cls = {"qwen3_5": Qwen3_5ForConditionalGeneration, "qwen3_5_text": Qwen3_5ForCausalLM}[config.model_type]
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=False)
    model = cls.from_pretrained(args.model, dtype=torch.bfloat16,
        attn_implementation="eager", trust_remote_code=False).eval().requires_grad_(False)
    count = quantize_frozen_linears(model)
    placement = json.loads(args.placement.read_text())
    hooks = place(model, placement)
    adapter = QwenAimeeAdapter(model, tokenizer, client, input_device=placement["embedding"],
                               memory_limit=args.memory_limit, host_memory=bool(args.memory_image) or args.host_memory, profile=args.profile, encoding_cache_bytes=args.encoding_cache_mib * (1 << 20))
    print(json.dumps({"event": "ready", "port": args.port, "quantized_base_linears": count,
                      "adapter_trainable_parameters": 0, "legacy_checkpoint_loaded": False}), flush=True)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_json(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"status": "ready", "model": "qwen-aimee-direct", "adapter_trainable_parameters": 0})
            else:
                self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/v1/chat/completions":
                self.send_json(404, {"error": "not found"})
                return
            request_id = uuid.uuid4().hex
            started = time.perf_counter()
            trace = {"id": request_id}
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("request body size unsupported")
                payload = json.loads(self.rfile.read(size))
                if any(k in payload for k in ("authorization", "subject", "scope", "scopes", "policy_epoch", "memory_image", "aimee_config")):
                    raise ValueError("authorization is fixed by trusted service configuration")
                backend = payload.get("memory_backend", next(iter(clients)))
                if backend not in clients:
                    raise ValueError("unconfigured memory backend")
                adapter.client = clients[backend]
                trace["memory_backend"] = backend
                if payload.get("stream"):
                    raise ValueError("prototype supports non-streaming requests")
                messages = payload["messages"]
                if not isinstance(messages, list) or not messages or not all(
                    isinstance(m, dict) and m.get("role") in ["system", "user", "assistant"]
                    and isinstance(m.get("content"), str) for m in messages):
                    raise ValueError("text chat messages required")
                query = next((m["content"] for m in reversed(messages) if m["role"] == "user"), None)
                if not query or not query.strip():
                    raise ValueError("user query required")
                use_memory = payload.get("aimee_memory", True)
                if type(use_memory) is not bool:
                    raise ValueError("aimee_memory must be boolean")
                recall_mode = payload.get("recall_mode", "attention")
                if recall_mode not in ("attention", "native_tokens", "native", "prefill"):
                    raise ValueError("unsupported recall_mode")
                preload_memory = payload.get("preload_memory", recall_mode == "attention")
                if type(preload_memory) is not bool or (preload_memory and recall_mode != "attention"):
                    raise ValueError("preload_memory requires a boolean and attention mode")
                decode_recall = payload.get("decode_recall", True)
                if type(decode_recall) is not bool:
                    raise ValueError("decode_recall must be boolean")
                decode_cue_boundary = payload.get("decode_cue_boundary", "whitespace")
                if decode_cue_boundary not in ("whitespace", "every_token"):
                    raise ValueError("unsupported decode_cue_boundary")
                max_tokens = payload.get("max_tokens", 128)
                if type(max_tokens) is not int or not 1 <= max_tokens <= 512:
                    raise ValueError("max_tokens must be in 1..512")
                if payload.get("temperature", 0) != 0:
                    raise ValueError("prototype uses deterministic greedy decoding")
                prompt = tokenizer.apply_chat_template(messages, tokenize=True,
                    add_generation_prompt=True, enable_thinking=False, return_dict=False)
                trace.update(query=query, prompt_token_ids=prompt, prompt_tokens=len(prompt),
                    prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                    generation_prompt=tokenizer.decode(prompt), memory_enabled=use_memory,
                    recall_mode=recall_mode, decode_recall=decode_recall,
                    preload_memory=use_memory and preload_memory)
                tensor = torch.tensor([prompt], device=placement["embedding"])
                eos = model.generation_config.eos_token_id
                eos = [eos] if isinstance(eos, int) else eos
                from contextlib import nullcontext
                reuse_encoding = payload.get("reuse_native_states", True)
                if type(reuse_encoding) is not bool:
                    raise ValueError("reuse_native_states must be boolean")
                trace["reuse_native_states"] = reuse_encoding
                context = adapter.request(query if recall_mode == "prefill" else None,
                                          recall_mode=recall_mode,
                                          preload_query=query if preload_memory else None,
                                          decode_recall=decode_recall,
                                          decode_cue_boundary=decode_cue_boundary, reuse_encoding=reuse_encoding) if use_memory else nullcontext({})
                clock = TokenClock()
                with torch.inference_mode(), context as state:
                    generated = model.generate(input_ids=tensor, attention_mask=torch.ones_like(tensor),
                        do_sample=False, use_cache=True, max_new_tokens=max_tokens, eos_token_id=eos, streamer=clock,
                        pad_token_id=tokenizer.pad_token_id or eos[0], return_dict_in_generate=True)
                    ids = generated.sequences[0, len(prompt):].tolist()
                    output = tokenizer.decode(ids, skip_special_tokens=True)
                    trace.update({k: v for k, v in state.items() if k not in ("banks", "query")})
                    trace["generation_cache_tokens"] = generated.past_key_values.get_seq_length()
                trace["profile_events"] = adapter.profile.events if use_memory else []
                trace["local_first_events"] = getattr(adapter.client, "events", []) if use_memory else []
                trace["encoding_cache_bytes"] = adapter.encoding_cache_size
                trace["token_seconds"] = [t-started for t in clock.times]
                trace["ttft_seconds"] = clock.times[0]-started if clock.times else None
                trace["intertoken_seconds"] = [b-a for a,b in zip(clock.times, clock.times[1:])]
                trace.update(answer=output, generated_ids=ids, terminated=bool(ids and ids[-1] in eos),
                    added_memory_prompt_tokens=0, adapter_trainable_parameters=0,
                    seconds=time.perf_counter()-started, status="complete")
                (args.trace_dir / (request_id + ".json")).write_text(json.dumps(trace, indent=2)+"\n")
                self.send_json(200, {"id": request_id, "object": "chat.completion", "model": "qwen-aimee-direct",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": output},
                                 "finish_reason": "stop" if trace["terminated"] else "length"}],
                    "usage": {"prompt_tokens": len(prompt), "completion_tokens": len(ids), "total_tokens": len(prompt)+len(ids)},
                    "aimee": {"requested": bool(state.get("requested")),
                              "request": state.get("request"),
                              "returned_memory_ids": [f["id"] for f in state.get("aimee_response", {}).get("facts", [])],
                              "native_reads": state.get("native_reads", 0),
                              "recall_calls": len(state.get("recall_events", [])),
                              "preload_calls": sum(e["origin"] == "prompt_preload" for e in state.get("recall_events", [])),
                              "native_recall_calls": sum(e["origin"] == "qwen_attention_query" for e in state.get("recall_events", [])),
                              "bank_memory_ids": [f["id"] for f in state.get("resident_facts", {}).values()],
                              "memory_encoding_passes": state.get("memory_encoding_passes", 0),
                              "memory_tokens_encoded": state.get("memory_tokens_encoded", 0),
                              "local_hits": sum(not e["remote"] for e in trace["local_first_events"]),
                              "remote_calls": sum(e["remote"] for e in trace["local_first_events"]) if backend == "local_first" else len(state.get("recall_events", [])),
                              "memory_encoding_tokens": state.get("memory_encoding_tokens", 0)}})
            except Exception as exc:
                # Preserve the failed stage without exposing credentials.
                if "state" in locals():
                    trace.update({k: v for k, v in state.items() if k not in ("banks", "query")})
                trace.update(status="error", error_type=type(exc).__name__, seconds=time.perf_counter()-started)
                (args.trace_dir / (request_id + ".json")).write_text(json.dumps(trace, indent=2)+"\n")
                print(json.dumps({"event": "request_error", "id": request_id, "error_type": type(exc).__name__}), flush=True)
                self.send_json(502 if isinstance(exc, AimeeError) else 400 if isinstance(exc, (ValueError, KeyError)) else 500,
                               {"id": request_id, "error": type(exc).__name__})

    try:
        HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
    finally:
        adapter.close()
        for client in clients.values():
            client.close()
        for hook in hooks:
            hook.remove()


if __name__ == "__main__":
    main()
