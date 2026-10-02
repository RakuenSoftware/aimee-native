"""Collect public dependency notices from locked Cargo metadata; no private code."""
import argparse,json,pathlib,re
p=argparse.ArgumentParser();p.add_argument('metadata');p.add_argument('--notice',required=True);p.add_argument('--report',required=True);a=p.parse_args()
metadata=json.loads(pathlib.Path(a.metadata).read_text());report=[];notices=['Public Rust dependency notices for the supplied Cargo resolution. Generate metadata with the release target and exact feature set.\n']
# Cargo may list packages outside the active target/feature graph. Walk only
# edges reachable from resolve.root; never mistake unused packages for shipped
# dependencies or silently omit reachable packages.
resolution=metadata['resolve'];nodes={n['id']:n for n in resolution['nodes']}
if not resolution.get('root'):raise ValueError('single release root required')
active=set();pending=[resolution['root']]
while pending:
 key=pending.pop()
 if key in active:continue
 if key not in nodes:raise ValueError('incomplete Cargo graph')
 active.add(key);pending.extend(d['pkg'] for d in nodes[key]['deps'])
for package in sorted(metadata['packages'],key=lambda p:(p['name'],p['version'])):
 if package['id'] not in active or not package.get('source'):continue # never read private workspace source
 root=pathlib.Path(package['manifest_path']).parent;files=[]
 for candidate in root.iterdir():
  if candidate.is_file() and re.match(r'^(license|copying|notice)([._-]|$)',candidate.name,re.I):files.append(candidate)
 sub=root/'LICENSES'
 if sub.is_dir():files.extend(f for f in sub.iterdir() if f.is_file())
 if package.get('license_file'):
  f=(root/package['license_file']).resolve()
  if f.is_relative_to(root.resolve()) and f.is_file() and f not in files:files.append(f)
 row={'name':package['name'],'version':package['version'],'license':package.get('license'),'notice_files':[str(f.relative_to(root)) for f in files]};report.append(row)
 notices.append('\n===== '+row['name']+' '+row['version']+' | '+str(row['license'])+' =====\n')
 for f in sorted(files):
  if f.stat().st_size>1024*1024:raise ValueError('unexpected notice size')
  notices.extend([f'--- {f.relative_to(root)} ---\n',f.read_text(errors='replace')+'\n'])
pathlib.Path(a.notice).write_text('\n'.join(line.rstrip() for line in ''.join(notices).splitlines()).rstrip()+'\n');pathlib.Path(a.report).write_text(json.dumps({'packages':report,'missing_notice_files':[r['name'] for r in report if not r['notice_files']],'status':'inventory; manual obligations review pending'},indent=2)+'\n')
