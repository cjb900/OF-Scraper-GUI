"""GUI for experimental Agora live capture plugin."""

from __future__ import annotations

import logging
from pathlib import Path
import datetime

from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QSpinBox,
    QLineEdit,
    QFileDialog,
    QGroupBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPlainTextEdit,
    QSplitter,
    QSizePolicy,
    QPushButton,
)

from ofscraper.gui.styles import c, is_dark_theme
from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton
from ofscraper.utils.paths.common import get_save_location

log = logging.getLogger("shared")

try:
    from .agora_recorder import sdk_available
    from .capture_backend import (
        backend_label,
        find_playwright_live_plugin,
        host_os,
        os_capture_summary,
        preferred_capture_backend,
        set_force_backend,
    )
    from .sdk_install import describe_install_plan
except ImportError:
    from agora_recorder import sdk_available  # type: ignore
    from capture_backend import (  # type: ignore
        backend_label,
        find_playwright_live_plugin,
        host_os,
        os_capture_summary,
        preferred_capture_backend,
        set_force_backend,
    )
    from sdk_install import describe_install_plan  # type: ignore


class AgoraLiveTab(QWidget):
    def __init__(self, main_window, plugin):
        super().__init__(main_window)
        self.main_window = main_window
        self.plugin = plugin
        self.plugin.gui = self
        self._privacy_actual_save = ""
        self._backend = preferred_capture_backend()
        self._os = host_os()
        self._setup_ui()
        self._apply_theme(is_dark_theme())
        app_signals.theme_changed.connect(self._apply_theme)
        app_signals.privacy_mode_changed.connect(self._on_privacy_mode_changed)
        self._apply_privacy_to_save_field()
        self._apply_os_mode()

        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._tick_recording_timers)
        self._duration_timer.start()

    def _apply_os_mode(self):
        """Show/hide controls for Playwright vs experimental Agora."""
        self._backend = preferred_capture_backend()
        agora = self._backend == "agora"
        playwright = self._backend == "playwright"

        self.os_banner.setText(os_capture_summary())
        self.subtitle_label.setText(
            f"{host_os().title()} · capture via {backend_label(self._backend)}"
        )
        self.enable_check.setText(
            f"Enable Auto-Capture ({'Agora' if agora else 'Playwright'})"
        )
        self.capture_btn.setText(
            "Capture selected (Agora join)"
            if agora
            else "Capture selected (Playwright)"
        )
        self.capture_btn.setToolTip(
            "Fetch creds then native Agora RTC join/record "
            "(falls back to Playwright if OF rejects the join)."
            if agora
            else "Starts Playwright capture via Live Stream Monitor (must be loaded)."
        )

        # SDK install panel: show on Linux/macOS even when Playwright is default
        show_sdk = host_os() in ("linux", "darwin")
        self.sdk_box.setVisible(show_sdk)
        if hasattr(self, "force_agora_check"):
            self.force_agora_check.setVisible(show_sdk)
        if hasattr(self, "headless_check"):
            self.headless_check.setVisible(True)
        if hasattr(self, "pw_status_label"):
            self.pw_status_label.setVisible(True)
            pw = find_playwright_live_plugin()
            if pw is None:
                self.pw_status_label.setText(
                    "🟠 Live Stream Monitor not loaded — enable it on the Plugins "
                    "page for Playwright capture."
                )
            else:
                self.pw_status_label.setText(
                    "🟢 Live Stream Monitor loaded — Playwright capture ready."
                )
        if show_sdk:
            self._refresh_sdk_status()

    def _on_force_agora_toggled(self, checked: bool):
        try:
            set_force_backend("agora" if checked else "playwright")
        except Exception as e:
            self.append_log(f"[System] Could not set backend: {e}")
            return
        self._backend = preferred_capture_backend()
        self._apply_os_mode()
        self.append_log(
            f"[System] Capture backend set to {backend_label(self._backend)}"
        )

    def _refresh_sdk_status(self):
        ok, detail = sdk_available()
        try:
            method, cmd, plan = describe_install_plan()
            extra = f"\nDetected: {method} — {plan}\nCommand: {' '.join(cmd)}"
        except Exception:
            extra = ""
        self.sdk_status_label.setText(("🟢 " if ok else "🟠 ") + detail + extra)
        self.install_sdk_btn.setEnabled(True)
        self.install_sdk_btn.setText(
            "Reinstall Agora SDK" if ok else "Install Agora SDK"
        )

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 12, 20, 16)
        main_layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("📡 Live Stream Capture (experiment)")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setProperty("heading", True)
        header.addWidget(title)
        self.subtitle_label = QLabel("Detecting OS…")
        self.subtitle_label.setProperty("subheading", True)
        header.addWidget(self.subtitle_label, alignment=Qt.AlignmentFlag.AlignBottom)
        header.addStretch()
        main_layout.addLayout(header)

        self.os_banner = QLabel("")
        self.os_banner.setWordWrap(True)
        self.os_banner.setProperty("subheading", True)
        main_layout.addWidget(self.os_banner)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 10, 0)

        opts = QGroupBox("Monitor Options")
        opts_l = QVBoxLayout(opts)
        self.enable_check = QCheckBox("Enable Auto-Capture")
        self.enable_check.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.enable_check.toggled.connect(self._on_toggle_monitor)
        opts_l.addWidget(self.enable_check)

        self.headless_check = QCheckBox("Hide Playwright capture window (off-screen)")
        self.headless_check.setChecked(True)
        self.headless_check.setToolTip(
            "Passed to Live Stream Monitor when capturing. "
            "True Playwright headless is not used (OF drops the session)."
        )
        opts_l.addWidget(self.headless_check)

        self.force_agora_check = QCheckBox(
            "Experimental: try native Agora RTC first (usually rejected by OF)"
        )
        self.force_agora_check.setChecked(False)
        self.force_agora_check.setToolTip(
            "OF's Agora edge returns CONNECTION_CHANGED_REJECTED_BY_SERVER "
            "(reason 10) for agora_python_server_sdk joins. Leave unchecked "
            "to use Playwright MediaRecorder (recommended on Linux too)."
        )
        self.force_agora_check.toggled.connect(self._on_force_agora_toggled)
        opts_l.addWidget(self.force_agora_check)

        self.pw_status_label = QLabel("")
        self.pw_status_label.setWordWrap(True)
        opts_l.addWidget(self.pw_status_label)

        row = QHBoxLayout()
        row.addWidget(QLabel("Poll Interval (seconds):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 3600)
        self.interval_spin.setValue(60)
        self.interval_spin.setFixedWidth(80)
        row.addWidget(self.interval_spin)
        row.addStretch()
        opts_l.addLayout(row)

        opts_l.addWidget(QLabel("Capture Directory:"))
        save_row = QHBoxLayout()
        self.save_input = QLineEdit()
        try:
            from ofscraper.utils.config.path_norm import normalize_windows_path

            initial = normalize_windows_path(get_save_location()) or get_save_location()
        except Exception:
            try:
                initial = get_save_location()
            except Exception:
                initial = ""
        self._privacy_actual_save = initial or ""
        self.save_input.setText(initial or "")
        self.browse_btn = StyledButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse)
        save_row.addWidget(self.save_input)
        save_row.addWidget(self.browse_btn)
        opts_l.addLayout(save_row)

        self.fetch_btn = StyledButton("Fetch Agora creds (selected)", primary=True)
        self.fetch_btn.setToolTip(
            "Calls OF /streams/active + /streams/active/url and saves a redacted "
            "summary. Works on all OS (API-only)."
        )
        self.fetch_btn.clicked.connect(self._on_fetch_selected)
        opts_l.addWidget(self.fetch_btn)

        self.capture_btn = StyledButton("Capture selected")
        self.capture_btn.clicked.connect(self._on_capture_selected)
        opts_l.addWidget(self.capture_btn)

        self.stop_selected_btn = StyledButton("Stop selected capture")
        self.stop_selected_btn.setToolTip(
            "Stop the capture for the selected creator (Agora or Playwright)."
        )
        self.stop_selected_btn.clicked.connect(self._on_stop_selected)
        opts_l.addWidget(self.stop_selected_btn)

        self.stop_all_btn = StyledButton("Stop all captures")
        self.stop_all_btn.setToolTip(
            "Stop every active live capture without disabling the monitor poller."
        )
        self.stop_all_btn.clicked.connect(self._on_stop_all)
        opts_l.addWidget(self.stop_all_btn)

        self.open_attempts_btn = StyledButton("Open attempts folder…")
        self.open_attempts_btn.clicked.connect(self._on_open_attempts)
        opts_l.addWidget(self.open_attempts_btn)

        left_l.addWidget(opts)

        self.sdk_box = QGroupBox("Agora SDK (Linux / macOS)")
        sdk_l = QVBoxLayout(self.sdk_box)
        self.sdk_status_label = QLabel("Checking…")
        self.sdk_status_label.setWordWrap(True)
        sdk_l.addWidget(self.sdk_status_label)
        self.install_sdk_btn = StyledButton("Install Agora SDK", primary=True)
        self.install_sdk_btn.setToolTip(
            "Installs agora_python_server_sdk the same way ofscraper was installed "
            "(uv pip / pipx inject / pip into the active venv)."
        )
        self.install_sdk_btn.clicked.connect(self._on_install_sdk)
        sdk_l.addWidget(self.install_sdk_btn)
        left_l.addWidget(self.sdk_box)
        left_l.addStretch(1)
        left.setMinimumWidth(280)
        left.setMaximumWidth(400)
        splitter.addWidget(left)

        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(10, 0, 0, 0)
        table_box = QGroupBox("Monitored Subscriptions")
        table_l = QVBoxLayout(table_box)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter creators…")
        self.search_input.textChanged.connect(self._filter_rows)
        table_l.addWidget(self.search_input)
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(5)
        self.status_table.setHorizontalHeaderLabels(
            ["Creator", "Subscription", "Status", "Stop", "Ignore"]
        )
        hdr = self.status_table.horizontalHeader()
        # All columns user-resizable (drag header edges)
        for col in range(5):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hdr.setStretchLastSection(False)
        hdr.setMinimumSectionSize(48)
        self.status_table.setColumnWidth(0, 160)
        self.status_table.setColumnWidth(1, 140)
        self.status_table.setColumnWidth(2, 180)
        self.status_table.setColumnWidth(3, 90)
        self.status_table.setColumnWidth(4, 72)
        self.status_table.verticalHeader().setDefaultSectionSize(36)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.status_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table_l.addWidget(self.status_table, 1)
        right_l.addWidget(table_box, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        log_box = QGroupBox("Terminal")
        log_l = QVBoxLayout(log_box)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        self.log_output.setMaximumHeight(220)
        log_l.addWidget(self.log_output)
        main_layout.addWidget(log_box, 0)

    def _capture_dir(self) -> str:
        from ofscraper.gui.utils.privacy_mode import resolve_saved_value

        displayed = self.save_input.text()
        actual = resolve_saved_value(displayed, self._privacy_actual_save)
        if not actual:
            try:
                actual = get_save_location()
            except Exception:
                actual = ""
        try:
            from ofscraper.utils.config.path_norm import normalize_windows_path

            actual = normalize_windows_path(actual) or actual
        except Exception:
            pass
        return actual or ""

    def _apply_privacy_to_save_field(self):
        from ofscraper.gui.utils.privacy_mode import (
            display_or_mask,
            is_privacy_mode,
            is_privacy_placeholder,
            resolve_saved_value,
        )

        current = self.save_input.text()
        if not is_privacy_placeholder(current):
            self._privacy_actual_save = current or self._privacy_actual_save
        if is_privacy_mode():
            self.save_input.setText(display_or_mask(self._privacy_actual_save))
            self.save_input.setReadOnly(True)
        else:
            self.save_input.setText(
                resolve_saved_value(current, self._privacy_actual_save)
            )
            self.save_input.setReadOnly(False)

    def _on_privacy_mode_changed(self, _enabled: bool):
        self._apply_privacy_to_save_field()

    def append_log(self, text):
        display = text
        try:
            from ofscraper.gui.utils.privacy_mode import redact_log_message

            display = redact_log_message(str(text))
        except Exception:
            display = text
        self.log_output.appendPlainText(display)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _selected_username(self) -> str | None:
        row = self.status_table.currentRow()
        if row < 0:
            return None
        item = self.status_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole) or item.text()

    @pyqtSlot()
    def _on_fetch_selected(self):
        username = self._selected_username()
        if not username:
            self.append_log("[API] Select a creator row first.")
            return
        try:
            self.plugin.fetch_creds_only(username)
        except Exception as e:
            self.append_log(f"[Error] Fetch failed: {e}")

    @pyqtSlot()
    def _on_install_sdk(self):
        self.install_sdk_btn.setEnabled(False)
        self.install_sdk_btn.setText("Installing…")
        self.append_log("[SDK] Starting install into ofscraper's environment…")

        def _done(ok: bool):
            self._refresh_sdk_status()
            if ok:
                self.append_log("[SDK] Install succeeded and import works.")
            else:
                self.append_log(
                    "[SDK] Install finished without a working import "
                    "(see log — on Windows this is expected for native RTC)."
                )

        self.plugin.install_sdk(log_sink=self.append_log, finished_cb=_done)

    @pyqtSlot()
    def _on_capture_selected(self):
        username = self._selected_username()
        if not username:
            self.append_log("[Capture] Select a creator row first.")
            return
        self.plugin.start_capture(username, self._capture_dir())

    @pyqtSlot()
    def _on_stop_selected(self):
        username = self._selected_username()
        if not username:
            self.append_log("[Capture] Select a recording row first, then Stop.")
            return
        if self.plugin.stop_capture(username):
            self.append_log(f"[Capture] Stop requested for {username}.")
        else:
            self.append_log(f"[Capture] Nothing to stop for {username}.")

    @pyqtSlot()
    def _on_stop_all(self):
        n = self.plugin.stop_all_captures()
        self.append_log(f"[Capture] Stop requested for {n} session(s).")

    def _session_is_active(self, username: str) -> bool:
        if username in getattr(self.plugin, "active_recordings", {}):
            return True
        if username in getattr(self.plugin, "_connecting", {}):
            return True
        pw = find_playwright_live_plugin()
        if pw is None:
            return False
        if username in getattr(pw, "active_recordings", {}):
            return True
        if username in getattr(pw, "_connecting_recordings", {}):
            return True
        return False

    def _format_duration(self, start_time) -> str:
        if start_time is None:
            return ""
        try:
            elapsed = int((datetime.datetime.now() - start_time).total_seconds())
        except Exception:
            return ""
        if elapsed < 0:
            elapsed = 0
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _tick_recording_timers(self):
        """Update Recording status labels with live HH:MM:SS duration."""
        for row in range(self.status_table.rowCount()):
            username_item = self.status_table.item(row, 0)
            if username_item is None:
                continue
            username = (
                username_item.data(Qt.ItemDataRole.UserRole) or username_item.text()
            )
            start = None
            try:
                start = self.plugin.recording_start_time(username)
            except Exception:
                start = None
            if start is None:
                continue
            widget = self.status_table.cellWidget(row, 2)
            if widget is None:
                continue
            label = widget.findChild(QLabel)
            if label is None:
                continue
            duration = self._format_duration(start)
            label.setText(f"Recording 🔴 ({duration})")

    @pyqtSlot()
    def _on_open_attempts(self):
        try:
            path = self.plugin.attempts_dir()
            import os
            import subprocess
            import sys

            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.append_log(f"[Error] {e}")

    @pyqtSlot()
    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(self, "Capture Directory")
        if d:
            try:
                from ofscraper.utils.config.path_norm import normalize_windows_path

                d = normalize_windows_path(d) or d
            except Exception:
                pass
            self._privacy_actual_save = d
            self.save_input.setText(d)

    @pyqtSlot(bool)
    def _on_toggle_monitor(self, checked):
        if checked:
            self.append_log("[System] Starting Agora live monitor…")
            self.save_input.setEnabled(False)
            self.browse_btn.setEnabled(False)
            self.interval_spin.setEnabled(False)
            self.plugin.start_monitor(
                interval=self.interval_spin.value(),
                save_location=self._capture_dir(),
            )
        else:
            self.append_log("[System] Stopping Agora live monitor…")
            self.save_input.setEnabled(True)
            self.browse_btn.setEnabled(True)
            self.interval_spin.setEnabled(True)
            self.plugin.stop_monitor()
            self._apply_privacy_to_save_field()

    @pyqtSlot()
    def handle_auth_error(self):
        self.enable_check.blockSignals(True)
        self.enable_check.setChecked(False)
        self.enable_check.blockSignals(False)
        self.save_input.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.interval_spin.setEnabled(True)
        try:
            self.plugin.stop_monitor(terminate_recordings=False)
        except Exception:
            pass
        self.append_log(
            "\n⚠️ Authentication failed. Fix Authentication tab, then re-enable.\n"
        )

    @pyqtSlot(dict)
    def update_status_table(self, model_statuses: dict):
        filter_text = (self.search_input.text() or "").strip().lower()
        selected = self._selected_username()
        rows = sorted(model_statuses.values(), key=lambda r: r["username"].lower())
        self.status_table.setRowCount(0)
        for info in rows:
            username = info["username"]
            if filter_text and filter_text not in username.lower():
                continue
            r = self.status_table.rowCount()
            self.status_table.insertRow(r)
            name_item = QTableWidgetItem(username)
            name_item.setData(Qt.ItemDataRole.UserRole, username)
            try:
                from ofscraper.gui.utils.privacy_mode import mask_username, is_privacy_mode

                if is_privacy_mode():
                    name_item.setText(mask_username(username) or username)
            except Exception:
                pass
            self.status_table.setItem(r, 0, name_item)
            self.status_table.setItem(
                r, 1, QTableWidgetItem(str(info.get("subscription", "")))
            )

            status_text = str(info.get("status", ""))
            start = None
            try:
                start = self.plugin.recording_start_time(username)
            except Exception:
                start = None
            if start is not None and "Recording" in status_text:
                dur = self._format_duration(start)
                status_text = f"Recording 🔴 ({dur})" if dur else status_text

            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(4, 2, 4, 2)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label = QLabel(status_text)
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            status_layout.addWidget(status_label)
            self.status_table.setCellWidget(r, 2, status_widget)

            stop_wrap = QWidget()
            stop_lay = QHBoxLayout(stop_wrap)
            stop_lay.setContentsMargins(0, 0, 0, 0)
            stop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            active = self._session_is_active(username) or (
                "Recording" in status_text or "Connecting" in status_text
            )
            if active:
                stop_btn = QPushButton("Stop")
                stop_btn.setMinimumWidth(70)
                stop_btn.setMinimumHeight(28)
                stop_btn.setStyleSheet(
                    "QPushButton { padding: 4px 12px; min-height: 24px; }"
                )
                stop_btn.setToolTip(f"Stop capture for {username}")
                stop_btn.clicked.connect(
                    lambda _checked=False, u=username: self._stop_row(u)
                )
                stop_lay.addWidget(stop_btn)
            self.status_table.setCellWidget(r, 3, stop_wrap)
            self.status_table.setRowHeight(r, max(self.status_table.rowHeight(r), 36))

            ignore = QCheckBox()
            ignore.setChecked(self.plugin.is_ignored(username))
            ignore.toggled.connect(
                lambda checked, u=username: self.plugin.set_ignored(u, checked)
            )
            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(ignore)
            self.status_table.setCellWidget(r, 4, wrap)
            if selected and selected == username:
                self.status_table.selectRow(r)

    def _stop_row(self, username: str):
        if self.plugin.stop_capture(username):
            self.append_log(f"[Capture] Stop requested for {username}.")
        else:
            self.append_log(f"[Capture] Nothing to stop for {username}.")

    def _filter_rows(self, _text: str):
        # Next poll refreshes; also hide unmatched immediately
        q = (self.search_input.text() or "").strip().lower()
        for r in range(self.status_table.rowCount()):
            item = self.status_table.item(r, 0)
            if item is None:
                continue
            real = (item.data(Qt.ItemDataRole.UserRole) or item.text() or "").lower()
            self.status_table.setRowHidden(r, bool(q) and q not in real)

    def _apply_theme(self, _dark: bool = False):
        pass
