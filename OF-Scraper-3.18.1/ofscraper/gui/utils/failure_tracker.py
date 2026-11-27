"""Per-scrape download failure tracker for the Pika GUI.

Records failed media during a run so the table page can show a post-run
summary dialog (model, media id, type, reason) with filter / cart actions.
"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_failures: list[dict[str, Any]] = []
_MAX_FAILURES = 500


def clear_failures() -> None:
    """Reset the failure list (call at scrape start)."""
    with _lock:
        _failures.clear()


def record_download_failure(
    *,
    media_id: Any = None,
    username: str = "",
    mediatype: str = "",
    post_id: Any = None,
    reason: str = "download failed",
) -> None:
    """Append one failed download (capped; thread-safe)."""
    entry = {
        "media_id": media_id if media_id is not None else "",
        "username": (username or "").strip() or "unknown",
        "mediatype": (mediatype or "").strip() or "unknown",
        "post_id": post_id if post_id is not None else "",
        "reason": (str(reason) or "download failed").strip()[:500],
    }
    with _lock:
        if len(_failures) >= _MAX_FAILURES:
            return
        # De-dupe by media_id when present
        mid = entry["media_id"]
        if mid != "" and mid is not None:
            for existing in _failures:
                if existing.get("media_id") == mid:
                    # Keep a more specific reason over the generic fallback.
                    if entry["reason"] not in ("", "download failed"):
                        existing["reason"] = entry["reason"]
                    return
        _failures.append(entry)


def clear_failure(media_id: Any, username: str = "") -> bool:
    """Forget a failure that a later attempt of the same item fixed (the
    retry after the links are refreshed), so the summary lists only what is
    still missing. True when one was removed."""
    if media_id is None or media_id == "":
        return False
    user = (username or "").strip().lower()
    with _lock:
        for i, existing in enumerate(_failures):
            if str(existing.get("media_id")) != str(media_id):
                continue
            if user and str(existing.get("username") or "").strip().lower() not in (user, "unknown"):
                continue
            del _failures[i]
            return True
    return False


def get_failures() -> list[dict[str, Any]]:
    """Return a copy of recorded failures for this scrape."""
    with _lock:
        return [dict(x) for x in _failures]


def failure_count() -> int:
    with _lock:
        return len(_failures)


def failure_count_for_user(username: str) -> int:
    """Count recorded failures for one username (case-insensitive)."""
    key = (username or "").strip().lower()
    if not key:
        return 0
    with _lock:
        return sum(
            1
            for f in _failures
            if str(f.get("username") or "").strip().lower() == key
        )


def _on_item_finished(ele=None, username=None, result=None, reason=None, **_):
    """ofscraper's item_finished event: a failed download goes into the
    post-run summary, and its row's cart cell shows [failed]. A later
    success of the same item (the retry) takes it out again."""
    if ele is None:
        return
    if result in ("downloaded", "skipped"):
        try:
            clear_failure(getattr(ele, "id", None), username or getattr(ele, "username", "") or "")
        except Exception:
            pass
        return
    if result != "failed":
        return
    try:
        record_download_failure(
            media_id=getattr(ele, "id", None),
            username=username or getattr(ele, "username", "") or "",
            mediatype=str(getattr(ele, "mediatype", "") or ""),
            post_id=getattr(ele, "file_postid", None),
            reason=reason or "download failed",
        )
    except Exception:
        pass
    try:
        mid = getattr(ele, "id", None)
        if mid is not None:
            from ofscraper.gui.utils.progress_bridge import update_cell_status

            update_cell_status(str(mid), "download_cart", "[failed]")
    except Exception:
        pass


def install_download_events() -> None:
    """Follow ofscraper's download events (ofscraper.utils.events). Calling it
    again does nothing."""
    try:
        from ofscraper.utils import events

        events.subscribe("item_finished", _on_item_finished)
    except Exception:
        pass
