"""One-shot first-run welcome dialog (Getting started / plugins)."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from ofscraper.gui.utils.ui_scale import apply_font, scale_px
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")


def plugins_dir() -> Path | None:
    try:
        from ofscraper.utils.paths.common import get_config_home

        return get_config_home() / "plugins"
    except Exception:
        return None


def mark_first_run_welcome_seen() -> None:
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

        settings = load_gui_settings()
        if settings.get("first_run_welcome_seen"):
            return
        settings["first_run_welcome_seen"] = True
        save_gui_settings(settings)
    except Exception as e:
        log.debug(f"[GUI] Could not save first_run_welcome_seen: {e}")


def should_show_first_run_welcome() -> bool:
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        return not bool(load_gui_settings().get("first_run_welcome_seen"))
    except Exception:
        return False


class WelcomeDialog(QDialog):
    """Non-modal first-run tips; open via ``show_welcome_dialog``."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to OF-Scraper GUI")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(480)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("Welcome")
        apply_font(title, "Segoe UI", 18, QFont.Weight.Bold)
        title.setProperty("heading", True)
        layout.addWidget(title)

        body = QLabel(
            "You launched the graphical UI with <b>ofscraper --gui</b>."
            "<br/><br/>"
            "<b>Quick start:</b>"
            "<ol>"
            "<li><b>Authentication</b> — save cookies / browser login</li>"
            "<li><b>Configuration</b> — save location, FFmpeg, CDM keys</li>"
            "<li><b>Scraper</b> — pick action → areas → models → Start Scraping</li>"
            "</ol>"
            "Help / README covers <code>--gui</code>, the GUI patch, and plugins. "
            "Plugins live in your config folder’s <code>plugins/</code> directory."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(body)

        plugins = plugins_dir()
        if plugins is not None:
            path_lbl = QLabel(f"Plugins folder: {plugins}")
            path_lbl.setWordWrap(True)
            path_lbl.setProperty("muted", True)
            path_lbl.setStyleSheet(f"color: {c('muted')}; font-size: {scale_px(11)}px;")
            path_lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(path_lbl)

        tip = QLabel(
            "This tip is shown once at first launch. Reopen it anytime from "
            "Help / README → Show Welcome."
        )
        tip.setWordWrap(True)
        tip.setProperty("muted", True)
        tip.setStyleSheet(f"color: {c('muted')}; font-size: {scale_px(11)}px;")
        layout.addWidget(tip)

        btns = QHBoxLayout()
        btns.addStretch()
        if plugins is not None:
            open_plugins = StyledButton("Open plugins folder")
            open_plugins.clicked.connect(self._open_plugins_folder)
            btns.addWidget(open_plugins)
        help_btn = StyledButton("Open Getting started", primary=True)
        help_btn.clicked.connect(self._open_getting_started)
        btns.addWidget(help_btn)
        close_btn = StyledButton("Got it")
        close_btn.clicked.connect(self._on_close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _open_plugins_folder(self):
        path = plugins_dir()
        if path is None:
            return
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.debug(f"[GUI] Could not create plugins dir: {e}")
        try:
            from PyQt6.QtGui import QDesktopServices
            from PyQt6.QtCore import QUrl

            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        except Exception:
            try:
                os.startfile(str(path))  # type: ignore[attr-defined]
            except Exception as e:
                log.debug(f"[GUI] Could not open plugins folder: {e}")

    def _open_getting_started(self):
        try:
            from ofscraper.gui.signals import app_signals

            app_signals.navigate_to_page.emit("help")
            app_signals.help_anchor_requested.emit("getting-started")
        except Exception:
            pass
        mark_first_run_welcome_seen()
        self.close()

    def _on_close(self):
        mark_first_run_welcome_seen()
        self.close()

    def closeEvent(self, event):
        mark_first_run_welcome_seen()
        super().closeEvent(event)


def show_welcome_dialog(parent=None) -> WelcomeDialog:
    """Show the welcome dialog, or raise the existing one."""
    from ofscraper.gui.utils.window_registry import show_or_raise

    def _factory():
        return WelcomeDialog(parent)

    return show_or_raise("welcome", _factory)  # type: ignore[return-value]
