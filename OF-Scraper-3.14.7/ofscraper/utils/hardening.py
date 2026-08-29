"""Import-safe hardening helpers (no CLI/settings side effects).

Used by downloads/paths and by ``test/unit`` so pytest can collect without
triggering ofscraper argument parsing.
"""
from __future__ import annotations

import pathlib
import re
from typing import Any, Mapping, Optional
from urllib.parse import urlparse

# --- Host allowlist ---------------------------------------------------------

_DEFAULT_MEDIA_HOST_SUFFIXES = (
    "onlyfans.com",
    "cloudfront.net",
)


def media_host_suffixes(extra: Optional[str] = None) -> tuple[str, ...]:
    extras: list[str] = []
    if extra:
        extras.extend(str(extra).split(","))
    cleaned: list[str] = []
    for item in list(_DEFAULT_MEDIA_HOST_SUFFIXES) + extras:
        s = str(item or "").strip().lower().lstrip(".")
        if s and s not in cleaned:
            cleaned.append(s)
    return tuple(cleaned)


def is_allowed_media_host(host: str | None, *, extra_suffixes: Optional[str] = None) -> bool:
    if not host:
        return False
    h = str(host).strip().lower()
    if h.startswith("."):
        h = h[1:]
    if not h or "/" in h or ":" in h or " " in h:
        return False
    for suffix in media_host_suffixes(extra_suffixes):
        if h == suffix or h.endswith("." + suffix):
            return True
    return False


def assert_allowed_download_url(
    url: str,
    *,
    kind: str = "media",
    extra_suffixes: Optional[str] = None,
) -> str:
    raw = (url or "").strip()
    if not raw:
        raise ValueError(f"Blocked empty {kind} URL")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError(
            f"Blocked {kind} URL with unsupported scheme '{scheme or 'none'}': {raw[:120]}"
        )
    host = parsed.hostname
    if not is_allowed_media_host(host, extra_suffixes=extra_suffixes):
        raise ValueError(
            f"Blocked {kind} URL host '{host}' (not in media allowlist). "
            f"URL: {raw[:160]}"
        )
    return raw


# --- Path confinement -------------------------------------------------------

def assert_path_under_root(path, root, *, label: str = "path"):
    root_path = pathlib.Path(root).expanduser()
    try:
        root_res = root_path.resolve(strict=False)
    except OSError:
        root_res = root_path.absolute()

    candidate = pathlib.Path(path)
    if not candidate.is_absolute():
        candidate = root_res / candidate
    try:
        cand_res = candidate.expanduser().resolve(strict=False)
    except OSError:
        cand_res = candidate.expanduser().absolute()

    try:
        cand_res.relative_to(root_res)
    except ValueError as e:
        raise ValueError(
            f"{label} escapes configured root: {cand_res} (root={root_res})"
        ) from e
    return cand_res


# --- DRM MPD → segment URL --------------------------------------------------

def mpd_segment_url(mpd_url: str, segment_name: str) -> str:
    """Build a CloudFront DASH segment URL from an MPD manifest URL.

    OF MPD URLs look like::

        https://cdn…/dash/files/…/<id>.mpd?Tag=2

    Segment names from the parsed MPD (e.g. ``<id>_audio.mp4``) live next to
    the manifest. Older code used ``re.sub(...mpd$, ..., mpd, re.IGNORECASE)``
    which (1) passed ``IGNORECASE`` as *count* and (2) failed when a query
    string followed ``.mpd``, so the downloader requested the playlist XML
    instead of the segment and then treated ``content-total: 0`` as success.
    """
    from urllib.parse import urlsplit, urlunsplit

    raw_mpd = (mpd_url or "").strip()
    name = (segment_name or "").strip().lstrip("/")
    if not raw_mpd:
        raise ValueError("Empty MPD URL")
    if not name:
        raise ValueError("Empty DRM segment name")
    if name.lower().endswith(".mpd"):
        raise ValueError(f"Segment name looks like an MPD playlist: {name}")

    parts = urlsplit(raw_mpd)
    path = parts.path or ""
    base_path = re.sub(r"[^/]+\.mpd$", "", path, flags=re.IGNORECASE)
    if base_path == path:
        # Manifest path did not end in *.mpd — fall back to directory.
        if "/" in path:
            base_path = path.rsplit("/", 1)[0] + "/"
        else:
            base_path = "/"
    if not base_path.endswith("/"):
        base_path += "/"

    return urlunsplit(
        (parts.scheme, parts.netloc, base_path + name, parts.query, "")
    )


