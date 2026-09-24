"""New fixture release of archived records; never mutate the old publication."""
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
def prepare(original, target):
    original,target=Path(original),Path(target)
    if (target/'READY').exists():return target
    target.mkdir();target.chmod(0o755)
    private=target/'private';private.mkdir(mode=0o700)
    def save(p,x):
        with p.open('x') as f:json.dump(x,f)
    def cli(*args):
        raw=subprocess.check_output([str(REPO/'.local/bin/aimee-memory-image'),*map(str,args)],text=True)
        return json.loads(raw) if raw.strip() else None
    cases=[c for c in json.loads((original/'cases.json').read_text()) if c['source']=='personal']
    change=json.loads((original/'private/personal-change.json').read_text())
    records=change['records'];by={r['id']:r for r in records}
    assert len(cases)==625 and len(records)==625
    for c in cases:
        assert {k:by[c['ref']['id']][k] for k in ['namespace','id','revision']}==c['ref']
    until=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=7)).isoformat()
    for contract in change['read_contracts']:contract['valid_until']=until
    corpus=json.loads((original/'private/general.json').read_text())
    save(private/'general.json',corpus)
    store=private/'source'
    base=cli('build','--root',store,'--input',private/'general.json')['view']
    change['upstream']=base
    save(private/'personal-change.json',change)
    head=cli('build','--root',store,'--input',private/'personal-change.json')['view']
    cli('publish','--root',store,'--view',head)
    auth=dict(version=1,id=target.name,subject='scale-model',policy_epoch='scale-1',source_view=head,
        active=True,valid_until=until,grants=['user:_user'],
        reference_lookups=[dict(namespace=corpus['namespace'],authority='test',mode='exact-key-v1')])
    save(private/'release.json',dict(authorization=auth,records=corpus['records']+records,reads=change['read_contracts']))
    subprocess.run([str(REPO/'.local/bin/aimee-issue-fixture'),'--input',str(private/'release.json'),
        '--output',str(private/'grant'),'--key',str(private/'key'),'--public-key',str(private/'public')],check=True,stdout=subprocess.DEVNULL)
    cli('compile-authorized','--root',store,'--output-root',private/'compiled','--authorization',private/'grant',
        '--authority-key',private/'public','--subject','scale-model','--policy-epoch','scale-1')
    installed=cli('install-published','--root',private/'compiled','--output-root',target/'image',
        '--reader-gid',subprocess.check_output(['id','-g','memory-model'],text=True).strip(),'--expected','')
    save(target/'cases.json',cases)
    save(target/'provenance.json',dict(original=str(original),original_cases_sha256=hashlib.sha256((original/'cases.json').read_bytes()).hexdigest(),
        original_change_sha256=hashlib.sha256((original/'private/personal-change.json').read_bytes()).hexdigest(),
        reason='Original image was replaced by the correction campaign and its research contracts expired; re-release original archived records in a new fixture.',
        changed='research release validity and publication metadata only; original records, revisions, queries and expected answers retained',
        valid_until=until,publication=installed))
    (target/'READY').write_text(dt.datetime.now(dt.timezone.utc).isoformat())
    return target
