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
