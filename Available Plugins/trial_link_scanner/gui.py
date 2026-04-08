"""Settings and log viewer page for the Trial Link Scanner plugin."""

import json
import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TrialLinkScannerPage(QWidget):
    """Settings page shown in the sidebar when the plugin is loaded."""

    def __init__(self, plugin, main_window):
        super().__init__()
        self._plugin = plugin
        self._main_window = main_window
        self._build_ui()
        self._refresh_log()

        # Auto-refresh log every 10 s while the page is open
        self._timer = QTimer(self)
        self._timer.setInterval(10_000)
        self._timer.timeout.connect(self._refresh_log)
        self._timer.start()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Title
        title = QLabel("Trial Link Scanner")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Automatically detects OnlyFans trial links in direct message text during scraping."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #aaa; font-size: 12px;")
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444;")
        layout.addWidget(sep)

        # ── Enable toggle ─────────────────────────────────────────────────
        layout.addWidget(self._section_label("Plugin Status"))

        enable_row = QHBoxLayout()
        self._enable_btn = QPushButton()
        self._enable_btn.setCheckable(True)
        self._enable_btn.setFixedWidth(110)
        self._enable_btn.clicked.connect(self._toggle_enabled)
        enable_row.addWidget(self._enable_btn)
        enable_row.addStretch()
        layout.addLayout(enable_row)

        # ── Settings group ────────────────────────────────────────────────
        settings_box = QGroupBox("Settings")
        settings_layout = QVBoxLayout(settings_box)
        settings_layout.setSpacing(10)

        # POST_MODE
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Post mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["link — URL only", "full — full message text"])
        self._mode_combo.currentIndexChanged.connect(self._save_settings)
        mode_row.addWidget(self._mode_combo)
        mode_row.addStretch()
        settings_layout.addLayout(mode_row)

        mode_hint = QLabel("'link' sends only the trial URL. 'full' includes the entire message text.")
        mode_hint.setWordWrap(True)
        mode_hint.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(mode_hint)

        # POST_TIMING
        timing_row = QHBoxLayout()
        timing_row.addWidget(QLabel("Post timing:"))
        self._timing_combo = QComboBox()
        self._timing_combo.addItems(["immediate — one message per link", "summary — one message at end of scrape"])
        self._timing_combo.currentIndexChanged.connect(self._save_settings)
        timing_row.addWidget(self._timing_combo)
        timing_row.addStretch()
        settings_layout.addLayout(timing_row)

        # DISCORD_ENABLED
        discord_row = QHBoxLayout()
        discord_row.addWidget(QLabel("Discord:"))
        self._discord_combo = QComboBox()
        self._discord_combo.addItems(["enabled", "disabled (log only)"])
        self._discord_combo.currentIndexChanged.connect(self._save_settings)
        discord_row.addWidget(self._discord_combo)
        discord_row.addStretch()
        settings_layout.addLayout(discord_row)

        discord_hint = QLabel(
            "Requires a Discord webhook in your ofscraper config. "
            "Trial links are always written to the logs/ folder regardless."
        )
        discord_hint.setWordWrap(True)
        discord_hint.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(discord_hint)

        layout.addWidget(settings_box)

        # ── Log viewer ────────────────────────────────────────────────────
        log_header = QHBoxLayout()
        log_header.addWidget(self._section_label("Recent Finds (today's log)"))
        log_header.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(80)
        refresh_btn.clicked.connect(self._refresh_log)
        log_header.addWidget(refresh_btn)
        layout.addLayout(log_header)

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText("No trial links found yet.")
        self._log_view.setMinimumHeight(160)
        self._log_view.setStyleSheet("font-family: monospace; font-size: 11px; background: #1a1a1a;")
        layout.addWidget(self._log_view)

        layout.addStretch()

        # Apply current state to controls
        self._sync_controls_to_settings()

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        return lbl

    # ── Control sync ──────────────────────────────────────────────────────

    def _sync_controls_to_settings(self):
        s = self._plugin._settings
        enabled = bool(s.get("ENABLED", False))
        self._enable_btn.setChecked(enabled)
        self._enable_btn.setText("Enabled" if enabled else "Disabled")
        self._enable_btn.setStyleSheet(
            "background: #2d7a2d; color: white;" if enabled
            else "background: #555; color: #ccc;"
        )

        for combo in (self._mode_combo, self._timing_combo, self._discord_combo):
            combo.blockSignals(True)

        mode = s.get("POST_MODE", "link")
        self._mode_combo.setCurrentIndex(0 if mode == "link" else 1)

        timing = s.get("POST_TIMING", "immediate")
        self._timing_combo.setCurrentIndex(0 if timing == "immediate" else 1)

        discord_on = bool(s.get("DISCORD_ENABLED", True))
        self._discord_combo.setCurrentIndex(0 if discord_on else 1)

        for combo in (self._mode_combo, self._timing_combo, self._discord_combo):
            combo.blockSignals(False)

    # ── Actions ───────────────────────────────────────────────────────────

    def _toggle_enabled(self):
        new_state = self._enable_btn.isChecked()
        self._plugin._settings["ENABLED"] = new_state
        self._enable_btn.setText("Enabled" if new_state else "Disabled")
        self._enable_btn.setStyleSheet(
            "background: #2d7a2d; color: white;" if new_state
            else "background: #555; color: #ccc;"
        )
        self._save_settings()

    def _save_settings(self):
        mode = "link" if self._mode_combo.currentIndex() == 0 else "full"
        timing = "immediate" if self._timing_combo.currentIndex() == 0 else "summary"
        discord_on = self._discord_combo.currentIndex() == 0

        self._plugin._settings["POST_MODE"] = mode
        self._plugin._settings["POST_TIMING"] = timing
        self._plugin._settings["DISCORD_ENABLED"] = discord_on

        settings_path = Path(self._plugin.plugin_dir) / "settings.json"
        try:
            # Preserve any existing keys (e.g. _comments)
            existing = {}
            if settings_path.exists():
                with open(settings_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing["ENABLED"] = self._plugin._settings["ENABLED"]
            existing["POST_MODE"] = mode
            existing["POST_TIMING"] = timing
            existing["DISCORD_ENABLED"] = discord_on
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            self._plugin.log.warning(f"[TrialLinkScanner] Could not save settings: {e}")

    def _refresh_log(self):
        from datetime import datetime
        logs_dir = Path(self._plugin.plugin_dir) / "logs"
        date_str = datetime.now().strftime("%Y-%m-%d")
        log_path = logs_dir / f"trial_links_{date_str}.log"
        if log_path.exists():
            try:
                text = log_path.read_text(encoding="utf-8")
                if text.strip():
                    self._log_view.setPlainText(text)
                    # Scroll to bottom
                    sb = self._log_view.verticalScrollBar()
                    sb.setValue(sb.maximum())
                    return
            except Exception:
                pass
        self._log_view.setPlainText("No trial links found today.")
