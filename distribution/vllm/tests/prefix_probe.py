"""Measure repeated-prompt prefix-cache reuse through live native admission."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


def send(endpoint, model, question):
    body = {'model': model, 'messages': [{'role': 'user', 'content': question}],
            'temperature': 0, 'max_tokens': 64,
            'chat_template_kwargs': {'enable_thinking': False}}
    request = Request(endpoint + '/v1/chat/completions', json.dumps(body).encode(),
                      {'Content-Type': 'application/json'})
    with urlopen(request, timeout=180) as response:
        result = json.load(response)
    return {'answer': result['choices'][0]['message']['content'],
            'usage': result['usage']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args()
    endpoint = options.endpoint.rstrip('/')
    with urlopen(endpoint + '/v1/models', timeout=10) as response:
        model = json.load(response)['data'][0]['id']
    # A long, identical prefix exceeds the first text-cache block. Keep the
    # retrieval-bearing question at the end and preserve it across repetitions.
    preamble = 'This is a repeated validation query. ' * 16
    native = preamble + 'What are the native release verification vault code, project, and drink?'
    empty = preamble + 'What is 17 + 24? Reply with the integer only.'
    rows = []
    for kind, question in [('native',native),('native',native),('native',native),
                           ('empty',empty),('empty',empty),('native',native)]:
        row = send(endpoint, model, question)
        row['kind'] = kind
        rows.append(row)
    options.output.write_text(json.dumps({'model':model,'rows':rows},indent=2)+'\n')
    print(json.dumps([{'kind':r['kind'],'usage':r['usage']} for r in rows]))


if __name__ == '__main__':
    main()
