"""Private full-checkpoint resident transport validation; synthetic source records."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).parent
SERVICE = ROOT / 'service'
LAB = Path('/opt/aimee-memory-lab')


def main():
    reports = []
    for profile, model in [('gemma26', LAB / 'gemma4-moe'), ('qwen27', LAB / 'model')]:
        root = ROOT / profile
        root.mkdir(exist_ok=False)
        config_hash = hashlib.sha256((model / 'config.json').read_bytes()).hexdigest()
        identity = profile + '-full-fp32-negative-v1-' + config_hash
        sock = str(root / 'compiler.sock')
        config = {'model': str(model), 'model_revision': identity,
                  'preparation_backend': 'bounded_text_fp32', 'compute_dtype': 'float32',
                  'position_policy': 'negative', 'encoding_revision': 'bounded-fp32-negative-v1',
                  'threads': 8, 'max_memory_tokens': 1024, 'state': str(root / 'state'),
                  'library': str(LAB / 'aimee-native/target/release/libaimee_native.so')}
        cfg = root / 'resident.json'; cfg.write_text(json.dumps(config)); cfg.chmod(0o600)
        worker = root / 'worker.json'
        worker.write_text(json.dumps({'model_revision': identity, 'resident_socket': sock})); worker.chmod(0o600)
        front = root / 'front.json'
        front.write_text(json.dumps({'command': [sys.executable, str(SERVICE / 'remote_compile.py'),
                                                'worker', '--config', str(worker)]})); front.chmod(0o600)
        log = (root / 'resident.log').open('w')
        daemon = subprocess.Popen([sys.executable, str(SERVICE / 'resident_compile.py'),
                                   '--config', str(cfg), '--socket', sock], stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 180
            while not Path(sock).exists():
                if daemon.poll() is not None:
                    raise RuntimeError('resident daemon exited before ready')
                if time.monotonic() > deadline:
                    raise TimeoutError('resident readiness')
                time.sleep(.2)
            source = json.loads((LAB / 'bounded-buffer-fix-20260928' / (profile + '-full') / 'request.json').read_text())
            source['identity'].update(model_revision=identity, position_policy='negative',
                                      encoding_revision=config['encoding_revision'])
            base = [sys.executable, str(SERVICE / 'remote_compile.py'), 'frontend', '--config', str(front),
                    '--identity', identity, '--key', 'a' * 64]
            wrong = json.loads(json.dumps(source)); wrong['identity']['position_policy'] = 'nonnegative'
            rejected = subprocess.run(base + ['--output', str(root / 'rejected')],
                                      input=json.dumps(wrong), capture_output=True, text=True, timeout=30)
            assert rejected.returncode != 0, 'mismatched preparation policy accepted'
            started = time.monotonic()
            result = subprocess.run(base + ['--output', str(root / 'prepared')],
                                    input=json.dumps(source), capture_output=True, text=True, timeout=540)
            (root / 'frontend.log').write_text(result.stderr)
            assert result.returncode == 0, 'full-checkpoint resident preparation failed'
            payload = root / 'prepared/compact.pack'
            index = root / 'prepared/index.json'
            reports.append({'profile': profile, 'status': 'passed', 'config_sha256': config_hash,
                            'scope': 'Full-checkpoint synthetic preparation through resident transport; no live authority test',
                            'mismatched_policy_rejected': True, 'selected_records': len(source['response']['facts']),
                            'seconds': time.monotonic() - started, 'payload_bytes': payload.stat().st_size,
                            'payload_sha256': hashlib.sha256(payload.read_bytes()).hexdigest(),
                            'index_sha256': hashlib.sha256(index.read_bytes()).hexdigest()})
            (ROOT / 'results.json').write_text(json.dumps(reports, indent=2) + '\n')
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=20)
            except subprocess.TimeoutExpired:
                daemon.kill(); daemon.wait()
            log.close()
    (ROOT / 'status.json').write_text(json.dumps({'status': 'passed', 'profiles': len(reports)}) + '\n')


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        (ROOT / 'status.json').write_text(json.dumps({'status': 'failed', 'error': repr(error)}) + '\n')
        raise
