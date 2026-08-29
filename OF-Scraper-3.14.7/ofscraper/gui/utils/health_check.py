"""Lightweight auth / config / key-mode health snapshot for the GUI status strip."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class HealthChip:
    """One clickable health indicator."""

    key: str  # auth | config | key
    text: str  # short chip label
    level: str  # ok | warn | error
    detail: str  # tooltip
    navigate: str  # sidebar page name (auth / config / drm)


def gather_health() -> List[HealthChip]:
    """Return Auth, Config, and Key chips reflecting current on-disk state."""
    return [_auth_chip(), _config_chip(), _key_chip()]


def _auth_chip() -> HealthChip:
    try:
        import ofscraper.utils.auth.utils.dict as auth_dict

        auth = auth_dict.get_auth_dict() or {}
    except Exception as e:
        return HealthChip(
            key="auth",
            text="Auth ✗",
            level="error",
            detail=f"Could not read auth.json: {e}",
            navigate="auth",
        )

    sess = str(auth.get("sess") or "").strip()
    auth_id = str(auth.get("auth_id") or "").strip()
    user_agent = str(auth.get("user_agent") or "").strip()
    x_bc = str(auth.get("x-bc") or "").strip()

    required = {
        "sess": sess,
        "auth_id": auth_id,
        "user_agent": user_agent,
        "x-bc": x_bc,
    }
    missing = [k for k, v in required.items() if not v]

    if len(missing) == 4:
        return HealthChip(
            key="auth",
            text="Auth ✗",
            level="error",
            detail="No credentials saved. Open Authentication to log in or import cookies.",
            navigate="auth",
        )
    if missing:
        return HealthChip(
            key="auth",
            text="Auth !",
            level="warn",
            detail="Incomplete credentials — missing: "
            + ", ".join(missing)
            + ". Open Authentication to finish setup.",
            navigate="auth",
        )
    return HealthChip(
        key="auth",
        text="Auth ✓",
        level="ok",
        detail="Auth credentials present (sess, auth_id, user-agent, x-bc).",
        navigate="auth",
    )


def _config_chip() -> HealthChip:
    try:
        from ofscraper.gui.utils.config_validation import validate_config

        result = validate_config()
    except Exception as e:
        return HealthChip(
            key="config",
            text="Config ✗",
            level="error",
            detail=f"Could not validate configuration: {e}",
            navigate="config",
        )

    if result.errors:
        detail = result.format_errors()
        return HealthChip(
            key="config",
            text="Config ✗",
            level="error",
            detail=detail or "Configuration has errors.",
            navigate="config",
        )
    if result.warnings:
        detail = result.format_warnings()
        return HealthChip(
            key="config",
            text="Config !",
            level="warn",
            detail=detail or "Configuration has warnings.",
            navigate="config",
        )
    return HealthChip(
        key="config",
        text="Config ✓",
        level="ok",
        detail="Save Location and file/path templates look OK.",
        navigate="config",
    )


def _key_chip() -> HealthChip:
    try:
        from ofscraper.gui.utils.key_mode_warning import (
            get_configured_key_mode,
            is_remote_key_mode,
        )
        from ofscraper.utils.config.config import read_config

        mode = get_configured_key_mode()
        cfg = read_config(update=False) or {}
    except Exception as e:
        return HealthChip(
            key="key",
            text="Key ?",
            level="warn",
            detail=f"Could not read key mode: {e}",
            navigate="config",
        )

    if is_remote_key_mode(mode):
        return HealthChip(
            key="key",
            text=f"Key: {mode}",
            level="warn",
            detail=(
                f"Key Mode is {mode} (remote helper). Prefer manual local CDM for "
                "OnlyFans DRM. Click to open Configuration → CDM."
            ),
            navigate="config",
        )

    cdm = cfg.get("cdm_options") if isinstance(cfg.get("cdm_options"), dict) else {}
    client = str((cdm or {}).get("client-id") or "").strip()
    private = str((cdm or {}).get("private-key") or "").strip()
    missing_files = True
    if client and private:
        try:
            missing_files = not (Path(client).is_file() and Path(private).is_file())
        except Exception:
            missing_files = True

    if missing_files:
        return HealthChip(
            key="key",
            text="Key: CDM?",
            level="warn",
            detail=(
                "Key Mode is manual but client_id.bin / private_key.pem paths are "
                "missing or invalid. Open Configuration → CDM or DRM Key Creation."
            ),
            navigate="drm",
        )

    return HealthChip(
        key="key",
        text="Key: manual",
        level="ok",
        detail="Key Mode is manual with local CDM files configured.",
        navigate="config",
    )
