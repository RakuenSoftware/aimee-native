set -eu
cd /opt/aimee-memory-lab
vllm-env/bin/python - <<'PY'
import json
p='vllm-native-fixture-r1/'
c=json.load(open(p+'gguf-config.json'));c['serve']={'tensor_parallel_size':2,'port':8139};c['device_memory_budget']=9551872
json.dump(c,open(p+'final-container-config.json','w'))
PY
podman --storage-driver=overlay run --rm --name aimee-final-test --cgroups=disabled --security-opt seccomp=unconfined --ipc=host --network=host --device /dev/kfd --device /dev/dri/renderD128 --device /dev/dri/renderD129 -e NCCL_P2P_DISABLE=1 -e VLLM_HOST_IP=127.0.0.1 -v /opt/aimee-memory-lab/gemma4:/opt/aimee-memory-lab/gemma4:ro -v /opt/aimee-memory-lab/gemma4-aimee-q8.gguf:/weights/gemma4-aimee-q8.gguf:ro -v /opt/aimee-memory-lab/vllm-native-fixture-r1:/opt/aimee-memory-lab/vllm-native-fixture-r1:rw -v /opt/aimee-memory-lab/vllm-native-build/distribution/vllm/tests/http_concurrency_probe.py:/probe.py:ro --entrypoint python3 localhost/aimee-native:gemma-preview-r5 /probe.py --config /opt/aimee-memory-lab/vllm-native-fixture-r1/final-container-config.json --executable /usr/local/bin/aimee-vllm --output /opt/aimee-memory-lab/vllm-native-fixture-r1/concurrency-q8-r3.json --requests 128
