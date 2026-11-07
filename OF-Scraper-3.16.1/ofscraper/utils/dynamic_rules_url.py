"""Custom dynamic-rules URL helpers (import-safe, no config side effects).

Used when Dynamic Mode is ``generic``: ``advanced_options.dynamic_rules_url``
or env ``OF_DYNAMIC_GENERIC_URL`` / ``OFSC_DYNAMIC_GENERIC_URL``.
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlparse


def normalize_dynamic_rules_url(raw: Any) -> str:
    """Strip whitespace; empty/None → ``\"\"``."""
    if raw is None:
        return ""
    return str(raw).strip()


def validate_dynamic_rules_url(raw: Any) -> Optional[str]:
    """Return error message if *raw* is not a usable http(s) URL, else None.

    Empty string is allowed (means “unset”).
    """
    text = normalize_dynamic_rules_url(raw)
    if not text:
        return None
    try:
        parsed = urlparse(text)
    except Exception:
        return "Dynamic Rules URL is not a valid URL"
    if parsed.scheme not in {"http", "https"}:
        return "Dynamic Rules URL must start with http:// or https://"
    if not parsed.netloc:
        return "Dynamic Rules URL is missing a host"
    return None


def resolve_dynamic_rules_url(
    env_value: Any = None, config_value: Any = None
) -> Optional[str]:
    """Prefer first valid non-empty URL among env, then config."""
    for raw in (env_value, config_value):
        text = normalize_dynamic_rules_url(raw)
        if not text:
            continue
        if validate_dynamic_rules_url(text) is not None:
            continue
        return text
    return None
