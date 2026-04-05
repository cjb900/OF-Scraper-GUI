#Enabled 1 / Disabled 0 - Set this plugin as enabled - Default value 1
plugin_enabled=1

import json
import shutil
import threading
from pathlib import Path

from ofscraper.plugins.base import BasePlugin

from .database import (
    MediaItem,
    canonical_media_path,
    extract_model_username,
    init_db,
    normalize_tag_pairs,
    resolve_media_path_for_tagging,
)
from .comfyui_client import ComfyUIClient, ComfyUIError


# Caption types the user can choose from in settings.
# Must match the keys in joycaption_comfyui's CAPTION_TYPE_MAP.
CAPTION_TYPES = [
    "Descriptive",
    "Descriptive (Casual)",
    "Straightforward",
    "Stable Diffusion Prompt",
    "MidJourney",
    "Danbooru tag list",
    "e621 tag list",
    "Rule34 tag list",
    "Booru-like tag list",
    "Art Critic",
    "Product Listing",
    "Social Media Post",
]

CAPTION_LENGTHS = [
    "any",
    "very short",
    "short",
    "medium-length",
    "long",
    "very long",
]


def _caption_to_tags(caption: str, caption_type: str, top_k: int) -> list[dict]:
    """
    Convert a JoyCaption output string to the [{label, score}] format.

    - Tag-list modes (booru / e621): split on commas → individual tags, score=1.0
    - All other modes: the full caption becomes the first entry; then individual
      comma-separated parts (if any) are appended so the gallery can display chips.
    """
    if not caption:
        return []

    is_tag_list = any(
        t in caption_type.lower() for t in ("booru", "e621", "rule34", "tag list")
    )

    if is_tag_list:
        tags = [t.strip() for t in caption.split(",") if t.strip()]
    else:
        # Keep the full caption as the first entry for easy reading in the gallery,
        # then add comma-split parts as individual chips (useful for smart-folders).
        parts = [t.strip() for t in caption.split(",") if t.strip()]
        # Deduplicate while preserving order.
        seen = set()
        tags = []
        if caption.strip():
            tags.append(caption.strip())
            seen.add(caption.strip())
        for p in parts:
            if p not in seen:
                tags.append(p)
                seen.add(p)

    result = [{"label": t, "score": 1.0} for t in tags]
    return result[:max(1, top_k)]


