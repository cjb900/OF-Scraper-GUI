"""Import-safe Windows filesystem path normalization for config fields.

No CLI / settings side effects — safe for ``test/unit`` collection.
"""
from __future__ import annotations

import os
import re
from typing import Any, Mapping, MutableMapping, Optional

# Nested config keys that hold real filesystem paths (not format templates).
WINDOWS_FS_PATH_FIELDS = (
    ("file_options", "save_location"),
    ("binary_options", "ffmpeg"),
    ("cdm_options", "client-id"),
    ("cdm_options", "private-key"),
    ("advanced_options", "temp_dir"),
)


def normalize_windows_path(value: Optional[Any]) -> Any:
    """On Windows, show/store drive & UNC paths with backslashes.

    Linux/macOS paths and placeholder templates (``{model_username}/...``) are
    left unchanged. ``json.dumps`` then writes ``\\\\`` escapes for ``\\``.
    """
    if os.name != "nt" or value is None:
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s or "://" in s:
        return value
    # Format templates / placeholder paths without a drive or UNC root
    if "{" in s and not re.match(r"^[A-Za-z]:", s) and not s.startswith(("\\\\", "//")):
        return value
    if re.match(r"^[A-Za-z]:", s) or s.startswith(("\\\\", "//")):
        return os.path.normpath(s)
    if "/" in s and "{" not in s:
        return os.path.normpath(s.replace("/", "\\"))
    return value


def normalize_config_paths_for_os(config: Optional[MutableMapping[str, Any]]) -> Any:
    """Normalize known filesystem path fields in-place for the current OS."""
    if os.name != "nt" or not isinstance(config, Mapping):
        return config
    for section, key in WINDOWS_FS_PATH_FIELDS:
        sec = config.get(section)
        if isinstance(sec, MutableMapping) and sec.get(key):
            sec[key] = normalize_windows_path(str(sec[key]))
    adv = config.get("advanced_options")
    if isinstance(adv, MutableMapping) and isinstance(adv.get("env_files"), list):
        adv["env_files"] = [
            normalize_windows_path(str(p)) if p else p for p in adv["env_files"]
        ]
    return config
