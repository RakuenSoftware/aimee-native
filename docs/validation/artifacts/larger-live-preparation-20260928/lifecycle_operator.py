from pathlib import Path
import subprocess,json,pwd
root=Path(__file__).parent
user=pwd.getpwuid(Path('/etc/aimee-native/preparation.json').stat().st_uid).pw_name
report={'status':'running','profiles':[]}
(root/'lifecycle-status.json').write_text(json.dumps(report))
try:
 for profile in ['gemma26','qwen27']:
  with (root/profile/'lifecycle.log').open('w') as log:
   subprocess.run(['python3',str(root/'live_publication_lifecycle.py'),'--config',str(root/profile/'preparation.json'),'--policy','/etc/aimee-native/release.json','--preparer','/opt/aimee-native/bin/native-prepare','--user',user,'--publisher-unit','aimee-native-publisher.service','--expected-records','3','--output',str(root/profile/'lifecycle.json')],stdout=log,stderr=log,check=True)
  report['profiles'].append(profile)
  (root/'lifecycle-status.json').write_text(json.dumps(report))
 report['status']='passed'
except BaseException as error:
 report.update(status='failed',error=repr(error));raise
finally:(root/'lifecycle-status.json').write_text(json.dumps(report,indent=2)+'
')
