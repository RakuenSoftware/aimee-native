"""Exercise CLI train/save/reload/evaluate on tiny random Qwen, not 27B accuracy."""
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
    here = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="aimee-native-p0-smoke-") as directory:
        root = Path(directory)
        model_dir = root / "model"
        model = tiny_qwen()
        model.save_pretrained(model_dir)
        vocab = {"[PAD]": 0, "[BOS]": 1, "[EOS]": 2, "[UNK]": 3}
        for word in ["user", "assistant", "system", "amber", "violet", "teal", "silver", "crimson"]:
            vocab[word] = len(vocab)
        backend = Tokenizer(WordLevel(vocab, unk_token="[UNK]"))
        backend.pre_tokenizer = Whitespace()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, unk_token="[UNK]",
            bos_token="[BOS]", eos_token="[EOS]", pad_token="[PAD]")
        tokenizer.chat_template = "{% for message in messages %}{{ message['role'] }} {{ message['content'] }}[EOS]{% endfor %}{% if add_generation_prompt %}assistant {% endif %}"
        tokenizer.save_pretrained(model_dir)
        subprocess.run([sys.executable, str(here / "corpus.py"), "--count", "12", "--out", str(root / "fixtures")], check=True)
        common = ["--model", str(model_dir), "--fixtures", str(root / "fixtures"),
                  "--dtype", "float32", "--value-width", "32", "--attention-width", "16", "--k", "4",
                  "--bank-policy", "oracle", "--adapter-dtype", "float32"]
        subprocess.run([sys.executable, str(here / "run_p0.py"), "train", *common,
                        "--steps", "2", "--out", str(root / "train")], check=True)
        subprocess.run([sys.executable, str(here / "run_p0.py"), "evaluate", *common,
                        "--checkpoint", str(root / "train" / "adapter.pt"), "--eval-limit", "1",
                        "--max-new-tokens", "4", "--out", str(root / "eval")], check=True)
        report = json.loads((root / "eval" / "summary.json").read_text())
        assert report["checks"]["disabled_and_empty_parity"]
        assert report["checks"]["native_prompt_parity"]
        assert report["stage_a_accuracy_gate"] == "fail_or_incomplete"
        rows = [json.loads(line) for line in (root / "eval" / "evaluation.jsonl").read_text().splitlines()]
        assert len(rows) == 7
        assert next(r for r in rows if r["mode"] == "text")["added_prompt_tokens"] > 0
        print(json.dumps(dict(smoke="pass", train_steps=2, evaluated_arms=7,
                              pretrained_27b_tested=False)))


if __name__ == "__main__":
    main()
