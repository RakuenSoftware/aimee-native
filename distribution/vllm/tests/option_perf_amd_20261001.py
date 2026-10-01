"""Paired, installed-wheel option measurements on two RX 7900 XTXs."""
import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path('/opt/aimee-large-release-validation/plugin-polish-20261001')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-name', default='perf-amd-hybrid-gate-v2-r1')
OUT = ROOT / parser.parse_args().output_name
OUT.mkdir(exist_ok=False)
CLIENT = ROOT / 'client'
BASE = json.loads((ROOT / 'gemma12-amd-combined-r3.json').read_text())
MODEL = BASE['model']
AIMEE = 'aimee-native'
PORT = BASE['serve']['port']
URL = f'http://127.0.0.1:{PORT}'
OPTIONS = {
    'eager_v1': {},
    'prefix_v1': {'enable_prefix_caching': True},
    'async_v1': {'async_scheduling': True},
    'piecewise_v1': {'enable_model_compilation': True, 'enable_piecewise_graphs': True},
    'eager_v2': {'v2_model_runner': True},
    'combined_v2': {'v2_model_runner': True, 'enable_prefix_caching': True,
                    'async_scheduling': True, 'enable_model_compilation': True,
                    'enable_piecewise_graphs': True},
}
PREAMBLE = 'This is a repeated validation query. ' * 16
QUESTIONS = {
    'native': PREAMBLE + 'What are the native release verification vault code, project, and drink?',
    'empty': PREAMBLE + 'Calculate 17 + 24. Reply with only the integer.',
}
ENV = dict(os.environ,
           NO_PROXY='*', no_proxy='*', HTTP_PROXY='', HTTPS_PROXY='', ALL_PROXY='',
           VLLM_USE_FLASHINFER_SAMPLER='0')

def gpu_mib():
    try:
        return sum(int(p.read_text()) for p in Path('/sys/class/drm').glob('card[01]/device/mem_info_vram_used')) // (1024*1024)
    except Exception:
        return None

def query(kind):
    body = {'model': MODEL, 'messages': [{'role': 'user', 'content': QUESTIONS[kind]}],
            'temperature': 0, 'max_tokens': 100, 'chat_template_kwargs': {'enable_thinking': False},
            'stream': True, 'stream_options': {'include_usage': True}}
    req = Request(URL + '/v1/chat/completions', json.dumps(body).encode(),
                  {'Content-Type': 'application/json'})
    start = time.perf_counter()
    first = None
    pieces = []
    usage = None
    try:
        with urlopen(req, timeout=240) as response:
            for line in response:
                if not line.startswith(b'data: '): continue
                raw = line[6:].strip()
                if raw == b'[DONE]': break
                event = json.loads(raw)
                if event.get('usage'): usage = event['usage']
                for choice in event.get('choices', []):
                    part = choice.get('delta', {}).get('content')
                    if part:
                        if first is None: first = time.perf_counter()
                        pieces.append(part)
        end = time.perf_counter()
        answer = ''.join(pieces)
        correct = all(x in answer.lower() for x in ('28461', 'juniper', 'hibiscus')) if kind == 'native' else answer.strip() == '41'
        return {'kind': kind, 'correct': correct, 'answer': answer[:300],
                'ttft_ms': round((first-start)*1000, 3) if first else None,
                'full_ms': round((end-start)*1000, 3), 'usage': usage,
                'gpu_mib_after': gpu_mib()}
    except Exception as e:
        out = {'kind': kind, 'correct': False, 'error_type': type(e).__name__,
               'error': str(e)[:300], 'full_ms': round((time.perf_counter()-start)*1000, 3)}
        if isinstance(e, HTTPError):
            out['http_status'] = e.code
            out['http_body'] = e.read().decode(errors='replace')[:300]
        return out

def summarize(rows):
    summary = {}
    for kind in QUESTIONS:
        hits = [r for r in rows if r['kind'] == kind and r.get('correct')]
        lat = [r['ttft_ms'] for r in hits if r.get('ttft_ms') is not None]
        full = [r['full_ms'] for r in hits]
        summary[kind] = {'correct': len(hits), 'total': sum(r['kind']==kind for r in rows),
                         'ttft_median_ms': statistics.median(lat) if lat else None,
                         'full_median_ms': statistics.median(full) if full else None,
                         'completion_tokens': sum((r.get('usage') or {}).get('completion_tokens', 0) for r in hits)}
    return summary

def main():
    for name, flags in OPTIONS.items():
        config = dict(BASE)
        serve = {k:v for k,v in BASE['serve'].items() if k not in
                 ('enable_prefix_caching','async_scheduling','enable_model_compilation',
                  'enable_piecewise_graphs','v2_model_runner')}
        serve.update(flags)
        config['serve'] = serve
        config_path = OUT / f'{name}.config.json'
        config_path.write_text(json.dumps(config, sort_keys=True, indent=2) + '\n')
        log = (OUT / f'{name}.server.log').open('x')
        raw = (OUT / f'{name}.requests.jsonl').open('x')
        started = time.perf_counter()
        child = subprocess.Popen([AIMEE, '--root', str(CLIENT), 'serve', '--config', str(config_path)],
                                 env=ENV, stdout=log, stderr=subprocess.STDOUT)
        report = {'condition': name, 'flags': flags, 'gpu_mib_before': gpu_mib()}
        rows = []
        try:
            for _ in range(1200):
                if child.poll() is not None: raise RuntimeError(f'server exited before ready: {child.returncode}')
                try:
                    with urlopen(URL + '/v1/models', timeout=1): break
                except Exception:
                    time.sleep(1)
            else: raise TimeoutError('startup exceeded 1200 seconds')
            report['ready_seconds'] = round(time.perf_counter()-started, 3)
            report['gpu_mib_ready'] = gpu_mib()
            for kind in ('native', 'empty'):
                row = query(kind)
                row['phase'] = 'warmup'
                raw.write(json.dumps(row) + '\n'); raw.flush()
                rows.append(row)
            first_measured = time.perf_counter()
            for i in range(6):
                for kind in (('native','empty') if i % 2 == 0 else ('empty','native')):
                    row = query(kind)
                    row['phase'] = 'measured'
                    raw.write(json.dumps(row) + '\n'); raw.flush()
                    rows.append(row)
            report['measured_seconds'] = round(time.perf_counter()-first_measured, 3)
            measured = [r for r in rows if r['phase'] == 'measured']
            report['summary'] = summarize(measured)
            report['gpu_mib_peak_sampled'] = max((r.get('gpu_mib_after') or 0 for r in rows), default=0)
            report['warmup'] = summarize([r for r in rows if r['phase']=='warmup'])
            report['status'] = 'passed' if all(r.get('correct') for r in rows) else 'failed_answers'
        except Exception as e:
            report['status'] = 'failed_setup'
            report['error'] = repr(e)
        finally:
            child.terminate()
            try: child.wait(timeout=60)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
            report['gpu_mib_after_stop'] = gpu_mib()
            log.close(); raw.close()
            (OUT / f'{name}.summary.json').write_text(json.dumps(report, indent=2) + '\n')
            print(name, report['status'], report.get('summary', {}), flush=True)
    print('all conditions finished', flush=True)

if __name__ == '__main__': main()
