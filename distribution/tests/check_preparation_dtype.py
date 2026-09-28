"""Check actual hosted preparation after the isolated candidate client probe."""
import json
import pathlib
import subprocess


def prepared_jobs(logs, expected_policy=None):
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
        if expected_policy is not None:
            if computation.get('reuse_policy')!=expected_policy:
                raise ValueError('served preparation used a different reuse policy')
            tokens=computation.get('tokens')
            if type(tokens) is not int or computation.get('reused_prefix_tokens') not in (0,tokens):
                raise ValueError('served preparation reused an unvalidated partial prefix')
    if not any(job['computation'].get('evaluated_tokens',0)>0 for job in jobs):
        raise ValueError('no freshly evaluated preparation observed')
    return jobs


def main():
    root=pathlib.Path('/root/aimee-release-cert-20260927')
    upgrade=json.loads((root/'preparation-upgrade.json').read_text())
    if upgrade['status']!='deployed_pending_client_validation':raise ValueError('preparation migration did not complete')
    client=json.loads(subprocess.check_output(['pct','exec','110','--','cat','/opt/aimee-client/release-evidence/candidate-6-runtime.json']))
    if client['status']!='passed':raise ValueError('candidate client validation did not pass')
    correction=json.loads((root/'preparation-reuse-correction.json').read_text())
    logs=subprocess.check_output(['pct','exec','101','--','journalctl','-u','aimee-native-compiler','--since','@'+str(int(correction['updated'])),'-o','cat','--no-pager'],text=True)
    report={'status':'failed','scope':'Observed preparation dtype during the isolated client-validation window; not a general accuracy claim'}
    try:
        report['jobs']=prepared_jobs(logs,expected_policy='identical-complete-input')
        report['correction']=correction
        report['status']='passed'
    except ValueError as error:
        report['error']=str(error)
        raise
    finally:
        (root/'preparation-dtype-check.json').write_text(json.dumps(report,indent=2)+'\n')

if __name__=='__main__':main()
