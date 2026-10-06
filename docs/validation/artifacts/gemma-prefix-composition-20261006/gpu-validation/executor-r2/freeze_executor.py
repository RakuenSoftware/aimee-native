import hashlib,json,shutil
from pathlib import Path
ROOT=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1')
NAS=Path('/mnt/pve/backup/aimee-experiments/root-evacuation-20261005-r1/gemma-composition-candidate-r1/gpu-validation')
names=['run_integration.py','queue_integration.py','integration_trace.py','service_boot.py','cpu_preflight.py','freeze_sources.py','gemma_integration_trace-1.0.dist-info/METADATA','gemma_integration_trace-1.0.dist-info/entry_points.txt']
h={name:hashlib.sha256((ROOT/'gpu-executor-r2'/name).read_bytes()).hexdigest() for name in names}
manifest={'format':'gemma-prefix-integration-executor-freeze-v1','protocol_sha256':'0e8ff8850e71f353ac45b547644a37674bd065e8223188f80a9ab98c203dac22','frozen_sources_sha256':'18a881813cfdbff1c24843980d025b5d9d9d834f38d62acb7ddff75a21d052f3','executor_sha256':h,'stock_template_kwargs':{'enable_thinking':False},'trace_scope':'subclass successful native route returns; unchanged candidate math and actual adapter/loader registration','result_relative_paths':{'pairs':'pairs-summary.json','native_calls':'native-calls.jsonl','empty_selection':'empty-selection.json','denials':'denial-controls.json','preflight':'preflight.json','postflight':'postflight.json'},'legacy_http_control':'not exercised; compiled actual admission CPU denial covered; explicit in resulting denial artifact','pairs_summary_schema':'pairs=6,canonical_revisions=2; name/publication/request_native_token_proof_passed/native_kernel_call_count/greedy_output_ids_equal/text_scores/native_scores','per_pair_file_schema':'{name}-pair.json: bank_token_ids + native_prompt_token_ids == text_prompt_token_ids; original JSON bodies/raw HTTP responses/greedy token IDs/EM/F1 retained','trace_schema':'JSONL pid/layer/query_rows/catalog_digest/pins[{request_id,publication,publication_key,publication_model}]/native_kernel_returned=true','completion_policy':'No scientific gold pass; structural pass only; any greedy disagreement retained and investigated'}
manifest['source_external_pins']={'/opt/aimee-native-serving/q4-serving-config-r6.json':'cd6a99aa4a207304fbdb3fca1f87401a1dc1dce1af2b3bba2bd40a86485bf3da'}
manifest['supersedes_executor_manifest_sha256']='8030e0b37b3875001212e3fb226ffeb6383c8e388bcf9d609c7ac8d9428f7f40'
manifest['amendment']='Append-only evidence copy and exclusive final receipt; exact released inherited serving config binding; no protocol/model/compiled-wheel changes'
for name in names:
 dest=NAS/'executor-r2'/name;dest.parent.mkdir(parents=True,exist_ok=True)
 with (ROOT/'gpu-executor-r2'/name).open('rb') as src,dest.open('xb') as out:shutil.copyfileobj(src,out)
with (NAS/'executor-manifest-r2.json').open('x') as f:f.write(json.dumps(manifest,indent=2)+'\n')
print(hashlib.sha256((NAS/'executor-manifest-r2.json').read_bytes()).hexdigest())
