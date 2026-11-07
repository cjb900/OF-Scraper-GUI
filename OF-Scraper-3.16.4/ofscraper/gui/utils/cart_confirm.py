"""Confirm before queuing a large download cart (>> Send Downloads)."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QMessageBox, QWidget

log = logging.getLogger("shared")

# Prompt when cart is at least this large (or always if skip is off and count >= threshold).
CART_CONFIRM_THRESHOLD = 25

_session_skip = False


@dataclass
class CartJobSummary:
    total: int = 0
    by_mediatype: dict[str, int] = field(default_factory=dict)
    by_username: dict[str, int] = field(default_factory=dict)

    @property
    def model_count(self) -> int:
        return len(self.by_username)


def reset_session_skip() -> None:
    global _session_skip
    _session_skip = False


def _privacy_name(name: str) -> str:
    try:
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode

        if is_privacy_mode():
            return "[Hidden for Privacy]"
    except Exception:
        pass
    return name


def peek_cart_rows(data_table) -> list[dict]:
    """Return row dicts currently marked ``[added]`` without mutating cart state."""
    rows = []
    try:
        display = getattr(data_table, "_display_data", None) or []
        for rd in display:
            if rd.get("download_cart") == "[added]":
                rows.append(rd)
    except Exception:
        pass
    return rows


def build_cart_summary(rows: list[dict]) -> CartJobSummary:
    by_type: Counter[str] = Counter()
    by_user: Counter[str] = Counter()
    for rd in rows:
        mt = str(
            rd.get("mediatype")
            or rd.get("Mediatype")
            or rd.get("media_type")
            or "Unknown"
        ).strip() or "Unknown"
        user = str(
            rd.get("username") or rd.get("UserName") or "unknown"
        ).strip() or "unknown"
        by_type[mt] += 1
        by_user[user] += 1
    return CartJobSummary(
        total=len(rows),
        by_mediatype=dict(by_type),
        by_username=dict(by_user),
    )


def estimate_cart_eta(summary: CartJobSummary) -> str:
    n = summary.total
    # Rough: images fast, videos slower — use blended band.
    videos = 0
    for key, count in summary.by_mediatype.items():
        if "video" in key.lower():
            videos += count
    images = n - videos
    # ~2s/image, ~20s/video as a coarse guide
    low_sec = max(30, images * 1 + videos * 8)
    high_sec = max(low_sec + 30, images * 3 + videos * 45)
    low_min = max(1, low_sec // 60)
    high_min = max(low_min + 1, (high_sec + 59) // 60)
    if high_min >= 180:
        return f"Rough ETA: ~{low_min}–{high_min} min (possibly several hours)"
    if high_min >= 60:
        return f"Rough ETA: ~{low_min}–{high_min} min (large cart — time varies)"
    return f"Rough ETA: ~{low_min}–{high_min} min (estimate only)"


def should_prompt(summary: CartJobSummary) -> bool:
    global _session_skip
    if summary.total <= 0:
        return False
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        if bool(load_gui_settings().get("skip_cart_confirm")):
            return False
    except Exception:
        pass
    if _session_skip:
        return False
    return summary.total >= CART_CONFIRM_THRESHOLD


def format_cart_html(summary: CartJobSummary) -> str:
    type_parts = [
        f"{k}: {v}" for k, v in sorted(summary.by_mediatype.items(), key=lambda x: (-x[1], x[0]))
    ]
    types_txt = ", ".join(type_parts) if type_parts else "(unknown)"

    users = sorted(summary.by_username.items(), key=lambda x: (-x[1], x[0]))
    if len(users) <= 6:
        users_txt = ", ".join(f"{_privacy_name(u)} ({c})" for u, c in users)
    else:
        head = users[:4]
        users_txt = (
            ", ".join(f"{_privacy_name(u)} ({c})" for u, c in head)
            + f", … +{len(users) - 4} more models"
        )

    return (
        f"<p><b>Items in cart:</b> {summary.total}<br/>"
        f"<b>Models:</b> {summary.model_count}<br/>"
        f"<b>By type:</b> {types_txt}<br/>"
        f"<b>By model:</b> {users_txt or '(none)'}</p>"
        f"<p>{estimate_cart_eta(summary)}</p>"
        "<p>ETA is a rough guide only — actual download time depends on file size, "
        "DRM, and network speed.</p>"
    )


def confirm_cart_downloads(parent: QWidget | None, summary: CartJobSummary) -> bool:
    """Show confirm when the cart is large. Return True to proceed."""
    global _session_skip

    if not should_prompt(summary):
        return True

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle("Confirm downloads")
    msg.setTextFormat(Qt.TextFormat.RichText)
    msg.setText("<b>Queue this download cart?</b>")
    msg.setInformativeText(format_cart_html(summary))
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(QMessageBox.StandardButton.Yes)
    yes = msg.button(QMessageBox.StandardButton.Yes)
    if yes is not None:
        yes.setText("Send Downloads")
    no = msg.button(QMessageBox.StandardButton.No)
    if no is not None:
        no.setText("Cancel")

    skip_cb = QCheckBox("Don't ask again for large carts")
    msg.setCheckBox(skip_cb)

    result = msg.exec()
    if result != QMessageBox.StandardButton.Yes:
        log.info("[GUI] Cart download confirm declined")
        return False

    if skip_cb.isChecked():
        _session_skip = True
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            s = load_gui_settings()
            s["skip_cart_confirm"] = True
            save_gui_settings(s)
            log.info("[GUI] Cart confirm suppressed (gui_settings.skip_cart_confirm)")
        except Exception as e:
            log.debug(f"[GUI] Could not persist skip_cart_confirm: {e}")

    return True
