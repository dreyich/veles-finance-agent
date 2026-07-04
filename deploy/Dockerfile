# RunPod Serverless Web Endpoint — Veles Finance Agent
# SGLang (Veles 7B AWQ-Marlin) + FastAPI + x402 paywall
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# SGLang with FlashInfer (CUDA 12.4 + Torch 2.4)
RUN pip install --no-cache-dir \
    "sglang[all]" \
    --find-links https://flashinfer.ai/whl/cu124/torch2.4/flashinfer/

# sglang[all] can pull a CPU-only torch wheel from PyPI, silently overwriting
# the CUDA build in the base image. Force the CUDA build back.
RUN pip install --no-cache-dir --force-reinstall \
    torch==2.4.0 --index-url https://download.pytorch.org/whl/cu124

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Startup script
RUN chmod +x deploy/entrypoint.sh

EXPOSE 8000

CMD ["bash", "deploy/entrypoint.sh"]