class Plugin(BasePlugin):
    """
    Image captioning via JoyCaption running inside ComfyUI.
    No local ML dependencies — all inference happens on the ComfyUI server.
    """

    def on_load(self):
        self.log.info("Loaded %s plugin!", self.metadata.get("name", "JoyCaption Tagger"))

        self.data_dir = Path(self.plugin_dir) if getattr(self, "plugin_dir", None) else Path(__file__).parent
        self.db_path = self.data_dir / "jc_tags.db"
        self.settings_path = self.data_dir / "settings.json"

        self.settings = {
            "comfyui_url": "http://192.168.90.163:8188",
            "caption_type": "Descriptive",
            "caption_length": "long",
            "extra_options": [],
            "name_input": "",
            "timeout": 600,
            "auto_tag_images": True,
            "smart_folders": False,
            "smart_folder_path": str(self.data_dir / "Smart_Tags"),
            "tag_top_k": 20,
            "workflow_file": "joycaption.json",
        }
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except Exception as e:
                self.log.error("Failed to load settings: %s", e)

        init_db(str(self.db_path))
        self.client = ComfyUIClient(self.settings.get("comfyui_url", "http://localhost:8188"))
        self._client_lock = threading.Lock()
        self._workflow_cache: dict | None = None
        self._workflow_file_mtime: float | None = None

    # ------------------------------------------------------------------
    # Workflow loading
    # ------------------------------------------------------------------

    def _load_workflow(self) -> dict:
        """Load the active workflow JSON, caching between calls."""
        wf_name = self.settings.get("workflow_file", "joycaption.json")
        wf_path = self.data_dir / "workflows" / wf_name
        if not wf_path.exists():
            # Fall back to the bundled default
            wf_path = Path(__file__).parent / "workflows" / wf_name
        if not wf_path.exists():
            raise FileNotFoundError(f"Workflow file not found: {wf_path}")

        mtime = wf_path.stat().st_mtime
        if self._workflow_cache is not None and self._workflow_file_mtime == mtime:
            return self._workflow_cache

        with open(wf_path, "r", encoding="utf-8") as f:
            wf = json.load(f)

        # Patch caption_type and caption_length into any JoyCaption node.
        cap_type = self.settings.get("caption_type", "Descriptive")
        cap_len = self.settings.get("caption_length", "long")
        extra = self.settings.get("extra_options", [])
        name_inp = self.settings.get("name_input", "")
        for node in wf.values():
            if isinstance(node, dict) and node.get("class_type") == "JJC_JoyCaption":
                node["inputs"]["caption_type"] = cap_type
                node["inputs"]["caption_length"] = cap_len
                node["inputs"]["person_name"] = name_inp
                # Map list of extra options to extra_option1..extra_option5
                for i in range(1, 6):
                    node["inputs"][f"extra_option{i}"] = extra[i - 1] if i - 1 < len(extra) else ""

        self._workflow_cache = wf
        self._workflow_file_mtime = mtime
        return wf

    def _invalidate_workflow_cache(self):
        self._workflow_cache = None
        self._workflow_file_mtime = None

    # ------------------------------------------------------------------
    # Core tagging
    # ------------------------------------------------------------------

    def _compute_tags_for_path(self, path_key: str) -> list[dict]:
        """Call ComfyUI and return [{label, score}] list. Thread-safe.

        The lock only protects the workflow cache read (cheap).  The actual HTTP
        pipeline (upload → queue → wait) runs lock-free so multiple callers can
        pipeline requests into ComfyUI's internal queue concurrently.
        """
        with self._client_lock:
            self.client.base_url = self.settings.get("comfyui_url", "http://localhost:8188").rstrip("/")
            workflow = self._load_workflow()
            timeout = int(self.settings.get("timeout", 120))
        caption = self.client.caption_image(path_key, workflow, timeout=timeout)

        if not caption:
            return []

        cap_type = self.settings.get("caption_type", "Descriptive")
        top_k = max(1, int(self.settings.get("tag_top_k", 20)))
        return _caption_to_tags(caption, cap_type, top_k)

    def _persist_media_item(self, path_key: str, tags: list, *, smart_source_path: str | None = None):
        model_used = f"joycaption/{self.settings.get('caption_type', 'Descriptive')}"
        item = MediaItem.create(
            file_path=path_key,
            model_used=model_used,
            model_username=extract_model_username(path_key),
        )
        item.set_tags(tags or [])

        copied = False
        if smart_source_path and self.settings.get("smart_folders", False) and tags:
            pairs = normalize_tag_pairs(tags)
            # For tag-list captions use the top tag; for descriptive use the
            # first comma-delimited part (index 1, since index 0 is the full caption).
            cap_type = self.settings.get("caption_type", "Descriptive")
            is_tag_list = any(t in cap_type.lower() for t in ("booru", "e621", "rule34", "tag list"))
            folder_tag = None
            if is_tag_list and pairs:
                folder_tag = pairs[0][0]
            elif len(pairs) > 1:
                folder_tag = pairs[1][0]  # skip full-caption entry at index 0
            if folder_tag:
                dest_dir = Path(self.settings.get("smart_folder_path", str(self.data_dir / "Smart_Tags"))) / folder_tag
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_file = dest_dir / Path(smart_source_path).name
                try:
                    shutil.copy2(path_key, dest_file)
                    copied = True
                except Exception as e:
                    self.log.error("Smart-folder copy failed: %s", e)

        item.copied_to_smart_folder = copied
        item.save()

    # ------------------------------------------------------------------
    # Plugin hooks
    # ------------------------------------------------------------------

    def try_ingest_existing_path(self, path_key: str) -> str:
        """Tag + insert one gallery row. Returns: skipped | added | noop | error"""
        if MediaItem.select().where(MediaItem.file_path == path_key).exists():
            return "skipped"
        if Path(path_key).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}:
            return "noop"
        try:
            tags = self._compute_tags_for_path(path_key)
        except Exception as e:
            self.log.error("Batch scan tagging failed for %s: %s", path_key, e)
            return "error"
        if not tags:
            return "noop"
        try:
            self._persist_media_item(path_key, tags)
        except Exception as e:
            self.log.error("Batch scan DB save failed for %s: %s", path_key, e)
            return "error"
        return "added"

    def on_item_downloaded(self, item_data, file_path):
        if not self.settings.get("auto_tag_images", True):
            return

        resolved = resolve_media_path_for_tagging(file_path)
        if not resolved:
            self.log.warning("JoyCaption: could not resolve downloaded file path: %r", file_path)
            return

        file_path_obj = Path(resolved)
        if file_path_obj.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}:
            return

        path_key = canonical_media_path(resolved)
        if MediaItem.select().where(MediaItem.file_path == path_key).exists():
            return

        self.log.info("JoyCaption processing new image: %s", file_path_obj.name)
        try:
            tags = self._compute_tags_for_path(path_key)
        except Exception as e:
            self.log.error("JoyCaption error for %s: %s", file_path_obj.name, e)
            return

        if not tags:
            self.log.info("JoyCaption: no caption returned for %s", file_path_obj.name)
            return

        self._persist_media_item(path_key, tags, smart_source_path=str(resolved))
        self._schedule_gallery_refresh()

    def _schedule_gallery_refresh(self):
        tab = getattr(self, "gallery_tab", None)
        if tab is not None:
            tab.request_refresh.emit()

    def on_ui_setup(self, main_window):
        from .gui import JoyCaptionTab
        self.gallery_tab = JoyCaptionTab(self)
        try:
            main_window._add_page("jc_gallery", self.gallery_tab)
            from ofscraper.gui.widgets.styled_button import NavButton

            btn = NavButton("🎨 JoyCaption")
            main_window._nav_group.addButton(btn)
            main_window._nav_buttons["jc_gallery"] = btn

            nav_layout = main_window._nav_frame.layout()
            from PyQt6.QtCore import Qt as _Qt
            stretch_idx = -1
            for _i in range(nav_layout.count()):
                _item = nav_layout.itemAt(_i)
                if _item and _item.spacerItem() is not None:
                    if _item.expandingDirections() & _Qt.Orientation.Vertical:
                        stretch_idx = _i
                        break
            if stretch_idx >= 0:
                nav_layout.insertWidget(stretch_idx, btn)
            else:
                theme_idx = nav_layout.indexOf(main_window._theme_btn)
                if theme_idx >= 0:
                    nav_layout.insertWidget(theme_idx, btn)
                else:
                    nav_layout.addWidget(btn)

            btn.clicked.connect(lambda checked: main_window._navigate("jc_gallery"))
            self.log.info("Attached JoyCaption Gallery to sidebar.")
        except Exception as e:
            self.log.error("Failed to attach GUI to sidebar: %s", e)

    def on_unload(self):
        self.client = None
