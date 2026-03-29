"""Persistent GUI-specific settings stored in gui_settings.json.

The file lives next to the ofscraper config (e.g.
  Windows: C:\\Users\\<user>\\.config\\ofscraper\\gui_settings.json
  Linux:   /home/<user>/.config/ofscraper/gui_settings.json
)
and is completely separate from the main ofscraper config so it never
interferes with the scraper's own schema/migration logic.

Currently stored keys:
  "theme"  -> "dark" | "light"  (default: "dark" if absent)
"""

import json
import logging
from pathlib import Path

log = logging.getLogger("shared")

_SETTINGS_FILE = "gui_settings.json"


def _settings_path() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths
        return common_paths.get_config_home() / _SETTINGS_FILE
    except Exception:
        return Path.home() / ".config" / "ofscraper" / _SETTINGS_FILE


def load_gui_settings() -> dict:
    """Load gui_settings.json and return the contents as a dict.
    Returns an empty dict if the file doesn't exist or can't be parsed."""
    p = _settings_path()
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[GUI] Could not read {_SETTINGS_FILE}: {e}")
    return {}


def save_gui_settings(settings: dict) -> bool:
    """Write *settings* dict to gui_settings.json.  Returns True on success."""
    p = _settings_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        log.debug(f"[GUI] Saved {_SETTINGS_FILE} -> {p}")
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not save {_SETTINGS_FILE}: {e}")
        return False
