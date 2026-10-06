import hashlib,json,importlib.metadata as md
from pathlib import Path
R=Path('/opt/jmlr-second-review-20261005/repair-cache/gemma-composition-candidate-r1');M=Path('/var/lib/aimee-large-release-validation/cuda-5080-20260930/models');S=Path('/opt/aimee-native-serving/clean-release-env-build2/lib/python3.12/site-packages')
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
paths=[M/n for n in ['config.json','tokenizer.json','tokenizer_config.json','chat_template.jinja','generation_config.json']]
paths += [Path('/mnt/pve/backup/aimee-experiments/native-serving-20261004/gemma12-q4/gemma12-q4_k_m.gguf')]
paths += list((S/'aimee_gemma4_12b').rglob('*'))
paths += list((R/'candidate3-site/aimee_native_runtime').rglob('*'))
paths += list((S/'vllm_gguf_plugin').rglob('*'))
paths += [R/'source/distribution/vllm/aimee_vllm/kernel.py',R/'aimee-model-client']
paths += [S/n for n in ['vllm/renderers/hf.py','vllm/renderers/base.py','vllm/inputs/engine.py','vllm/renderers/params.py','vllm/entrypoints/chat_utils.py','vllm/entrypoints/openai/chat_completion/protocol.py','transformers/tokenization_utils_base.py','transformers/utils/chat_template_utils.py']]
paths=[p for p in paths if p.is_file() and '__pycache__' not in str(p) and p.suffix!='.pyc']
result={'format':'gemma-prefix-integration-source-freeze-v1','source_sha256':{str(p):sha(p) for p in sorted(set(paths))},'dependency_versions':{n:md.version(n) for n in ['vllm','torch','triton','transformers','tokenizers','aimee-gemma4-12b']}}
assert result['source_sha256'][str(M/'config.json')]=='478c46e8d2c52d5c2d85bf67e3b3e8c90e7c9d91086cee27e3c267907e936bd9'
assert result['source_sha256'][str(paths[5])]=='a509d1e25b028dfcf9b311a3321e510b7d78309f04421891a62488feab3289e9'
print(json.dumps(result,indent=2))
