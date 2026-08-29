"""
Download the JoyCaption Alpha Two model weights into ./models/LLM/
so the Docker container can find them at startup.

Usage:
    python download_models.py

Requirements (run once on the host, not inside Docker):
    pip install huggingface_hub
"""

import sys
from pathlib import Path

MODEL_REPO = "fancyfeast/llama-joycaption-alpha-two-hf-llava"
LOCAL_DIR  = Path(__file__).parent / "models" / "LLM" / "llama-joycaption-alpha-two-hf-llava"

def main():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("huggingface_hub is not installed.")
        print("Run:  pip install huggingface_hub")
        sys.exit(1)

    print(f"Downloading {MODEL_REPO}")
    print(f"  → {LOCAL_DIR}")
    print()
    print("This is ~15 GB. It will resume if interrupted.")
    print()

    # Accept gated-model terms on HuggingFace before running if needed:
    # https://huggingface.co/fancyfeast/llama-joycaption-alpha-two-hf-llava

    token = None
    try:
        import os
        token = os.environ.get("HF_TOKEN") or None
    except Exception:
        pass

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_download(
        repo_id=MODEL_REPO,
        local_dir=str(LOCAL_DIR),
        token=token,
        # Skip large files that aren't needed for inference
        ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
    )

    print()
    print("Download complete!")
    print(f"Model saved to: {LOCAL_DIR}")
    print()
    print("Next steps:")
    print("  1. docker compose build")
    print("  2. docker compose up -d")
    print("  3. Open http://localhost:8188 to verify ComfyUI is running")
    print("  4. Set ComfyUI URL to http://localhost:8188 in the JoyCaption plugin settings")


if __name__ == "__main__":
    main()
