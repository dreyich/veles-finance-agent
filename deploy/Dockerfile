# RunPod Serverless Web Endpoint — Veles Finance Agent
# SGLang (Veles 7B AWQ-Marlin) + FastAPI + x402 paywall
#
# sglang==0.4.1.post7 (tried in v9-v13) pulls several transitive deps with
# unbounded version floors (torchao>=0.7.0, sgl-kernel>=0.0.2.post14,
# transformers>=4.45.2 via vllm). No combination of manual pins fully worked:
# the exact sgl-kernel version that originally matched 0.4.1.post7's Python
# API has been removed from PyPI entirely, and the oldest one still published
# (0.1.0) is missing symbols that version's sglang code imports
# ("cannot import name 'sampling_scaling_penalties'"). The official
# lmsysorg/sglang:v0.4.1.post7-cu124 image doesn't help either — it has the
# same unbounded-pip-install bug baked in, frozen at whatever those deps
# resolved to on its 2025-01-20 build day.
#
# Fix: use sglang==0.4.6.post5 instead. Starting around here, sglang's own
# "srt"/"all" extra pins torch, torchvision, sgl-kernel, and flashinfer_python
# to *exact* versions (no floors), so pip resolves a self-consistent set with
# no guessing on our part — as long as those exact pins are still on PyPI,
# which they are (sgl-kernel==0.1.4, torch==2.6.0, torchvision==0.21.0).
# flashinfer_python==0.2.5 only ships an sdist on PyPI (would compile from
# source), so we still need the prebuilt wheel via --find-links.
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y curl libnuma1 && rm -rf /var/lib/apt/lists/*

# This upgrades the base image's torch 2.4.0 to the exact 2.6.0 sglang pins —
# expected and fine, since it's an exact version pip resolves deliberately,
# not an unbounded floor drifting to whatever's newest.
RUN pip install --no-cache-dir \
    "sglang[all]==0.4.6.post5" \
    --find-links https://flashinfer.ai/whl/cu124/torch2.6/flashinfer-python/

# vllm (pulled in by sglang) depends on compressed-tensors with no version
# pin. Unpinned, pip installs today's latest, which imports
# transformers.masking_utils — a module that doesn't exist in the
# transformers==4.51.1 sglang itself pins ("ModuleNotFoundError: No module
# named 'transformers.masking_utils'"). Pin to a release from the same era
# as sglang 0.4.6.post5 (2025-05-24) that doesn't reference it.
RUN pip install --no-cache-dir compressed-tensors==0.10.0

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
