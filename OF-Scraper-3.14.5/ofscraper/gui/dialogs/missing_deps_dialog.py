import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from ofscraper.gui.styles import c

log = logging.getLogger("shared")


class MissingDepsDialog(QDialog):
    """Single popup that warns about missing ffmpeg / manual CDM key paths."""

    def __init__(
        self,
        *,
        missing_ffmpeg: bool,
        missing_manual_cdm: bool,
        key_mode: str = "cdrm",
        on_open_ffmpeg=None,
        on_open_cdm=None,
        on_open_drm=None,
        parent=None,
    ):
        super().__init__(parent)
        self._missing_ffmpeg = bool(missing_ffmpeg)
        self._missing_manual_cdm = bool(missing_manual_cdm)
        self._key_mode = str(key_mode).lower().strip() or "cdrm"
        self._on_open_ffmpeg = on_open_ffmpeg
        self._on_open_cdm = on_open_cdm
        self._on_open_drm = on_open_drm

        self.setWindowTitle("Missing configuration paths")
        self.setWindowModality(Qt.WindowModality.NonModal)
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
        viewer.setStyleSheet(
            f"QTextBrowser {{ background-color: {c('base')}; color: {c('text')};"
            f" border: 1px solid {c('surface1')}; }}"
        )
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
            self.drm_btn = QPushButton("Generate DRM Keys")
            self.drm_btn.clicked.connect(self._open_drm)
            actions_row.addWidget(self.drm_btn)

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

        css = (
            f"<style>"
            f"body {{ color: {c('text')}; }}"
            f" a {{ color: {c('blue')}; }}"
            f" code {{ background-color: {c('surface1')}; color: {c('text')};"
            f" padding: 1px 4px; border-radius: 3px; }}"
            f"</style>"
        )

        if self._missing_ffmpeg:
            parts.append(
                """
                <h3>FFmpeg</h3>
                <p><b>Missing file path for FFmpeg in your config.</b> This is needed to merge DRM protected audio and video files.</p>
                <p>Use version <b>7.1.1</b> — download:
                <a href="https://www.videohelp.com/download/ffmpeg-7.1.1-full_build.7z?r=GvPKbvspT">ffmpeg-7.1.1-full_build.7z</a>. (Link for Windows systems only)</p>
                <p>Extract the downloaded 7z file and provide the full file path to <code>ffmpeg.exe</code></p>
                """
            )

        if self._missing_manual_cdm:
            if self._key_mode == "manual":
                severity = (
                    "<p><b>Key Mode is set to <code>manual</code> but the DRM key file paths "
                    "are missing or invalid.</b> OF-Scraper cannot decrypt DRM-protected content "
                    "until valid paths are configured.</p>"
                )
            else:
                severity = (
                    f"<p>Your current Key Mode is <code>{self._key_mode}</code>. "
                    "Manual Widevine keys (<code>client_id.bin</code> / <code>private_key.pem</code>) "
                    "are not configured. Setting up manual keys is recommended as a reliable "
                    "fallback if the current key service is unavailable.</p>"
                )
            parts.append(
                f"""
                <h3>Manual DRM keys not configured</h3>
                {severity}
                <ul>
                  <li><b>Already have keys?</b> Click <i>Open Config → CDM</i>
                  to enter the paths to your <code>client_id.bin</code> and
                  <code>private_key.pem</code> files, then set Key Mode to
                  <code>manual</code>.</li>
                  <li><b>Don't have keys yet?</b> Click <i>Generate DRM Keys</i> to use the
                  built-in extraction tool to create them automatically.</li>
                </ul>
                """
            )

        if not parts:
            parts.append("<p>No missing settings detected.</p>")

        return css + "\n" + "\n<hr/>\n".join(parts)

    def _open_drm(self):
        if not callable(self._on_open_drm):
            return
        self._on_open_drm()
        self.accept()

    def _open_ffmpeg(self):
        if callable(self._on_open_ffmpeg):
            self._on_open_ffmpeg()

    def _open_cdm(self):
        if callable(self._on_open_cdm):
            self._on_open_cdm()
