#!/bin/bash
# =============================================================================
# Sync project to RunPod pod via SSH
#
# Usage:
#   1. Find your SSH command in RunPod pod page → "Connect" → "SSH over exposed TCP"
#      It looks like: ssh root@<IP> -p <PORT> -i ~/.ssh/id_ed25519
#   2. Set env vars below (or export them before running):
#        export RUNPOD_IP=<IP>
#        export RUNPOD_PORT=<PORT>
#        export RUNPOD_KEY=~/.ssh/id_ed25519   # optional, defaults to id_ed25519
#   3. bash deploy/sync_to_runpod.sh
# =============================================================================
set -euo pipefail

RUNPOD_IP="${RUNPOD_IP:?Set RUNPOD_IP to your RunPod pod IP}"
RUNPOD_PORT="${RUNPOD_PORT:?Set RUNPOD_PORT to your RunPod SSH port}"
RUNPOD_KEY="${RUNPOD_KEY:-$HOME/.ssh/id_ed25519}"
REMOTE_DIR="/workspace/finance-agent"

SSH_OPTS="-p $RUNPOD_PORT -i $RUNPOD_KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10"
RSYNC_OPTS="-avz --progress --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '*.log' \
  --exclude '.git' \
  --exclude 'datasets/' \
  --exclude 'golden_run/' \
  --exclude '*.gguf' \
  --exclude '*.bin' \
  --exclude '*.safetensors' \
  --exclude 'node_modules/'"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Veles Finance Agent — RunPod Sync ==="
echo "Source:  $PROJECT_ROOT"
echo "Target:  root@$RUNPOD_IP:$REMOTE_DIR (port $RUNPOD_PORT)"
echo ""

# Test connection
echo "Testing SSH connection..."
ssh $SSH_OPTS root@$RUNPOD_IP "echo 'SSH OK'" || {
    echo "ERROR: Cannot connect. Check RUNPOD_IP, RUNPOD_PORT, and SSH key."
    exit 1
}

# Create remote directory
ssh $SSH_OPTS root@$RUNPOD_IP "mkdir -p $REMOTE_DIR"

# Sync files
echo "Syncing files..."
rsync $RSYNC_OPTS -e "ssh $SSH_OPTS" \
    "$PROJECT_ROOT/" \
    "root@$RUNPOD_IP:$REMOTE_DIR/"

echo ""
echo "Sync complete!"
echo ""
echo "Next steps on RunPod:"
echo "  ssh root@$RUNPOD_IP -p $RUNPOD_PORT -i $RUNPOD_KEY"
echo "  cd $REMOTE_DIR"
echo "  bash deploy/runpod_sglang.sh"
