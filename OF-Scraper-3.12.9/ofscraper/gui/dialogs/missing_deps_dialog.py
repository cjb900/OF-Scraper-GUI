import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

log = logging.getLogger("shared")


class MissingDepsDialog(QDialog):
    """Single popup that warns about missing ffmpeg / manual CDM key paths."""

    def __init__(
        self,
        *,
        missing_ffmpeg: bool,
        missing_manual_cdm: bool,
        on_open_ffmpeg=None,
        on_open_cdm=None,
        parent=None,
    ):
        super().__init__(parent)
        self._missing_ffmpeg = bool(missing_ffmpeg)
        self._missing_manual_cdm = bool(missing_manual_cdm)
        self._on_open_ffmpeg = on_open_ffmpeg
        self._on_open_cdm = on_open_cdm

        self.setWindowTitle("Missing configuration paths")
        self.setModal(True)
        self.setMinimumWidth(720)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Missing required file paths in `config.json`")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel(
            "Some features require external binaries/keys. Add the missing paths below."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        layout.addWidget(subtitle)

        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(True)
        viewer.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        viewer.setMinimumHeight(220)
        viewer.setHtml(self._build_html())
        layout.addWidget(viewer, stretch=1)

        # Action buttons (conditional)
        actions_row = QHBoxLayout()
        actions_row.addStretch()

        if self._missing_ffmpeg:
            self.ffmpeg_btn = QPushButton("Open Config → Download (FFmpeg)")
            self.ffmpeg_btn.clicked.connect(self._open_ffmpeg)
            actions_row.addWidget(self.ffmpeg_btn)

        if self._missing_manual_cdm:
            self.cdm_btn = QPushButton("Open Config → CDM (Manual keys)")
            self.cdm_btn.clicked.connect(self._open_cdm)
            actions_row.addWidget(self.cdm_btn)

        layout.addLayout(actions_row)

        # Close button
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_html(self) -> str:
        parts = []

        if self._missing_ffmpeg:
            parts.append(
                """
                <h3>FFmpeg</h3>
                <p><b>Missing file path for FFmpeg in your config.</b> This is needed to merge DRM protected audio and video files.</p>
                <p>Use version <b>7.1.1 or lower</b> from
                <a href="https://www.gyan.dev/ffmpeg/builds">https://www.gyan.dev/ffmpeg/builds</a>.</p>
                """
            )

        if self._missing_manual_cdm:
            parts.append(
                """
                <h3>Manual CDM keys</h3>
                <p><b>Missing the file path for manual DRM keys.</b> These are needed to be able to scrape DRM protected content.</p>
                <p>Guide:
                <a href="https://github.com/FoxRefire/wvg/wiki/How-to-dump-CDM-key-pair-from-AVD">
                https://github.com/FoxRefire/wvg/wiki/How-to-dump-CDM-key-pair-from-AVD</a></p>
                """
            )

        if not parts:
            parts.append("<p>No missing settings detected.</p>")

        return "\n<hr/>\n".join(parts)

    def _confirm_jump(self, title: str, msg: str) -> bool:
        try:
            reply = QMessageBox.question(
                self,
                title,
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            return reply == QMessageBox.StandardButton.Yes
        except Exception:
            return True

    def _open_ffmpeg(self):
        if not callable(self._on_open_ffmpeg):
            return
        if self._confirm_jump(
            "Open Configuration?",
            "Open Configuration to the Download tab to enter the FFmpeg file path?",
        ):
            self._on_open_ffmpeg()

    def _open_cdm(self):
        if not callable(self._on_open_cdm):
            return
        if self._confirm_jump(
            "Open Configuration?",
            "Open Configuration to the CDM tab to enter the manual DRM key paths?",
        ):
            self._on_open_cdm()

