"""Persist partial progress while the separately owned campaign is running."""
import json,os,pathlib,subprocess,sys,time
root=pathlib.Path(os.environ.get('SWE_RUN_ROOT','/opt/swe-native'))
while True:
    subprocess.run([sys.executable,str(root/'summarize.py')],check=True,stdout=subprocess.DEVNULL)
    try:state=json.loads((root/'status.json').read_text())
    except (FileNotFoundError,json.JSONDecodeError):time.sleep(2);continue
    if state.get('status')!='running':break
    time.sleep(30)
