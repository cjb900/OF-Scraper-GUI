"""Persistent recent scrape / check-mode run history for the GUI.

Stored as scrape_history.json next to gui_settings.json. Used for a
History menu on the table page and optional re-run of a past job.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger("shared")

_HISTORY_FILE = "scrape_history.json"
MAX_RUNS = 20


def _history_path() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths

        return common_paths.get_config_home() / _HISTORY_FILE
    except Exception:
        return Path.home() / ".config" / "ofscraper" / _HISTORY_FILE


def load_history() -> list[dict]:
    p = _history_path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        runs = data.get("runs") if isinstance(data, dict) else data
        if isinstance(runs, list):
            return [r for r in runs if isinstance(r, dict)]
    except Exception as e:
        log.warning(f"[GUI] Could not read {_HISTORY_FILE}: {e}")
    return []


def save_history(runs: list[dict]) -> bool:
    p = _history_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        trimmed = list(runs)[:MAX_RUNS]
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"runs": trimmed}, f, indent=2)
        return True
    except Exception as e:
        log.warning(f"[GUI] Could not save {_HISTORY_FILE}: {e}")
        return False


def _privacy_name(name: str) -> str:
    try:
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode

        if is_privacy_mode():
            return "[Hidden for Privacy]"
    except Exception:
        pass
    return name


def _now_iso() -> str:
    """Current wall-clock time on this machine (local TZ), ISO-8601 with offset."""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _parse_iso(iso: str) -> datetime:
    s = str(iso).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def snapshot_from_workflow(workflow) -> dict[str, Any]:
    """Capture job inputs at scrape start."""
    models = getattr(workflow, "_selected_models", None) or []
    names = []
    for m in models:
        n = getattr(m, "name", None) or str(m)
        if n:
            names.append(str(n))
    actions = sorted(
        str(a) for a in (getattr(workflow, "_selected_actions", None) or set())
    )
    check_modes = getattr(workflow, "_CHECK_MODES", set()) or set()
    advanced = getattr(workflow, "_advanced", None) or {}
    manual = list(getattr(workflow, "_manual_urls", None) or [])
    return {
        "id": uuid.uuid4().hex[:12],
        "ts_start": _now_iso(),
        "actions": actions,
        "models": names,
        "areas": list(getattr(workflow, "_selected_areas", None) or []),
        "mediatypes": list(getattr(workflow, "_selected_mediatypes", None) or []),
        "manual_url_count": len(manual),
        "manual_urls": [str(u) for u in manual[:30]],
        "check_mode": bool(set(actions) & set(check_modes)),
        "scrape_paid": bool(getattr(workflow, "_scrape_paid", False)),
        "daemon": bool(getattr(workflow, "_daemon_enabled", False)),
        "allow_dupes": bool(advanced.get("allow_dupe_downloads")),
        "keep_msg_purchased_dupes": bool(advanced.get("keep_message_purchased_dupes")),
        "rescrape_all": bool(advanced.get("rescrape_all")),
    }


def delete_entry(entry_id: str) -> bool:
    """Remove one history entry by id. Returns True if something was removed."""
    eid = str(entry_id or "").strip()
    if not eid:
        return False
    runs = load_history()
    new_runs = [r for r in runs if str(r.get("id") or "") != eid]
    if len(new_runs) == len(runs):
        return False
    return save_history(new_runs)


def duration_seconds(entry: dict | None) -> int | None:
    """Elapsed seconds between ts_start and ts_end, or None if unknown."""
    if not entry:
        return None
    if entry.get("duration_sec") is not None:
        try:
            return max(0, int(entry["duration_sec"]))
        except (TypeError, ValueError):
            pass
    start = entry.get("ts_start")
    end = entry.get("ts_end")
    if not start or not end:
        return None
    try:
        def _parse(iso: str) -> datetime:
            return _parse_iso(iso)

        delta = _parse(str(end)) - _parse(str(start))
        return max(0, int(delta.total_seconds()))
    except Exception:
        return None


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {sec:02d}s"
    return f"{sec}s"


def record_run(
    snapshot: dict | None,
    *,
    status: str = "ok",
    run_dl: int = 0,
    failed: int = 0,
    forced: int = 0,
    total_bytes: int = 0,
    row_count: int = 0,
    model_names: list[str] | None = None,
) -> dict | None:
    """Append a finished run. Returns the saved entry or None."""
    entry: dict[str, Any] = dict(snapshot or {})
    if not entry.get("id"):
        entry["id"] = uuid.uuid4().hex[:12]
    if not entry.get("ts_start"):
        entry["ts_start"] = _now_iso()
    entry["ts_end"] = _now_iso()
    entry["status"] = status  # ok | cancelled | error
    entry["run_dl"] = int(run_dl or 0)
    entry["failed"] = int(failed or 0)
    entry["forced"] = int(forced or 0)
    entry["total_bytes"] = int(total_bytes or 0)
    entry["row_count"] = int(row_count or 0)
    dur = duration_seconds(entry)
    if dur is not None:
        entry["duration_sec"] = dur
    if model_names:
        # Prefer outcome list when snapshot had none (e.g. check downloads).
        if not entry.get("models"):
            entry["models"] = list(model_names)

    runs = load_history()
    runs.insert(0, entry)
    if save_history(runs):
        log.info(
            f"[GUI] Scrape history recorded: {entry.get('status')} "
            f"models={len(entry.get('models') or [])} dl={entry.get('run_dl')} "
            f"duration={format_duration(entry.get('duration_sec'))}"
        )
        return entry
    return None


def clear_history() -> bool:
    return save_history([])


def format_bytes(n: int) -> str:
    n = float(max(0, int(n or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def format_short_ts(iso: str | None) -> str:
    """Compact local wall time for History UI (system timezone)."""
    if not iso:
        return "?"
    try:
        dt = _parse_iso(iso)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(iso)[:16]


def _short_ts(iso: str | None) -> str:
    return format_short_ts(iso)


def format_menu_label(entry: dict) -> str:
    ts = _short_ts(entry.get("ts_end") or entry.get("ts_start"))
    status = str(entry.get("status") or "ok")
    mark = {"ok": "✓", "cancelled": "✗", "error": "!"}.get(status, "·")
    models = entry.get("models") or []
    if not models and entry.get("manual_url_count"):
        who = f"{entry['manual_url_count']} URL(s)"
    elif not models:
        who = "(no models)"
    elif len(models) == 1:
        who = _privacy_name(str(models[0]))
    else:
        who = f"{len(models)} models"
    actions = entry.get("actions") or []
    act = actions[0] if len(actions) == 1 else (
        ",".join(actions[:2]) + ("…" if len(actions) > 2 else "")
    ) or "download"
    dl = int(entry.get("run_dl") or 0)
    fail = int(entry.get("failed") or 0)
    dur = format_duration(duration_seconds(entry))
    tail = f"{dl} dl"
    if fail:
        tail += f", {fail} fail"
    return f"{mark} {ts}  {who}  [{act}]  {tail}  ({dur})"


def format_models_short(entry: dict, *, limit: int = 3) -> str:
    models = entry.get("models") or []
    if not models and entry.get("manual_url_count"):
        return f"{entry['manual_url_count']} URL(s)"
    if not models:
        return "(none)"
    if len(models) == 1:
        return _privacy_name(str(models[0]))
    if len(models) <= limit:
        return ", ".join(_privacy_name(str(m)) for m in models)
    head = ", ".join(_privacy_name(str(m)) for m in models[:limit])
    return f"{len(models)} models ({head}, …)"


def format_details_html(entry: dict) -> str:
    models = entry.get("models") or []
    if len(models) <= 8:
        models_txt = ", ".join(_privacy_name(str(m)) for m in models) or "(none)"
    else:
        head = ", ".join(_privacy_name(str(m)) for m in models[:5])
        models_txt = f"{len(models)} models ({head}, …)"

    areas = entry.get("areas") or []
    areas_txt = ", ".join(str(a) for a in areas) if areas else "(none / N/A)"
    media = entry.get("mediatypes") or []
    media_txt = ", ".join(str(m) for m in media) if media else "(default)"
    actions = entry.get("actions") or []
    actions_txt = ", ".join(str(a) for a in actions) if actions else "(default)"

    flags = []
    if entry.get("check_mode"):
        flags.append("Check mode")
    if entry.get("scrape_paid"):
        flags.append("Scrape paid")
    if entry.get("daemon"):
        flags.append("Daemon")
    if entry.get("rescrape_all"):
        flags.append("Rescrape all")
    if entry.get("allow_dupes"):
        flags.append("Allow dupes")
    if entry.get("manual_url_count"):
        flags.append(f"Manual URLs: {entry['manual_url_count']}")

    status = str(entry.get("status") or "ok")
    status_color = {
        "ok": "#a6e3a1",
        "cancelled": "#f9e2af",
        "error": "#f38ba8",
    }.get(status, "#cdd6f4")

    dur = format_duration(duration_seconds(entry))
    start = _short_ts(entry.get("ts_start"))
    end = _short_ts(entry.get("ts_end") or entry.get("ts_start"))

    return (
        f"<p><b>Started:</b> {start}<br/>"
        f"<b>Ended:</b> {end}<br/>"
        f"<b>Duration:</b> {dur}<br/>"
        f"<b>Status:</b> <span style='color:{status_color}'>{status}</span><br/>"
        f"<b>Actions:</b> {actions_txt}<br/>"
        f"<b>Models:</b> {models_txt}<br/>"
        f"<b>Areas:</b> {areas_txt}<br/>"
        f"<b>Media types:</b> {media_txt}</p>"
        f"<p><b>Downloads:</b> {int(entry.get('run_dl') or 0)} "
        f"(skipped {int(entry.get('forced') or 0)}, "
        f"failed {int(entry.get('failed') or 0)})<br/>"
        f"<b>Size:</b> {format_bytes(int(entry.get('total_bytes') or 0))}<br/>"
        f"<b>Table rows:</b> {int(entry.get('row_count') or 0)}</p>"
        + (f"<p><b>Flags:</b> {', '.join(flags)}</p>" if flags else "")
    )



def resolve_models_by_name(names: list[str], model_page) -> tuple[list, list[str]]:
    """Return (model_objects, missing_names)."""
    found = []
    missing = []
    all_models = getattr(model_page, "_all_models", None) or {}
    # Case-insensitive map
    lower_map = {str(k).lower(): v for k, v in all_models.items()}
    for name in names:
        key = str(name)
        m = all_models.get(key) or lower_map.get(key.lower())
        if m is not None:
            found.append(m)
        else:
            missing.append(key)
    return found, missing


def apply_entry_to_pages(entry: dict, *, main_window) -> tuple[bool, str]:
    """Restore actions/areas/models onto GUI pages for a re-run.

    Returns (ok, message). Does not start the scrape.
    """
    workflow = getattr(main_window, "workflow", None)
    area_page = getattr(main_window, "area_page", None)
    model_page = getattr(main_window, "model_page", None)
    if workflow is None or area_page is None:
        return False, "Could not find scrape workflow / area page."

    actions = set(str(a) for a in (entry.get("actions") or []) if str(a).strip())
    if not actions:
        actions = {"download"}

    # Manual URL jobs
    if "manual_url" in actions or entry.get("manual_url_count"):
        urls = list(entry.get("manual_urls") or [])
        if not urls:
            return False, "This history entry has no stored manual URLs to re-run."
        workflow._manual_urls = urls
        workflow._selected_actions = {"manual_url"}
        workflow._selected_models = []
        workflow._selected_areas = []
        return True, f"Restored {len(urls)} manual URL(s)."

    models_wanted = list(entry.get("models") or [])
    if not models_wanted:
        return False, "This history entry has no models to re-run."

    if model_page is None or not getattr(model_page, "_all_models", None):
        return (
            False,
            "Models are not loaded yet. Open the Model selector once, then try Re-run.",
        )

    models, missing = resolve_models_by_name(models_wanted, model_page)
    if not models:
        return (
            False,
            "None of the models from this run are in the current list "
            f"({', '.join(missing[:5])}{'…' if len(missing) > 5 else ''}).",
        )

    workflow._selected_actions = actions
    workflow._manual_urls = []
    try:
        area_page._current_actions = set(actions)
        if hasattr(area_page, "_update_available_areas"):
            area_page._update_available_areas()
    except Exception as e:
        log.debug(f"[GUI] History re-run area actions: {e}")

    areas = set(str(a) for a in (entry.get("areas") or []))
    try:
        for area, cb in (getattr(area_page, "_area_checks", None) or {}).items():
            want = area in areas
            if cb.isEnabled() and not cb.isHidden():
                cb.setChecked(want)
            elif want:
                # Area not available for this action set — leave unchecked.
                pass
    except Exception as e:
        log.debug(f"[GUI] History re-run areas: {e}")

    media = set(str(m) for m in (entry.get("mediatypes") or []))
    if media:
        try:
            for mt, cb in (getattr(area_page, "_mediatype_checks", None) or {}).items():
                cb.setChecked(mt in media)
        except Exception:
            pass

    # Optional flags (non-destructive only — never auto-enable delete).
    try:
        if getattr(area_page, "scrape_paid_check", None):
            area_page.scrape_paid_check.setChecked(bool(entry.get("scrape_paid")))
        if getattr(area_page, "allow_dupes_check", None):
            area_page.allow_dupes_check.setChecked(bool(entry.get("allow_dupes")))
        if getattr(area_page, "keep_msg_purchased_dupes_check", None):
            area_page.keep_msg_purchased_dupes_check.setChecked(
                bool(entry.get("allow_dupes"))
                and bool(entry.get("keep_msg_purchased_dupes"))
            )
            area_page.keep_msg_purchased_dupes_check.setEnabled(
                bool(entry.get("allow_dupes"))
            )
        if getattr(area_page, "rescrape_all_check", None):
            area_page.rescrape_all_check.setChecked(bool(entry.get("rescrape_all")))
        # Never restore delete_db / delete_downloads from history.
        if getattr(area_page, "delete_db_check", None):
            area_page.delete_db_check.setChecked(False)
        if getattr(area_page, "delete_downloads_check", None):
            area_page.delete_downloads_check.setChecked(False)
        if getattr(area_page, "daemon_check", None):
            area_page.daemon_check.setChecked(False)
    except Exception:
        pass

    workflow._selected_models = models
    try:
        workflow._selected_areas = list(area_page.get_selected_areas() or [])
    except Exception:
        workflow._selected_areas = list(areas)
    try:
        mt = getattr(area_page, "get_selected_mediatypes", None)
        if callable(mt):
            workflow._selected_mediatypes = list(mt() or [])
    except Exception:
        pass

    msg = f"Restored {len(models)} model(s)"
    if missing:
        msg += f" ({len(missing)} missing skipped)"
    return True, msg
