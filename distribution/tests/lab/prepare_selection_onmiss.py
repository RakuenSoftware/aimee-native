import json,pathlib
root=pathlib.Path('/opt/aimee-memory-lab');fixture=root/'vllm-native-fixture-r1'
result=json.loads((root/'real-reader-preparation-r2.json').read_text())['reuse']['result']
catalog=json.loads((fixture/'catalog.json').read_text());catalog['publications']={result['key']:{k:result[k] for k in ('root','model','key')}};catalog['selections']=[{'publication':result['key'],'authorized_view':result['authorized_view'],'records':result['records']}]
(fixture/'onmiss-catalog.json').write_text(json.dumps(catalog))
config=json.loads((fixture/'disk-config.json').read_text());config.update(catalog=str(fixture/'onmiss-catalog.json'),selection_socket=str(fixture/'onmiss-selection.sock'),control_socket=str(fixture/'onmiss-control.sock'),serve={'tensor_parallel_size':2,'port':8141})
(fixture/'onmiss-serving.json').write_text(json.dumps(config))
prep=json.loads((root/'real-reader-preparation-config.json').read_text())
selector={k:prep[k] for k in ('image_reader','memory_image','authority','recipient','limit')};selector.update(catalog=config['catalog'],socket=config['selection_socket'],control_socket=config['control_socket'],preparation_config=str(root/'real-reader-preparation-config.json'),native_prepare=str(root/'vllm-native-build/target/release/native-prepare'))
(fixture/'onmiss-selector.json').write_text(json.dumps(selector))
