"""Live, installed-wheel check for publication changes during an active stream.

Requires a dedicated canary recipient with the three documented release facts.
The caller supplies an already connected client root and a serving config. This
test changes no authority records: two queries select different signed canary
publications, and the client broker updates the local catalogue between them.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--launcher", default="aimee-native")
parser.add_argument("--repeat-selection", type=int, default=30)
args = parser.parse_args()
assert args.repeat_selection > 0

config = json.loads(args.config.read_text())
endpoint = f"http://127.0.0.1:{config['serve']['port']}"
model = config["model"]
catalog = args.root / "memory" / "catalog.json"
question_a = (
    "What are the native release verification vault code, project, and drink? "
    "Repeat the three values in 100 numbered sentences."
)
question_b = "What is the native release verification project?"
results = {"scope": "live Aimee canary, two distinct approved publications"}


def snapshot():
    raw = catalog.read_bytes()
    data = json.loads(raw)
    return {"digest": hashlib.sha256(raw).hexdigest(),
            "publications": sorted(data["publications"])}


def request(question, *, stream=False, max_tokens=300):
    body = {"model": model, "messages": [{"role": "user", "content": question}],
            "temperature": 0, "max_tokens": max_tokens,
            "chat_template_kwargs": {"enable_thinking": False}, "stream": stream}
    req = Request(endpoint + "/v1/chat/completions", json.dumps(body).encode(),
                  {"Content-Type": "application/json"})
    started = time.monotonic()
    try:
        with urlopen(req, timeout=240) as response:
            if not stream:
                data = json.load(response)
                return {"status": response.status,
                        "answer": data["choices"][0]["message"]["content"],
                        "seconds": round(time.monotonic() - started, 3)}
            pieces = []
            first = None
            events = 0
            for line in response:
                if not line.startswith(b"data: "):
                    continue
                raw = line[6:].strip()
                if raw == b"[DONE]":
                    break
                event = json.loads(raw)
                part = "".join(choice.get("delta", {}).get("content") or ""
                               for choice in event.get("choices", []))
                if part:
                    pieces.append(part)
                    events += 1
                    if first is None:
                        first = time.monotonic()
                        first_token.set()
            return {"status": response.status, "answer": "".join(pieces),
                    "events": events, "first_token_seconds": round(first - started, 3) if first else None,
                    "seconds": round(time.monotonic() - started, 3)}
    except HTTPError as exc:
        return {"status": exc.code, "error": exc.read().decode(errors="replace")[:300],
                "seconds": round(time.monotonic() - started, 3)}


server_log = args.output.with_suffix(".server.log")
args.output.parent.mkdir(parents=True, exist_ok=True)
first_token = threading.Event()
with server_log.open("x") as log:
    child = subprocess.Popen([args.launcher, "--root", str(args.root), "serve", "--config",
                              str(args.config)], stdout=log, stderr=subprocess.STDOUT)
    try:
        for _ in range(1200):
            if child.poll() is not None:
                raise RuntimeError(f"server exited before ready: {child.returncode}")
            try:
                with urlopen(endpoint + "/v1/models", timeout=1):
                    break
            except Exception:
                time.sleep(1)
        else:
            raise TimeoutError("server startup exceeded 1200 seconds")
        results["initial"] = snapshot()
        warmup = request(question_a, max_tokens=100)
        results["warmup"] = {k: v for k, v in warmup.items() if k != "answer"}
        assert warmup["status"] == 200 and "28461" in warmup["answer"]
        results["after_first_publication"] = snapshot()
        old = {}

        def consume_old():
            old.update(request(question_a, stream=True, max_tokens=200))
            old["ended_at"] = time.monotonic()

        thread = threading.Thread(target=consume_old)
        thread.start()
        assert first_token.wait(120), "old publication did not stream a token"
        new_started_at = time.monotonic()
        attempts = []
        for _ in range(4):
            replacement = request(question_b, max_tokens=100)
            attempts.append({k: v for k, v in replacement.items() if k != "answer"})
            if replacement["status"] == 200:
                break
            if replacement["status"] != 503:
                break
            time.sleep(1)
        thread.join(timeout=240)
        assert not thread.is_alive(), "old stream did not terminate"
        results["overlap"] = new_started_at < old["ended_at"]
        results["old_stream"] = {k: v for k, v in old.items() if k not in ("answer", "ended_at")}
        results["replacement"] = {k: v for k, v in replacement.items() if k != "answer"}
        results["replacement_attempts"] = attempts
        results["after_replacement"] = snapshot()
        assert results["overlap"], "new selection did not overlap an old stream"
        assert old["status"] == 200 and all(x in old["answer"].lower()
                                            for x in ("28461", "juniper", "hibiscus"))
        assert replacement["status"] == 200 and "juniper" in replacement["answer"].lower()
        assert results["after_first_publication"]["digest"] != results["after_replacement"]["digest"]
        assert results["after_first_publication"]["publications"] != results["after_replacement"]["publications"]
        followups = [request(question_b, max_tokens=100)
                     for _ in range(args.repeat_selection)]
        results["followup"] = {
            "correct": sum(r["status"] == 200 and "juniper" in r["answer"].lower()
                           for r in followups),
            "total": len(followups),
            "statuses": [r["status"] for r in followups],
            "median_response_seconds": statistics.median(r["seconds"] for r in followups),
        }
        assert results["followup"]["correct"] == args.repeat_selection
        results["status"] = "passed"
    except Exception as exc:
        results["status"] = "failed"
        results["error"] = repr(exc)
    finally:
        child.terminate()
        try:
            child.wait(timeout=60)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        args.output.write_text(json.dumps(results, indent=2) + "\n")
print(json.dumps({k: v for k, v in results.items() if k not in ("initial", "after_first_publication", "after_replacement")}))
if results["status"] != "passed":
    raise SystemExit(1)
