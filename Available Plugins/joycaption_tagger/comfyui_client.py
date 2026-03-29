"""
ComfyUI HTTP API client for the JoyCaption Tagger plugin.

Flow for each image:
  1. POST /upload/image          — upload the file, get back its server-side name
  2. POST /prompt                — queue the workflow with the image name substituted
  3. GET  /history/{prompt_id}   — poll until the job completes
  4. Extract text from outputs   — return the caption string
"""

import copy
import json
import logging
import time
import uuid
from pathlib import Path

log = logging.getLogger("ofscraper_plugin.joycaption_tagger.comfyui")


class ComfyUIError(RuntimeError):
    pass


class ComfyUIClient:
    # Placeholder replaced in the workflow JSON with the uploaded filename.
    IMAGE_PLACEHOLDER = "__INPUT_IMAGE__"

    def __init__(self, base_url: str = "http://localhost:8188"):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Low-level HTTP helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, timeout: int = 10):
        import requests
        return requests.get(f"{self.base_url}{path}", timeout=timeout)

    def _post_json(self, path: str, data: dict, timeout: int = 30):
        import requests
        return requests.post(
            f"{self.base_url}{path}",
            json=data,
            timeout=timeout,
        )

    def _post_files(self, path: str, files: dict, timeout: int = 60):
        import requests
        return requests.post(f"{self.base_url}{path}", files=files, timeout=timeout)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_connection(self) -> bool:
        """Return True if the ComfyUI server is reachable."""
        try:
            r = self._get("/system_stats", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def upload_image(self, file_path: str) -> str:
        """
        Upload a local image file to ComfyUI's input folder.
        Returns the server-side filename (may differ from the local name if
        a file with the same name already exists on the server).
        """
        p = Path(file_path)
        mime = "image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg") else "image/png"
        with open(file_path, "rb") as fh:
            r = self._post_files(
                "/upload/image",
                {"image": (p.name, fh, mime), "overwrite": (None, "false")},
            )
        if not r.ok:
            raise ComfyUIError(f"Upload failed ({r.status_code}): {r.text[:200]}")
        return r.json()["name"]

    def queue_prompt(self, workflow: dict) -> str:
        """Submit a workflow dict and return the server-assigned prompt_id."""
        payload = {"prompt": workflow, "client_id": self.client_id}
        r = self._post_json("/prompt", payload)
        if not r.ok:
            raise ComfyUIError(f"Queue failed ({r.status_code}): {r.text[:200]}")
        data = r.json()
        if "error" in data:
            raise ComfyUIError(f"Workflow error: {data['error']}")
        return data["prompt_id"]

    def get_history(self, prompt_id: str) -> dict:
        r = self._get(f"/history/{prompt_id}", timeout=10)
        if not r.ok:
            raise ComfyUIError(f"History fetch failed ({r.status_code})")
        return r.json()

    def wait_for_result(self, prompt_id: str, timeout: int = 120) -> dict | None:
        """
        Poll /history until the prompt finishes or the timeout is reached.
        Returns the result dict for prompt_id, or None on timeout.
        """
        deadline = time.time() + timeout
        poll_interval = 1.0
        while time.time() < deadline:
            try:
                history = self.get_history(prompt_id)
            except ComfyUIError:
                time.sleep(poll_interval)
                continue
            if prompt_id in history:
                return history[prompt_id]
            time.sleep(poll_interval)
        return None

    def extract_text_outputs(self, result: dict) -> list[str]:
        """
        Walk all node outputs in a completed prompt result and return
        caption strings.  The joycaption_comfyui node returns two strings:
        "query" (the prompt sent to the model) and "caption" (the result).
        We prefer the "caption" key; fall back to any non-empty string if
        neither key is present (forward-compatibility with other nodes).
        """
        texts: list[str] = []
        for _node_id, node_out in result.get("outputs", {}).items():
            if not isinstance(node_out, dict):
                continue
            # Prefer the explicit "caption" output from JoyCaption nodes.
            if "caption" in node_out:
                val = node_out["caption"]
                items = val if isinstance(val, list) else [val]
                for item in items:
                    if isinstance(item, str) and item.strip():
                        texts.append(item.strip())
                continue
            # Fallback: collect any non-empty string that isn't the query prompt.
            for key, value in node_out.items():
                if key == "query":
                    continue
                items = value if isinstance(value, list) else [value]
                for item in items:
                    if isinstance(item, str) and item.strip():
                        texts.append(item.strip())
        return texts

    # ------------------------------------------------------------------
    # High-level caption helper
    # ------------------------------------------------------------------

    def caption_image(
        self,
        file_path: str,
        workflow_template: dict,
        timeout: int = 120,
    ) -> str | None:
        """
        Full pipeline:
          upload → queue workflow → wait → return caption text.

        The workflow_template must contain the string "__INPUT_IMAGE__" wherever
        the uploaded filename should appear (inside a LoadImage node's "image"
        input is typical).
        """
        # 1. Upload
        uploaded_name = self.upload_image(file_path)
        log.debug("Uploaded '%s' → server name '%s'", Path(file_path).name, uploaded_name)

        # 2. Substitute placeholder
        workflow_str = json.dumps(copy.deepcopy(workflow_template))
        workflow_str = workflow_str.replace(self.IMAGE_PLACEHOLDER, uploaded_name)
        workflow = json.loads(workflow_str)

        # 3. Queue
        prompt_id = self.queue_prompt(workflow)
        log.debug("Queued as prompt_id=%s", prompt_id)

        # 4. Wait
        result = self.wait_for_result(prompt_id, timeout=timeout)
        if result is None:
            log.error("ComfyUI timed out after %ds for '%s'", timeout, file_path)
            return None

        # 5. Extract text
        texts = self.extract_text_outputs(result)
        if texts:
            return texts[0]

        log.warning("No text output returned by ComfyUI for '%s'", file_path)
        return None
