"""Allowlist + domain checks for OnlyFans auth cookies.

Persist only the cookies/headers required for API auth. Drop unrelated
browser cookies and reject lookalike cookie hosts.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger("shared")

# Cookie names required (or optional for 2FA) for OnlyFans API auth.
AUTH_COOKIE_NAMES = frozenset({"sess", "auth_id"})
AUTH_UID_PREFIX = "auth_uid"

# Keys written to auth.json (cookies + request headers).
AUTH_FILE_KEYS = frozenset({"sess", "auth_id", "auth_uid", "user_agent", "x-bc"})

# SQL fragment for Chromium / Firefox cookie DB queries (host column varies).
OF_HOST_SQL = (
    "(host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' "
    "OR host = 'www.onlyfans.com')"
)
OF_HOST_KEY_SQL = (
    "(host_key = 'onlyfans.com' OR host_key = '.onlyfans.com' "
    "OR host_key LIKE '%.onlyfans.com' OR host_key = 'www.onlyfans.com')"
)
OF_COOKIE_NAME_SQL = "(name IN ('sess', 'auth_id') OR name LIKE 'auth_uid%')"


def is_onlyfans_host(host: str | None) -> bool:
    """True if *host* is onlyfans.com or a subdomain (not a lookalike domain)."""
    if not host:
        return False
    h = str(host).strip().lower()
    # Strip leading dot used by cookie Domain attributes.
    if h.startswith("."):
        h = h[1:]
    return h == "onlyfans.com" or h.endswith(".onlyfans.com")


def is_allowed_cookie_name(name: str | None) -> bool:
    """True for sess / auth_id / auth_uid* cookie names."""
    if not name:
        return False
    n = str(name).strip()
    if n in AUTH_COOKIE_NAMES:
        return True
    return n.startswith(AUTH_UID_PREFIX)


def filter_cookie_map(
    cookies: Mapping[str, Any] | None,
    *,
    keep_meta: bool = True,
    keep_headers: bool = True,
) -> dict[str, Any]:
    """Keep allowlisted cookie names (+ optional x-bc / user_agent / ``_`` meta).

    ``auth_uid_*`` variants are normalized to ``auth_uid`` when writing form/auth
    values, while the original key is kept if callers need it for diagnostics.
    """
    if not cookies:
        return {}
    out: dict[str, Any] = {}
    for key, value in cookies.items():
        if value is None:
            continue
        k = str(key)
        if keep_meta and k.startswith("_"):
            out[k] = value
            continue
        if keep_headers and k in {"user_agent", "x-bc", "x_bc"}:
            out["x-bc" if k == "x_bc" else k] = value
            continue
        if not is_allowed_cookie_name(k):
            continue
        sv = str(value).strip() if not isinstance(value, (bytes, bytearray)) else value
        if isinstance(sv, str) and not sv:
            continue
        out[k] = sv
        if k.startswith(AUTH_UID_PREFIX) and k != "auth_uid":
            # Canonical field used by auth.json / GUI.
            out.setdefault("auth_uid", sv)
    return out


def sanitize_auth_dict(auth: Mapping[str, Any] | None) -> dict[str, str]:
    """Return a flat auth.json dict with only allowlisted keys (strings)."""
    if not auth:
        return {k: "" for k in ("sess", "auth_id", "auth_uid", "user_agent", "x-bc")}
    raw = dict(auth)
    if "auth" in raw and isinstance(raw.get("auth"), Mapping):
        raw = dict(raw["auth"])

    # Prefer schema extractors when available (handles legacy cookie-string blobs).
    try:
        import ofscraper.utils.auth.schema as auth_schema

        cleaned = auth_schema.auth_schema(raw)
    except Exception:
        cleaned = {
            "sess": str(raw.get("sess") or ""),
            "auth_id": str(raw.get("auth_id") or ""),
            "auth_uid": str(raw.get("auth_uid") or ""),
            "user_agent": str(raw.get("user_agent") or ""),
            "x-bc": str(raw.get("x-bc") or raw.get("x_bc") or ""),
        }

    # Drop anything outside the allowlist.
    return {k: str(cleaned.get(k) or "") for k in AUTH_FILE_KEYS}


def harden_auth_file_permissions(path) -> None:
    """Best-effort: owner-only access on Unix; restrict ACL on Windows."""
    try:
        p = Path(path)
        if not p.is_file():
            return
        if os.name == "nt":
            user = os.environ.get("USERNAME") or ""
            if not user:
                return
            import subprocess

            # Remove inherited ACEs; grant current user full control only.
            subprocess.run(
                [
                    "icacls",
                    str(p),
                    "/inheritance:r",
                    "/grant:r",
                    f"{user}:(F)",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        else:
            os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception as e:
        log.debug(f"Could not harden auth file permissions on {path}: {e}")
