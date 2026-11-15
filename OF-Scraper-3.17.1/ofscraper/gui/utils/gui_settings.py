"""Persistent GUI-specific settings stored in gui_settings.json.

The file lives next to the ofscraper config (e.g.
  Windows: C:\\Users\\<user>\\.config\\ofscraper\\gui_settings.json
  Linux:   /home/<user>/.config/ofscraper/gui_settings.json
)
and is completely separate from the main ofscraper config so it never
interferes with the scraper's own schema/migration logic.

Currently stored keys:
  "theme"         -> "dark" | "light"  (default: "dark" if absent)
  "verbose_log"   -> bool
  "privacy_mode"  -> bool  (hide secrets/paths for screenshots)
  "dismissed_update_version" -> str  (PyPI version the user dismissed)
  "first_run_welcome_seen" -> bool  (first-run Getting started dialog shown)
  "skip_scrape_confirm" -> bool  (skip typical pre-scrape size/ETA confirms)
  "skip_cart_confirm" -> bool  (skip large download-cart confirms)
  "skip_disk_space_check" -> bool  (skip typical low-disk warnings; critical still prompts)
  "auth_login_timeout_min" -> int  (browser login hard timeout minutes; default 10; 0=off)
  "console_height" -> int  (Scraping page console pane height in px; drag splitter to change)
  "gui_font_size"  -> int  (global GUI text size in px; default 13; typical 12–20; also drives Help)
  "help_font_size" -> int  (legacy; migrated to gui_font_size)
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


def save_gui_settings(settings: dict, *, quiet: bool = False) -> bool:
    """Write *settings* dict to gui_settings.json.  Returns True on success.

    ``quiet=True`` skips the routine debug log (e.g. debounced console resize).
    """
    p = _settings_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=4)
        if not quiet:
            log.debug(f"[GUI] Saved {_SETTINGS_FILE} -> {p}")
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not save {_SETTINGS_FILE}: {e}")
        return False
