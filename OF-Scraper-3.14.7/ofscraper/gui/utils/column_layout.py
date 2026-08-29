"""Persist media-table column widths / visibility / order.

Stored as column_layout.json next to gui_settings.json.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("shared")

_LAYOUT_FILE = "column_layout.json"


def _layout_path() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths

        return common_paths.get_config_home() / _LAYOUT_FILE
    except Exception:
        return Path.home() / ".config" / "ofscraper" / _LAYOUT_FILE


def load_layout() -> dict[str, Any]:
    p = _layout_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        log.warning(f"[GUI] Could not read {_LAYOUT_FILE}: {e}")
        return {}


def save_layout(layout: dict[str, Any]) -> bool:
    p = _layout_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(layout, f, indent=2)
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not save {_LAYOUT_FILE}: {e}")
        return False


def clear_layout() -> bool:
    p = _layout_path()
    try:
        if p.exists():
            p.unlink()
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not clear {_LAYOUT_FILE}: {e}")
        return False


def capture_from_table(table, columns: list[str]) -> dict[str, Any]:
    """Snapshot widths, hidden columns, and visual order from a QTableWidget."""
    header = table.horizontalHeader()
    widths: dict[str, int] = {}
    hidden: list[str] = []
    for i, name in enumerate(columns):
        try:
            widths[name] = int(table.columnWidth(i))
        except Exception:
            continue
        try:
            if table.isColumnHidden(i):
                hidden.append(name)
        except Exception:
            pass

    order: list[str] = []
    try:
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            if 0 <= logical < len(columns):
                order.append(columns[logical])
    except Exception:
        order = list(columns)

    frozen = 0
    try:
        frozen = int(getattr(table, "_frozen_count", 0) or 0)
    except Exception:
        frozen = 0
    frozen = max(0, min(frozen, 3))

    return {
        "widths": widths,
        "hidden": hidden,
        "order": order,
        "frozen_count": frozen,
    }


def apply_to_table(table, columns: list[str], layout: dict | None) -> bool:
    """Apply a saved layout. Returns True if anything was applied."""
    if not layout:
        return False
    header = table.horizontalHeader()
    widths = layout.get("widths") if isinstance(layout.get("widths"), dict) else {}
    hidden = layout.get("hidden") if isinstance(layout.get("hidden"), list) else []
    order = layout.get("order") if isinstance(layout.get("order"), list) else []
    applied = False

    # Restore visual order first (move sections).
    if order and len(order) == len(columns):
        name_to_logical = {name: i for i, name in enumerate(columns)}
        try:
            # Build target: visual position -> logical index
            for visual_target, name in enumerate(order):
                logical = name_to_logical.get(name)
                if logical is None:
                    continue
                current_visual = header.visualIndex(logical)
                if current_visual != visual_target and current_visual >= 0:
                    header.moveSection(current_visual, visual_target)
                    applied = True
        except Exception as e:
            log.debug(f"[GUI] Column order apply skipped: {e}")

    # Widths — briefly disable stretch so saved sizes stick.
    stretch = True
    try:
        stretch = bool(header.stretchLastSection())
        header.setStretchLastSection(False)
    except Exception:
        pass

    for i, name in enumerate(columns):
        w = widths.get(name)
        if w is None:
            continue
        try:
            w = int(w)
            if 40 <= w <= 2000:
                table.setColumnWidth(i, w)
                applied = True
        except Exception:
            pass

    try:
        header.setStretchLastSection(stretch)
    except Exception:
        pass

    hidden_set = {str(x) for x in hidden}
    for i, name in enumerate(columns):
        try:
            want_hidden = name in hidden_set
            if table.isColumnHidden(i) != want_hidden:
                table.setColumnHidden(i, want_hidden)
                applied = True
        except Exception:
            pass

    if "frozen_count" in layout and hasattr(table, "set_frozen_count"):
        try:
            n = int(layout.get("frozen_count") or 0)
            table.set_frozen_count(n, persist=False, ensure_left=True)
            applied = True
        except Exception as e:
            log.debug(f"[GUI] Frozen column apply skipped: {e}")
    elif hasattr(table, "set_frozen_count"):
        # Older layout files: keep default sticky Number + Cart.
        try:
            table.set_frozen_count(
                getattr(table, "_frozen_count", 2) or 2,
                persist=False,
                ensure_left=True,
            )
        except Exception:
            pass

    return applied
