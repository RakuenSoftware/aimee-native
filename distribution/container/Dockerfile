# Official upstream runtime; no source checkout, fork or patches.
FROM docker.io/vllm/vllm-openai-rocm@sha256:2e7da1ad1c66836802072588adea75f9f4991da5f9545b4318e91d422c22ce6a
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
