import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")


class BinaryDialog(QWidget):
    """FFmpeg path configuration — replaces the binary prompt."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QLabel("FFmpeg Configuration")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(header)

        info = QLabel(
            "FFmpeg is required for merging audio/video streams and DRM content. "
            "Set the path to your ffmpeg binary."
        )
        info.setWordWrap(True)
        info.setProperty("muted", True)
        layout.addWidget(info)

        path_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Path to ffmpeg binary...")
        self.path_input.setClearButtonEnabled(True)
        path_layout.addWidget(self.path_input)

        browse_btn = StyledButton("Browse")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)

        layout.addLayout(path_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = StyledButton("Save", primary=True)
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()
        self._load()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select FFmpeg Binary", "", "All Files (*)"
        )
        if path:
            self.path_input.setText(path)

    def _load(self):
        try:
            from ofscraper.utils.config.config import read_config
            config = read_config(update=False) or {}
            binary = config.get("binary_options", {})
            self.path_input.setText(binary.get("ffmpeg", ""))
        except Exception:
            pass

    def _save(self):
        try:
            from ofscraper.utils.config.config import read_config
            from ofscraper.utils.config.file import write_config

            config = read_config(update=False) or {}
            if "binary_options" not in config:
                config["binary_options"] = {}
            config["binary_options"]["ffmpeg"] = self.path_input.text().strip()
            write_config(config)
            app_signals.status_message.emit("FFmpeg path saved")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")
