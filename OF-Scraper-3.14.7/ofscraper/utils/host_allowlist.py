"""Allowlist checks for media / DRM download URLs.

Rejects lookalike hosts and non-HTTPS schemes before CDN/MPD/license fetches.
Extra suffixes can be added via ``OFSC_MEDIA_HOST_SUFFIXES`` (env) and
``advanced_options.media_host_suffixes`` (config/GUI), comma-separated.
"""
from __future__ import annotations

import logging
import os

from ofscraper.utils.hardening import (
    assert_allowed_download_url as _assert_allowed_download_url,
    is_allowed_media_host as _is_allowed_media_host,
)
from ofscraper.utils.media_host_suffixes import normalize_media_host_suffixes

log = logging.getLogger("shared")


def _extra_suffixes() -> str:
    parts: list[str] = []
    try:
        import ofscraper.utils.of_env.of_env as of_env

        raw = of_env.getattr("MEDIA_HOST_SUFFIXES")
        if raw:
            parts.append(str(raw))
    except Exception:
        pass
    env_raw = os.getenv("OFSC_MEDIA_HOST_SUFFIXES", "")
    if env_raw:
        parts.append(env_raw)
    try:
        import ofscraper.utils.config.data as config_data

        cfg = config_data.get_media_host_suffixes()
        if cfg:
            parts.append(str(cfg))
    except Exception:
        pass
    # Re-normalize so duplicates / junk from merges collapse cleanly.
    return normalize_media_host_suffixes(",".join(parts))


def is_allowed_media_host(host: str | None) -> bool:
    return _is_allowed_media_host(host, extra_suffixes=_extra_suffixes())


def assert_allowed_download_url(url: str, *, kind: str = "media") -> str:
    return _assert_allowed_download_url(
        url, kind=kind, extra_suffixes=_extra_suffixes()
    )


def ensure_allowed_download_url(url: str, *, kind: str = "media") -> str:
    """Like assert_allowed_download_url but logs and re-raises as Exception."""
    try:
        return assert_allowed_download_url(url, kind=kind)
    except ValueError as e:
        log.warning(str(e))
        raise Exception(str(e)) from e
