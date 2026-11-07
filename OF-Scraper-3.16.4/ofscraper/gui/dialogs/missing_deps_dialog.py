"""Missing FFmpeg / manual CDM path notice.

Kept intentionally simple (no QTextBrowser): labels + a plain download button.
Older QTextBrowser + show()/finished paths hard-crashed the whole GUI on Windows
when Close was clicked from the Areas page. Navigation happens *after* exec()
returns (never while the modal dialog is still alive).
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c

log = logging.getLogger("shared")

_FFMPEG_URL = (
    "https://www.videohelp.com/download/ffmpeg-7.1.1-full_build.7z?r=GvPKbvspT"
)


class MissingDepsDialog(QDialog):
    """Single popup that warns about missing ffmpeg / manual CDM key paths."""

    def __init__(
        self,
        *,
        missing_ffmpeg: bool,
        missing_manual_cdm: bool,
        key_mode: str = "manual",
        parent=None,
    ):
        super().__init__(parent)
        self._missing_ffmpeg = bool(missing_ffmpeg)
        self._missing_manual_cdm = bool(missing_manual_cdm)
        self._key_mode = str(key_mode).lower().strip() or "manual"
        # "ffmpeg" | "cdm" | "drm" | None — read after exec() returns
        self.chosen_action = None

        self.setWindowTitle("Missing configuration paths")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(640)
        self.setMinimumHeight(360)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Missing required file paths in config.json")
        apply_font(title, "Segoe UI", 13, QFont.Weight.Bold)
        layout.addWidget(title)

        subtitle = QLabel(
            "Some features require external binaries/keys. Add the missing paths below."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 4, 0)
        body_layout.setSpacing(12)

        if self._missing_ffmpeg:
            body_layout.addWidget(self._section_ffmpeg())
        if self._missing_manual_cdm:
            body_layout.addWidget(self._section_cdm())
        if not self._missing_ffmpeg and not self._missing_manual_cdm:
            body_layout.addWidget(QLabel("No missing settings detected."))
        body_layout.addStretch(1)

        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        actions_row = QHBoxLayout()
        actions_row.addStretch()

        if self._missing_ffmpeg:
            ffmpeg_btn = QPushButton("Open Config → Download (FFmpeg)")
            ffmpeg_btn.clicked.connect(lambda: self._finish_with("ffmpeg"))
            actions_row.addWidget(ffmpeg_btn)

        if self._missing_manual_cdm:
            drm_btn = QPushButton("Generate DRM Keys")
            drm_btn.clicked.connect(lambda: self._finish_with("drm"))
            actions_row.addWidget(drm_btn)
            cdm_btn = QPushButton("Open Config → CDM (Manual keys)")
            cdm_btn.clicked.connect(lambda: self._finish_with("cdm"))
            actions_row.addWidget(cdm_btn)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(lambda: self._finish_with(None))
        actions_row.addWidget(close_btn)
        layout.addLayout(actions_row)

    def _section_ffmpeg(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        h = QLabel("FFmpeg")
        apply_font(h, "Segoe UI", 11, QFont.Weight.Bold)
        v.addWidget(h)

        # Rich-text QLabel + linkActivated (not QTextBrowser). Inline style on
        # <a> is required — Qt ignores stylesheet "QLabel a { color }" for links.
        link_color = c("blue") or "#89b4fa"
        msg = QLabel(
            "<p><b>Missing file path for FFmpeg in your config.</b> "
            "This is needed to merge DRM protected audio and video files.</p>"
            "<p>Use version <b>7.1.1</b> — download: "
            f'<a href="{_FFMPEG_URL}" style="color: {link_color}; '
            f'text-decoration: underline;">ffmpeg-7.1.1-full_build.7z</a>. '
            "(Link for Windows systems only)</p>"
            "<p>Extract the downloaded 7z file and provide the full file path "
            "to <code>ffmpeg.exe</code> under Configuration → Download.</p>"
        )
        msg.setWordWrap(True)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setOpenExternalLinks(False)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        msg.linkActivated.connect(self._open_url)
        msg.setStyleSheet(f"QLabel {{ color: {c('text')}; }}")
        v.addWidget(msg)
        return box

    def _section_cdm(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        h = QLabel("Manual DRM keys not configured")
        apply_font(h, "Segoe UI", 11, QFont.Weight.Bold)
        v.addWidget(h)

        if self._key_mode == "manual":
            body = (
                "Key Mode is set to manual but the DRM key file paths are missing "
                "or invalid. OF-Scraper cannot decrypt DRM-protected content until "
                "valid paths are configured.\n\n"
                "Already have keys? Open Config → CDM and set client_id.bin / "
                "private_key.pem, with Key Mode = manual.\n\n"
                "Don't have keys yet? Use Generate DRM Keys to create them."
            )
        else:
            body = (
                f"Your current Key Mode is {self._key_mode}. Manual Widevine keys "
                "(client_id.bin / private_key.pem) are not configured. Setting up "
                "manual keys is recommended as a fallback if the current key "
                "service is unavailable."
            )
        msg = QLabel(body)
        msg.setWordWrap(True)
        v.addWidget(msg)
        return box

    def _open_url(self, url: str):
        try:
            QDesktopServices.openUrl(QUrl(str(url)))
        except Exception as e:
            log.debug(f"[GUI] Open URL failed: {e}")

    def _finish_with(self, action):
        """Close the dialog; navigation (if any) runs after exec() returns."""
        self.chosen_action = action
        try:
            code = (
                QDialog.DialogCode.Accepted
                if action
                else QDialog.DialogCode.Rejected
            )
            self.done(int(code))
        except Exception:
            try:
                self.hide()
            except Exception:
                pass
