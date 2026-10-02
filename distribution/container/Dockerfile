# Official upstream runtime; no source checkout, fork or patches.
FROM docker.io/vllm/vllm-openai-rocm@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a
# Ubuntu fixes only; do not upgrade the matched GPU stack from vendor repositories.
# Exact package versions fail closed if the distribution no longer serves them.
COPY os-packages.lock /opt/aimee/os-packages.lock
RUN apt-get -o Dir::Etc::sourceparts=- update && DEBIAN_FRONTEND=noninteractive apt-get -o Dir::Etc::sourceparts=- install --only-upgrade --no-install-recommends -y $(cat /opt/aimee/os-packages.lock) && rm -rf /var/lib/apt/lists/*
# Public wheels are hash-locked and installed offline. Keep the upstream
# setuptools pin: its reviewed sdist-only advisory does not affect this binary
# allowlist build, and newer versions violate the pinned inference runtime.
COPY runtime-wheels /opt/aimee/runtime-wheels
COPY runtime-requirements.lock /opt/aimee/runtime-requirements.lock
RUN python3 -m pip install --no-index --find-links=/opt/aimee/runtime-wheels --require-hashes --ignore-installed -r /opt/aimee/runtime-requirements.lock && rm -rf /opt/aimee/runtime-wheels
COPY client.whl /opt/aimee/client.whl
COPY libaimee_native.so /opt/aimee/libaimee_native.so
COPY kernels /opt/aimee/kernels
COPY licenses /opt/aimee/licenses
# pip requires a valid wheel filename; the context generator writes it below.
COPY wheel-name.txt /opt/aimee/wheel-name.txt
RUN name=$(cat /opt/aimee/wheel-name.txt) && mv /opt/aimee/client.whl /opt/aimee/$name && python3 -m pip install --no-deps /opt/aimee/$name && rm /opt/aimee/$name /opt/aimee/wheel-name.txt
ENV NCCL_P2P_DISABLE=1 VLLM_HOST_IP=127.0.0.1
ENV AIMEE_KERNEL_BANK=/opt/aimee/kernels
ENV VLLM_USE_V2_MODEL_RUNNER=0 VLLM_PLUGINS=aimee_native VLLM_ROCM_USE_AITER=0
ENTRYPOINT ["aimee-vllm"]
