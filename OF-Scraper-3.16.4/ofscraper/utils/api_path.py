"""OnlyFans API path prefix helpers (import-safe, no config side effects).

Default OF endpoints live under ``/api2/v2``. When OnlyFans renames that prefix,
``advanced_options.api_path`` (or ``OFSC_API_PATH``) rewrites default URLs without
changing call sites.
"""
from __future__ import annotations

DEFAULT_API_PATH = "/api2/v2"


def normalize_api_path(value: str | None) -> str:
    """Return a usable API path prefix; invalid/empty → ``DEFAULT_API_PATH``."""
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_API_PATH
    # Reject absolute URLs / hostnames — this field is path-only.
    if "://" in raw or " " in raw or "\\" in raw:
        return DEFAULT_API_PATH
    if not raw.startswith("/"):
        raw = "/" + raw
    # Collapse duplicate slashes (keep leading).
    while "//" in raw:
        raw = raw.replace("//", "/")
    if len(raw) > 1:
        raw = raw.rstrip("/")
    if raw in {"", "/"}:
        return DEFAULT_API_PATH
    return raw


def apply_api_path_prefix(value: str | None, api_path: str | None) -> str | None:
    """Replace default ``/api2/v2`` in *value* with normalized *api_path*."""
    if value is None or not isinstance(value, str):
        return value
    path = normalize_api_path(api_path)
    if path == DEFAULT_API_PATH:
        return value
    if DEFAULT_API_PATH not in value:
        return value
    return value.replace(DEFAULT_API_PATH, path)
