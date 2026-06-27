#!/bin/bash
# =============================================================================
# Veles Finance Agent — Production deployment on RunPod
# Architecture:
#   • SGLang port 30000 → Veles 7B (Qwen2.5 fine-tuned, XGrammar extraction)
#   • SGLang port 30001 → Llama 3.1 8B Instruct (orchestrator, tool calling)
#   • FastAPI port 3003  → Public API
#
# Recommended pod: RunPod A40 48GB (or 2x A100 for both models in parallel)
# Prerequisites: Python 3.10+, 48GB VRAM, /workspace volume
#
# Usage:
#   1. Upload project to /workspace/finance-agent/
#   2. (Optional) Set HF_TOKEN if adapter is private
#   3. bash /workspace/finance-agent/deploy/runpod_sglang.sh
# =============================================================================
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/workspace/finance-agent}"
VELES_MERGED="${VELES_MERGED_PATH:-/workspace/veles-merged}"
LLAMA_MODEL="${LLAMA_MODEL:-meta-llama/Meta-Llama-3.1-8B-Instruct}"
LOG_DIR="/workspace/logs"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

mkdir -p "$LOG_DIR"

# =============================================================================
# Step 1: Check GPU
# =============================================================================
info "=== Veles Finance Agent — SGLang Deployment ==="
info "GPU check:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || warn "nvidia-smi not available"
echo ""

# =============================================================================
# Step 2: Install dependencies
# =============================================================================
info "[1/5] Installing SGLang + dependencies..."
pip install "sglang[all]" --find-links https://flashinfer.ai/whl/cu124/torch2.4/ -q 2>&1 | tail -5
pip install openai fastapi uvicorn httpx yfinance langchain-openai langgraph peft transformers accelerate -q 2>&1 | tail -3
info "Dependencies installed."

# =============================================================================
# Step 3: Merge Veles adapter (if not already done)
# =============================================================================
info "[2/5] Preparing Veles model..."
if [ -f "$VELES_MERGED/config.json" ]; then
    info "Merged model found at $VELES_MERGED — skipping merge."
else
    info "Merging LoRA adapter into base model (takes ~5 min)..."
    cd "$PROJECT_DIR"
    python deploy/merge_veles.py
fi

# =============================================================================
# Step 4: Launch SGLang servers
# =============================================================================
info "[3/5] Starting SGLang — Veles 7B on port 30000..."

# Kill any leftover processes
pkill -f "sglang.launch_server" 2>/dev/null || true
sleep 2

# Veles 7B — extraction specialist
python -m sglang.launch_server \
    --model-path "$VELES_MERGED" \
    --served-model-name "veles-finance-7b" \
    --port 30000 \
    --host 0.0.0.0 \
    --grammar-backend xgrammar \
    --context-length 4096 \
    --max-num-reqs 8 \
    --mem-fraction-static 0.45 \
    --dtype bfloat16 \
    --enable-metrics \
    > "$LOG_DIR/sglang_veles.log" 2>&1 &
VELES_PID=$!
info "Veles SGLang PID=$VELES_PID (log: $LOG_DIR/sglang_veles.log)"

# Wait for Veles to be ready
info "Waiting for Veles SGLang to start (up to 120s)..."
for i in $(seq 1 24); do
    sleep 5
    if curl -sf http://localhost:30000/health > /dev/null 2>&1; then
        info "Veles SGLang ready!"
        break
    fi
    echo -n "."
    if [ $i -eq 24 ]; then
        error "Veles SGLang failed to start. Check $LOG_DIR/sglang_veles.log"
    fi
done

info "[4/5] Starting SGLang — Llama 3.1 8B on port 30001..."
python -m sglang.launch_server \
    --model-path "$LLAMA_MODEL" \
    --served-model-name "llama3.1-8b-instruct" \
    --port 30001 \
    --host 0.0.0.0 \
    --context-length 8192 \
    --max-num-reqs 4 \
    --mem-fraction-static 0.50 \
    --dtype bfloat16 \
    --enable-metrics \
    > "$LOG_DIR/sglang_llama.log" 2>&1 &
LLAMA_PID=$!
info "Llama SGLang PID=$LLAMA_PID (log: $LOG_DIR/sglang_llama.log)"

info "Waiting for Llama SGLang to start (up to 180s)..."
for i in $(seq 1 36); do
    sleep 5
    if curl -sf http://localhost:30001/health > /dev/null 2>&1; then
        info "Llama SGLang ready!"
        break
    fi
    echo -n "."
    if [ $i -eq 36 ]; then
        error "Llama SGLang failed to start. Check $LOG_DIR/sglang_llama.log"
    fi
done

# =============================================================================
# Step 5: Start FastAPI
# =============================================================================
info "[5/5] Starting Veles Finance API on port 3003..."
cd "$PROJECT_DIR"

export VELES_BASE_URL="http://localhost:30000/v1"
export VELES_MODEL="veles-finance-7b"
export VELES_API_KEY="EMPTY"
export ORCHESTRATOR_BASE_URL="http://localhost:30001/v1"
export ORCHESTRATOR_MODEL="llama3.1-8b-instruct"
export ORCHESTRATOR_API_KEY="EMPTY"

python main.py > "$LOG_DIR/fastapi.log" 2>&1 &
API_PID=$!

sleep 4
if curl -sf http://localhost:3003/health > /dev/null 2>&1; then
    info "FastAPI ready!"
else
    warn "FastAPI may not be ready yet. Check $LOG_DIR/fastapi.log"
fi

# =============================================================================
# Summary
# =============================================================================
echo ""
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Veles Finance Agent — Production Running!     ${NC}"
echo -e "${GREEN}════════════════════════════════════════════════${NC}"
echo ""
echo "  Veles 7B SGLang:    http://localhost:30000  (PID $VELES_PID)"
echo "  Llama 3.1 SGLang:   http://localhost:30001  (PID $LLAMA_PID)"
echo "  Finance API:        http://localhost:3003   (PID $API_PID)"
echo ""
echo "  Public URL (RunPod): https://\$POD_ID-3003.proxy.runpod.net"
echo ""
echo "  Health check:"
echo "    curl http://localhost:3003/health"
echo ""
echo "  Logs:"
echo "    tail -f $LOG_DIR/sglang_veles.log"
echo "    tail -f $LOG_DIR/sglang_llama.log"
echo "    tail -f $LOG_DIR/fastapi.log"
echo ""

# Keep script alive (RunPod pod stays up while script runs)
wait
