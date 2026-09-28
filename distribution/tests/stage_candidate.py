"""Stage exact candidate bytes for the lab-enabled launcher, without promotion.

This does not sign a production manifest or replace the normal installed release.
The later normal signed install/update/rollback remains a separate release gate.
"""
import argparse,hashlib,json,os,pathlib,shutil
p=argparse.ArgumentParser();p.add_argument('--installed-root',required=True);p.add_argument('--candidate-root',required=True);p.add_argument('--inputs',required=True);a=p.parse_args()
installed=pathlib.Path(a.installed_root).resolve();root=pathlib.Path(a.candidate_root).resolve();inputs=pathlib.Path(a.inputs).resolve()
if root.exists():raise ValueError('candidate root already exists')
profile=json.loads((inputs/'profile.json').read_text())
budgets={k:profile.get(k) for k in ('host_memory_budget','device_memory_budget','disk_budget')}
system_budget=profile.get('system_memory_budget',48*1024**3)
if (any(type(v) is not int or v<=0 for v in budgets.values())
    or type(system_budget) is not int
    or budgets['disk_budget']<budgets['host_memory_budget']
    or system_budget<max(1024**3,budgets['host_memory_budget'])):
 raise ValueError('candidate budgets violate installed launcher runtime defaults')
active=json.loads((installed/'active.json').read_text());previous=installed/'releases'/active['current'];manifest=json.loads((previous/'manifest.json').read_text());expected=json.loads((inputs/'expected-artifacts.json').read_text())
root.mkdir(mode=0o700);stage=root/'staged';stage.mkdir();actual=[]
for artifact in expected['artifacts']:
 relative=pathlib.PurePosixPath(artifact['path'])
 if relative.is_absolute() or '..' in relative.parts:raise ValueError('invalid artifact path')
 source=inputs/('image.json' if str(relative)=='runtime/image.json' else 'profile.json') if str(relative) in ('runtime/image.json','runtime/profile.json') else previous/relative
 if source.is_symlink() or not source.is_file():raise ValueError('not a regular artifact')
 with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
 if digest!=artifact['sha256'] or source.stat().st_size!=artifact['bytes']:raise ValueError('artifact bytes differ: '+str(relative))
 target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True)
 # Existing immutable installed blobs can be shared without copying model weights.
 if source.parent==inputs:shutil.copyfile(source,target);target.chmod(0o600)
 else:os.link(source,target)
 actual.append(dict(artifact))
identity=hashlib.sha256(json.dumps(sorted(actual,key=lambda x:x['path']),sort_keys=True,separators=(',',':')).encode()).hexdigest()
if identity!=expected['artifact_set_sha256']:raise ValueError('candidate artifact identity mismatch')
manifest.update(sequence=6,version='candidate-validation-6',model='lab-gemma4-12b-q8-native',gates=['lab_only'],artifacts=actual)
raw=(json.dumps(manifest,sort_keys=True,separators=(',',':'))+'\n').encode();manifest_id=hashlib.sha256(raw).hexdigest();(stage/'manifest.json').write_bytes(raw)
(root/'releases').mkdir();stage.rename(root/'releases'/manifest_id)
config=json.loads((installed/'config.json').read_text());config['memory_root']=str(root/'memory');(root/'memory').mkdir(mode=0o700)
(root/'config.json').write_text(json.dumps(config));(root/'config.json').chmod(0o600)
(root/'active.json').write_text(json.dumps({'current':manifest_id,'previous':None,'high_water_sequence':6})+'\n')
report={'status':'staged','artifact_set_sha256':identity,'manifest':manifest_id,'source_release':active['current'],'scope':'lab-enabled candidate runtime test; no production gates or signature asserted','artifacts_verified':len(actual)}
(root/'staging-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
