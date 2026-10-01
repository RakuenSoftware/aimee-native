"""Live installed-plugin recall, empty-selection and mixed-concurrency probe.

Run against a separately started, authenticated Aimee-connected vLLM instance.
This is an integration check on repeated synthetic facts, not a knowledge sample.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import statistics
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(endpoint, model, kind, expected, attempt):
    question = ('Give my private vault code, private project codename, and '
                'preferred meeting drink. Be concise.' if kind == 'native' else
                'What is 17 + 24? Reply with the integer only.')
    body = {'model': model, 'messages': [{'role': 'user', 'content': question}],
            'temperature': 0, 'max_tokens': 96,
            'chat_template_kwargs': {'enable_thinking': False},
            # Aimee replaces client-controlled selection and cache identity.
            'cache_salt': 'untrusted-client-salt'}
    started = time.perf_counter()
    rejected = 0
    for retry in range(12):
        request = Request(endpoint + '/v1/chat/completions',
                          data=json.dumps(body).encode(),
                          headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
            break
        except HTTPError as error:
            if error.code != 429:
                raise
            rejected += 1
            time.sleep(min(0.1 * 2 ** retry, 1.5))
    else:
        raise RuntimeError('admission retry budget exhausted')
    answer = result['choices'][0]['message']['content'] or ''
    if kind == 'native':
        correct = all(value.lower() in answer.lower() for value in expected)
    else:
        correct = bool(re.search(r'\b41\b', answer)) and not any(
            value.lower() in answer.lower() for value in expected)
    return {'kind': kind, 'attempt': attempt, 'correct': correct,
            'usage': result['usage'], 'elapsed_ms': (time.perf_counter() - started) * 1000,
            'rejections': rejected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--expected', required=True, nargs=3,
                        metavar=('CODE', 'PROJECT', 'DRINK'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=24)
    parser.add_argument('--clients', type=int, default=8)
    options = parser.parse_args()
    if options.repeats < 1 or options.clients < 1:
        parser.error('repeats and clients must be positive')
    endpoint = options.endpoint.rstrip('/')
    with urlopen(endpoint + '/v1/models', timeout=10) as response:
        model = json.load(response)['data'][0]['id']
    work = [(kind, i) for i in range(options.repeats)
            for kind in ('native', 'empty')]
    rows = []
    with ThreadPoolExecutor(max_workers=options.clients) as pool:
        for row in pool.map(lambda item: call(endpoint, model, item[0],
                                              options.expected, item[1]), work):
            rows.append(row)
    groups = {}
    for kind in ('native', 'empty'):
        cohort = [row for row in rows if row['kind'] == kind]
        groups[kind] = {'correct': sum(row['correct'] for row in cohort),
                        'requests': len(cohort),
                        'median_response_ms': statistics.median(row['elapsed_ms'] for row in cohort),
                        'admission_retries': sum(row['rejections'] for row in cohort)}
    report = {'scope': 'Repeated three-fact canary and arithmetic empty selection; '
                       'not independent knowledge examples or revision testing',
              'model': model, 'clients': options.clients, 'groups': groups, 'rows': rows}
    if options.output.exists():
        raise FileExistsError(options.output)
    options.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(groups))
    if any(group['correct'] != group['requests'] for group in groups.values()):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
