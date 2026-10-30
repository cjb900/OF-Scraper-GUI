import datetime
import logging
import time
from pathlib import Path

log = logging.getLogger("shared")
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSpinBox, QLineEdit, QFileDialog, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QSplitter, QProgressBar, QDialog, QDialogButtonBox, QFrame,
    QMessageBox, QSizePolicy, QPushButton, QMenu, QApplication,
)
from ofscraper.gui.styles import c, is_dark_theme
from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton
from ofscraper.utils.paths.common import get_save_location

# Lines kept in the Live Monitoring Terminal (older lines drop off the top).
LOG_MAX_LINES = 2000


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


def _mask(username: str) -> str:
    """Username as shown on screen (hidden in Privacy mode)."""
    try:
        from ofscraper.gui.utils.privacy_mode import mask_username
        return mask_username(username) or username
    except Exception:
        return username


def _format_size(size: int) -> str:
    mb = size / (1024 * 1024)
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def _status_style(status: str, ignored: bool = False) -> str:
    if not ignored:
        if "Recording" in status:
            return _badge_style("red", 0.15)
        if "Connecting" in status or "Probing" in status:
            return _badge_style("yellow", 0.15)
        if "Live" in status:
            return _badge_style("green", 0.15)
    return (
        f"background-color: {_rgba('subtext', 0.12)}; "
        f"color: {c('subtext')}; "
        f"border: 1px solid {c('surface1')}; "
        f"border-radius: 10px; padding: 2px 10px;"
    )


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
            self.plugin.chromium_ready = True
            self.status.setText("Ready — Playwright browser verified. You can close this dialog.")
            self.append_log(
                "[Playwright] Browser ready (system Chrome/Edge or bundled Chromium). "
                "Click Close — do not reinstall unless capture still fails."
            )
            # Do not accept() immediately: auto-close looked like a crash when
            # the old installer died mid-download. Leave the success log visible.
            self.close_btn.setDefault(True)
            self.close_btn.setFocus()
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
        # Action waiting for the background Chromium check to finish.
        self._pending_chromium_action = None

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

        # Version shown so it's easy to tell which plugin copy is loaded.
        self.subtitle_label = QLabel(
            f"Active subscription auto-capture dashboard · v{getattr(self.plugin, 'version', '?')}"
        )
        self.subtitle_label.setProperty("subheading", True)
        self.subtitle_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        header_layout.addWidget(
            self.subtitle_label, alignment=Qt.AlignmentFlag.AlignBottom
        )
        header_layout.addStretch()

        # "Last check … · next in …" so a quiet page still shows it is working.
        self.monitor_status_label = QLabel("Monitor off")
        self.monitor_status_label.setProperty("subheading", True)
        header_layout.addWidget(
            self.monitor_status_label, alignment=Qt.AlignmentFlag.AlignBottom
        )
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

        self.no_window_check = QCheckBox("No window (headless browser)")
        self.no_window_check.setChecked(bool(getattr(self.plugin, "no_window", True)))
        self.no_window_check.setToolTip(
            "Capture with Chrome's headless mode: no window at all, not even off-screen.\n"
            "Uses the login from the Authentication tab (Test must pass). Untick to use a\n"
            "real Chrome window, e.g. to log in by hand inside it."
        )
        self.no_window_check.toggled.connect(self._on_toggle_no_window)
        config_layout.addWidget(self.no_window_check)

        self.headless_check = QCheckBox("Hide capture window (off-screen Chrome)")
        self.headless_check.setChecked(bool(getattr(self.plugin, "headless_capture", True)))
        self.headless_check.setToolTip(
            "With a capture window (No window unticked): keep it off-screen."
        )
        self.headless_check.toggled.connect(self._on_toggle_headless)
        config_layout.addWidget(self.headless_check)
        self.headless_check.setEnabled(not self.no_window_check.isChecked())

        self.notify_check = QCheckBox("Desktop notifications")
        self.notify_check.setChecked(bool(getattr(self.plugin, "notify", True)))
        self.notify_check.setToolTip(
            "Notify when a recording starts, is saved, or a capture fails."
        )
        self.notify_check.toggled.connect(
            lambda on: self.plugin.set_page_settings(notify=bool(on))
        )
        config_layout.addWidget(self.notify_check)

        # Capture / stop controls
        self.capture_selected_btn = StyledButton("Capture selected", primary=True)
        self.capture_selected_btn.setToolTip(
            "Start Playwright capture for the creator selected in the table "
            "(even if Auto-Capture is off). Creator should be Live."
        )
        self.capture_selected_btn.clicked.connect(self._on_capture_selected)
        config_layout.addWidget(self.capture_selected_btn)


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
        self.interval_spin.setValue(int(getattr(self.plugin, "poll_interval", 60) or 60))
        self.interval_spin.setFixedWidth(80)
        self.interval_spin.valueChanged.connect(
            lambda v: self.plugin.set_page_settings(poll_interval=int(v))
        )
        interval_layout.addWidget(self.interval_label)
        interval_layout.addWidget(self.interval_spin)
        interval_layout.addStretch()
        config_layout.addLayout(interval_layout)

        save_layout = QVBoxLayout()
        self.save_label = QLabel("Capture Directory:")
        save_input_layout = QHBoxLayout()
        self.save_input = QLineEdit()
        self.save_input.setPlaceholderText("Default OF-Scraper Save Location")

        initial = getattr(self.plugin, "capture_dir", "") or self._default_save_dir()
        self._privacy_actual_save = initial or ""
        self.save_input.setText(initial or "")
        self.save_input.editingFinished.connect(self._remember_capture_dir)

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

        # Install / clear buttons; folded behind "Manage…" once Chromium works.
        self.setup_details = QWidget()
        details_layout = QVBoxLayout(self.setup_details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(10)

        self.install_btn = StyledButton("Install Chromium Browser", primary=True)
        self.install_btn.clicked.connect(self._on_install_chromium)
        details_layout.addWidget(self.install_btn)

        self.clear_profiles_btn = StyledButton("Clear saved browser logins")
        self.clear_profiles_btn.setToolTip(
            "Each creator's capture browser keeps its own OnlyFans login. "
            "Delete them all (the next capture logs in again from Authentication)."
        )
        self.clear_profiles_btn.clicked.connect(self._on_clear_profiles)
        details_layout.addWidget(self.clear_profiles_btn)
        browser_layout.addWidget(self.setup_details)

        self.manage_btn = StyledButton("Manage…")
        self.manage_btn.setToolTip("Reinstall Chromium or clear saved browser logins.")
        self.manage_btn.clicked.connect(
            lambda: self.setup_details.setVisible(not self.setup_details.isVisible())
        )
        self.manage_btn.hide()
        browser_layout.addWidget(self.manage_btn)

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
        self.only_live_check = QCheckBox("Only live")
        self.only_live_check.setToolTip("Show only creators who are live or being captured.")
        self.only_live_check.toggled.connect(lambda _on: self._filter_table_rows())
        filter_layout.addWidget(self.only_live_check)
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
        self.status_table.setColumnWidth(2, 200)
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
        self.status_table.itemSelectionChanged.connect(self._update_action_buttons)
        self.status_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.status_table.customContextMenuRequested.connect(self._on_table_menu)
        self.status_table.setToolTip(
            "Right-click a creator for more actions; double-click opens their recordings."
        )
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
        # Long-running monitors would otherwise grow without limit.
        self.log_output.setMaximumBlockCount(LOG_MAX_LINES)
        self.log_output.setMinimumHeight(120)
        self.log_output.setMaximumHeight(200)
        self.log_output.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        log_layout.addWidget(self.log_output)
        main_layout.addWidget(self.log_group, 0)

        self._check_browser_status()
        self._update_action_buttons()

        if getattr(self.plugin, "auto_capture", False):
            # Left on last time: start again once the page is up.
            QTimer.singleShot(1500, self._resume_auto_capture)

    def _resume_auto_capture(self):
        if self.plugin.worker is not None or self.enable_check.isChecked():
            return
        self.append_log("[System] Auto-Capture was on last time — starting it again.")
        self._on_toggle_monitor(True)

    @staticmethod
    def _default_save_dir() -> str:
        try:
            initial = get_save_location()
        except Exception:
            return ""
        try:
            from ofscraper.utils.config.path_norm import normalize_windows_path
            return normalize_windows_path(initial) or initial
        except Exception:
            return initial or ""

    def _remember_capture_dir(self):
        """Save the capture folder ("" when it is the OF-Scraper default)."""
        actual = self._capture_dir()
        self.plugin.set_page_settings(
            capture_dir="" if actual == self._default_save_dir() else actual
        )

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
        # Refresh names and Stop tooltips without waiting for the next poll.
        statuses = getattr(self, "_last_statuses", None)
        if statuses:
            self.update_status_table(statuses)

    def _check_browser_status(self):
        """Asynchronously checks if Chromium is installed and ready."""
        import sys

        if self._chromium_check is not None and self._chromium_check.isRunning():
            return  # the running check will report (and run any pending action)
        self.browser_status_label.setText("Checking Chromium browser...")
        self.install_btn.setEnabled(False)

        mod = sys.modules.get(type(self.plugin).__module__)
        WorkerCls = getattr(mod, "ChromiumCheckWorker", None) if mod else None
        if WorkerCls is None:
            ok = self.plugin.check_chromium_installed()
            self._on_chromium_check_done(ok)
            return

        self._chromium_check = WorkerCls(self.plugin)
        # Prefer completed (v1.3.2+); fall back for older plugin copies.
        sig = getattr(self._chromium_check, "completed", None) or getattr(
            self._chromium_check, "finished", None
        )
        if sig is not None:
            from PyQt6.QtCore import Qt

            sig.connect(
                self._on_chromium_check_done, Qt.ConnectionType.QueuedConnection
            )
        self._chromium_check.start()

    def _on_chromium_check_done(self, is_installed: bool):
        self.install_btn.setEnabled(True)
        self.plugin.chromium_ready = bool(is_installed)
        if is_installed:
            self.browser_status_label.setText("🟢 Chromium ready")
            self.install_btn.setText("Reinstall Chromium")
        else:
            self.browser_status_label.setText(
                "❌ Playwright Chromium is missing. Auto-capture requires Chromium."
            )
            self.install_btn.setText("Install Chromium Browser")
        self.setup_details.setVisible(not is_installed)
        self.manage_btn.setVisible(bool(is_installed))

        action, self._pending_chromium_action = self._pending_chromium_action, None
        if action is None:
            return
        if not is_installed:
            dlg = ChromiumSetupDialog(self.plugin, parent=self)
            if not (dlg.exec() and dlg.was_successful()):
                self.append_log("[Warning] This needs Playwright Chromium. Install it first.")
                return
        action()

    def _with_chromium(self, action, what: str):
        """Run *action* once Chromium is known to work.

        The check launches a browser, so it runs in the background (never on
        the GUI thread); a cached good result skips it.
        """
        if getattr(self.plugin, "chromium_ready", None) is True:
            action()
            return
        self.append_log(f"[System] Checking Chromium before {what}…")
        self._pending_chromium_action = action
        self._check_browser_status()

    def append_log(self, text):
        """Appends a new line of text to the console monitor terminal."""
        display = text
        try:
            from ofscraper.gui.utils.privacy_mode import redact_log_message
            display = redact_log_message(str(text))
        except Exception:
            display = text
        sb = self.log_output.verticalScrollBar()
        # Keep following new lines only if the reader hasn't scrolled up.
        at_bottom = sb.value() >= sb.maximum() - 4
        self.log_output.appendPlainText(display)
        if at_bottom:
            sb.setValue(sb.maximum())
        log.debug(f"[Live Monitor Console] {str(text).strip()}")

    def update_status_table(self, model_statuses):
        """Show a poll result. Rows are updated in place; the table is only
        rebuilt when the row order changes (someone went live / stopped)."""
        self._last_statuses = dict(model_statuses)
        sessions = self.plugin.session_snapshot()

        def _sort_key(k):
            s = model_statuses[k]["status"]
            order = 0 if "Recording" in s else (1 if "Connecting" in s else (2 if "Live" in s else 3))
            return (order, k)
        sorted_keys = sorted(model_statuses.keys(), key=_sort_key)

        table = self.status_table
        table.setUpdatesEnabled(False)
        if sorted_keys != self._row_usernames():
            prev_selected = self._selected_username()
            scroll = table.verticalScrollBar().value()
            table.setRowCount(0)  # drop widgets bound to the old row order
            table.setRowCount(len(sorted_keys))
            for row, username in enumerate(sorted_keys):
                self._fill_row(row, username, model_statuses[username], sessions)
            if prev_selected in sorted_keys:
                table.selectRow(sorted_keys.index(prev_selected))
            table.verticalScrollBar().setValue(scroll)
        else:
            for row, username in enumerate(sorted_keys):
                self._fill_row(row, username, model_statuses[username], sessions)
        table.setUpdatesEnabled(True)

        self._filter_table_rows(self.search_input.text())
        self._update_action_buttons()
        self._update_monitor_status()

    def _row_usernames(self) -> list:
        names = []
        for row in range(self.status_table.rowCount()):
            item = self.status_table.item(row, 0)
            names.append(item.data(Qt.ItemDataRole.UserRole) if item is not None else None)
        return names

    def _row_of(self, username: str) -> int:
        try:
            return self._row_usernames().index(username)
        except ValueError:
            return -1

    def _fill_row(self, row, username, info, sessions):
        """Create the row's cells if missing, otherwise update them."""
        table = self.status_table
        ignored = self.plugin.is_ignored(username)
        session = sessions.get(username)

        def text_item(col, text, tooltip=None):
            item = table.item(row, col)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, col, item)
            if item.text() != text:
                item.setText(text)
            if tooltip is not None:
                item.setToolTip(tooltip)
            # Ignored creators are greyed out.
            item.setForeground(QColor(c("muted")) if ignored else QBrush())
            return item

        name_item = text_item(0, _mask(username))
        name_item.setData(Qt.ItemDataRole.UserRole, username)
        text_item(1, info["subscription"])

        status_widget = table.cellWidget(row, 2)
        if status_widget is None:
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_layout.setContentsMargins(4, 4, 4, 4)
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            status_layout.addWidget(label)
            table.setCellWidget(row, 2, status_widget)
        label = status_widget.findChild(QLabel)
        if session and session[0] == "recording" and session[1] is not None:
            label.setText(self._recording_text(username, session[1]))
        else:
            label.setText(info["status"] + (" · ignored" if ignored else ""))
        label.setStyleSheet(_status_style(info["status"], ignored))

        # Counted by the poll thread: no disk access on the GUI thread.
        text_item(3, str(info.get("streams_count", 0)), info.get("streams_tooltip") or "")

        # Stop button (active capture/probe only)
        stop_wrap = table.cellWidget(row, 4)
        if stop_wrap is None:
            stop_wrap = QWidget()
            stop_lay = QHBoxLayout(stop_wrap)
            stop_lay.setContentsMargins(4, 2, 4, 2)
            stop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setCellWidget(row, 4, stop_wrap)
        stop_btn = stop_wrap.findChild(QPushButton)
        if session and stop_btn is None:
            stop_btn = QPushButton("Stop")
            stop_btn.setMinimumWidth(70)
            stop_btn.setMinimumHeight(28)
            stop_btn.setStyleSheet("QPushButton { padding: 4px 12px; min-height: 24px; }")
            stop_btn.clicked.connect(lambda _checked=False, u=username: self._stop_row(u))
            stop_wrap.layout().addWidget(stop_btn)
        elif not session and stop_btn is not None:
            stop_btn.setParent(None)
            stop_btn.deleteLater()
            stop_btn = None
        if stop_btn is not None:
            stop_btn.setToolTip(f"Stop capture/probe for {_mask(username)}")
        table.setRowHeight(row, max(table.rowHeight(row), 36))

        cb_container = table.cellWidget(row, 5)
        if cb_container is None:
            cb_container = QWidget()
            cb_layout = QHBoxLayout(cb_container)
            cb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cb_layout.setContentsMargins(0, 0, 0, 0)
            cb = QCheckBox()
            cb.toggled.connect(lambda checked, u=username: self._on_ignore_toggled(u, checked))
            cb_layout.addWidget(cb)
            table.setCellWidget(row, 5, cb_container)
        cb = cb_container.findChild(QCheckBox)
        if cb.isChecked() != ignored:
            cb.blockSignals(True)
            cb.setChecked(ignored)
            cb.blockSignals(False)

    def _recording_text(self, username, start_time) -> str:
        elapsed = max(0, int((datetime.datetime.now() - start_time).total_seconds()))
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        duration = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        size = self.plugin.recording_size(username)
        if size:
            duration += f" · {_format_size(size)}"
        return f"Recording 🔴 ({duration})"

    def _on_ignore_toggled(self, username: str, checked: bool):
        self.plugin.set_ignored(username, checked)
        row = self._row_of(username)
        info = (getattr(self, "_last_statuses", {}) or {}).get(username)
        if row >= 0 and info is not None:
            self._fill_row(row, username, info, self.plugin.session_snapshot())
        self._filter_table_rows(self.search_input.text())
        self._update_action_buttons()

    def _update_action_buttons(self):
        """Enable only the buttons that can do something right now."""
        sessions = self.plugin.session_snapshot()
        username = self._selected_username()
        selected = bool(username)
        ignored = selected and self.plugin.is_ignored(username)
        busy = selected and username in sessions

        can_start = selected and not ignored and not busy
        self.capture_selected_btn.setEnabled(can_start)
        self.probe_selected_btn.setEnabled(can_start)
        self.fetch_api_btn.setEnabled(selected)
        self.stop_all_btn.setEnabled(bool(sessions))

    def _update_monitor_status(self):
        """Header line: is the poller alive, when it last/next checks, counts."""
        worker = self.plugin.worker
        if worker is None:
            self.monitor_status_label.setText("Monitor off")
            return
        if worker.polling or worker.last_poll_at is None:
            text = "Checking subscriptions…"
        else:
            last = datetime.datetime.fromtimestamp(worker.last_poll_at)
            text = f"Last check {last:%H:%M:%S}"
            if not worker.last_poll_ok:
                text += " (failed — see console)"
            wait = int((worker.next_poll_at or 0) - time.time())
            text += f" · next in {wait}s" if wait > 0 else " · checking soon"
        statuses = getattr(self, "_last_statuses", {}) or {}
        live = sum(1 for info in statuses.values() if info.get("is_live"))
        recording = sum(
            1 for kind, _ in self.plugin.session_snapshot().values() if kind == "recording"
        )
        text += f" · {live} live"
        if recording:
            text += f" · {recording} recording"
        self.monitor_status_label.setText(text)

    def _tick_recording_timers(self):
        """Update recording durations every second without waiting for a poll."""
        self._update_monitor_status()
        self._update_action_buttons()
        for username, (kind, start_time) in self.plugin.session_snapshot().items():
            if kind != "recording" or start_time is None:
                continue
            row = self._row_of(username)
            widget = self.status_table.cellWidget(row, 2) if row >= 0 else None
            label = widget.findChild(QLabel) if widget is not None else None
            if label is not None:
                label.setText(self._recording_text(username, start_time))

    def _filter_table_rows(self, text=None):
        """Filter rows by name (real or masked) and, optionally, live only."""
        text = (self.search_input.text() if text is None else text).lower().strip()
        only_live = self.only_live_check.isChecked()
        statuses = getattr(self, "_last_statuses", {}) or {}
        sessions = self.plugin.session_snapshot() if only_live else {}
        for row in range(self.status_table.rowCount()):
            username_item = self.status_table.item(row, 0)
            if username_item is None:
                continue
            real = username_item.data(Qt.ItemDataRole.UserRole) or username_item.text()
            display = username_item.text()
            show = (not text) or (text in str(real).lower()) or (text in display.lower())
            if show and only_live:
                show = real in sessions or bool((statuses.get(real) or {}).get("is_live"))
            self.status_table.setRowHidden(row, not show)

    def _on_cell_double_clicked(self, row, column):
        """Double clicking opens creator's Live Streams output directory."""
        username_item = self.status_table.item(row, 0)
        if username_item is None:
            return
        self._open_recordings(username_item.data(Qt.ItemDataRole.UserRole) or username_item.text())

    def _recordings_dir(self, username: str) -> Path:
        return Path(self._capture_dir()) / username / "Live_Streams"

    def _open_recordings(self, username: str):
        path = self._recordings_dir(username)
        if not path.is_dir():
            # Don't create empty folders just by clicking around.
            self.append_log(f"[Info] No recordings yet for {_mask(username)}.")
            return
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    # ---------- 7: right-click menu on a table row ----------
    def _on_table_menu(self, pos):
        row = self.status_table.rowAt(pos.y())
        if row < 0:
            return
        self.status_table.selectRow(row)
        username = self._selected_username()
        if not username:
            return
        sessions = self.plugin.session_snapshot()
        ignored = self.plugin.is_ignored(username)
        busy = username in sessions
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode

        menu = QMenu(self)
        capture = menu.addAction("Capture now")
        capture.setEnabled(not ignored and not busy)
        capture.triggered.connect(self._on_capture_selected)
        if self.show_diag_check.isChecked():
            probe = menu.addAction("Probe now")
            probe.setEnabled(not ignored and not busy)
            probe.triggered.connect(self._on_probe_selected)
        stop = menu.addAction("Stop")
        stop.setEnabled(busy)
        stop.triggered.connect(lambda: self._stop_row(username))
        menu.addSeparator()
        menu.addAction("Open recordings folder").triggered.connect(
            lambda: self._open_recordings(username)
        )
        ignore = menu.addAction("Ignore")
        ignore.setCheckable(True)
        ignore.setChecked(ignored)
        ignore.triggered.connect(lambda checked: self._on_ignore_toggled(username, checked))
        if not is_privacy_mode():
            menu.addAction("Copy name").triggered.connect(
                lambda: QApplication.clipboard().setText(username)
            )
        menu.exec(self.status_table.viewport().mapToGlobal(pos))
        return menu

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
    def _on_toggle_no_window(self, checked):
        self.plugin.set_page_settings(no_window=bool(checked))
        # "Hide capture window" only matters when there is a window.
        self.headless_check.setEnabled(not checked)
        mode = "without a window (headless)" if checked else "in a Chrome window"
        self.append_log(f"[System] New captures run {mode}.")

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
        save_dir = self._capture_dir()

        def _go():
            self.append_log(f"[Probe] Starting one-shot diagnostics for {username}...")
            self.plugin.start_probe(username, save_dir)

        self._with_chromium(_go, "the probe")

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
        save_dir = self._capture_dir()

        def _go():
            self.append_log(f"[Capture] Starting Playwright capture for {username}…")
            self.plugin.start_recording(username, save_dir)

        self._with_chromium(_go, "capturing")

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
            self.append_log(f"[API] Fetch failed for {username}: {type(e).__name__}: {e}")

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
            # Stay unchecked until the (background) Chromium check passes.
            self.enable_check.blockSignals(True)
            self.enable_check.setChecked(False)
            self.enable_check.blockSignals(False)
            self._with_chromium(self._start_monitor_now, "starting the monitor")
        else:
            self.append_log("[System] Stopping Live Stream Monitor...")
            self.plugin.set_page_settings(auto_capture=False)
            self.save_input.setEnabled(True)
            self.browse_btn.setEnabled(True)
            self.interval_spin.setEnabled(True)
            self.plugin.stop_monitor()
            self._apply_privacy_to_save_field()

    def _start_monitor_now(self):
        if self.plugin.worker is not None:
            return
        self.enable_check.blockSignals(True)
        self.enable_check.setChecked(True)
        self.enable_check.blockSignals(False)
        self.append_log("[System] Starting Live Stream Monitor...")
        self.save_input.setEnabled(False)
        self.browse_btn.setEnabled(False)
        self.interval_spin.setEnabled(False)
        try:
            self.plugin.set_headless_capture(self.headless_check.isChecked())
            self.plugin.set_probe_mode(self.probe_check.isChecked())
        except Exception:
            pass

        self._remember_capture_dir()
        self.plugin.set_page_settings(
            auto_capture=True, poll_interval=self.interval_spin.value()
        )
        self.plugin.start_monitor(
            interval=self.interval_spin.value(),
            save_location=self._capture_dir(),
        )
        self._update_monitor_status()

    @pyqtSlot()
    def handle_auth_error(self):
        # Uncheck without going through the normal Stop path that kills captures.
        self.enable_check.blockSignals(True)
        self.enable_check.setChecked(False)
        self.enable_check.blockSignals(False)
        # Don't auto-start next launch with broken auth.
        self.plugin.set_page_settings(auto_capture=False)
        self.save_input.setEnabled(True)
        self.browse_btn.setEnabled(True)
        self.interval_spin.setEnabled(True)
        try:
            self.plugin.stop_monitor(terminate_recordings=False)
        except Exception:
            pass
        active = []
        try:
            active = list(self.plugin.session_snapshot())
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
            self._remember_capture_dir()
            self.append_log(f"[Config] Save directory set to: {dir_path}")

    @pyqtSlot()
    def _on_clear_profiles(self):
        reply = QMessageBox.question(
            self,
            "Clear saved browser logins",
            "Delete the saved OnlyFans logins of the capture browser (one per "
            "creator)?\n\nThe next capture logs in again using your "
            "Authentication settings.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n = self.plugin.clear_browser_profiles()
            self.append_log(f"[System] Cleared {n} saved browser login(s).")
        except Exception as e:
            self.append_log(f"[Error] Could not clear browser logins: {e}")

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
