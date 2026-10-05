"""Systemd readiness: authenticated model discovery and private admission health."""
import argparse
import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def ready(config, timeout=1700):
    c=json.loads(Path(config).read_text());serve=c['serve']
    deadline=time.monotonic()+timeout
    endpoint='http://'+serve.get('host','127.0.0.1')+':'+str(serve['port'])
    main_pid=os.environ.get('MAINPID') or subprocess.check_output(['systemctl','show','aimee-native-serving','--property=MainPID','--value'],text=True).strip()
    if main_pid=='0':raise RuntimeError('serving process exited before readiness')
    while time.monotonic()<deadline:
        if main_pid and not Path('/proc/'+main_pid).exists():
            raise RuntimeError('serving process exited before readiness')
        try:
            request=urllib.request.Request(endpoint+'/v1/models',headers={'Authorization':'Bearer '+os.environ['VLLM_API_KEY']})
            with urllib.request.urlopen(request,timeout=5) as response:
                if not json.load(response)['data']:raise RuntimeError('no model loaded')
            with socket.socket(socket.AF_UNIX) as channel:
                channel.settimeout(5);channel.connect(c['control_socket']);channel.sendall(b'{"op":"status"}\n')
                status=json.loads(channel.makefile('rb').readline())
            if status!={'state':'active'}:raise RuntimeError('native admission is inactive')
            break
        except (OSError,ValueError,KeyError,RuntimeError):time.sleep(2)
    else:raise RuntimeError('serving readiness deadline exceeded')
    canary=c.get('canary')
    if canary:
        body={'model':c['model'],'messages':[{'role':'system','content':canary['system']},{'role':'user','content':canary['query']}],
              'temperature':0,'max_tokens':32,'chat_template_kwargs':{'enable_thinking':False},
              'vllm_xargs':{'aimee_publication':canary['publication']}}
        request=urllib.request.Request(endpoint+'/v1/chat/completions',data=json.dumps(body).encode(),
                    headers={'Content-Type':'application/json','Authorization':'Bearer '+os.environ['VLLM_API_KEY']})
        with urllib.request.urlopen(request,timeout=180) as response:result=json.load(response)
        answer=result['choices'][0]['message']['content'].strip().rstrip('.')
        if answer.lower()!=canary['expected'].lower():raise RuntimeError('native readiness canary failed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a=p.parse_args();ready(a.config)
