"""Check actual hosted preparation after the isolated candidate client probe."""
import json
import pathlib
import subprocess


def prepared_jobs(logs):
    jobs=[]
    for line in logs.splitlines():
        try:row=json.loads(line)
        except json.JSONDecodeError:continue
        if row.get('event')=='prepared':jobs.append(row)
    if not jobs:raise ValueError('no actual preparation job observed after migration')
    for job in jobs:
        computation=job.get('computation',{})
        if computation.get('compute_dtype')!='torch.float32':
            raise ValueError('served preparation used a different computation dtype')
    if not any(job['computation'].get('evaluated_tokens',0)>0 for job in jobs):
        raise ValueError('no freshly evaluated preparation observed')
    return jobs


def main():
    root=pathlib.Path('/root/aimee-release-cert-20260927')
    upgrade=json.loads((root/'preparation-upgrade.json').read_text())
    if upgrade['status']!='deployed_pending_client_validation':raise ValueError('preparation migration did not complete')
    client=json.loads(subprocess.check_output(['pct','exec','110','--','cat','/opt/aimee-client/release-evidence/candidate-6-runtime.json']))
    if client['status']!='passed':raise ValueError('candidate client validation did not pass')
    logs=subprocess.check_output(['pct','exec','101','--','journalctl','-u','aimee-native-compiler','--since','@'+str(int(upgrade['started'])),'-o','cat','--no-pager'],text=True)
    report={'status':'failed','scope':'Observed preparation dtype during the isolated client-validation window; not a general accuracy claim'}
    try:
        report['jobs']=prepared_jobs(logs)
        report['status']='passed'
    except ValueError as error:
        report['error']=str(error)
        raise
    finally:
        (root/'preparation-dtype-check.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
