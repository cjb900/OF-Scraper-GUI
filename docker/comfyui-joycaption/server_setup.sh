#!/usr/bin/env bash
# ============================================================
# server_setup.sh
# Run this ON the CasaOS server (192.168.90.163) after copying
# the docker directory there.
#
# Usage:
#   chmod +x server_setup.sh
#   sudo ./server_setup.sh
# ============================================================
set -e

APP_DIR="/DATA/AppData/comfyui-joycaption"
VENV_DIR="/opt/hf-download-venv"

echo "==> Creating data directories under $APP_DIR ..."
mkdir -p "$APP_DIR/models/LLM"
mkdir -p "$APP_DIR/input"
mkdir -p "$APP_DIR/output"
mkdir -p "$APP_DIR/workflows"

echo "==> Copying workflow template ..."
cp -n custom_workflows/joycaption_alpha2.json "$APP_DIR/workflows/" 2>/dev/null || true

# Ubuntu 24.04+ uses PEP 668 — pip is blocked system-wide.
# Use a dedicated venv just for the model download tool.
echo "==> Setting up Python venv for huggingface_hub ..."
apt-get install -y --quiet python3-venv python3-full
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet huggingface_hub

echo ""
echo "==> Downloading JoyCaption Alpha Two model (~15 GB) ..."
echo "    This will resume automatically if interrupted."
echo ""

"$VENV_DIR/bin/python" - <<'EOF'
from huggingface_hub import snapshot_download
import os

MODEL_REPO = "fancyfeast/llama-joycaption-alpha-two-hf-llava"
LOCAL_DIR  = "/DATA/AppData/comfyui-joycaption/models/LLM/llama-joycaption-alpha-two-hf-llava"

snapshot_download(
    repo_id=MODEL_REPO,
    local_dir=LOCAL_DIR,
    token=os.environ.get("HF_TOKEN"),
    ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
)
print("Model download complete.")
EOF

echo ""
echo "==> Building Docker image (this takes ~15 min first time) ..."
docker compose build

echo ""
echo "==> Starting container ..."
docker compose up -d

echo ""
echo "==> Done! ComfyUI should be available at:"
echo "    http://192.168.90.163:8188"
echo ""
echo "    Check logs with:  docker compose logs -f"
