"""Named table-filter presets for the GUI.

Stored as filter_presets.json next to gui_settings.json. Serializes the
FilterSidebar widget values (not runtime FilterState arrow objects) so
presets round-trip cleanly.

File shape::

    {"presets": [...], "last_used": "Videos unpaid"}
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("shared")

_PRESETS_FILE = "filter_presets.json"
MAX_PRESETS = 40


def _presets_path() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths

        return common_paths.get_config_home() / _PRESETS_FILE
    except Exception:
        return Path.home() / ".config" / "ofscraper" / _PRESETS_FILE


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_name(name: str) -> str:
    name = re.sub(r"\s+", " ", str(name or "").strip())
    return name[:80]


def _read_store() -> dict[str, Any]:
    """Return ``{"presets": list, "last_used": str|None}``."""
    p = _presets_path()
    if not p.exists():
        return {"presets": [], "last_used": None}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            presets = data
            last_used = None
        elif isinstance(data, dict):
            presets = (
                data.get("presets") if isinstance(data.get("presets"), list) else []
            )
            last_used = data.get("last_used")
            if last_used is not None:
                last_used = sanitize_name(str(last_used)) or None
        else:
            return {"presets": [], "last_used": None}
        cleaned = [x for x in presets if isinstance(x, dict) and x.get("name")]
        return {"presets": cleaned, "last_used": last_used}
    except Exception as e:
        log.warning(f"[GUI] Could not read {_PRESETS_FILE}: {e}")
        return {"presets": [], "last_used": None}


def _write_store(presets: list[dict], last_used: str | None) -> bool:
    p = _presets_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        cleaned = [x for x in presets if isinstance(x, dict) and x.get("name")]
        cleaned = cleaned[:MAX_PRESETS]
        names = {sanitize_name(x.get("name", "")).lower() for x in cleaned}
        if last_used:
            last_used = sanitize_name(last_used)
            if last_used.lower() not in names:
                last_used = None
        else:
            last_used = None
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"presets": cleaned, "last_used": last_used}, f, indent=2)
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not save {_PRESETS_FILE}: {e}")
        return False


def load_presets() -> list[dict]:
    return list(_read_store().get("presets") or [])


def save_presets(presets: list[dict]) -> bool:
    store = _read_store()
    return _write_store(presets, store.get("last_used"))


def get_preset(name: str) -> dict | None:
    key = sanitize_name(name).lower()
    for p in load_presets():
        if sanitize_name(p.get("name", "")).lower() == key:
            return p
    return None


def get_last_used() -> str | None:
    name = _read_store().get("last_used")
    if not name:
        return None
    entry = get_preset(name)
    return str(entry["name"]) if entry else None


def set_last_used(name: str | None) -> bool:
    store = _read_store()
    if name:
        name = sanitize_name(name)
        entry = None
        key = name.lower()
        for p in store["presets"]:
            if sanitize_name(p.get("name", "")).lower() == key:
                entry = p
                break
        if not entry:
            return False
        name = str(entry["name"])
    else:
        name = None
    ok = _write_store(store["presets"], name)
    if ok and name:
        log.debug(f"[GUI] Filter preset last_used: {name}")
    return ok


def upsert_preset(name: str, filters: dict) -> dict | None:
    name = sanitize_name(name)
    if not name:
        return None
    entry = {
        "name": name,
        "updated": _utc_now_iso(),
        "filters": dict(filters or {}),
    }
    store = _read_store()
    presets = list(store["presets"])
    key = name.lower()
    replaced = False
    for i, p in enumerate(presets):
        if sanitize_name(p.get("name", "")).lower() == key:
            presets[i] = entry
            replaced = True
            break
    if not replaced:
        presets.insert(0, entry)
    if _write_store(presets, store.get("last_used")):
        log.info(f"[GUI] Filter preset saved: {name}")
        return entry
    return None


def rename_preset(old_name: str, new_name: str) -> str | None:
    """Rename a preset. Returns the new canonical name, or None on failure."""
    old_name = sanitize_name(old_name)
    new_name = sanitize_name(new_name)
    if not old_name or not new_name:
        return None
    store = _read_store()
    presets = list(store["presets"])
    old_key = old_name.lower()
    new_key = new_name.lower()
    idx = None
    for i, p in enumerate(presets):
        if sanitize_name(p.get("name", "")).lower() == old_key:
            idx = i
            break
    if idx is None:
        return None
    for i, p in enumerate(presets):
        if i == idx:
            continue
        if sanitize_name(p.get("name", "")).lower() == new_key:
            return None
    presets[idx] = dict(presets[idx])
    presets[idx]["name"] = new_name
    presets[idx]["updated"] = _utc_now_iso()
    last_used = store.get("last_used")
    if last_used and sanitize_name(str(last_used)).lower() == old_key:
        last_used = new_name
    if _write_store(presets, last_used):
        log.info(f"[GUI] Filter preset renamed: {old_name} -> {new_name}")
        return new_name
    return None


def delete_preset(name: str) -> bool:
    key = sanitize_name(name).lower()
    store = _read_store()
    presets = list(store["presets"])
    new_list = [
        p for p in presets if sanitize_name(p.get("name", "")).lower() != key
    ]
    if len(new_list) == len(presets):
        return False
    last_used = store.get("last_used")
    if last_used and sanitize_name(str(last_used)).lower() == key:
        last_used = None
    ok = _write_store(new_list, last_used)
    if ok:
        log.info(f"[GUI] Filter preset deleted: {name}")
    return ok


def preset_names() -> list[str]:
    return [str(p.get("name")) for p in load_presets() if p.get("name")]


def export_sidebar_filters(sidebar) -> dict[str, Any]:
    """Capture current FilterSidebar widget values as a JSON-safe dict."""
    media = {
        mt: bool(cb.isChecked())
        for mt, cb in (getattr(sidebar, "media_checks", None) or {}).items()
    }
    response = {
        rt: bool(cb.isChecked())
        for rt, cb in (getattr(sidebar, "resp_checks", None) or {}).items()
    }

    def _time_str(te) -> str:
        try:
            t = te.time()
            return f"{t.hour()}:{t.minute()}:{t.second()}"
        except Exception:
            return "0:0:0"

    return {
        "text_search": sidebar.text_input.text(),
        "full_string_match": bool(sidebar.fullstring_check.isChecked()),
        "media": media,
        "response": response,
        "downloaded": {
            "true": bool(sidebar.dl_true.isChecked()),
            "false": bool(sidebar.dl_false.isChecked()),
            "no": bool(sidebar.dl_no.isChecked()),
        },
        "unlocked": {
            "true": bool(sidebar.ul_true.isChecked()),
            "false": bool(sidebar.ul_false.isChecked()),
            "locked": bool(sidebar.ul_not_paid.isChecked()),
        },
        "after": {
            "enabled": bool(sidebar.after_enabled.isChecked()),
            "mode": sidebar.after_mode_combo.currentText(),
            "date": sidebar.min_date.date().toString("yyyy-MM-dd"),
            "rel_value": int(sidebar.after_rel_value.value()),
            "rel_unit": sidebar.after_rel_unit.currentText(),
        },
        "before": {
            "enabled": bool(sidebar.before_enabled.isChecked()),
            "mode": sidebar.before_mode_combo.currentText(),
            "date": sidebar.max_date.date().toString("yyyy-MM-dd"),
            "rel_value": int(sidebar.before_rel_value.value()),
            "rel_unit": sidebar.before_rel_unit.currentText(),
        },
        "length": {
            "enabled": bool(sidebar.length_enabled.isChecked()),
            "min": _time_str(sidebar.min_time),
            "max": _time_str(sidebar.max_time),
        },
        "price_enabled": bool(sidebar.price_enabled.isChecked()),
        "price_min": float(sidebar.price_min.value()),
        "price_max": float(sidebar.price_max.value()),
        "media_id": sidebar.media_id_input.text(),
        "post_id": sidebar.post_id_input.text(),
        "post_media_count": int(sidebar.post_media_count_input.value()),
        "other_posts": int(sidebar.other_posts_input.value()),
        "username": sidebar.username_input.text(),
    }


def apply_sidebar_filters(sidebar, filters: dict | None) -> bool:
    """Restore FilterSidebar widgets from a preset filters dict."""
    if not isinstance(filters, dict):
        return False
    try:
        from PyQt6.QtCore import QDate, QTime
    except Exception:
        return False

    def _set_checks(mapping: dict, checks: dict):
        for key, cb in checks.items():
            if key in mapping:
                cb.setChecked(bool(mapping[key]))

    try:
        sidebar.text_input.setText(str(filters.get("text_search") or ""))
        sidebar.fullstring_check.setChecked(bool(filters.get("full_string_match")))

        _set_checks(filters.get("media") or {}, sidebar.media_checks)
        _set_checks(filters.get("response") or {}, sidebar.resp_checks)

        dl = filters.get("downloaded") or {}
        sidebar.dl_true.setChecked(bool(dl.get("true", True)))
        sidebar.dl_false.setChecked(bool(dl.get("false", True)))
        sidebar.dl_no.setChecked(bool(dl.get("no", True)))

        ul = filters.get("unlocked") or {}
        sidebar.ul_true.setChecked(bool(ul.get("true", True)))
        sidebar.ul_false.setChecked(bool(ul.get("false", True)))
        sidebar.ul_not_paid.setChecked(bool(ul.get("locked", True)))

        after = filters.get("after") or {}
        mode = str(after.get("mode") or "Fixed date")
        idx = sidebar.after_mode_combo.findText(mode)
        if idx < 0 and "relative" in mode.lower():
            idx = sidebar.after_mode_combo.findText("Relative")
        if idx >= 0:
            sidebar.after_mode_combo.setCurrentIndex(idx)
        try:
            d = QDate.fromString(str(after.get("date") or "2000-01-01"), "yyyy-MM-dd")
            if d.isValid():
                sidebar.min_date.setDate(d)
        except Exception:
            pass
        try:
            sidebar.after_rel_value.setValue(int(after.get("rel_value") or 1))
            unit = str(after.get("rel_unit") or "days ago")
            uidx = sidebar.after_rel_unit.findText(unit)
            if uidx >= 0:
                sidebar.after_rel_unit.setCurrentIndex(uidx)
        except Exception:
            pass
        sidebar.after_enabled.setChecked(bool(after.get("enabled")))

        before = filters.get("before") or {}
        mode = str(before.get("mode") or "Fixed date")
        idx = sidebar.before_mode_combo.findText(mode)
        if idx < 0 and "relative" in mode.lower():
            idx = sidebar.before_mode_combo.findText("Relative")
        if idx >= 0:
            sidebar.before_mode_combo.setCurrentIndex(idx)
        try:
            d = QDate.fromString(str(before.get("date") or ""), "yyyy-MM-dd")
            if d.isValid():
                sidebar.max_date.setDate(d)
        except Exception:
            pass
        try:
            sidebar.before_rel_value.setValue(int(before.get("rel_value") or 1))
            unit = str(before.get("rel_unit") or "days ago")
            uidx = sidebar.before_rel_unit.findText(unit)
            if uidx >= 0:
                sidebar.before_rel_unit.setCurrentIndex(uidx)
        except Exception:
            pass
        sidebar.before_enabled.setChecked(bool(before.get("enabled")))

        length = filters.get("length") or {}

        def _parse_time(s: str) -> QTime:
            parts = str(s or "0:0:0").split(":")
            while len(parts) < 3:
                parts.append("0")
            try:
                return QTime(int(parts[0]), int(parts[1]), int(parts[2]))
            except Exception:
                return QTime(0, 0, 0)

        # Set values with signals blocked so auto-Enable hooks don't fight presets.
        sidebar.min_time.blockSignals(True)
        sidebar.max_time.blockSignals(True)
        try:
            sidebar.min_time.setTime(_parse_time(length.get("min")))
            sidebar.max_time.setTime(_parse_time(length.get("max")))
        finally:
            sidebar.min_time.blockSignals(False)
            sidebar.max_time.blockSignals(False)
        sidebar.length_enabled.setChecked(bool(length.get("enabled")))

        sidebar.price_min.blockSignals(True)
        sidebar.price_max.blockSignals(True)
        try:
            sidebar.price_min.setValue(float(filters.get("price_min") or 0))
            sidebar.price_max.setValue(float(filters.get("price_max") or 0))
        except Exception:
            pass
        finally:
            sidebar.price_min.blockSignals(False)
            sidebar.price_max.blockSignals(False)
        if "price_enabled" in filters:
            sidebar.price_enabled.setChecked(bool(filters.get("price_enabled")))
        else:
            # Back-compat: old presets had no Enable flag — treat any >0 as on.
            sidebar.price_enabled.setChecked(
                float(filters.get("price_min") or 0) > 0
                or float(filters.get("price_max") or 0) > 0
            )

        sidebar.media_id_input.setText(str(filters.get("media_id") or ""))
        sidebar.post_id_input.setText(str(filters.get("post_id") or ""))
        try:
            sidebar.post_media_count_input.setValue(
                int(filters.get("post_media_count") or 0)
            )
            sidebar.other_posts_input.setValue(int(filters.get("other_posts") or 0))
        except Exception:
            pass
        sidebar.username_input.setText(str(filters.get("username") or ""))
        return True
    except Exception as e:
        log.debug(f"[GUI] apply_sidebar_filters failed: {e}")
        return False
