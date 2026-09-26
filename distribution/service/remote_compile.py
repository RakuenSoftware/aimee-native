"""Private compiler transport; encoding remains on the managed preparation host.

Use a restricted SSH key and pinned host key. Neither role is a customer runtime.
The frontend accepts only fixed artifact names; Rust admits their content later.
"""
import argparse,fcntl,json,os,pathlib,re,signal,socket,stat,struct,subprocess,sys,tempfile
MAGIC=b'AMCP1';MAX_REQUEST=8*1024**2;MAX_INDEX=16*1024**2;MAX_PAYLOAD=1024**3

def read_exact(stream,count):
    result=bytearray()
    while len(result)<count:
        chunk=stream.read(min(count-len(result),1024**2))
        if not chunk:raise ValueError('truncated compiler transport')
        result.extend(chunk)
    return bytes(result)

def transfer(source,target,count):
    while count:
        chunk=source.read(min(count,1024**2))
        if not chunk:raise ValueError('truncated compiler artifact')
        target.write(chunk);count-=len(chunk)

def owned_config(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_uid not in (0,os.geteuid()) or st.st_mode&0o022:raise ValueError('untrusted compiler configuration')
        raw=f.read(MAX_REQUEST+1)
        if len(raw)>MAX_REQUEST:raise ValueError('compiler configuration too large')
        return json.loads(raw)

def frontend(config,output,identity,key):
    raw=sys.stdin.buffer.read(MAX_REQUEST+1)
    if len(raw)>MAX_REQUEST:raise ValueError('compiler request too large')
    request=json.loads(raw)
    wire=json.dumps({'identity':identity,'key':key,'request':request}).encode()
    if len(wire)>MAX_REQUEST:raise ValueError('compiler envelope too large')
    root=pathlib.Path(output);root.mkdir(parents=True,exist_ok=True)
    command=config['command']
    if not isinstance(command,list) or not command or not all(isinstance(x,str) and x for x in command):raise ValueError('invalid compiler transport')
    # A temporary input avoids deadlock between large request writes and response
    # reads. Both directions are bounded; stdout artifacts stream without buffering.
    with tempfile.TemporaryFile() as input:
        input.write(wire);input.seek(0)
        child=subprocess.Popen(command,stdin=input,stdout=subprocess.PIPE)
        try:
            if read_exact(child.stdout,5)!=MAGIC:raise ValueError('invalid compiler response')
            index_size,payload_size=struct.unpack('!QQ',read_exact(child.stdout,16))
            if not 0<index_size<=MAX_INDEX or not 0<payload_size<=MAX_PAYLOAD:raise ValueError('compiler artifact exceeds limit')
            for name,size in [('index.json',index_size),('compact.pack',payload_size)]:
                with (root/name).open('xb') as target:
                    os.chmod(root/name,0o600);transfer(child.stdout,target,size);target.flush();os.fsync(target.fileno())
            if child.stdout.read(1) or child.wait(timeout=10)!=0:raise ValueError('compiler response not complete')
        finally:
            child.stdout.close()
            if child.poll() is None:child.kill();child.wait()

def validate_wire(raw, model_revision):
    if len(raw)>MAX_REQUEST:raise ValueError('compiler request too large')
    wire=json.loads(raw)
    if set(wire)!={'identity','key','request'} or wire['identity']!=model_revision or not re.fullmatch('[a-f0-9]{64}',wire['key']):raise ValueError('compiler identity rejected')
    if wire['request']['identity']['model_revision']!=wire['identity']:raise ValueError('compiler model mismatch')
    return wire


def resident_worker(config, raw):
    # The daemon owns model lifetime and temporary output. No caller paths or
    # shell commands cross this socket; disconnected responses are discarded.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(540)
        client.connect(config['resident_socket'])
        client.sendall(raw)
        client.shutdown(socket.SHUT_WR)
        with client.makefile('rb') as response:
            if read_exact(response,5)!=MAGIC:raise ValueError('invalid resident compiler response')
            sizes=struct.unpack('!QQ',read_exact(response,16))
            if not 0<sizes[0]<=MAX_INDEX or not 0<sizes[1]<=MAX_PAYLOAD:raise ValueError('resident compiler artifact exceeds limit')
            sys.stdout.buffer.write(MAGIC+struct.pack('!QQ',*sizes))
            for size in sizes:transfer(response,sys.stdout.buffer,size)
            if response.read(1):raise ValueError('extra resident compiler response')
            sys.stdout.buffer.flush()


def worker(config):
    raw=sys.stdin.buffer.read(MAX_REQUEST+1)
    wire=validate_wire(raw,config['model_revision'])
    if config.get('resident_socket'):
        resident_worker(config,raw)
        return
    state=pathlib.Path(config['state']);state.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (state/'compiler.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with tempfile.TemporaryDirectory(prefix='job-',dir=state) as temporary:
            root=pathlib.Path(temporary);output=root/'payload'
            env=dict(os.environ,HF_HUB_OFFLINE='1',AIMEE_NATIVE_LIBRARY=config['library'])
            command=config['compiler']+['--output',str(output),'--identity',wire['identity'],'--key',wire['key']]
            with tempfile.TemporaryFile() as input:
                input.write(json.dumps(wire['request']).encode());input.seek(0)
                child=subprocess.Popen(command,stdin=input,stdout=subprocess.DEVNULL,env=env,start_new_session=True)
                def interrupted(signum,frame):raise InterruptedError('compiler channel closed')
                previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGHUP,signal.SIGTERM,signal.SIGINT)}
                try:
                    if child.wait(timeout=540)!=0:raise ValueError('private compiler failed')
                finally:
                    for sig,handler in previous.items():signal.signal(sig,handler)
                    # Also remove descendants if their leader exited first.
                    try:os.killpg(child.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    child.wait()
            with (output/'index.json').open('rb') as index,(output/'compact.pack').open('rb') as payload:
                sizes=[os.fstat(f.fileno()).st_size for f in (index,payload)]
                if not 0<sizes[0]<=MAX_INDEX or not 0<sizes[1]<=MAX_PAYLOAD:raise ValueError('compiler artifact exceeds limit')
                sys.stdout.buffer.write(MAGIC+struct.pack('!QQ',*sizes))
                transfer(index,sys.stdout.buffer,sizes[0]);transfer(payload,sys.stdout.buffer,sizes[1]);sys.stdout.buffer.flush()

def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=('frontend','worker'));p.add_argument('--config',required=True);p.add_argument('--output');p.add_argument('--identity');p.add_argument('--key');a=p.parse_args()
    config=owned_config(a.config)
    if a.role=='worker':worker(config)
    else:frontend(config,a.output,a.identity,a.key)
if __name__=='__main__':main()
