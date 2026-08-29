"""Privacy / demo mode — hide secrets and paths in the GUI for screenshots.

Mirrors SubScraper's ``--hide-private-info`` UX: display placeholders while
keeping real values for save/scrape operations.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("shared")

PRIVACY_PLACEHOLDER = "[Hidden for Privacy]"

# Config QLineEdit keys that should show the placeholder when privacy is on.
PRIVACY_CONFIG_KEYS = frozenset(
    {
        "save_location",
        "discord",
        "ffmpeg",
        "client-id",
        "private-key",
        "temp_dir",
    }
)

_enabled = False


def is_privacy_mode() -> bool:
    return bool(_enabled)


def set_privacy_mode(enabled: bool, *, persist: bool = True, emit: bool = True) -> None:
    """Enable/disable privacy mode. Optionally persist and emit Qt signal."""
    global _enabled
    enabled = bool(enabled)
    _enabled = enabled
    if persist:
        _persist(enabled)
    if emit:
        try:
            from ofscraper.gui.signals import app_signals

            app_signals.privacy_mode_changed.emit(enabled)
        except Exception:
            pass
    log.info(f"[GUI] Privacy / demo mode {'On' if enabled else 'Off'}")


def load_privacy_mode_from_settings() -> bool:
    """Load preference from gui_settings.json into module state (no emit)."""
    global _enabled
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        _enabled = bool(load_gui_settings().get("privacy_mode", False))
    except Exception:
        _enabled = False
    return _enabled


def _persist(enabled: bool) -> None:
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

        s = load_gui_settings()
        s["privacy_mode"] = bool(enabled)
        save_gui_settings(s)
    except Exception as e:
        log.debug(f"[GUI] Could not persist privacy_mode: {e}")


def is_privacy_placeholder(text: Optional[str]) -> bool:
    return (text or "").strip() == PRIVACY_PLACEHOLDER


def display_or_mask(value: Optional[str]) -> str:
    """Return placeholder when privacy is on and value is non-empty."""
    text = "" if value is None else str(value)
    if is_privacy_mode() and text.strip():
        return PRIVACY_PLACEHOLDER
    return text


def resolve_saved_value(displayed: Optional[str], actual: Optional[str]) -> str:
    """When saving, keep the stashed actual value if the field still shows the placeholder."""
    shown = "" if displayed is None else str(displayed).strip()
    if is_privacy_placeholder(shown):
        return "" if actual is None else str(actual)
    return shown


def mask_username(username: Optional[str]) -> str:
    if not is_privacy_mode():
        return "" if username is None else str(username)
    text = "" if username is None else str(username).strip()
    return PRIVACY_PLACEHOLDER if text else ""


# Status / log lines that embed a model username after a fixed prefix.
_STATUS_USER_PREFIXES = (
    r"Processing\s+",
    r"Skipping download for\s+",
    r"Starting download of \d+ items for\s+",
    r"Download complete for\s+",
    r"Running actions for\s+",
    r"Finished\s+",
)

_STATUS_USER_RE = re.compile(
    r"(?i)\b((?:"
    + "|".join(_STATUS_USER_PREFIXES)
    + r"))([A-Za-z0-9_.-]+)"
)


def redact_status_message(message: str) -> str:
    """Mask model usernames in short status-bar lines when privacy is on."""
    if not is_privacy_mode() or not message:
        return message
    try:
        return _STATUS_USER_RE.sub(rf"\1{PRIVACY_PLACEHOLDER}", str(message))
    except Exception:
        return message


def format_model_list_line(
    name: str,
    *,
    sub_date: str = "N/A",
    price=0,
    style: str = "page",
    name_width: int = 28,
) -> str:
    """Display line for Select Models list. Masks identity when privacy is on.

    ``style`` is ``page`` or ``dialog`` (same column layout). Columns are
    fixed-width (username / date / price) — the list widget must use a
    monospace font or padding will not line up under Segoe UI.
    """
    width = max(12, min(int(name_width or 28), 40))

    def _pad_name(raw: str) -> str:
        text = str(raw or "")
        if len(text) > width:
            return text[: max(1, width - 1)] + "…"
        return text.ljust(width)

    date_s = str(sub_date or "N/A").strip() or "N/A"
    if len(date_s) > 10:
        date_s = date_s[:10]
    date_col = date_s.ljust(10)

    try:
        price_col = f"{float(price):>8g}"
    except (TypeError, ValueError):
        price_col = f"{str(price if price is not None else 0):>8}"

    if not is_privacy_mode():
        return f"{_pad_name(name)}  {date_col}  {price_col}"
    return f"{_pad_name(PRIVACY_PLACEHOLDER)}  {'[hidden]':<10}  {'[hidden]':>8}"


def model_list_header_line(name_width: int = 28) -> str:
    """Column header matching ``format_model_list_line`` widths."""
    width = max(12, min(int(name_width or 28), 40))
    return f"{'Username'.ljust(width)}  {'Subscribed':<10}  {'Price':>8}"


_EXTRA_REDACTIONS = [
    (re.compile(r"(?i)\bsess=[^\s;\"']+"), "sess={hidden}"),
    (re.compile(r"(?i)\bauth_id=[^\s;\"']+"), "auth_id={hidden}"),
    (re.compile(r"(?i)\bauth_uid[^=\s]*=[^\s;\"']+"), "auth_uid={hidden}"),
    (re.compile(r"(?i)\bx-bc[\"']?\s*[:=]\s*[^\s,\"']+"), "x-bc={hidden}"),
    (re.compile(r"(?i)\"x-bc\"\s*:\s*\"[^\"]+\""), '"x-bc":"{hidden}"'),
    (re.compile(r"(?i)cookie:\s*[^\n]+"), "Cookie: {hidden}"),
    (
        re.compile(
            r"(?i)https?://(?:discord(?:app)?\.com|discord\.com)/api/webhooks/[^\s\"']+"
        ),
        "https://discord.com/api/webhooks/{hidden}",
    ),
    # Common Windows/Unix home path prefixes in logs
    (
        re.compile(r"(?i)(?:[A-Z]:\\|/)Users[/\\][^/\\\s]+"),
        r"{home}",
    ),
    (re.compile(r"(?i)/home/[^/\\\s]+"), "/home/{user}"),
    # Dict / log dumps of usernames
    (
        re.compile(r"(?i)(['\"]username['\"]\s*:\s*['\"])[^'\"]+(['\"])"),
        r"\1{hidden}\2",
    ),
    (
        re.compile(r"(?i)(['\"]model_username['\"]\s*:\s*['\"])[^'\"]+(['\"])"),
        r"\1{hidden}\2",
    ),
    (
        re.compile(r"(?i)\buser_name['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_.-]+"),
        "user_name={hidden}",
    ),
]


def redact_log_message(message: str) -> str:
    """Extra redaction applied to GUI console lines when privacy mode is on."""
    if not is_privacy_mode() or not message:
        return message
    out = redact_status_message(message)
    try:
        from ofscraper.utils.logs.utils.sensitive import getSenstiveDict

        for pattern, replacement in getSenstiveDict().items():
            try:
                out = re.sub(pattern, str(replacement), out)
            except re.error:
                out = out.replace(str(pattern), str(replacement))
    except Exception:
        pass
    for regex, replacement in _EXTRA_REDACTIONS:
        try:
            out = regex.sub(replacement, out)
        except Exception:
            pass
    return out
