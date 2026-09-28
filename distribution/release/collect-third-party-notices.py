"""Collect notices from the exact runtime image; report gaps without approving release.

Run inside the image with an empty output directory mounted. This copies only
notice/license files, never private source, model files, credentials or settings.
Corresponding source/build archives are a separate unfinished deliverable.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(exist_ok=True)
    manifest = a.output / 'manifest.json'
    if manifest.exists():
        raise FileExistsError(manifest)
    blobs = a.output / 'notices'
    blobs.mkdir(exist_ok=False)
    def retain(path):
        try:
            if not path.is_file():
                return dict(path=str(path), status='missing')
            if path.stat().st_size > 4 * 1024**2:
                return dict(path=str(path), status='oversize')
            raw = path.read_bytes()
        except OSError as error:
            return dict(path=str(path), status='unreadable', error=str(error))
        digest = hashlib.sha256(raw).hexdigest()
        target = blobs / (digest + '.txt')
        if not target.exists():
            target.write_bytes(raw)
        return dict(path=str(path), status='collected', sha256=digest, bytes=len(raw), artifact='notices/' + target.name)
    fields = '${binary:Package}\t${Version}\t${source:Package}\t${source:Version}\t${Homepage}\n'
    os_rows = []
    for row in subprocess.check_output(['dpkg-query', '-W', '-f=' + fields], text=True).splitlines():
        binary, version, source, source_version, homepage = row.split('\t')
        notice = retain(Path('/usr/share/doc') / binary.split(':')[0] / 'copyright')
        alternatives = []
        if notice['status'] != 'collected':
            owned = subprocess.check_output(['dpkg-query', '-L', binary], text=True).splitlines()
            for item in owned:
                candidate = Path(item)
                if any(word in candidate.name.lower() for word in ('license', 'copying', 'copyright', 'notice')):
                    if candidate.is_file():
                        alternatives.append(retain(candidate))
        os_rows.append(dict(binary=binary, version=version, source=source, source_version=source_version,
                            homepage=homepage, notice=notice, alternative_notices=alternatives,
                            corresponding_source='not_collected'))
    python_rows = []
    for dist in importlib.metadata.distributions():
        # Only explicit license filenames from the distribution's own manifest.
        files = []
        for relative in dist.files or []:
            name = Path(str(relative)).name.lower()
            if any(word in name for word in ('license', 'copying', 'copyright', 'notice')):
                files.append(retain(Path(dist.locate_file(relative))))
        # System Python distributions often keep notices in their owning Debian
        # package, outside the Python file manifest. Resolve actual ownership;
        # do not guess from similar package names or license identifiers.
        system_notice_owners = []
        metadata_path = getattr(dist, '_path', None)
        if metadata_path is not None and not any(n['status'] == 'collected' for n in files):
            owned = subprocess.run(['dpkg-query', '-S', str(metadata_path)],
                                   capture_output=True, text=True)
            if owned.returncode == 0:
                for line in owned.stdout.splitlines():
                    if ': ' not in line:
                        continue
                    for owner in line.split(': ', 1)[0].split(', '):
                        candidate = retain(Path('/usr/share/doc') / owner.split(':')[0] / 'copyright')
                        if candidate['status'] == 'collected':
                            system_notice_owners.append(owner)
                            files.append(candidate)
        python_rows.append(dict(name=dist.metadata.get('Name'), version=dist.version,
            license_expression=dist.metadata.get('License-Expression'), license_metadata=dist.metadata.get('License'),
            declared_license_files=dist.metadata.get_all('License-File', []), notices=files,
            system_notice_owners=sorted(set(system_notice_owners)),
            source_archives='not_collected'))
    # Debian copyright files often refer to these full license texts instead
    # of embedding them. Retain them even when base-files has its own copyright.
    common_licenses = [retain(path) for path in sorted(Path('/usr/share/common-licenses').iterdir())
                       if path.is_file()]
    report = dict(schema=1, status='collected_with_gaps', scope=__doc__,
                  os_packages=os_rows, python_packages=python_rows,
                  common_licenses=common_licenses,
                  gaps=dict(os_without_notice=[r['binary'] for r in os_rows if r['notice']['status'] != 'collected' and not any(n['status'] == 'collected' for n in r['alternative_notices'])],
                    python_without_notice=[r['name'] for r in python_rows if not any(n['status'] == 'collected' for n in r['notices'])]),
                  public_redistribution_cleared=False)
    manifest.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(os_packages=len(os_rows), python_packages=len(python_rows), unique_notices=len(list(blobs.iterdir())), gaps=report['gaps'])))


if __name__ == '__main__':
    main()
