"""Designated-host CPU-only Qwen conversion using an unmodified pinned converter.

This produces artifacts for validation, not a distributable release approval.
"""
import json
import pathlib
import subprocess
import time

ROOT = pathlib.Path('/root/aimee-qwen27-conversion-20260928')
WORK = '/opt/aimee-memory-lab/qwen27-release-20260928'
IMAGE = '79d7f03eedc74943f2ffd9c1271141086ea0813bcd3f697c718e09501908cf58'
CONVERTER_REVISION = 'e85e15cf6d810cd1268498c2e5b657bb3ece47bc'


def save(**data):
    (ROOT / 'status.json').write_text(json.dumps(dict(data, updated=time.time()), indent=2) + '\n')


def main():
    ROOT.mkdir(exist_ok=True)
    # Leave room for the queued client update as well as a 40 GiB pool reserve.
    pools = json.loads(subprocess.check_output([
        'lvs', '--reportformat', 'json', '--units', 'b', '--nosuffix',
        '-o', 'lv_name,lv_size,data_percent'], text=True))['report'][0]['lv']
    pool = next(row for row in pools if row['lv_name'] == 'storage')
    free = float(pool['lv_size']) * (1 - float(pool['data_percent']) / 100)
    if free < 35_000_000_000 + 13_000_000_000 + 40 * 1024**3:
        raise RuntimeError('insufficient thin-pool reserve for conversion and queued update')
    available = int(next(line.split()[1] for line in pathlib.Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))) * 1024
    if available < 24 * 1024**3:
        raise RuntimeError('insufficient available host memory for bounded conversion')
    subprocess.run(['pct', 'exec', '101', '--', 'python3', '-c',
        "import pathlib; r=pathlib.Path(" + repr(WORK) + "); "
        "assert not list(r.glob('*.gguf')), 'existing conversion requires inspection'"], check=True)
    save(status='converting', converter_revision=CONVERTER_REVISION,
         scope='CPU-only text and vision conversion; inference and native-memory validation pending')
    for label, extra in [('text', ['--outtype', 'q8_0', '--outfile', '/work/qwen27-q8.gguf']),
                         ('vision', ['--mmproj', '--outtype', 'f32', '--outfile', '/work/qwen27-mmproj-f32.gguf'])]:
        save(status='converting_' + label)
        with (ROOT / (label + '.log')).open('w') as log:
            subprocess.run(['pct', 'exec', '101', '--', 'podman', 'run', '--rm',
                '--name', 'aimee-qwen27-convert-' + label + '-20260928',
                '--network', 'none', '--cpus', '2', '--memory', '20g',
                '-e', 'OMP_NUM_THREADS=2', '-v', WORK + ':/work',
                '-v', '/opt/aimee-memory-lab/model:/model:ro', '--entrypoint', 'python', IMAGE,
                '/work/converter/convert_hf_to_gguf.py', '/model'] + extra,
                stdout=log, stderr=subprocess.STDOUT, check=True)
    save(status='converted', converter_revision=CONVERTER_REVISION,
         scope='Conversion completed; artifact hashing, loader plans, real model and native-memory validation still required')


if __name__ == '__main__':
    ROOT.mkdir(exist_ok=True)
    try:
        main()
    except BaseException as error:
        save(status='failed', error=repr(error))
        raise
