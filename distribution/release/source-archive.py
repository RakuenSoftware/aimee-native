#!/usr/bin/env python3
"""Export an immutable Git commit to a reproducible, uncompressed source ZIP.

Fixed headers and ZIP_STORED avoid platform, timestamp and compression-library
differences. Read Git objects, never working-tree files or ignored operator data.
"""
import argparse
from pathlib import Path
import re
import subprocess
import zipfile


def archive(repo, revision, output, prefix):
    if not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', revision):
        raise ValueError('a full immutable commit ID is required')
    if not re.fullmatch(r'[A-Za-z0-9._-]+/', prefix):
        raise ValueError('a single archive root is required')
    git = ['git', '-C', str(repo), '--no-replace-objects']
    subprocess.run([*git, 'cat-file', '-e', revision + '^{commit}'], check=True)
    tree = subprocess.check_output([*git, 'ls-tree', '-rz', revision])
    with output.open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as result:
        with subprocess.Popen([*git, 'cat-file', '--batch'], stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE) as objects:
            for row in tree.split(b'\0'):
                if not row:
                    continue
                header, name = row.split(b'\t', 1)
                mode, kind, oid = header.split()
                if kind != b'blob' or mode not in (b'100644', b'100755', b'120000'):
                    raise ValueError('unsupported Git object in source export')
                name = name.decode('utf-8')
                if name.startswith('/') or any(p in ('.', '..') for p in name.split('/')):
                    raise ValueError('unsafe source filename')
                objects.stdin.write(oid + b'\n')
                objects.stdin.flush()
                actual, object_type, size = objects.stdout.readline().split()
                if actual != oid or object_type != b'blob':
                    raise ValueError('unexpected source object')
                size = int(size)
                info = zipfile.ZipInfo(prefix + name, (1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = int(mode, 8) << 16
                info.file_size = size
                with result.open(info, 'w') as target:
                    remaining = size
                    while remaining:
                        block = objects.stdout.read(min(1024 * 1024, remaining))
                        if not block:
                            raise ValueError('truncated Git object')
                        target.write(block)
                        remaining -= len(block)
                if objects.stdout.read(1) != b'\n':
                    raise ValueError('invalid Git object framing')
            objects.stdin.close()
            if objects.wait():
                raise RuntimeError('Git source export failed')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--revision', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--prefix', required=True)
    a = p.parse_args()
    archive(a.repo, a.revision, a.output, a.prefix)
