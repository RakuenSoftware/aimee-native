FROM localhost/aimee-native:gemma-preview-r13
COPY aimee_vllm-0.1.0-cp312-cp312-linux_x86_64.whl /tmp/plugin.whl
RUN mv /tmp/plugin.whl /tmp/aimee_vllm-0.1.0-cp312-cp312-linux_x86_64.whl && python -m pip install --no-deps --force-reinstall /tmp/aimee_vllm-0.1.0-cp312-cp312-linux_x86_64.whl && rm /tmp/aimee_vllm-0.1.0-cp312-cp312-linux_x86_64.whl
COPY libaimee_native.so /opt/aimee/libaimee_native.so
