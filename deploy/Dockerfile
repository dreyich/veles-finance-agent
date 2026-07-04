# RunPod Serverless Web Endpoint — Veles Finance Agent
# SGLang (Veles 7B AWQ-Marlin) + FastAPI + x402 paywall
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# SGLang with FlashInfer (CUDA 12.4 + Torch 2.4).
# Pinned to 0.4.1.post7: this is the last release whose "srt"/"all" extra
# leaves torch unversioned (so pip keeps the base image's CUDA build instead
# of upgrading to whatever the unpinned "sglang[all]" latest requires — recent
# releases pin torch==2.11.0, which drags in a mismatched torch/torchvision/
# flashinfer set and breaks CUDA detection at runtime) and requires
# flashinfer==0.1.6, matching the cu124/torch2.4 wheel below.
RUN pip install --no-cache-dir \
    "sglang[all]==0.4.1.post7" \
    --find-links https://flashinfer.ai/whl/cu124/torch2.4/flashinfer/

# vllm==0.6.4.post1 (pulled in by sglang above) requires "transformers>=4.45.2"
# with no upper bound, so pip installs whatever is newest at build time. Newer
# transformers releases restructured AutoProcessor's lazy-import registry,
# breaking sglang's hf_transformers_utils import ("ModuleNotFoundError: Could
# not import module 'AutoProcessor'"). Pin to the version this vllm/sglang
# release was actually built against.
RUN pip install --no-cache-dir transformers==4.46.1

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Startup script
RUN chmod +x deploy/entrypoint.sh

EXPOSE 8000

CMD ["bash", "deploy/entrypoint.sh"]
