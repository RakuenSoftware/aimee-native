"""Exercise Aimee-source compilation/evaluation wiring on tiny random Qwen."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace
from transformers import PreTrainedTokenizerFast

from test_p0 import tiny_qwen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--aimee-record", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="aimee-source-smoke-") as directory:
        root = Path(directory)
        model_dir = root/"model"
        tiny_qwen().save_pretrained(model_dir)
        vocab = {"[PAD]":0, "[BOS]":1, "[EOS]":2, "[UNK]":3, "ultraviolet":4, "violet":5}
        backend = Tokenizer(WordLevel(vocab, unk_token="[UNK]"))
        backend.pre_tokenizer = Whitespace()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]",
            bos_token="[BOS]", eos_token="[EOS]", pad_token="[PAD]")
        tokenizer.chat_template = "{% for message in messages %}{{ message['role'] }} {{ message['content'] }}[EOS]{% endfor %}{% if add_generation_prompt %}assistant {% endif %}"
        tokenizer.save_pretrained(model_dir)
        def run(script, *arguments):
            subprocess.run([sys.executable, str(here/script), *map(str,arguments)], check=True)
        run("corpus.py", "--count", 100, "--out", root/"fixtures")
        run("run_p0.py", "train", "--model", model_dir, "--fixtures", root/"fixtures", "--out", root/"train",
            "--dtype", "float32", "--value-width", 32, "--attention-width", 16, "--bank-policy", "oracle", "--steps", 2)
        run("run_aimee_source.py", "--source", here, "--train", root/"train",
            "--aimee-record", args.aimee_record.resolve(), "--out", root/"evaluation", "--steps", 2)
        report = json.loads((root/"evaluation/summary.json").read_text())
        assert all(report["checks"].values())
        assert not report["speed_is_acceptance_gate"] and not report["text_parity_is_acceptance_gate"]
        assert len((root/"evaluation/evaluation.jsonl").read_text().splitlines())==36
        assert report["trainable_parameters"]==32
        print(json.dumps(dict(smoke="pass", real_aimee_memory_id=report["memory_id"], pretrained_27b_tested=False)))


if __name__=="__main__":
    main()
