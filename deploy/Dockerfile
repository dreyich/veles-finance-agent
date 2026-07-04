# RunPod Serverless Web Endpoint — Veles Finance Agent
# SGLang (Veles 7B AWQ-Marlin) + FastAPI + x402 paywall
#
# sglang==0.4.1.post7 pulls several transitive deps with unbounded version
# floors (torchao>=0.7.0, sgl-kernel>=0.0.2.post14, transformers>=4.45.2 via
# vllm). Letting pip resolve these to "whatever's newest today" breaks things
# in ways that only show up at runtime import/launch time:
#   - transformers latest restructured AutoProcessor's lazy-import registry
#     -> "Could not import module 'AutoProcessor'"
#   - torchao latest needs torch>=2.6 (torch.int1) -> AttributeError
#   - sgl-kernel latest ships only Blackwell (SM100) binaries, no SM89 (Ada:
#     RTX 4090/A5000, what RunPod actually schedules onto this endpoint)
#     -> "Could not load any common_ops library"
# We even tried the official lmsysorg/sglang:v0.4.1.post7-cu124 image — it
# has the exact same bug baked in, just frozen at whatever those unbounded
# deps resolved to on its build day (2025-01-20), which was already broken.
# So: build on the plain RunPod PyTorch image and pin every one of these
# explicitly to versions from sglang 0.4.1.post7's own era (Dec 2024/Jan 2025).
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y curl libnuma1 && rm -rf /var/lib/apt/lists/*

# SGLang with FlashInfer (CUDA 12.4 + Torch 2.4). Leaves torch unversioned
# (see note above) so pip keeps the base image's CUDA build untouched, and
# requires flashinfer==0.1.6, matching the cu124/torch2.4 wheel below.
RUN pip install --no-cache-dir \
    "sglang[all]==0.4.1.post7" \
    --find-links https://flashinfer.ai/whl/cu124/torch2.4/flashinfer/

# Pin the three transitive deps that are otherwise unbounded (see top note).
# transformers==4.46.1: last release before the AutoProcessor lazy-import
#   registry restructuring, matches vllm 0.6.4.post1's floor.
# torchao==0.7.0: sglang's own floor version, predates the torch>=2.6-only
#   torch.int1 usage in later torchao releases.
# sgl-kernel==0.1.0: oldest version still on PyPI (pre-0.1.0 releases were
#   removed) that ships a single multi-arch common_ops binary instead of
#   the newer per-SM-directory layout that dropped SM89 (Ada) support.
RUN pip install --no-cache-dir \
    transformers==4.46.1 \
    torchao==0.7.0 \
    sgl-kernel==0.1.0

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
