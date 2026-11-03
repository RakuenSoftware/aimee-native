#!/usr/bin/env python3
"""Create and verify an offline Ed25519-signed Aimee Native release bundle.

Verification requires an independently trusted public key. Never obtains a key
from an unverified bundle. Installation verifies every manifest entry first and
uses only listed wheels; caller supplies an isolated, compatible Python runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

REPOSITORY = 'https://github.com/RakuenSoftware/aimee-native'


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def signed_manifest(root, key, version=None):
    root, key = root.resolve(), key.resolve()
    # OpenSSL receives paths, never private-key bytes or credentials in argv.
    subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-inkey', str(key),
                    '-rawin', '-in', str(root / 'manifest.json'),
                    '-sigfile', str(root / 'manifest.sig')], check=True, capture_output=True)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('repository') != REPOSITORY:
        raise ValueError('unexpected manifest identity')
    if version is not None and manifest.get('version') != version:
        raise ValueError('unexpected release version')
    return manifest


def verify(root, key, version=None):
    root = root.resolve()
    manifest = signed_manifest(root, key, version)
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('empty release manifest')
    names = set()
    for entry in entries:
        name = entry['name']
        if (not isinstance(name, str) or Path(name).name != name or name in ('.', '..')
                or name in names or name in ('manifest.json', 'manifest.sig')):
            raise ValueError('invalid or duplicate manifest filename')
        names.add(name)
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('missing regular asset: ' + name)
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ValueError('asset mismatch: ' + name)
    extras = {p.name for p in root.iterdir()} - names - {'manifest.json', 'manifest.sig'}
    if extras:
        raise ValueError('unlisted assets: ' + ', '.join(sorted(extras)))
    wheels = [e['name'] for e in entries if e['role'] == 'wheel']
    if len(wheels) != 7 or not all(n.endswith('.whl') for n in wheels):
        raise ValueError('expected five model wheels, shared runtime and GGUF dependency')
    return manifest


def download(root, key, version):
    root.mkdir(parents=True, exist_ok=False)
    base = REPOSITORY + '/releases/download/' + urllib.parse.quote('v' + version, safe='') + '/'
    def fetch(name, limit):
        request = urllib.request.Request(base + urllib.parse.quote(name, safe=''),
                                         headers={'User-Agent': 'Aimee-Native-release'})
        with urllib.request.urlopen(request, timeout=120) as response, (root / name).open('xb') as out:
            total = 0
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise ValueError('download exceeds declared size: ' + name)
                out.write(chunk)
    fetch('manifest.json', 1024 * 1024)
    fetch('manifest.sig', 1024)
    # Authenticate names and hashes before following any asset instructions.
    manifest = signed_manifest(root, key, version)
    names = {'manifest.json', 'manifest.sig'}
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('empty release manifest')
    for entry in entries:
        name = entry['name']
        if (not isinstance(name, str) or Path(name).name != name or name in ('.', '..') or name in names):
            raise ValueError('invalid or duplicate manifest filename')
        if type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= 2 * 1024**3:
            raise ValueError('invalid download size')
        names.add(name)
    for entry in entries:
        fetch(entry['name'], entry['bytes'])
    return verify(root, key, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    pack = sub.add_parser('pack')
    pack.add_argument('--wheels', type=Path, required=True)
    pack.add_argument('--source', type=Path, required=True)
    pack.add_argument('--version', required=True)
    pack.add_argument('--source-ref', required=True)
    pack.add_argument('--key', type=Path, required=True)
    pack.add_argument('--public-key', type=Path, required=True)
    pack.add_argument('--output', type=Path, required=True)
    pack.add_argument('--document', type=Path, action='append', default=[])
    for name in ('verify', 'install', 'download'):
        command = sub.add_parser(name)
        command.add_argument('--bundle', type=Path, required=True)
        command.add_argument('--public-key', type=Path, required=True)
        command.add_argument('--expected-version', required=True)
        if name == 'install':
            command.add_argument('--python', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'pack':
        if args.key.stat().st_mode & 0o077:
            raise ValueError('signing key must be owner-only')
        args.output.mkdir(parents=True, exist_ok=False)
        assets = [(p, 'wheel') for p in sorted(args.wheels.glob('*.whl'))]
        assets += [(args.source, 'corresponding-source'), (args.public_key, 'public-key')]
        assets += [(p, 'documentation') for p in args.document]
        if len({p.name for p, _ in assets}) != len(assets):
            raise ValueError('asset filename collision')
        rows = []
        for source, role in assets:
            dest = args.output / source.name
            shutil.copyfile(source, dest)
            rows.append(dict(name=dest.name, role=role, bytes=dest.stat().st_size, sha256=digest(dest)))
        manifest = dict(schema=1, repository=REPOSITORY, version=args.version,
                        source_ref=args.source_ref, signature='Ed25519 over exact manifest.json bytes', files=rows)
        path = args.output / 'manifest.json'
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
        subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(args.key),
                        '-in', str(path), '-out', str(args.output / 'manifest.sig')], check=True)
        verify(args.output, args.public_key, args.version)
        print(json.dumps(dict(status='signed_and_verified', version=args.version, assets=len(rows))))
    else:
        manifest = (download(args.bundle, args.public_key, args.expected_version) if args.action == 'download'
                    else verify(args.bundle, args.public_key, args.expected_version))
        if args.action == 'install':
            # Preserve the venv executable path: resolving its symlink would
            # execute the base interpreter and lose the isolated environment.
            python = args.python.absolute()
            isolated = subprocess.check_output([str(python), '-c',
                'import sys; print(int(sys.prefix != sys.base_prefix))'], text=True).strip()
            if isolated != '1':
                raise ValueError('installation requires an isolated virtual environment')
            # Deliberately offline. The compatible vLLM/Torch/CUDA runtime must
            # already be installed and cannot be replaced by an unpinned fetch.
            wheels = [str((args.bundle / e['name']).resolve()) for e in manifest['files'] if e['role'] == 'wheel']
            subprocess.run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps',
                            '--force-reinstall', *wheels], check=True)
            subprocess.run([str(python), '-m', 'pip', 'check'], check=True)
        status = {'verify': 'verified', 'download': 'downloaded_verified', 'install': 'installed_verified'}[args.action]
        print(json.dumps(dict(status=status,
                              version=manifest['version'], assets=len(manifest['files']))))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print('Release operation refused: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
