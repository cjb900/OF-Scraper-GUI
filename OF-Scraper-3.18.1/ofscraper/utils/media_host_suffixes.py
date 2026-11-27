"""Media / DRM CDN host-suffix helpers (import-safe).

Feeds the download allowlist extras used by ``host_allowlist`` /
``hardening.is_allowed_media_host``. Built-in defaults remain
``onlyfans.com`` and ``cloudfront.net``.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse


def _clean_one(token: str) -> Optional[str]:
    s = str(token or "").strip().lower()
    if not s:
        return None
    if "://" in s:
        try:
            host = urlparse(s).hostname
        except Exception:
            return None
        if not host:
            return None
        s = host.lower()
    s = s.lstrip(".")
    # Drop path/query if someone pasted host/path without scheme.
    if "/" in s:
        s = s.split("/", 1)[0]
    if ":" in s:
        # Reject host:port — allowlist matches hostname only.
        return None
    if not s or " " in s or "\\" in s:
        return None
    if "." not in s and s not in {"localhost"}:
        # Require a dotted suffix (cdn.example) except localhost.
        return None
    return s


def parse_media_host_suffixes(raw: Any) -> list[str]:
    """Split comma/whitespace-separated host suffixes into cleaned list."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        tokens = [str(x) for x in raw]
    else:
        text = str(raw).replace(";", ",")
        tokens = []
        for part in text.split(","):
            tokens.extend(part.split())
    out: list[str] = []
    for tok in tokens:
        cleaned = _clean_one(tok)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def normalize_media_host_suffixes(raw: Any) -> str:
    """Return canonical comma-separated suffixes (empty if none)."""
    return ",".join(parse_media_host_suffixes(raw))


def validate_media_host_suffixes(raw: Any) -> Optional[str]:
    """Return error if *raw* has content that yields no valid hosts, else None.

    Empty input is valid (means unset).
    """
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        text = ",".join(str(x) for x in raw).strip()
    else:
        text = str(raw).strip()
    if not text:
        return None
    parsed = parse_media_host_suffixes(raw)
    if not parsed:
        return (
            "Media Host Suffixes must be hostnames "
            "(e.g. examplecdn.net), comma-separated"
        )
    return None
