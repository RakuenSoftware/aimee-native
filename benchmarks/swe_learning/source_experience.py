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


def accept_success(task,row,trajectory,replay):
    if row.get('resolved') is not True:raise ValueError('successful outcome required')
    patch=row.get('model_patch','')
    if not patch.strip():raise ValueError('successful procedure requires a nonempty own patch')
    trials=[]
    # Replay returns the independently observed diff from a fresh base checkout.
    for command in edit_candidates(patch,trajectory)+[patch_command(patch)]:
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
            'observations':observations,'resolved':row.get('resolved')}


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
