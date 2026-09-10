import datetime
import logging
from pathlib import Path

log = logging.getLogger("shared")
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSpinBox, QLineEdit, QFileDialog, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QSplitter, QProgressBar, QDialog, QDialogButtonBox, QFrame,
    QMessageBox, QSizePolicy, QPushButton,
)
from ofscraper.gui.styles import c, is_dark_theme
from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton
from ofscraper.utils.paths.common import get_save_location


def _rgba(token: str, alpha: float) -> str:
    """Theme-aware rgba() from a palette token (hex)."""
    raw = (c(token) or "").lstrip("#")
    if len(raw) != 6:
        return f"rgba(128, 128, 128, {alpha})"
    try:
        r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
        return f"rgba({r}, {g}, {b}, {alpha})"
    except Exception:
        return f"rgba(128, 128, 128, {alpha})"


def _badge_style(fg_token: str, bg_alpha: float = 0.15) -> str:
    return (
        f"background-color: {_rgba(fg_token, bg_alpha)}; "
        f"color: {c(fg_token)}; "
        f"border: 1px solid {c(fg_token)}; "
        f"border-radius: 10px; padding: 2px 10px;"
    )


class ChromiumSetupDialog(QDialog):
    """Modal prompt when Playwright Chromium is missing (mirrors LLM deps UX)."""

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self._success = False
        self.setWindowTitle("Live Stream Monitor — Chromium Required")
        self.setMinimumSize(520, 360)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(20, 20, 20, 20)

        title = QLabel("Missing Playwright Chromium")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        root.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        info = QLabel(
            "Auto-capture needs a local Chromium browser via Playwright.<br><br>"
            "Click <b>Install Chromium</b> to download it into OF-Scraper's "
            "Playwright browsers folder (this can take a few minutes)."
        )
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        root.addWidget(info)

        self.status = QLabel("Ready to install.")
        root.addWidget(self.status)

        self.progress = QProgressBar()
        self.progress.hide()
        root.addWidget(self.progress)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        root.addWidget(self.log_view, 1)

        btns = QDialogButtonBox()
        self.install_btn = btns.addButton(
            "Install Chromium", QDialogButtonBox.ButtonRole.ActionRole
        )
        self.close_btn = btns.addButton(
            "Close", QDialogButtonBox.ButtonRole.RejectRole
        )
        self.install_btn.clicked.connect(self._start_install)
        self.close_btn.clicked.connect(self.reject)
        root.addWidget(btns)

    def was_successful(self) -> bool:
        return bool(self._success)

    def append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def _start_install(self):
        self.install_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText("Installing Chromium… please wait.")
        self.append_log("[Playwright] Initiating Chromium installation...")
        # Reuse plugin installer; route logs into this dialog
        self.plugin.install_chromium(log_sink=self.append_log, finished_cb=self._on_finished)

    def _on_finished(self, success: bool):
        self.progress.hide()
        self.install_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        self._success = bool(success)
        if success:
            self.status.setText("Chromium installed successfully.")
            self.append_log("[Playwright] Chromium installation succeeded.")
            self.accept()
        else:
            self.status.setText("Installation failed — see log above.")
            self.append_log("[Error] Chromium installation failed.")


