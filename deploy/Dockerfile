# RunPod Serverless Web Endpoint — Veles Finance Agent
# SGLang (Veles 7B AWQ-Marlin) + FastAPI + x402 paywall
#
# Base: official lmsysorg/sglang image for the exact sglang release we target.
# Hand-installing "sglang[all]==0.4.1.post7" on top of a generic RunPod PyTorch
# image (v8-v11) failed repeatedly because sglang's own transitive deps
# (vllm, sgl-kernel, flashinfer) have unbounded version floors — pip always
# resolves to whatever is newest on PyPI *today*, which drifts out of sync
# with what this sglang release's code actually supports (wrong torch, wrong
# transformers internals, sgl-kernel built for a GPU arch that didn't exist
# yet at 0.4.1.post7's release). The lmsysorg image pins all of that at the
# exact combination sglang's own maintainers built and tested.
FROM lmsysorg/sglang:v0.4.1.post7-cu124

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Python dependencies (FastAPI gateway, LangGraph orchestrator, x402 — none of
# these touch torch/transformers, so they're safe to layer on top)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Startup script
RUN chmod +x deploy/entrypoint.sh

EXPOSE 8000

CMD ["bash", "deploy/entrypoint.sh"]
