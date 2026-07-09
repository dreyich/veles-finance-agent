#!/bin/bash
set -e

MODEL_PATH="${MODEL_PATH:-/workspace/veles-7b}"
HF_REPO="${HF_REPO:-Drushka/Veles-Finance-7B-v6}"
SGLANG_PORT=30000

# Download model if not on network volume
if [ ! -f "$MODEL_PATH/config.json" ]; then
    echo "[startup] Model not found at $MODEL_PATH — downloading from HuggingFace..."
    python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='${HF_REPO}',
    local_dir='${MODEL_PATH}',
    token='${HF_TOKEN:-}',
    ignore_patterns=['*.md','*.txt'],
)
"
    echo "[startup] Download complete."
fi

# Start SGLang inference server (Veles 7B BF16 — AWQ quantization done separately)
echo "[startup] Launching SGLang on port $SGLANG_PORT..."
python -m sglang.launch_server \
    --model-path "$MODEL_PATH" \
    --dtype bfloat16 \
    --port "$SGLANG_PORT" \
    --host 0.0.0.0 \
    --served-model-name veles-finance-7b \
    --grammar-backend xgrammar \
    --context-length 8192 \
    --mem-fraction-static 0.85 \
    --enable-cache-report \
    &

# Wait until SGLang is healthy (max 120 sec)
echo "[startup] Waiting for SGLang..."
for i in $(seq 1 60); do
    if curl -sf "http://localhost:$SGLANG_PORT/health" > /dev/null 2>&1; then
        echo "[startup] SGLang ready after ${i}x2 sec."
        break
    fi
    sleep 2
done

# Start FastAPI agent (RunPod Load Balancer routes to $PORT and health-checks /ping on $PORT_HEALTH)
API_PORT="${PORT:-8000}"
echo "[startup] Launching Veles FastAPI on port $API_PORT..."
export VELES_BASE_URL="http://localhost:${SGLANG_PORT}/v1"
export VELES_MODEL="veles-finance-7b"
export VELES_API_KEY="EMPTY"

# Production env vars with fallbacks
# DEBUG: Print what RunPod actually passes
echo "[entrypoint] DEBUG env vars BEFORE fallback:"
echo "  ORCHESTRATOR_BASE_URL='${ORCHESTRATOR_BASE_URL}'"
echo "  ORCHESTRATOR_MODEL='${ORCHESTRATOR_MODEL}'"
echo "  ORCHESTRATOR_API_KEY='${ORCHESTRATOR_API_KEY}'"
echo "  TAVILY_API_KEY='${TAVILY_API_KEY}'"

# Apply fallbacks only if empty or unset
if [ -z "${ORCHESTRATOR_BASE_URL}" ]; then
  export ORCHESTRATOR_BASE_URL="https://api.groq.com/openai/v1"
fi
if [ -z "${ORCHESTRATOR_MODEL}" ]; then
  export ORCHESTRATOR_MODEL="llama-3.1-70b-versatile"
fi
if [ -z "${ORCHESTRATOR_API_KEY}" ]; then
  export ORCHESTRATOR_API_KEY=""
fi
if [ -z "${TAVILY_API_KEY}" ]; then
  export TAVILY_API_KEY=""
fi

echo "[entrypoint] DEBUG env vars AFTER fallback:"
echo "  ORCHESTRATOR_BASE_URL='${ORCHESTRATOR_BASE_URL}'"
echo "  ORCHESTRATOR_MODEL='${ORCHESTRATOR_MODEL}'"

exec uvicorn main:api --host 0.0.0.0 --port "$API_PORT" --workers 1
