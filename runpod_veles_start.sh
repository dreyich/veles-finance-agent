#!/bin/bash
# RunPod startup script — Llama 3.3 70B AWQ + 32k context
# Запускати в JupyterLab Terminal на RunPod pod

pip install vllm -q

# Зупинити попередній vLLM якщо запущений
pkill -f "vllm.entrypoints" 2>/dev/null || true
sleep 3

python3 -m vllm.entrypoints.openai.api_server \
  --model /workspace/llama-3.3-70b-awq \
  --quantization awq_marlin \
  --served-model-name veles \
  --port 8000 \
  --host 0.0.0.0 \
  --max-model-len 32768 \
  --max-num-seqs 4 \
  --kv-cache-dtype fp8 \
  --gpu-memory-utilization 0.95 \
  --enable-prefix-caching \
  --tool-call-parser llama3_json \
  --dtype auto

# Після запуску URL:
# https://YOUR-POD-ID-8000.proxy.runpod.net
