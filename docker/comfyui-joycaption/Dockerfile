FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: git, libGL (Pillow/OpenCV), libglib2 (OpenCV), wget
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        wget \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── ComfyUI ──────────────────────────────────────────────────────────────────
RUN git clone --depth 1 https://github.com/comfyanonymous/ComfyUI.git ComfyUI

# CPU-only PyTorch (smaller than the CUDA wheel, faster to pull)
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# ComfyUI core requirements
WORKDIR /app/ComfyUI
RUN pip install -r requirements.txt

# ── Custom nodes ─────────────────────────────────────────────────────────────

# ComfyUI Manager (lets you install/manage nodes from the browser UI)
RUN git clone --depth 1 https://github.com/ltdrdata/ComfyUI-Manager.git \
        custom_nodes/ComfyUI-Manager \
    && pip install -r custom_nodes/ComfyUI-Manager/requirements.txt

# ── Extra deps useful for CPU inference ─────────────────────────────────────
# accelerate: allows load_in_8bit / device_map for lower RAM usage
RUN pip install accelerate

# JoyCaption is installed at runtime via ComfyUI Manager (see README).
# Pre-installing its known Python deps here avoids a long wait after
# Manager installs the node and triggers a pip install inside the container.
RUN pip install \
        transformers \
        sentencepiece \
        protobuf \
        einops

# ── Expose + launch ──────────────────────────────────────────────────────────
EXPOSE 8188

# --cpu forces CPU mode even if torch detects a CUDA device somehow
CMD ["python", "main.py", \
     "--listen", "0.0.0.0", \
     "--port", "8188", \
     "--cpu", \
     "--preview-method", "none"]