# --- .part expected size ----------------------------------------------------

def parse_expected_file_size(
    headers: Mapping[str, Any] | None,
    *,
    resume_size: int = 0,
    content_length=None,
) -> int:
    headers = headers or {}
    cr = headers.get("Content-Range") or headers.get("content-range")
    if cr:
        match = re.search(r"bytes\s+(\d+)-(\d+)/(\d+)", str(cr), flags=re.IGNORECASE)
        if match:
            return int(match.group(3))

    try:
        body_len = int(content_length) if content_length is not None else None
    except (TypeError, ValueError):
        body_len = None
    if body_len is None:
        try:
            body_len = int(
                headers.get("content-length") or headers.get("Content-Length") or 0
            )
        except (TypeError, ValueError):
            body_len = 0

    resume_size = int(resume_size or 0)
    if resume_size > 0 and body_len > 0:
        return resume_size + body_len
    return body_len or 0


# --- Media integrity (pure) -------------------------------------------------

_DEFAULT_MATCH_THRESHOLD = 0.98
_MIN_BYTES = 1024
_MIN_DURATION_SECONDS = 0.05
# OnlyFans often reports whole-second durations; remux/ffprobe can be a few
# tenths shorter (e.g. expected=12, actual=11.71 → 97.6% fails a strict 98%).
# Allow this absolute shortfall in addition to the percent gate.
_ABS_DURATION_SLACK_SECONDS = 1.0


def resolve_match_threshold(match_threshold) -> float:
    try:
        value = float(match_threshold)
    except (TypeError, ValueError):
        return _DEFAULT_MATCH_THRESHOLD
    if value <= 0:
        return _DEFAULT_MATCH_THRESHOLD
    if value > 1.0:
        if value <= 100:
            value = value / 100.0
        else:
            return _DEFAULT_MATCH_THRESHOLD
    return min(value, 1.0)


def check_media_integrity(
    file_path,
    actual_duration_seconds,
    expected_duration_seconds=None,
    *,
    match_threshold=None,
    min_bytes=_MIN_BYTES,
    abs_slack_seconds=_ABS_DURATION_SLACK_SECONDS,
) -> bool:
    """Pure integrity gate given an already-probed duration (or None).

    When an expected duration is provided, the file passes if either:
    - ``actual / expected >= match_threshold``, or
    - ``expected - actual <= abs_slack_seconds`` (API whole-second rounding /
      normal remux skew on short clips).
    """
    path = pathlib.Path(file_path)
    try:
        size = path.stat().st_size
    except OSError:
        return False

    if size < int(min_bytes):
        return False

    if actual_duration_seconds is None:
        return False
    try:
        actual = float(actual_duration_seconds)
    except (TypeError, ValueError):
        return False
    if actual <= _MIN_DURATION_SECONDS:
        return False

    threshold = resolve_match_threshold(match_threshold)
    try:
        expected = (
            float(expected_duration_seconds)
            if expected_duration_seconds not in (None, "", 0, "0")
            else None
        )
    except (TypeError, ValueError):
        expected = None

    if expected and expected > 0:
        ratio = actual / expected
        if ratio >= threshold:
            return True
        try:
            slack = float(abs_slack_seconds)
        except (TypeError, ValueError):
            slack = _ABS_DURATION_SLACK_SECONDS
        if slack > 0 and (expected - actual) <= slack:
            return True
        return False
    return True
