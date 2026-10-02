"""Record executable versions and hashes, with no secrets or model weights."""
import datetime,hashlib,json,platform,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
paths=list((repo/'benchmarks/native_followup').glob('*.py'))+list((repo/'benchmarks/native_followup').glob('*.sh'))+[repo/'benchmarks/native_followup/PLAN.md']
paths += [repo/p for p in ['benchmarks/native_scale/gemma.py','benchmarks/native_scale/qwen.py','benchmarks/native_replication/reuse_worker.py','integrations/qwen_aimee/qwen_adapter.py','.local/bin/scale-ingest','.local/bin/aimee-memory-image','.local/bin/aimee-issue-fixture','target/release/aimee-qwen','integrations/qwen_aimee/placement-dual7900xtx-int8.json']]
value=dict(created=datetime.datetime.now(datetime.timezone.utc).isoformat(),platform=platform.platform(),python=sys.version,aimee_dependency='ad3585ac5381e3f0569dd8661b41fbe82cd6501d',baseline_source='40046da',files={str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},models={'Qwen/Qwen3.8-27B':'1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0','google/gemma-4-12B-it':'707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7'},model_account=subprocess.check_output(['id','memory-model'],text=True).strip())
with Path(sys.argv[1]).open('x') as f:json.dump(value,f,indent=2)
