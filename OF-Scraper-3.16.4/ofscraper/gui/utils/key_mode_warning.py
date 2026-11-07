"""Remote DRM key-mode warnings for the Pika GUI.

Remote modes (cdrm / cdrm2 / keydb) post only pssh + license URL to a
third-party helper — never session cookies / sign / x-bc. Prefer local
``manual`` CDM keys (more reliable for OnlyFans DRM).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QMessageBox, QWidget

log = logging.getLogger("shared")

REMOTE_KEY_MODES = frozenset({"cdrm", "cdrm2", "keydb"})

# Session-only: skip scrape-time warning after user checks "Don't ask again".
_session_skip_scrape_warning = False
# One-shot: table Start confirms first; workflow._start_scraping must not re-prompt.
_scrape_warning_ack = False


def normalize_key_mode(mode) -> str:
    return str(mode or "manual").lower().strip() or "manual"


def is_remote_key_mode(mode) -> bool:
    return normalize_key_mode(mode) in REMOTE_KEY_MODES


def get_configured_key_mode() -> str:
    """Read key-mode-default from config.json (falls back to manual)."""
    try:
        from ofscraper.utils.config.config import read_config

        cfg = read_config(update=False) or {}
        cdm = cfg.get("cdm_options") if isinstance(cfg.get("cdm_options"), dict) else {}
        return normalize_key_mode(cdm.get("key-mode-default"))
    except Exception:
        return "manual"


def reset_session_skip() -> None:
    """Clear the session skip flag (e.g. after switching back to remote mode)."""
    global _session_skip_scrape_warning, _scrape_warning_ack
    _session_skip_scrape_warning = False
    _scrape_warning_ack = False


def _warning_body(key_mode: str) -> str:
    mode = normalize_key_mode(key_mode)
    return (
        f"Key Mode is set to <b><code>{mode}</code></b>.\n\n"
        "Remote helpers send only <b>pssh</b> and the <b>license URL</b> to a "
        "third-party service. Session cookies and signed auth headers stay on "
        "this machine.\n\n"
        "OnlyFans DRM often still needs those cookies on the license request, "
        "so remote modes may fail to decrypt.\n\n"
        "<b>Recommended:</b> switch Key Mode to <code>manual</code> and use "
        "local CDM files (<code>client_id.bin</code> / <code>private_key.pem</code>) "
        "from Configuration → CDM, or generate them via <b>DRM Key Creation</b>.\n\n"
        "Continue with the remote key mode anyway?"
    )


def confirm_remote_key_mode(
    parent: QWidget | None,
    key_mode: str | None = None,
    *,
    context: str = "scrape",
    allow_session_skip: bool = True,
) -> bool:
    """Show a warning if *key_mode* is remote. Return True to proceed.

    ``context``:
      - ``\"scrape\"`` — before starting downloads / scrape
      - ``\"config\"`` — before saving Configuration with a remote mode
    """
    global _session_skip_scrape_warning, _scrape_warning_ack

    mode = normalize_key_mode(key_mode if key_mode is not None else get_configured_key_mode())
    if not is_remote_key_mode(mode):
        return True

    if context == "scrape" and allow_session_skip and _session_skip_scrape_warning:
        return True

    # Table Start already confirmed; workflow start must not ask twice.
    if context == "scrape" and _scrape_warning_ack:
        _scrape_warning_ack = False
        return True

    title = "Remote DRM key mode"
    if context == "config":
        title = "Save remote DRM key mode?"

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Warning)
    msg.setWindowTitle(title)
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setText(_warning_body(mode))
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(QMessageBox.StandardButton.No)

    skip_cb = None
    if context == "scrape" and allow_session_skip:
        skip_cb = QCheckBox("Don't ask again this session")
        msg.setCheckBox(skip_cb)

    result = msg.exec()
    if result != QMessageBox.StandardButton.Yes:
        log.info(f"[GUI] Remote key mode ({mode}) declined (context={context})")
        _scrape_warning_ack = False
        return False

    if skip_cb is not None and skip_cb.isChecked():
        _session_skip_scrape_warning = True
        log.info("[GUI] Remote key-mode scrape warning suppressed for this session")

    if context == "scrape":
        # Allow the immediate workflow._start_scraping call to proceed without
        # a second identical dialog.
        _scrape_warning_ack = True

    return True
