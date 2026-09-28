#!/usr/bin/env python3
"""Reconcile the fixed release inventory with retained source and notice evidence."""
from pathlib import Path
import json,hashlib,collections
r=Path('docs/validation/artifacts')
load=lambda p:json.loads((r/p).read_text())
plan=load('larger-os-source-plan-20260928/report.json')
notices=load('consolidated-notices-20260928/manifest.json')['os_packages']
relationships={p['package']:p for p in load('os-notice-reconciliation-20260928/report.json')['packages']}
rows=[]
for p in plan['packages']:
 source=p['source']; version=p['version']
 binaries=[b for b in notices if b['source']==source and b['source_version']==version]
 refs=set()
 for b in binaries:
  for n in [b['notice']]+b['alternative_notices']+relationships.get(b['binary'],{}).get('notices',[]):
   if 'sha256' in n:refs.add(n['sha256'])
 if p['status']=='resolved' or source in {'curl','gcc-13','gcc-16','pyjwt'}:
  state='exact_source_delivered';evidence='larger-source-collection-20260928/'
 elif source=='python3.12':state='exact_source_delivered';evidence='python-source-delivery-20260929/'
 elif source=='rocm-gdb':state='matching_release_source_delivered';evidence='rocgdb-source-collection-20260928/'
 elif source=='ionic':state='installed_payload_is_source_and_configuration';evidence='network-package-evidence-20260928/'
 elif source in {'rocm-dev','rocm-libs','rocm-utils'}:state='version_marker_metapackage';evidence='os-notice-reconciliation-20260928/'
 elif source=='bnxt-rocelib':state='vendor_binary_terms_unresolved';evidence='broadcom-original-package-20260928/'
 elif source=='rdma-core':state='file_scoped_dual_license_notice_retained';evidence='network-package-evidence-20260928/'
 else:
  state='component_notice_retained_no_separate_source_gap_established';evidence='consolidated-notices-20260928/'
  if not refs:
   assert source=='hsa-amd-aqlprofile',source
   refs.add('b185aaa652b0bf066c37a0d6314ce4bf4521e4a3c9bf46edd2f6a777ac522223')
   evidence='supplemental-notice-delivery-20260928/'
 rows.append(dict(source=source,version=version,binaries=p['binaries'],disposition=state,evidence=evidence,notice_sha256=sorted(refs)))
assert len(rows)==342
report=dict(scope='Source/version delivery reconciliation for the installed OS inventory. No blanket legal clearance or reproducible-build claim.',counts=dict(collections.Counter(x['disposition'] for x in rows)),packages=rows,limitations=['Exact-source delivery status records the previously verified archive collection, not independent binary reproduction.','Component notices and installed-file relationships are used at their documented scope; no requirement for all permissive upstream source trees is invented.','rdma-core notices are file-scoped: GPL packaging/header entries do not by themselves establish the license of libionic binaries.','Broadcom exact compiled payload terms remain unresolved.'])
out=r/'source-reconciliation-20260929';out.mkdir(exist_ok=True)
p=out/'report.json';p.write_text(json.dumps(report,indent=2)+'\n')
(out/'SHA256SUMS').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'  report.json\n')
print(json.dumps(report['counts'],indent=2))
