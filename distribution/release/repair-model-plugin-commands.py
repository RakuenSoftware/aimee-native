#!/usr/bin/env python3
"""Restore deployment command forwarding while preserving all native/runtime bytes."""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import zipfile
from model_plugin_layout import write_binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True)
    reports = []
    for source in sorted(args.wheels.glob('*.whl')):
        if source.name.startswith(('aimee_native_runtime-', 'vllm_gguf_plugin-')):
            shutil.copyfile(source, args.output / source.name)
            reports.append({'wheel': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'all_bytes_preserved': True})
            continue
        package = source.name.split('-', 1)[0]
        with zipfile.ZipFile(source) as archive:
            entries = {entry.filename: entry for entry in archive.infolist()}
            files = {name: archive.read(name) for name in entries}
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / package
            write_binding(generated)
            replacement = (generated / 'cli.py').read_bytes()
        member = package + '/cli.py'
        old_hash = hashlib.sha256(files[member]).hexdigest()
        files[member] = replacement
        record = next(name for name in files if name.endswith('.dist-info/RECORD'))
        files.pop(record)
        stream = io.StringIO()
        writer = csv.writer(stream, lineterminator='\n')
        for name, data in sorted(files.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            writer.writerow([name, 'sha256=' + digest, len(data)])
        writer.writerow([record, '', ''])
        files[record] = stream.getvalue().encode()
        parts = source.name.split('-')
        assert len(parts) == 6
        parts[2] = '3'
        target = args.output / '-'.join(parts)
        with target.open('xb') as output, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = entries[name]
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        with zipfile.ZipFile(source) as before, zipfile.ZipFile(target) as after:
            assert before.namelist() == after.namelist()
            changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
            assert set(changed) == {member, record}
            assert all(before.getinfo(name).external_attr == after.getinfo(name).external_attr for name in before.namelist())
        reports.append({'wheel': target.name, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                        'original_wheel': source.name, 'original_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                        'changed_members': changed, 'cli_before_sha256': old_hash,
                        'cli_after_sha256': hashlib.sha256(replacement).hexdigest(),
                        'native_libraries_and_contracts_preserved': True})
    assert len(reports) == 5
    (args.output / 'command-repair.json').write_text(json.dumps({'status': 'passed', 'scope': __doc__, 'wheels': reports}, indent=2) + '\n')


if __name__ == '__main__':
    main()
