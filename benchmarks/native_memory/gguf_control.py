#!/usr/bin/env python3
"""Independent installed-GGUF text control; NOT the HF Stage A teacher score."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18092)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    source = json.loads((args.fixtures / "memories.json").read_text())
    memories = {m["memory_id"]: m for m in source["memories"]}
    heldout = json.loads((args.fixtures / "heldout.json").read_text())
    examples = heldout[:6] + [e for e in heldout if e["category"] == "composition"][:2]
    url = f"http://127.0.0.1:{args.port}"
    command = [args.server, "-m", args.model, "--host", "127.0.0.1", "--port", str(args.port),
               "-ngl", "99", "--tensor-split", "1,1", "-c", "2048", "--parallel", "1", "-t", "8",
               "--jinja", "--flash-attn", "on", "--no-webui"]
    (args.out / "configuration.json").write_text(json.dumps(dict(command=command,
        purpose="GGUF text/no-memory sanity control only; not comparable to HF native training",
        fixture_sha256=hashlib.sha256((args.fixtures / "heldout.json").read_bytes()).hexdigest()), indent=2)+"\n")
    records = []
    with (args.out / "server.log").open("w") as log:
        server = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 240
            while True:
                if server.poll() is not None:
                    raise RuntimeError("temporary server exited; inspect server.log")
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except (urllib.error.URLError, TimeoutError):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("temporary server startup")
                time.sleep(1)
            with (args.out / "answers.jsonl").open("x") as answers:
                for example in examples:
                    for mode in ("none", "text"):
                        prompt = example["query"]
                        if mode == "text":
                            prompt += "\n\nAuthoritative memory:\n" + "\n".join(memories[mid]["content"] for mid in example["memory_ids"])
                        payload = dict(messages=[dict(role="system", content="Answer using the available memory. Return only the requested value or values. If unknown, return unknown."),
                                                 dict(role="user", content=prompt)],
                                       temperature=0, seed=4817, max_tokens=64, cache_prompt=False,
                                       chat_template_kwargs=dict(enable_thinking=False))
                        request = urllib.request.Request(url + "/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
                        with urllib.request.urlopen(request, timeout=240) as response:
                            result = json.load(response)
                        choice = result["choices"][0]
                        answer = choice["message"].get("content") or ""
                        record = dict(id=example["id"], category=example["category"], mode=mode,
                            expected=example["answer"], answer=answer, response=result,
                            correct=choice["finish_reason"] == "stop" and " ".join(answer.casefold().split()) == " ".join(example["answer"].casefold().split()))
                        records.append(record)
                        answers.write(json.dumps(record)+"\n")
                        answers.flush()
                        print(json.dumps({k:v for k,v in record.items() if k != "response"}), flush=True)
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
    report = {mode: dict(correct=sum(r["correct"] for r in records if r["mode"] == mode), total=sum(r["mode"] == mode for r in records)) for mode in ("none", "text")}
    (args.out / "summary.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    main()
