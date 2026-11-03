#!/usr/bin/env python3
"""Validate local links in the maintained documentation entry points.

Archived evidence/report bodies retain historical paths and are excluded.
External URLs and links into separately owned sibling repositories are not
network-checked by this command.
"""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
PAGES = (
    'README.md', 'CONTRIBUTING.md', 'SECURITY.md', 'docs/README.md',
    'docs/usage.md', 'docs/aimee-compatibility.md', 'docs/development.md',
    'docs/public-release.md', 'docs/research-index.md', 'docs/rust-runtime.md',
    'distribution/README.md', 'distribution/vllm/README.md',
    'distribution/vllm/MODEL_PLUGINS.md', 'memory/sparse/README.md',
    'dependencies/README.md', 'docs/validation/aimee-v1.0.2-20261103.md',
)


def main():
    failures = []
    checked = 0
    for name in PAGES:
        page = ROOT / name
        text = re.sub(r'```.*?```', '', page.read_text(), flags=re.S)
        for match in re.finditer(r'\]\(([^\s)]+)(?:\s+"[^"\n]*")?\)', text):
            target = urlsplit(match.group(1).strip('<>'))
            if target.scheme or target.netloc or not target.path:
                continue
            path = (page.parent / unquote(target.path)).resolve()
            if not path.is_relative_to(ROOT):
                continue
            checked += 1
            if not path.exists():
                line = text.count('\n', 0, match.start()) + 1
                failures.append(f'{name}:{line}: missing {target.path}')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'{len(PAGES)} maintained pages, {checked} local links verified')


if __name__ == '__main__':
    main()
