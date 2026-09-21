"""Research unit lifecycle check; never operates on production Aimee services."""
import errno,json,socket,stat,subprocess,time,urllib.request
from pathlib import Path
b=Path('/opt/aimee-qwen-rust');root=b/'kb-cue-fix-20260921';path=Path('/run/aimee-rust-native/search.sock')
unit='aimee-rust-gateway'
def stop():subprocess.run(['systemctl','stop',unit],check=True)
def start():
    lines=(b/'start-cue-fix.sh').read_text().splitlines()
    line=next(x for x in lines if '--unit='+unit in x)
    subprocess.run(['bash','-c','\n'.join(lines[:4]+[line])],check=True)
    for _ in range(100):
        with socket.socket(socket.AF_UNIX) as s:
            try:s.connect(str(path));return
            except OSError:time.sleep(.1)
    raise RuntimeError('research gateway did not become ready')
stop()
# One-time migration from the previous unit that did not own its runtime dir.
if path.exists():
    with socket.socket(socket.AF_UNIX) as s:
        try:s.connect(str(path))
        except OSError as e:
            assert e.errno==errno.ECONNREFUSED
            info=path.lstat();assert stat.S_ISSOCK(info.st_mode) and info.st_uid==0
            path.unlink()
        else:raise RuntimeError('live socket after stop; refusing removal')
start()
assert subprocess.check_output(['systemctl','show',unit,'--property=RuntimeDirectory','--value'],text=True).strip()=='aimee-rust-native'
stop();assert not path.exists(),'managed socket survived stop'
start()
case=next(c for c in json.loads((b/'general-cases.json').read_text()) if c['id']=='personal-1')
payload=dict(messages=[dict(role='system',content='Answer using the available memory. Return only the requested value or values. If unknown, return unknown.'),dict(role='user',content=case['query'])],temperature=0,max_tokens=40)
with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:18793/v1/chat/completions',json.dumps(payload).encode(),{'Content-Type':'application/json'}),timeout=180) as r:response=json.load(r)
answer=response['choices'][0]['message']['content']
result=dict(socket_removed_on_stop=True,gateway_restart_succeeded=True,answer=answer,expected=case['expected'],response=response)
(root/'gateway-restart.json').write_text(json.dumps(result,indent=2)+'\n')
assert answer.replace(' ','')==case['expected']
print(json.dumps(result),flush=True)
