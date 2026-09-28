"""Source-backed experiences for the isolated SWE research harness.

Official outcome is a fixture acceptance signal, not production authorization.
No model-generated summary can replace a successful, replay-checked procedure.
"""
import hashlib,json,re


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


def scope(task):return {'instance_id':task['instance_id'],'base_commit':task['base_commit']}


def successful_commands(trajectory):
    """Pair executed actions with actual tool outcomes, not assistant claims."""
    pending=[];found=[]
    for message in trajectory.get('messages',[]):
        if message.get('role')=='assistant':
            pending=[a['command'] for a in message.get('extra',{}).get('actions',[])]
        elif message.get('role')=='user' and pending:
            extra=message.get('extra',{})
            if extra.get('returncode')==0 and len(pending)==1:found.append(pending[0])
            pending=[]
    return found


def edit_candidates(patch,trajectory):
    paths=re.findall(r'^\+\+\+ b/(.+)$',patch,re.M)
    readonly=re.compile(r'^\s*(?:cat\s|grep\s|rg\s|head\s|tail\s|sed\s+-n|git\s+(?:diff|show|status))')
    return list(dict.fromkeys(c for c in successful_commands(trajectory)
        if any(p in c for p in paths) and not readonly.match(c) and 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT' not in c))[:8]


def patch_command(patch):
    """Lossless fallback, including shell metacharacters in a model's own patch."""
    marker='AIMEE_PATCH_'+digest(patch)[:24]
    while marker in patch.splitlines():marker+='X'
    return "git apply <<'"+marker+"'\n"+patch.rstrip('\n')+'\n'+marker


def compact_patch_command(patch):
    """Lossless line edits for ordinary text patches; acceptance still needs replay.

    No model summary or semantic rewrite. Unsupported patch features retain the
    original git-apply fallback. Coordinates refer only to the scoped clean base.
    """
    if '\r' in patch or '\\ No newline' in patch:return None
    lines=patch.splitlines(keepends=True);files={};path=None;i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('diff --git '):path=None
        elif line.startswith('+++ b/'):
            path=line[6:].rstrip('\n')
            if not path or path.startswith('/') or '..' in path.split('/'):return None
            files.setdefault(path,[])
        elif line.startswith('@@ '):
            match=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line)
            if not match or path is None:return None
            start,old_count,_,new_count=match.groups()
            old_count=int(old_count) if old_count is not None else 1
            new_count=int(new_count) if new_count is not None else 1
            pos=int(start)-(old_count!=0);old_seen=new_seen=0;block=None;i+=1
            def flush():
                nonlocal block
                if block is not None:files[path].append(block);block=None
            while i<len(lines) and lines[i][:1] in (' ','+','-'):
                item=lines[i];kind=item[0]
                if kind==' ':
                    flush();pos+=1;old_seen+=1;new_seen+=1
                else:
                    if block is None:block=[pos,pos,[]]
                    if kind=='-':pos+=1;block[1]=pos;old_seen+=1
                    else:block[2].append(item[1:]);new_seen+=1
                i+=1
            flush()
            if old_seen!=old_count or new_seen!=new_count:return None
            continue
        elif not line.startswith(('index ','--- a/')):return None
        i+=1
    if not files or not any(files.values()):return None
    program=['from pathlib import Path']
    for path,edits in files.items():
        if not edits:continue
        ordered=sorted(edits,key=lambda edit:edit[0])
        if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):return None
        program+=['p=Path('+repr(path)+');s=p.read_text().splitlines(True)']
        for start,end,new in reversed(ordered):
            program.append('s['+str(start)+':'+str(end)+']='+repr(new))
        program.append("p.write_text(''.join(s))")
    marker='AIMEE_EDIT_'+digest(patch)[:24]
    command="python3 <<'"+marker+"'\n"+'\n'.join(program)+'\n'+marker
    return command if len(command)<len(patch_command(patch)) else None


def accept_success(task,row,trajectory,replay):
    if row.get('resolved') is not True:raise ValueError('successful outcome required')
    patch=row.get('model_patch','')
    if not patch.strip():raise ValueError('successful procedure requires a nonempty own patch')
    trials=[]
    # Replay returns the independently observed diff from a fresh base checkout.
    compact=compact_patch_command(patch)
    fallbacks=([compact] if compact else [])+[patch_command(patch)]
    for command in edit_candidates(patch,trajectory)+fallbacks:
        observation=replay(command)
        match=observation.get('returncode')==0 and observation.get('patch','').strip()==patch.strip()
        trials.append({'command':command,'observation':observation,'matches_successful_patch':match})
        if match:
            return {'schema':1,'scope':scope(task),'kind':'accepted_success','source_arm':row['arm'],
                    'own_patch':patch,'patch_sha256':digest(patch),'command':command,
                    'trajectory_sha256':digest(json.dumps(trajectory,sort_keys=True)),
                    'validation':'official overall success plus independent exact-patch replay',
                    'replay_trials':trials}
    raise ValueError('no candidate reproduced successful patch')


def format_failures(trajectory):
    """Capture parser rejection evidence, distinct from executed tool failures."""
    failures=[]; pending=None
    for message in trajectory.get('messages',[]):
        if message.get('role')=='assistant':
            extra=message.get('extra',{})
            pending=message if 'finish_reason' in extra and not extra.get('actions') else None
        elif message.get('role')=='user':
            feedback=message.get('content','')
            if (pending is not None and 'returncode' not in message.get('extra',{})
                    and feedback.startswith('Return exactly one fenced bash command.')):
                response=pending.get('content','')
                failures.append({'finish_reason':pending['extra']['finish_reason'],
                    'response':response,'response_sha256':digest(response),'feedback':feedback})
            pending=None
    return failures


def render_format_failure(experience):
    for failure in reversed(experience.get('format_failures',[])):
        feedback=failure['feedback']
        if len(feedback)<=3000:
            return ('The previous assistant response was rejected before any command executed. '
                    'Response finish reason: '+failure['finish_reason']+'.\nObserved parser feedback:\n'+feedback)
    return ''


def failure_evidence(task,row,trajectory):
    observations=[]
    pending=[]
    for m in trajectory.get('messages',[]):
        if m.get('role')=='assistant':pending=[a['command'] for a in m.get('extra',{}).get('actions',[])]
        elif m.get('role')=='user' and pending:
            extra=m.get('extra',{})
            if extra.get('returncode') not in (None,0):
                observations.append({'command':pending[0],'returncode':extra['returncode'],
                                     'observation':m.get('content','')})
            pending=[]
    return {'schema':1,'scope':scope(task),'kind':'failed_attempt','source_arm':row['arm'],
            'exit_status':row.get('exit_status'),'own_patch':row.get('model_patch',''),
            'observations':observations,'format_failures':format_failures(trajectory),'resolved':row.get('resolved')}


def promote(previous,candidate):
    if previous is not None and previous['scope']!=candidate['scope']:raise ValueError('experience scope mismatch')
    if previous is not None and previous['kind']=='accepted_success':
        return previous  # Preserve the first validated procedure, including after failures.
    return candidate


def render_success(experience):
    if experience['kind']!='accepted_success':raise ValueError('not an accepted procedure')
    return ('Observed successful edit for this exact issue on a clean checkout, in /testbed:\n```bash\n'
            +experience['command']+'\n```\nThis exact edit independently reproduces the patch from a successful attempt. '
            'Inspect the checkout before applying; do not repeat an already-applied edit. Run relevant existing tests.')