class LiveMonitorTab(QWidget):
    """The dashboard tab for configuring and monitoring OnlyFans live stream captures."""

    def __init__(self, main_window, plugin):
        super().__init__(main_window)
        self.main_window = main_window
        self.plugin = plugin
        self.plugin.gui = self
        self._privacy_actual_save = ""
        self._chromium_check = None

        self._setup_ui()
        self._apply_theme(is_dark_theme())

        app_signals.theme_changed.connect(self._apply_theme)
        app_signals.privacy_mode_changed.connect(self._on_privacy_mode_changed)

        # 1-second timer to keep recording durations live
        self._duration_timer = QTimer(self)
        self._duration_timer.setInterval(1000)
        self._duration_timer.timeout.connect(self._tick_recording_timers)
        self._duration_timer.start()

        self._apply_privacy_to_save_field()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 12, 20, 16)
        main_layout.setSpacing(10)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel("📺 Live Stream Monitor")
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.title_label.setProperty("heading", True)
        self.title_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        header_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Active subscription auto-capture dashboard")
        self.subtitle_label.setProperty("subheading", True)
        self.subtitle_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        header_layout.addWidget(
            self.subtitle_label, alignment=Qt.AlignmentFlag.AlignBottom
        )
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Mid band: options (left) + subscriptions table (right) — fills leftover height
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # ------------------ LEFT SIDE: CONFIG & BROWSER INSTALL ------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 10, 0)
        left_layout.setSpacing(12)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.config_group = QGroupBox("Monitor Options")
        self.config_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        config_layout = QVBoxLayout(self.config_group)
        config_layout.setSpacing(10)

        self.enable_check = QCheckBox("Enable Auto-Capture")
        self.enable_check.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.enable_check.toggled.connect(self._on_toggle_monitor)
        config_layout.addWidget(self.enable_check)

        self.headless_check = QCheckBox("Hide capture window (off-screen Chrome)")
        self.headless_check.setChecked(bool(getattr(self.plugin, "headless_capture", True)))
        self.headless_check.setToolTip(
            "Keeps the capture Chrome window off-screen. True Playwright headless "
            "is not used — OnlyFans drops the login session in headless mode."
        )
        self.headless_check.toggled.connect(self._on_toggle_headless)
        config_layout.addWidget(self.headless_check)

        # Capture / stop controls
        self.capture_selected_btn = StyledButton("Capture selected", primary=True)
        self.capture_selected_btn.setToolTip(
            "Start Playwright capture for the creator selected in the table "
            "(even if Auto-Capture is off). Creator should be Live."
        )
        self.capture_selected_btn.clicked.connect(self._on_capture_selected)
        config_layout.addWidget(self.capture_selected_btn)

        self.stop_selected_btn = StyledButton("Stop selected capture")
        self.stop_selected_btn.setToolTip(
            "Stop only the selected creator's capture/probe without disabling Auto-Capture."
        )
        self.stop_selected_btn.clicked.connect(self._on_stop_selected)
        config_layout.addWidget(self.stop_selected_btn)

        self.stop_all_btn = StyledButton("Stop all captures")
        self.stop_all_btn.setToolTip(
            "Stop every active/connecting capture without disabling the monitor poller."
        )
        self.stop_all_btn.clicked.connect(self._on_stop_all)
        config_layout.addWidget(self.stop_all_btn)

        interval_layout = QHBoxLayout()
        self.interval_label = QLabel("Poll Interval (seconds):")
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(10, 3600)
        self.interval_spin.setValue(60)
        self.interval_spin.setFixedWidth(80)
        interval_layout.addWidget(self.interval_label)
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()
        config_layout.addLayout(interval_layout)

        save_layout = QVBoxLayout()
        self.save_label = QLabel("Capture Directory:")
        save_input_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.save_input.setPlaceholderText("Default OF-Scraper Save Location")

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
        self.browse_btn.clicked.connect(self._on_browse_directory)

        save_input_layout.addWidget(self.save_input)
        save_input_layout.addWidget(self.browse_btn)
        save_layout.addWidget(self.save_label)
        save_layout.addLayout(save_input_layout)
        config_layout.addLayout(save_layout)

        # Diagnostics — hidden by default
        self.show_diag_check = QCheckBox("Show diagnostics")
        self.show_diag_check.setChecked(
            bool(getattr(self.plugin, "show_diagnostics", False))
        )
        self.show_diag_check.setToolTip(
            "Reveal probe / live-API dump tools (for developers). Hidden by default."
        )
        self.show_diag_check.toggled.connect(self._on_toggle_show_diagnostics)
        config_layout.addWidget(self.show_diag_check)

        self.diag_panel = QWidget()
        diag_l = QVBoxLayout(self.diag_panel)
        diag_l.setContentsMargins(0, 4, 0, 0)
        diag_l.setSpacing(8)

        self.probe_check = QCheckBox("Diagnostics probe only (no WebM recording)")
        self.probe_check.setChecked(bool(getattr(self.plugin, "probe_mode", False)))
        self.probe_check.setToolTip(
            "When Auto-Capture is on, join each live for ~45s and save a redacted "
            "JSON report (HLS / WebRTC / API evidence) under the plugin's "
            "live_probe_reports folder — does not record video."
        )
        self.probe_check.toggled.connect(self._on_toggle_probe_mode)
        diag_l.addWidget(self.probe_check)

        probe_btn_row = QHBoxLayout()
        self.probe_selected_btn = StyledButton("Probe selected…")
        self.probe_selected_btn.setToolTip(
            "Run a one-shot diagnostics probe for the creator selected in the table "
            "(works even if Auto-Capture is off). Creator should be Live."
        )
        self.probe_selected_btn.clicked.connect(self._on_probe_selected)
        self.open_reports_btn = StyledButton("Open reports…")
        self.open_reports_btn.setToolTip("Open the live_probe_reports folder.")
        self.open_reports_btn.clicked.connect(self._on_open_probe_reports)
        probe_btn_row.addWidget(self.probe_selected_btn)
        probe_btn_row.addWidget(self.open_reports_btn)
        diag_l.addLayout(probe_btn_row)

        api_row = QHBoxLayout()
        self.fetch_api_btn = StyledButton("Fetch live API dump…")
        self.fetch_api_btn.setToolTip(
            "Call OF /streams/active + /streams/active/url for the selected creator "
            "and save a redacted dump (includes Agora token claims). Diagnostics only."
        )
        self.fetch_api_btn.clicked.connect(self._on_fetch_live_api)
        self.open_api_dumps_btn = StyledButton("Open API dumps…")
        self.open_api_dumps_btn.setToolTip("Open the live_api_dumps folder.")
        self.open_api_dumps_btn.clicked.connect(self._on_open_api_dumps)
        api_row.addWidget(self.fetch_api_btn)
        api_row.addWidget(self.open_api_dumps_btn)
        diag_l.addLayout(api_row)

        self.diag_panel.setVisible(self.show_diag_check.isChecked())
        config_layout.addWidget(self.diag_panel)

        left_layout.addWidget(self.config_group)

        self.browser_group = QGroupBox("Playwright Setup")
        self.browser_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        browser_layout = QVBoxLayout(self.browser_group)
        browser_layout.setSpacing(10)

        self.browser_status_label = QLabel("Checking Chromium browser...")
        self.browser_status_label.setWordWrap(True)
        browser_layout.addWidget(self.browser_status_label)

        self.install_progress = QProgressBar()
        self.install_progress.hide()
        browser_layout.addWidget(self.install_progress)

        self.install_btn = StyledButton("Install Chromium Browser", primary=True)
        self.install_btn.clicked.connect(self._on_install_chromium)
        browser_layout.addWidget(self.install_btn)

        left_layout.addWidget(self.browser_group)
        left_layout.addStretch(1)
        left_widget.setMinimumWidth(280)
        left_widget.setMaximumWidth(360)
        splitter.addWidget(left_widget)

        # ------------------ RIGHT SIDE: SUBSCRIPTIONS TABLE ------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.table_group = QGroupBox("Monitored Subscriptions")
        self.table_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        table_layout = QVBoxLayout(self.table_group)
        table_layout.setContentsMargins(8, 8, 8, 8)

        filter_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter creators...")
        self.search_input.textChanged.connect(self._filter_table_rows)
        filter_layout.addWidget(self.search_input)
        table_layout.addLayout(filter_layout)

        self.status_table = QTableWidget()
        self.status_table.setColumnCount(6)
        self.status_table.setHorizontalHeaderLabels(
            [
                "Creator",
                "Active Subscription",
                "Status",
                "Recorded Streams",
                "Stop",
                "Ignore",
            ]
        )
        header = self.status_table.horizontalHeader()
        for col in range(6):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(48)
        self.status_table.setColumnWidth(0, 140)
        self.status_table.setColumnWidth(1, 130)
        self.status_table.setColumnWidth(2, 160)
        self.status_table.setColumnWidth(3, 120)
        self.status_table.setColumnWidth(4, 90)
        self.status_table.setColumnWidth(5, 70)
        self.status_table.verticalHeader().setDefaultSectionSize(36)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.status_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.status_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.status_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.status_table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        table_layout.addWidget(self.status_table, 1)
        right_layout.addWidget(self.table_group, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 900])
        main_layout.addWidget(splitter, 1)

        # Terminal spans full width under the splitter (compact)
        self.log_group = QGroupBox("Live Monitoring Terminal")
        self.log_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        log_layout = QVBoxLayout(self.log_group)
        log_layout.setContentsMargins(8, 8, 8, 8)

        log_toolbar = QHBoxLayout()
        self.clear_logs_btn = StyledButton("Clear Console")
        self.clear_logs_btn.clicked.connect(self._on_clear_logs)
        self.export_logs_btn = StyledButton("Export Logs...")
        self.export_logs_btn.clicked.connect(self._on_export_logs)
        log_toolbar.addWidget(self.clear_logs_btn)
        log_toolbar.addWidget(self.export_logs_btn)
        log_toolbar.addStretch()
        log_layout.addLayout(log_toolbar)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(120)
        self.log_output.setMaximumHeight(200)
        self.log_output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        log_layout.addWidget(self.log_output)
        main_layout.addWidget(self.log_group, 0)

        self._check_browser_status()

    def _capture_dir(self) -> str:
        """Real capture directory (privacy-safe)."""
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
            restored = resolve_saved_value(current, self._privacy_actual_save)
            self.save_input.setText(restored)
            self.save_input.setReadOnly(False)

    def _on_privacy_mode_changed(self, _enabled: bool):
        self._apply_privacy_to_save_field()
        # Refresh table display names without waiting for next poll
        for row in range(self.status_table.rowCount()):
            item = self.status_table.item(row, 0)
            if item is None:
                continue
            real = item.data(Qt.ItemDataRole.UserRole) or item.text()
            try:
                from ofscraper.gui.utils.privacy_mode import mask_username
                item.setText(mask_username(real) or real)
            except Exception:
                item.setText(real)

    def _check_browser_status(self):
        """Asynchronously checks if Chromium is installed and ready."""
        import sys

        self.browser_status_label.setText("Checking Chromium browser...")
        self.install_btn.setEnabled(False)

        mod = sys.modules.get(type(self.plugin).__module__)
        WorkerCls = getattr(mod, "ChromiumCheckWorker", None) if mod else None
        if WorkerCls is None:
            ok = self.plugin.check_chromium_installed()
            self._on_chromium_check_done(ok)
            return

        self._chromium_check = WorkerCls(self.plugin)
        self._chromium_check.finished.connect(self._on_chromium_check_done)
        self._chromium_check.start()

    def _on_chromium_check_done(self, is_installed: bool):
        self.install_btn.setEnabled(True)
        if is_installed:
            self.browser_status_label.setText(
                "🟢 Playwright Chromium is fully installed and ready."
            )
            self.install_btn.setText("Reinstall Chromium")
        else:
            self.browser_status_label.setText(
                "❌ Playwright Chromium is missing. Auto-capture requires Chromium."
            )
            self.install_btn.setText("Install Chromium Browser")

    def append_log(self, text):
        """Appends a new line of text to the console monitor terminal."""
        display = text
        try:
            from ofscraper.gui.utils.privacy_mode import redact_log_message
            display = redact_log_message(str(text))
        except Exception:
            display = text
        self.log_output.appendPlainText(display)
        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())
        log.debug(f"[Live Monitor Console] {str(text).strip()}")

    def update_status_table(self, model_statuses):
        # Preserve selection across poll refreshes
        prev_selected = None
        try:
            row = self.status_table.currentRow()
            if row >= 0:
                item = self.status_table.item(row, 0)
                if item is not None:
                    prev_selected = item.data(Qt.ItemDataRole.UserRole) or item.text()
        except Exception:
            prev_selected = None

        self.status_table.setUpdatesEnabled(False)
        self.status_table.setRowCount(0)

        def _sort_key(k):
            s = model_statuses[k]["status"]
            order = 0 if "Recording" in s else (1 if "Connecting" in s else (2 if "Live" in s else 3))
            return (order, k)
        sorted_keys = sorted(model_statuses.keys(), key=_sort_key)

        self.status_table.setRowCount(len(sorted_keys))

        try:
            from ofscraper.gui.utils.privacy_mode import mask_username
        except Exception:
            mask_username = lambda u: "" if u is None else str(u)  # noqa: E731

        save_base = self._capture_dir()
        restore_row = -1

        for row, username in enumerate(sorted_keys):
            info = model_statuses[username]
            if prev_selected and username == prev_selected:
                restore_row = row

            name_item = QTableWidgetItem(mask_username(username) or username)
            name_item.setData(Qt.ItemDataRole.UserRole, username)
            self.status_table.setItem(row, 0, name_item)

            sub_item = QTableWidgetItem(info["subscription"])
            self.status_table.setItem(row, 1, sub_item)

            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.setContentsMargins(4, 4, 4, 4)

            status_label = QLabel(info["status"])
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))

            if "Recording" in info["status"]:
                status_label.setStyleSheet(_badge_style("red", 0.15))
            elif "Connecting" in info["status"]:
                status_label.setStyleSheet(_badge_style("yellow", 0.15))
            elif "Live" in info["status"]:
                status_label.setStyleSheet(_badge_style("green", 0.15))
            else:
                status_label.setStyleSheet(
                    f"background-color: {_rgba('subtext', 0.12)}; "
                    f"color: {c('subtext')}; "
                    f"border: 1px solid {c('surface1')}; "
                    f"border-radius: 10px; padding: 2px 10px;"
                )

            status_layout.addWidget(status_label)
            self.status_table.setCellWidget(row, 2, status_widget)

            streams_count = self.plugin.get_streams_count(username, save_base)
            count_item = QTableWidgetItem(str(streams_count))

            path = Path(save_base) / username / "Live_Streams" if save_base else None
            if path is not None and path.is_dir():
                files = sorted(
                    [f for f in path.iterdir() if f.is_file()],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True,
                )
                if files:
                    tooltip_lines = []
                    for f in files[:10]:
                        mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime(
                            "%Y-%m-%d %H:%M"
                        )
                        size_mb = f.stat().st_size / (1024 * 1024)
                        tooltip_lines.append(f"  • {f.name} ({size_mb:.1f} MB) - {mtime}")
                    if len(files) > 10:
                        tooltip_lines.append(f"  • ... and {len(files) - 10} more stream(s)")
                    count_item.setToolTip("Recent Captures:\n" + "\n".join(tooltip_lines))
                else:
                    count_item.setToolTip("No recorded streams found in directory")
            else:
                count_item.setToolTip("Directory does not exist yet (no captures started)")

            self.status_table.setItem(row, 3, count_item)

            # Stop button (active capture/probe only)
            stop_wrap = QWidget()
            stop_lay = QHBoxLayout(stop_wrap)
            stop_lay.setContentsMargins(4, 2, 4, 2)
            stop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            active = (
                username in getattr(self.plugin, "active_recordings", {})
                or username in getattr(self.plugin, "_connecting_recordings", {})
            )
            if active:
                stop_btn = QPushButton("Stop")
                stop_btn.setMinimumWidth(70)
                stop_btn.setMinimumHeight(28)
                stop_btn.setStyleSheet(
                    "QPushButton { padding: 4px 12px; min-height: 24px; }"
                )
                stop_btn.setToolTip(f"Stop capture/probe for {username}")
                stop_btn.clicked.connect(
                    lambda _checked=False, u=username: self._stop_row(u)
                )
                stop_lay.addWidget(stop_btn)
            self.status_table.setCellWidget(row, 4, stop_wrap)
            self.status_table.setRowHeight(row, max(self.status_table.rowHeight(row), 36))

            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.setChecked(self.plugin.is_ignored(username))
            cb.toggled.connect(lambda checked, u=username: self.plugin.set_ignored(u, checked))
            cb_layout.addWidget(cb)
            self.status_table.setCellWidget(row, 5, cb_container)

        self.status_table.setUpdatesEnabled(True)
        self._filter_table_rows(self.search_input.text())
        if restore_row >= 0:
            self.status_table.selectRow(restore_row)

    def _tick_recording_timers(self):
        """Update recording durations every second without waiting for a poll."""
        if not self.plugin.active_recordings:
            return
        for row in range(self.status_table.rowCount()):
            username_item = self.status_table.item(row, 0)
            if username_item is None:
                continue
            username = username_item.data(Qt.ItemDataRole.UserRole) or username_item.text()
            if username not in self.plugin.active_recordings:
                continue
            widget = self.status_table.cellWidget(row, 2)
            if widget is None:
                continue
            label = widget.findChild(QLabel)
            if label is None:
                continue
            _thread, _stop, start_time = self.plugin.active_recordings[username]
            elapsed = int((datetime.datetime.now() - start_time).total_seconds())
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            duration = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
            label.setText(f"Recording 🔴 ({duration})")

    def _filter_table_rows(self, text):
        """Filters table rows based on input creator text (matches real username)."""
        text = text.lower().strip()
        for row in range(self.status_table.rowCount()):
            username_item = self.status_table.item(row, 0)
            if username_item is not None:
                real = username_item.data(Qt.ItemDataRole.UserRole) or username_item.text()
                display = username_item.text()
                show = (not text) or (text in str(real).lower()) or (text in display.lower())
                self.status_table.setRowHidden(row, not show)

    def _on_cell_double_clicked(self, row, column):
        """Double clicking opens creator's Live Streams output directory."""
        username_item = self.status_table.item(row, 0)
        if username_item is None:
            return
        username = username_item.data(Qt.ItemDataRole.UserRole) or username_item.text()
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        save_base = self._capture_dir()
        path = Path(save_base) / username / "Live_Streams"
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    @pyqtSlot()
    def _on_clear_logs(self):
        self.log_output.clear()
        self.append_log("[System] Console logs cleared.")

    @pyqtSlot()
    def _on_export_logs(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Console Logs", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.log_output.toPlainText())
                self.append_log(f"[System] Logs successfully exported to: {file_path}")
            except Exception as e:
                self.append_log(f"[Error] Failed to export logs: {e}")

    @pyqtSlot(bool)
    def _on_toggle_headless(self, checked):
        try:
            self.plugin.set_headless_capture(bool(checked))
            state = "on" if checked else "off"
            self.append_log(
                f"[System] Hide capture window {state} "
                "(applies to new recordings; current captures keep their window mode)."
            )
        except Exception as e:
            self.append_log(f"[Error] Failed to save headless setting: {e}")

    @pyqtSlot(bool)
    def _on_toggle_show_diagnostics(self, checked):
        self.diag_panel.setVisible(bool(checked))
        try:
            self.plugin.set_show_diagnostics(bool(checked))
        except Exception as e:
            self.append_log(f"[Error] Failed to save diagnostics visibility: {e}")

    @pyqtSlot(bool)
    def _on_toggle_probe_mode(self, checked):
        try:
            self.plugin.set_probe_mode(bool(checked))
            if checked:
                self.append_log(
                    "[System] Diagnostics probe mode ON — Auto-Capture will save "
                    "JSON reports (no WebM) when creators go live."
                )
            else:
                self.append_log(
                    "[System] Diagnostics probe mode OFF — Auto-Capture records WebM again."
                )
        except Exception as e:
            self.append_log(f"[Error] Failed to save probe setting: {e}")

    @pyqtSlot()
    def _on_probe_selected(self):
        if not self.plugin.check_chromium_installed():
            dlg = ChromiumSetupDialog(self.plugin, parent=self)
            if not (dlg.exec() and dlg.was_successful()):
                self.append_log("[Warning] Probe needs Playwright Chromium.")
                return
        username = self._selected_username()
        if not username:
            self.append_log(
                "[Probe] Select a creator row in the table first, then click Probe selected."
            )
            return
        if self.plugin.is_ignored(username):
            self.append_log(f"[Probe] {username} is ignored — uncheck Ignore first.")
            return
        try:
            self.plugin.set_headless_capture(self.headless_check.isChecked())
        except Exception:
            pass
        self.append_log(f"[Probe] Starting one-shot diagnostics for {username}...")
        self.plugin.start_probe(username, self._capture_dir())

    def _selected_username(self):
        row = self.status_table.currentRow()
        if row < 0:
            return None
        item = self.status_table.item(row, 0)
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole) or item.text()

    def _stop_row(self, username: str):
        try:
            if self.plugin.stop_capture(username):
                self.append_log(f"[Capture] Stop requested for {username}")
            else:
                self.append_log(f"[Capture] No active session for {username}")
        except Exception as e:
            self.append_log(f"[Error] Stop failed for {username}: {e}")

    @pyqtSlot()
    def _on_capture_selected(self):
        if not self.plugin.check_chromium_installed():
            dlg = ChromiumSetupDialog(self.plugin, parent=self)
            if not (dlg.exec() and dlg.was_successful()):
                self.append_log("[Warning] Capture needs Playwright Chromium.")
                return
        username = self._selected_username()
        if not username:
            self.append_log("[Capture] Select a creator row first.")
            return
        if self.plugin.is_ignored(username):
            self.append_log(f"[Capture] {username} is ignored — uncheck Ignore first.")
            return
        try:
            self.plugin.set_headless_capture(self.headless_check.isChecked())
        except Exception:
            pass
        self.append_log(f"[Capture] Starting Playwright capture for {username}…")
        self.plugin.start_recording(username, self._capture_dir())

    @pyqtSlot()
    def _on_stop_selected(self):
        username = self._selected_username()
        if not username:
            self.append_log("[Capture] Select a creator row first.")
            return
        self._stop_row(username)

    @pyqtSlot()
    def _on_stop_all(self):
        try:
            n = self.plugin.stop_all_captures()
            self.append_log(f"[Capture] Stopped {n} session(s).")
        except Exception as e:
            self.append_log(f"[Error] Stop all failed: {e}")

    @pyqtSlot()
    def _on_fetch_live_api(self):
        username = self._selected_username()
        if not username:
            self.append_log("[API] Select a creator row first.")
            return
        try:
            path = self.plugin.fetch_live_api_dump(username)
            self.append_log(f"[API] Live API dump saved: {path}")
        except Exception as e:
            self.append_log(f"[API] Fetch failed for {username}: {e}")

    @pyqtSlot()
    def _on_open_api_dumps(self):
        try:
            path = self.plugin.api_dumps_dir()
            import os
            import subprocess
            import sys

            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.append_log(f"[API] Opened {path}")
        except Exception as e:
            self.append_log(f"[API] Could not open dumps folder: {e}")

    @pyqtSlot()
    def _on_open_probe_reports(self):
        try:
            path = self.plugin.probe_reports_dir()
            import os
            import subprocess
            import sys

            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
            self.append_log(f"[Probe] Opened reports folder: {path}")
        except Exception as e:
            self.append_log(f"[Error] Could not open reports folder: {e}")

    @pyqtSlot(bool)
    def _on_toggle_monitor(self, checked):
        if checked:
            # Quick probe — ChromiumCheckWorker already ran at tab open; this is a
            # final gate before starting (may briefly block if Playwright cold-imports).
            if not self.plugin.check_chromium_installed():
                self.enable_check.blockSignals(True)
                self.enable_check.setChecked(False)
                self.enable_check.blockSignals(False)
                dlg = ChromiumSetupDialog(self.plugin, parent=self)
                if dlg.exec() and dlg.was_successful():
                    self.enable_check.setChecked(True)
                    return
                self.append_log(
                    "[Warning] Cannot start monitor. Playwright Chromium is not installed."
                )
                return

            self.append_log("[System] Starting Live Stream Monitor...")
            self.save_input.setEnabled(False)
            self.browse_btn.setEnabled(False)
            self.interval_spin.setEnabled(False)
            try:
                self.plugin.set_headless_capture(self.headless_check.isChecked())
                self.plugin.set_probe_mode(self.probe_check.isChecked())
            except Exception:
                pass

            self.plugin.start_monitor(
                interval=self.interval_spin.value(),
                save_location=self._capture_dir(),
            )
        else:
            self.append_log("[System] Stopping Live Stream Monitor...")
            self.save_input.setEnabled(True)
            self.browse_btn.setEnabled(True)
            self.interval_spin.setEnabled(True)
            self.plugin.stop_monitor()
            self._apply_privacy_to_save_field()

    @pyqtSlot()
    def handle_auth_error(self):
        # Uncheck without going through the normal Stop path that kills captures.
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
        active = []
        try:
            active = list(self.plugin.active_recordings.keys()) + list(
                self.plugin._connecting_recordings.keys()
            )
        except Exception:
            pass
        self.append_log(
            "\n⚠️ [Monitor Error] Authentication failed or credentials not configured.\n"
            "Please go to the 'Authentication' tab and fix OnlyFans cookies "
            "(Auth Test must succeed — include auth_uid if 2FA is enabled).\n"
            "Auto-capture polling is paused to prevent server spam.\n"
        )
        if active:
            self.append_log(
                "[Monitor] In-progress capture(s) will keep recording until the "
                "stream ends: " + ", ".join(active) + "\n"
            )
        self._apply_privacy_to_save_field()

    @pyqtSlot()
    def _on_browse_directory(self):
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode
        if is_privacy_mode():
            QMessageBox.information(
                self,
                "Privacy Mode",
                "Turn off Privacy mode to change the capture directory.",
            )
            return
        start = self._capture_dir() or ""
        dir_path = QFileDialog.getExistingDirectory(
            self, "Select Save Location", start
        )
        if dir_path:
            try:
                from ofscraper.utils.config.path_norm import normalize_windows_path
                dir_path = normalize_windows_path(dir_path) or dir_path
            except Exception:
                pass
            self._privacy_actual_save = dir_path
            self.save_input.setText(dir_path)
            self.append_log(f"[Config] Save directory set to: {dir_path}")

    @pyqtSlot()
    def _on_install_chromium(self):
        dlg = ChromiumSetupDialog(self.plugin, parent=self)
        dlg.exec()
        self._check_browser_status()

    def install_finished(self, success):
        """Called by main.py when Chromium installation completes (inline progress)."""
        self.install_progress.hide()
        self.install_btn.setEnabled(True)
        self._check_browser_status()
        if success:
            self.append_log("[Playwright] Chromium installation succeeded! Ready to capture.")
        else:
            self.append_log("[Error] Chromium installation failed. See terminal output for details.")

    def _apply_theme(self, is_dark=True):
        self.title_label.setStyleSheet(f"color: {c('blue')};")

        group_style = f"""
            QGroupBox {{
                border: 1px solid {c('surface1')};
                border-radius: 6px;
                margin-top: 10px;
                font-weight: bold;
                color: {c('blue')};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }}
        """
        self.config_group.setStyleSheet(group_style)
        self.browser_group.setStyleSheet(group_style)
        self.table_group.setStyleSheet(group_style)
        self.log_group.setStyleSheet(group_style)

        self.save_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {c('base')};
                color: {c('text')};
                border: 1px solid {c('surface1')};
                border-radius: 4px;
                padding: 4px;
            }}
        """)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {c('base')};
                color: {c('text')};
                border: 1px solid {c('surface1')};
                border-radius: 4px;
                padding: 6px;
            }}
        """)

        self.status_table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {c('base')};
                color: {c('text')};
                gridline-color: {c('surface1')};
                border: 1px solid {c('surface1')};
                border-radius: 6px;
            }}
            QHeaderView::section {{
                background-color: {c('mantle')};
                color: {c('blue')};
                padding: 6px;
                border: 1px solid {c('surface1')};
                font-weight: bold;
            }}
        """)

        self.log_output.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {c('mantle')};
                color: {c('text')};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 12px;
                border: 1px solid {c('surface1')};
                border-radius: 6px;
            }}
        """)
