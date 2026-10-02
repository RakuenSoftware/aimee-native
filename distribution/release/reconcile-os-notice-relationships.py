#!/usr/bin/env python3
"""Connect split SDK packages to retained component notices using installed evidence."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

base = Path(sys.argv[1])
out = Path(sys.argv[2])
manifest = json.loads((base / 'consolidated-notices-20260928/manifest.json').read_text())
packages = {r['binary']: r for r in manifest['os_packages']}
relationships = json.loads(gzip.decompress((base / 'os-notice-relationships-20260928/report.json.gz').read_bytes()))
providers = {
    'hip-dev': 'hip-runtime-amd', 'hip-doc': 'hip-runtime-amd', 'hip-samples': 'hip-runtime-amd',
    'hsa-rocr-dev': 'hsa-rocr', 'rocm-opencl-dev': 'rocm-opencl',
    'rocprofiler-plugins': 'rocprofiler',
}
rows = []
for item in relationships['packages']:
    name = item['package']
    row = {'package': name, 'version': packages[name]['version'],
           'installed_metadata': item['metadata'],
           'payload_files': len(item['regular_files']),
           'elf_files': sum(f['elf'] for f in item['regular_files']),
           'static_archives': sum(f['static_archive'] for f in item['regular_files'])}
    if name in {'rocm-dev', 'rocm-libs', 'rocm-utils'}:
        assert len(item['regular_files']) == 1
        f = item['regular_files'][0]
        assert f['path'].startswith('/opt/rocm-7.2.3/.info/version-') and f['bytes'] == 9
        row.update(disposition='version_marker_only', files=item['regular_files'])
    elif name == 'hsa-amd-aqlprofile':
        row.update(disposition='matching_release_notice_collected',
                   evidence='aqlprofile-upstream-notice-20260928/report.json')
    elif name == 'bnxt-rocelib':
        row.update(disposition='vendor_payload_notice_review',
                   evidence='network-package-evidence-20260928/',
                   limitation='Retained header notices include differing SPDX expressions; do not infer all binary coverage from one header.')
    else:
        provider = providers.get(name, name.removesuffix('-dev'))
        p = packages[provider]
        notices = [n for n in [p['notice']] + p['alternative_notices'] if n.get('status') == 'collected']
        if not notices:
            raise ValueError(f'No retained component notice for {name}: {provider}')
        row.update(disposition='split_component_notice_retained',
                   provider=provider, provider_version=p['version'], notices=notices,
                   scope='Installed package metadata and payload identify the component. '
                         'This mapping preserves its existing notices; it is not a file-by-file licensing or source-build attestation.')
    rows.append(row)
report = {'scope': __doc__, 'packages': rows,
          'counts': {key: sum(r['disposition'] == key for r in rows) for key in sorted({r['disposition'] for r in rows})}}
out.mkdir(parents=True, exist_ok=True)
p = out / 'report.json'
p.write_text(json.dumps(report, indent=2) + '\n')
(out / 'SHA256SUMS').write_text(hashlib.sha256(p.read_bytes()).hexdigest() + '  report.json\n')
print(json.dumps(report['counts']))
