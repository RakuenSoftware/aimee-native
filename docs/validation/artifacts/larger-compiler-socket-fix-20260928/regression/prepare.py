"""Prepare complete public source procedures for larger-model coding validation.

Research fixture admission only; live authorization is validated separately.
"""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import time

ROOT = Path('/opt/aimee-large-release-validation/regression')
SERVICE = Path('/opt/aimee-native-compiler')


def main():
    rows = json.loads((ROOT / 'frozen-inputs.json').read_text())
    preflight = json.loads((ROOT / 'preflight-r3.json').read_text())
    assert hashlib.sha256((ROOT / 'frozen-inputs.json').read_bytes()).hexdigest() == preflight['input_sha256']
    assert len(rows) == 6
    state = {'status': 'running', 'scope': __doc__, 'profiles': {}}
    def save():
        state['updated'] = time.time()
        stage = ROOT / 'preparation-status.next'
        stage.write_text(json.dumps(state, indent=2) + '\n')
        stage.replace(ROOT / 'preparation-status.json')
    save()
    try:
        for profile in ('gemma26', 'qwen27'):
            folder = ROOT / profile
            folder.mkdir(exist_ok=False)
            worker = SERVICE / 'larger-20260928' / (profile + '-worker.json')
            model = json.loads(worker.read_text())['model_revision']
            digest = preflight['profiles'][profile]['config_sha256']
            assert model.endswith(digest)
            catalog = {'recipient': 'larger-coding-public-fixture', 'model_config_sha256': digest, 'publications': {}}
            outputs = []
            state['profiles'][profile] = {'status': 'preparing', 'records': outputs}
            for row in rows:
                fact = row['fact']; iid = row['task']['instance_id']
                assert hashlib.sha256(fact.encode()).hexdigest() == row['fact_sha256']
                identity = {'recipient': catalog['recipient'], 'authorized_view': 'accepted-public-source-procedures-v1',
                    'model_revision': model, 'runtime_profile': profile + '-q8-tp2-v1',
                    'encoding_revision': 'bounded-fp32-negative-v1', 'position_policy': 'negative',
                    'records': [{'namespace': 'swe-public-experience', 'id': iid, 'revision': row['fact_sha256']}]}
                request = {'identity': identity, 'response': {'facts': [{'content': fact}]}}
                key = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
                wire = {'identity': model, 'key': key, 'request': request}
                started = time.monotonic()
                result = subprocess.run(['runuser', '-u', 'aimee-compiler', '--',
                    '/opt/aimee-memory-lab/venv/bin/python', str(SERVICE / 'remote_compile.py'),
                    'worker', '--config', str(worker)], input=json.dumps(wire).encode(),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1200)
                (folder / (iid + '-preparation.log')).write_bytes(result.stderr)
                result.check_returncode()
                raw = result.stdout
                assert raw[:5] == b'AMCP1'
                ni, np = struct.unpack('!QQ', raw[5:21]); assert len(raw) == 21 + ni + np
                target = folder / key; target.mkdir()
                (target / 'index.json').write_bytes(raw[21:21+ni])
                (target / 'compact.pack').write_bytes(raw[21+ni:])
                (target / 'request.json').write_text(json.dumps(request, indent=2) + '\n')
                index = json.loads(raw[21:21+ni]); assert index['model'] == model
                assert set(index['records']) == {key}
                expected = next(r['prepared_memory_tokens'] for r in preflight['profiles'][profile]['rows'] if r['instance_id'] == iid)
                encoded_tokens = len(index['records'][key]['tokens'])
                assert encoded_tokens == expected, (iid, encoded_tokens, expected)
                catalog['publications'][key] = {'root': '/fixture/' + key, 'model': model, 'key': key}
                outputs.append({'instance_id': iid, 'publication': key, 'fact_sha256': row['fact_sha256'],
                    'selected_source_records': 1, 'encoded_memory_tokens': encoded_tokens,
                    'complete_memory_token_count_verified': True, 'seconds': time.monotonic() - started,
                    'payload_bytes': np, 'payload_sha256': hashlib.sha256(raw[21+ni:]).hexdigest(),
                    'index_sha256': hashlib.sha256(raw[21:21+ni]).hexdigest()})
                save()
            (folder / 'catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
            state['profiles'][profile]['status'] = 'prepared'; save()
        state['status'] = 'prepared'
    except BaseException as error:
        state.update(status='failed', error=repr(error)); raise
    finally:
        save()


if __name__ == '__main__':
    main()
