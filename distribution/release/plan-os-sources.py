"""Resolve exact installed source versions against signed Ubuntu indexes.

Run inside a disposable copy of the shipped image. Only source indexes are
updated; packages are neither installed nor upgraded. Results describe source
availability, not completion of a corresponding-source distribution bundle.
"""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from urllib.parse import urlsplit

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--output', type=Path, required=True)
a = p.parse_args()
a.output.mkdir(exist_ok=False)
sources = []
for line in Path('/etc/apt/sources.list').read_text().splitlines():
    fields = line.split()
    if fields and fields[0] == 'deb':
        if urlsplit(fields[1]).hostname not in {'archive.ubuntu.com', 'security.ubuntu.com'}:
            raise ValueError('unexpected repository; review required')
        sources.append('deb-src ' + ' '.join(fields[1:]))
if not sources:
    raise ValueError('no supported Ubuntu repositories')
source_list = Path('/tmp/aimee-source-repositories.list')
source_list.write_text('\n'.join(sources)+'\n')
options = ['-o', f'Dir::Etc::sourcelist={source_list}', '-o', 'Dir::Etc::sourceparts=-',
           '-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=20']
report = dict(status='updating_indexes', scope=__doc__, repositories=sources, packages=[])
def save():
    (a.output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
save()
try:
    with (a.output/'index-update.log').open('x') as log:
        subprocess.run(['apt-get', *options, 'update'],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    fields='${binary:Package}\t${source:Package}\t${source:Version}\n'
    installed={}
    for line in subprocess.check_output(['dpkg-query','-W','-f='+fields],text=True).splitlines():
        binary,source,version=line.split('\t')
        installed.setdefault((source,version),[]).append(binary)
    report['status']='resolving'
    for (source,version),binaries in sorted(installed.items()):
        r=subprocess.run(['apt-get',*options,'--print-uris','--only-source','source',source+'='+version],
                         capture_output=True,text=True,timeout=30)
        files=[]
        for line in r.stdout.splitlines():
            if line.startswith("'"):
                uri,name,size,*checksum=shlex.split(line)
                files.append(dict(uri=uri,name=name,bytes=int(size),index_checksum=checksum))
        resolved=r.returncode==0 and bool(files)
        report['packages'].append(dict(source=source,version=version,binaries=binaries,
            status='resolved' if resolved else 'unresolved',files=files,returncode=r.returncode,
            diagnostic=(r.stdout+r.stderr) if not resolved else r.stderr))
        save()
    report['status']='availability_checked'
    report['resolved']=sum(x['status']=='resolved' for x in report['packages'])
    report['unresolved']=len(report['packages'])-report['resolved']
except BaseException as error:
    report.update(status='failed',error=repr(error))
    raise
finally:
    save()
print(json.dumps({k:report[k] for k in ['status','resolved','unresolved']}))
