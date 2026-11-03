#!/usr/bin/env python3
"""Publish verified assets through GitHub Actions' repository-scoped gh token.

Uploads to a draft, downloads and verifies every byte, then publishes. A retry
can complete the same draft; it never replaces mismatched assets or published
release contents. No operator signing key is used by CI.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

REPO = 'RakuenSoftware/aimee-native'


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def validate_metadata(release, tag, commit, expected):
    if release['tag_name'] != tag or release['target_commitish'] != commit:
        raise ValueError('existing release has a different target')
    names = set()
    for asset in release['assets']:
        name = asset['name']
        if name not in expected or name in names:
            raise ValueError('unexpected or duplicate release asset')
        names.add(name)
        if asset['size'] != expected[name]['bytes']:
            raise ValueError('existing asset size mismatch: ' + name)
        if asset.get('digest') and asset['digest'] != 'sha256:' + expected[name]['sha256']:
            raise ValueError('existing asset digest mismatch: ' + name)
    return names


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--public-key', type=Path, required=True)
    p.add_argument('--notes', type=Path, required=True)
    p.add_argument('--version', required=True)
    a = p.parse_args()
    tag = 'v' + a.version
    if os.environ.get('GITHUB_REPOSITORY') != REPO or os.environ.get('GITHUB_REF') != 'refs/tags/' + tag:
        raise ValueError('publication requires the canonical repository tag workflow')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    assert subprocess.check_output(['git', 'rev-parse', 'refs/tags/' + tag + '^{commit}'], text=True).strip() == commit
    verifier = Path(__file__).with_name('release-bundle.py')
    def verify(folder):
        subprocess.run(['python3', str(verifier), 'verify', '--bundle', str(folder),
            '--public-key', str(a.public_key), '--expected-version', a.version], check=True)
    verify(a.bundle)
    expected = {f.name: {'bytes': f.stat().st_size, 'sha256': sha(f)} for f in a.bundle.iterdir()}
    def lookup():
        # The tag endpoint only promises published releases. The authenticated
        # list also returns drafts, which matters after an interrupted upload.
        pages = json.loads(subprocess.check_output(['gh', 'api',
            'repos/' + REPO + '/releases?per_page=100', '--paginate', '--slurp']))
        matches = [r for page in pages for r in page if r['tag_name'] == tag]
        if len(matches) > 1:
            raise ValueError('duplicate releases for tag')
        return matches[0] if matches else None
    release = lookup()
    if release is None:
        subprocess.run(['gh', 'release', 'create', tag, '--repo', REPO, '--verify-tag',
            '--target', commit, '--draft', '--title', 'Aimee Native ' + a.version,
            '--notes-file', str(a.notes)], check=True)
        release = lookup()
        if release is None:
            raise RuntimeError('created draft was not returned by GitHub')
    existing = validate_metadata(release, tag, commit, expected)
    with tempfile.TemporaryDirectory(prefix='aimee-release-download-') as folder:
        folder = Path(folder)
        if existing:
            subprocess.run(['gh', 'release', 'download', tag, '--repo', REPO, '--dir', str(folder)], check=True)
            for name in existing:
                if sha(folder / name) != expected[name]['sha256']:
                    raise ValueError('existing asset bytes mismatch: ' + name)
        missing = sorted(set(expected) - existing)
        if missing:
            if not release['draft']:
                raise ValueError('published release is incomplete; refusing to replace it')
            subprocess.run(['gh', 'release', 'upload', tag, '--repo', REPO,
                            *(str(a.bundle / n) for n in missing)], check=True)
            command = ['gh', 'release', 'download', tag, '--repo', REPO, '--dir', str(folder)]
            for name in missing:
                command += ['--pattern', name]
            subprocess.run(command, check=True)
        verify(folder)
    if release['draft']:
        subprocess.run(['gh', 'release', 'edit', tag, '--repo', REPO, '--draft=false', '--latest'], check=True)
    print('Published and download-verified: https://github.com/' + REPO + '/releases/tag/' + tag)


if __name__ == '__main__':
    main()
