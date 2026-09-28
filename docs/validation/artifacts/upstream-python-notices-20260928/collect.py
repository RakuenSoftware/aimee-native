from pathlib import Path
import urllib.request,urllib.parse,json,base64,hashlib,tarfile
root=Path('/tmp/aimee-native-precomputed/docs/validation/artifacts/upstream-python-notices-20260928');root.mkdir(exist_ok=False)
report={'scope':'Retain upstream notices from pinned release references. Mooncake uses the upstream 0.3.13 base release for the ROCm post1 distribution; this does not prove every downstream binary is identical to upstream.','results':[]}
def get(url):
 with urllib.request.urlopen(url,timeout=30) as f:return json.load(f)
def save():(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def retain(package,repo,ref,paths,extra=None):
 commit=get(f'https://api.github.com/repos/{repo}/commits/{urllib.parse.quote(ref,safe="")}')['sha']
 row={'package':package,'repository':repo,'ref':ref,'commit':commit,'notices':[],**(extra or {})};report['results'].append(row);save()
 for path in paths:
  url=f'https://api.github.com/repos/{repo}/contents/{path}?ref={commit}';d=get(url);b=base64.b64decode(d['content']);assert hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()==d['sha'];digest=hashlib.sha256(b).hexdigest();p=root/package/(digest+'.txt');p.parent.mkdir(exist_ok=True);p.write_bytes(b);row['notices'].append({'path':path,'url':d['html_url'],'git_blob_sha1':d['sha'],'sha256':digest,'file':str(p.relative_to(root))})
 row['status']='notices_collected';save()
retain('loguru','Delgan/loguru','0.7.3',['LICENSE'])
retain('mistral_common','mistralai/mistral-common','v1.11.7',['LICENCE'])
retain('model-hosting-container-standards','aws/model-hosting-container-standards','v0.1.16',['LICENSE','NOTICE'])
retain('mooncake-transfer-engine-rocm','kvcache-ai/Mooncake','v0.3.13',['LICENSE-APACHE'],{'scope':'Base release notice for the ROCm post1 package, not an exact downstream source attestation.'})
package='opentelemetry-semantic-conventions-ai';path='packages/'+package+'/pyproject.toml';repo='traceloop/openllmetry'
meta=get('https://pypi.org/pypi/'+package+'/0.5.1/json');until=min(x['upload_time_iso_8601'] for x in meta['urls'])
archive=Path('/home/virant/.cache/aimee-release-sources-20260928/pypi-notices-r1')/package/'opentelemetry_semantic_conventions_ai-0.5.1.tar.gz'
with tarfile.open(archive) as t:
 m=next(m for m in t if m.name.endswith('/pyproject.toml'));published=t.extractfile(m).read()
query=urllib.parse.urlencode({'path':path,'until':until,'per_page':10})
commits=get(f'https://api.github.com/repos/{repo}/commits?'+query)
for item in commits:
 commit=item['sha'];d=get(f'https://api.github.com/repos/{repo}/contents/{path}?ref={commit}');raw=base64.b64decode(d['content'])
 if raw==published:
  retain(package,repo,commit,['LICENSE'],{'published_pyproject_sha256':hashlib.sha256(published).hexdigest(),'version_metadata_match':'Exact bytes match the 0.5.1 source distribution pyproject; does not claim a full source-tree comparison.'});break
else:raise RuntimeError('no matching published telemetry version metadata in bounded history')
report['status']='collection_complete';save()
(root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in sorted(root.rglob('*')) if p.is_file() and p.name!='SHA256SUMS'))
print([(x['package'],x['status']) for x in report['results']])
