"""Operator-only crash/recovery probe for the documented private preview host.

Run on the Aimee host after enrollment, against its dedicated canary publication.
This deliberately SIGKILLs native delivery/follower and touches the upstream
socket timestamp; it never terminates the Aimee frontend or changes source data.
"""
import json,pathlib,subprocess,time,os
report={};directory=pathlib.Path('/run/aimee-native');inode=directory.stat().st_ino

def pid(unit):return int(subprocess.check_output(['systemctl','show','--property=MainPID','--value',unit]))
def active(unit):return subprocess.run(['systemctl','is-active','--quiet',unit]).returncode==0
def check(config='/etc/aimee-native/preparation.json'):
 return subprocess.run(['runuser','-u','aimee','--','/opt/aimee-native/bin/native-prepare',config,'--check'],capture_output=True).returncode==0

def await_ready(previous,unit):
 for _ in range(150):
  if active(unit) and pid(unit)!=previous and pid(unit)>0 and check():return
  time.sleep(.2)
 raise RuntimeError('service did not recover')

before=pid('aimee-native-delivery')
subprocess.run(['systemctl','kill','--signal=SIGKILL','--kill-whom=main','aimee-native-delivery'],check=True)
await_ready(before,'aimee-native-delivery')
assert inode==directory.stat().st_ino
report['delivery_sigkill']={'passed':True,'directory_inode_preserved':True,'stale_socket_recovered':True}
before=pid('aimee-native-follower')
subprocess.run(['systemctl','kill','--signal=SIGKILL','--kill-whom=main','aimee-native-follower'],check=True)
withdrawn=False
for _ in range(100):
 if not (pathlib.Path('/var/lib/aimee-native/image')/'CURRENT').exists():
  assert not check(),'killed follower left an admissible image'
  withdrawn=True;break
 time.sleep(.02)
assert withdrawn,'follower withdrawal not observed'
await_ready(before,'aimee-native-follower')
for _ in range(100):
 if active('aimee-native-delivery'):break
 time.sleep(.05)
assert active('aimee-native-delivery')
assert inode==directory.stat().st_ino
report['follower_sigkill']={'passed':True,'stale_image_withdrawn':True,'delivery_recovered':True}
before=pid('aimee-native-gateway')
os.utime('/var/lib/docker/volumes/aimee_aimee-server-home/_data/aimee-http.sock',None)
await_ready(before,'aimee-native-gateway')
assert check('/etc/aimee-native/fallback-test.json'),'fallback failed after gateway socket refresh'
report['upstream_socket_refresh']={'passed':True,'gateway_restarted':True,'restricted_fallback_ready':True}
pathlib.Path('/var/lib/aimee-native/supervision-test.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
