#!/usr/bin/env python3
"""Version qualified wheel payloads without changing executable bytes or modes.

Produces unsigned candidates and a member-by-member continuity report. Historical
inputs remain untouched. Run the wheel auditor and installed contract tests next.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile


def promote(source, output, old_version='0.3.2', version='0.3.3'):
    from packaging.version import Version
    if Version(version) <= Version(old_version):
        raise ValueError('release version must increase')
    output.mkdir(parents=True, exist_ok=False)
    reports = []
    for wheel in sorted(source.glob('aimee_*.whl')):
        parts = wheel.name.split('-')
        if parts[1] != old_version:
            raise ValueError('unexpected input version: ' + wheel.name)
        package = parts[0]
        old_info = package + '-' + old_version + '.dist-info'
        new_info = package + '-' + version + '.dist-info'
        payload = {}
        with zipfile.ZipFile(wheel) as z:
            entries = z.infolist()
            if len(entries) != len({e.filename for e in entries}):
                raise ValueError('duplicate wheel members')
            for entry in entries:
                old_name = entry.filename
                if old_name == old_info + '/RECORD':
                    continue
                data = z.read(old_name)
                name = old_name.replace(old_info + '/', new_info + '/', 1)
                if old_name == old_info + '/METADATA':
                    data = data.replace(('Version: ' + old_version + '\n').encode(),
                                        ('Version: ' + version + '\n').encode())
                    data = data.replace(('aimee-native-runtime==' + old_version).encode(),
                                        ('aimee-native-runtime==' + version).encode())
                elif old_name == old_info + '/WHEEL':
                    data = b'\n'.join(line for line in data.split(b'\n') if not line.startswith(b'Build: '))
                payload[name] = (entry, data)
        record = new_info + '/RECORD'
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator='\n')
        for name, (_, data) in sorted(payload.items()):
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip('=')
            writer.writerow([name, 'sha256=' + digest, len(data)])
        writer.writerow([record, '', ''])
        payload[record] = (zipfile.ZipInfo(record), buffer.getvalue().encode())
        dest = output / '-'.join([package, version] + parts[-3:])
        continuity = []
        with zipfile.ZipFile(dest, 'x', zipfile.ZIP_DEFLATED) as z:
            for name, (entry, data) in sorted(payload.items()):
                entry.filename = name
                z.writestr(entry, data)
        with zipfile.ZipFile(wheel) as original, zipfile.ZipFile(dest) as promoted:
            for entry in original.infolist():
                if entry.filename.startswith(old_info + '/'):
                    continue
                data = original.read(entry.filename)
                assert data == promoted.read(entry.filename)
                assert entry.external_attr == promoted.getinfo(entry.filename).external_attr
                continuity.append({'member': entry.filename, 'sha256': hashlib.sha256(data).hexdigest(),
                                   'external_attr': entry.external_attr})
        reports.append({'wheel': dest.name, 'sha256': hashlib.sha256(dest.read_bytes()).hexdigest(),
                        'qualified_input': wheel.name, 'input_sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
                        'unchanged_payload': continuity})
    if not reports:
        raise ValueError('no input wheels')
    (output / 'promotion.json').write_text(json.dumps({'status': 'passed', 'version': version,
        'scope': __doc__, 'wheels': reports}, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--old-version', default='0.3.2')
    p.add_argument('--version', default='0.3.3')
    a = p.parse_args()
    promote(a.source, a.output, a.old_version, a.version)
