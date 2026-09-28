#!/usr/bin/env python3
"""Promote already tested candidates on the existing controlled private origin."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/opt/aimee-native-release')
SHARED = Path('/opt/aimee-large-release-validation')
WWW = ROOT / 'www'
EXPECTED_LAUNCHER = 'a7ebbb5d0f9493f205ca355fab640f56e31cc686219aa038ac348de4ac4727e6'
EXPECTED_OLD_LAUNCHER = '2fab42f593e26a51334c3e34cdfc5ee7c9e3e87932b68a1573450ba6c32df693'
EXPECTED_12B = '3577d8041f929ae5376160c276d8136f0ddc4a80247d33f27325f4899f1a8636'
EXPECTED_LARGER = {
    'gemma26': '1041c84fe25d84b5700b5cdf53de6eb78b38021d10689e49583cc3425f876cae',
    'qwen27': '90e75bcfb3e58bce208e8568d6ea335e89fdf8ecb02a4e055384d164367196bc',
}


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    status = json.loads((SHARED / 'normal-lifecycle-r2-20260928/status.json').read_text())
    if status.get('status') != 'passed' or status.get('binding_unchanged') is not True or status.get('compiler_restored') is not True:
        raise RuntimeError('Normal lifecycle and cleanup are not complete')
    phases = {(r['profile'], r['phase']) for r in status['phases']}
    expected = {(p, phase) for p in EXPECTED_LARGER for phase in ['fresh1', 'updated2', 'rollback1', 'restored2']}
    if phases != expected:
        raise RuntimeError('Incomplete normal lifecycle set')
    for profile, expected_digest in EXPECTED_LARGER.items():
        for phase in ['fresh1', 'updated2', 'rollback1', 'restored2']:
            result = json.loads((SHARED / 'normal-lifecycle-r2-20260928' / profile / (phase + '.json')).read_text())
            if result['status'] != 'passed' or len(result['answers']) != 2 or not all(x['passed'] for x in result['answers']):
                raise RuntimeError(f'Failed phase: {profile}/{phase}')
            if phase == 'restored2' and result['active']['current'] != expected_digest:
                raise RuntimeError(f'Wrong restored manifest: {profile}')
    source = SHARED / 'model-selection-normal-launcher/aimee-native'
    current = WWW / 'bootstrap/linux-x86_64'
    staged = current.with_name('linux-x86_64.next-20260928')
    backup = current.with_name('linux-x86_64.before-20260928')
    if digest(source) != EXPECTED_LAUNCHER or digest(current / 'aimee-native') != EXPECTED_OLD_LAUNCHER:
        raise RuntimeError('Unexpected launcher identity')
    candidate = ROOT / 'candidate6-assembly-20260928/signed'
    channel = WWW / 'linux-x86_64/gemma4-12b-q8-native'
    if digest(candidate / 'manifest.json') != EXPECTED_12B:
        raise RuntimeError('Unexpected 12B manifest')
    if not channel.is_symlink() or channel.resolve() != WWW / 'releases/private-preview-5':
        raise RuntimeError('Unexpected existing 12B channel')
    if staged.exists() or backup.exists():
        raise RuntimeError('Promotion paths already exist; inspect before retry')
    libc = ctypes.CDLL(None, use_errno=True)
    exchange = libc.renameat2
    exchange.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    exchange.restype = ctypes.c_int
    staged.mkdir(mode=0o755)
    shutil.copyfile(source, staged / 'aimee-native')
    (staged / 'aimee-native').chmod(0o755)
    subprocess.run(['openssl', 'pkeyutl', '-sign', '-rawin', '-inkey', str(ROOT / 'private/release.key'),
                    '-in', str(staged / 'aimee-native'), '-out', str(staged / 'aimee-native.sig')], check=True)
    identity = json.loads((current / 'identity.json').read_text())
    identity.update(sha256=EXPECTED_LAUNCHER, bytes=source.stat().st_size,
                    scope='controlled private preview; model-aware launcher validated on all three candidates')
    (staged / 'identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    for name in ['aimee-native.sig', 'identity.json']:
        (staged / name).chmod(0o644)
    # Verify with the existing pinned public identity, not a newly inferred trust key.
    public = SHARED / 'promotion-public-20260928.der'
    public.write_bytes(bytes.fromhex('302a300506032b6570032100' + identity['public_key']))
    for package, signature in [(staged / 'aimee-native', staged / 'aimee-native.sig'),
                               (candidate / 'manifest.json', candidate / 'manifest.sig')]:
        subprocess.run(['openssl', 'pkeyutl', '-verify', '-pubin', '-keyform', 'DER', '-inkey', str(public),
                        '-rawin', '-in', str(package), '-sigfile', str(signature)], check=True)
    next_channel = channel.with_name(channel.name + '.next-20260928')
    next_channel.symlink_to(candidate, target_is_directory=True)
    os.replace(next_channel, channel)
    # Exchange complete directories atomically so launcher, signature and identity agree.
    if exchange(-100, os.fsencode(staged), -100, os.fsencode(current), 2) != 0:
        error = ctypes.get_errno()
        rollback = channel.with_name(channel.name + '.rollback-20260928')
        rollback.symlink_to(WWW / 'releases/private-preview-5', target_is_directory=True)
        os.replace(rollback, channel)
        raise OSError(error, os.strerror(error))
    staged.rename(backup)
    report = {'status': 'promoted', 'scope': __doc__, 'launcher_sha256': digest(current / 'aimee-native'),
              'previous_bootstrap': str(backup), 'gemma12_manifest_sha256': digest(channel / 'manifest.json'),
              'larger_manifests': EXPECTED_LARGER, 'public_distribution': False,
              'limitation': 'Measured task and distribution-fulfillment limits remain in release notes.'}
    (SHARED / 'controlled-promotion-20260928.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
