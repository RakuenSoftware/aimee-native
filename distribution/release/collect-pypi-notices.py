"""Collect notices from exact-version upstream distributions; never execute them.

This supplements installed-image notices. Matching version and registry SHA-256
prove the downloaded artifact identity, not equivalence to every installed file.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tarfile
import urllib.parse
import urllib.request
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--package', help='Collect only this package from the inventory gaps')
    parser.add_argument('--python-tag', default='cp312', help='Python ABI of the pinned runtime')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    inventory = json.loads(args.inventory.read_text())
    missing = set(inventory['gaps']['python_without_notice']) - {'aimee-vllm'}
    report = {'status': 'collecting', 'scope': __doc__, 'results': []}
    def save():
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    save()
    for package in inventory['python_packages']:
        name, version = package['name'], package['version']
        if name not in missing or (args.package and name != args.package):
            continue
        row = {'name': name, 'version': version, 'status': 'pending', 'notices': []}
        report['results'].append(row)
        try:
            assert re.fullmatch(r'[A-Za-z0-9_.-]+', name)
            folder = args.output/name; folder.mkdir()
            url = 'https://pypi.org/pypi/'+urllib.parse.quote(name, safe='')+'/'+urllib.parse.quote(version, safe='')+'/json'
            with urllib.request.urlopen(url, timeout=30) as source:
                metadata = json.load(source)
            assert metadata['info']['version'] == version
            candidates = [x for x in metadata['urls'] if x['size'] <= 256*1024**2 and
                (x['packagetype']=='sdist' or x['filename'].endswith('py3-none-any.whl') or
                 ('manylinux' in x['filename'] and 'x86_64' in x['filename'] and
                  ('-'+args.python_tag+'-' in x['filename'] or '-abi3-' in x['filename'])))]
            candidates.sort(key=lambda x: (x['packagetype']!='sdist', x['size']))
            if not candidates:
                raise ValueError('no bounded source or relevant wheel distribution')
            chosen = candidates[0]; parsed = urllib.parse.urlparse(chosen['url'])
            assert parsed.scheme == 'https' and parsed.hostname == 'files.pythonhosted.org'
            filename = chosen['filename']; assert Path(filename).name == filename
            target = folder/filename; sha = hashlib.sha256(); count = 0
            with urllib.request.urlopen(chosen['url'],timeout=60) as source, target.open('xb') as output:
                while data := source.read(1024*1024):
                    count += len(data)
                    if count > chosen['size']:
                        raise ValueError('download exceeds registry size')
                    output.write(data); sha.update(data)
            assert count == chosen['size'] and sha.hexdigest()==chosen['digests']['sha256']
            row.update(archive=filename, archive_sha256=sha.hexdigest(), bytes=count,
                       source_url=chosen['url'], metadata_url=url, package_type=chosen['packagetype'])
            def wanted(path, size):
                leaf=Path(path).name.lower()
                return size <= 4*1024**2 and re.fullmatch(r'(license|licence|copying|copyright|notice)([._-].*)?',leaf) and Path(leaf).suffix not in {'.py','.c','.h','.rs','.sh'}
            def retain(path, data):
                digest=hashlib.sha256(data).hexdigest(); (folder/(digest+'.txt')).write_bytes(data)
                row['notices'].append({'archive_path':path,'sha256':digest,'bytes':len(data),'file':name+'/'+digest+'.txt'})
            if filename.endswith('.whl') or filename.endswith('.zip'):
                with zipfile.ZipFile(target) as archive:
                    for item in archive.infolist():
                        if not item.is_dir() and wanted(item.filename,item.file_size):
                            retain(item.filename,archive.read(item))
            else:
                with tarfile.open(target) as archive:
                    for item in archive:
                        if item.isfile() and wanted(item.name,item.size):
                            retain(item.name,archive.extractfile(item).read())
            row['status']='archive_verified_notices_collected' if row['notices'] else 'archive_verified_no_notice_found'
        except Exception as error:
            row.update(status='failed', error=str(error))
        save()
    report['status']='collection_finished'
    save()


if __name__ == '__main__':
    main()
