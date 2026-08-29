"""Unified scrape status strip — phase, health, message, progress, daemon, row count."""
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import scale_px
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.progress_panel import ProgressSummaryBar

# "running" is the active scrape/download phase (shown as Running).
_PHASE_LABELS = {
    "ready": "Ready",
    "running": "Running",
    "scraping": "Running",  # alias for host/workflow callers
    "cancelling": "Cancelling",
    "daemon": "Daemon",
    "complete": "Complete",
}

_PHASE_COLORS = {
    "ready": "overlay1",
    "running": "blue",
    "scraping": "blue",
    "cancelling": "peach",
    "daemon": "yellow",
    "complete": "green",
}

_HEALTH_LEVEL_COLORS = {
    "ok": "green",
    "warn": "peach",
    "error": "red",
}


def _format_elapsed(seconds: int) -> str:
    """Compact elapsed clock: ``m:ss`` or ``h:mm:ss``."""
    s = max(0, int(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def _help_btn_qss():
    return (
        f"QToolButton {{ border: 1px solid {c('surface1')}; border-radius: 9px;"
        f" background-color: {c('surface0')}; color: {c('text')}; font-weight: bold; }}"
        f" QToolButton:hover {{ border-color: {c('blue')}; background-color: {c('surface1')}; }}"
    )


class _HealthChipLabel(QLabel):
    """Compact clickable health badge."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._navigate = "config"
        self.setObjectName("statusHealthChip")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("")

    def set_chip(self, text: str, level: str, detail: str, navigate: str):
        self.setText(text)
        self._navigate = navigate or "config"
        self.setToolTip(detail or "")
        accent = c(_HEALTH_LEVEL_COLORS.get(level, "overlay1"))
        base = c("base")
        self.setStyleSheet(
            f"QLabel#statusHealthChip {{"
            f" background-color: {accent}; color: {base};"
            f" border-radius: 6px; padding: 2px 8px; font-weight: bold;"
            f" font-size: {scale_px(11)}px; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._navigate:
            app_signals.navigate_to_page.emit(self._navigate)
            event.accept()
            return
        super().mousePressEvent(event)


class StatusStrip(QWidget):
    """Single footer strip driven by host-callback signals.

    Shows scrape phase, auth/config/key health chips, latest status text,
    download progress, optional daemon countdown + last-run chip, and table
    row count — so users are not hunting across the window title bar, toolbar,
    and status bar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = "ready"
        self._scrape_t0 = None
        self._setup_ui()
        self._connect_signals()
        self.apply_theme()
        self.set_phase("ready")
        self.refresh_health()

    def _setup_ui(self):
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 2, 12, 2)
        layout.setSpacing(8)

        self.phase_badge = QLabel("Ready")
        self.phase_badge.setObjectName("statusPhaseBadge")
        self.phase_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_badge.setFixedHeight(22)
        self.phase_badge.setMinimumWidth(92)
        layout.addWidget(self.phase_badge)

        self.elapsed_label = QLabel("")
        self.elapsed_label.setObjectName("statusElapsedChip")
        self.elapsed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.elapsed_label.setFixedHeight(22)
        self.elapsed_label.setMinimumWidth(52)
        self.elapsed_label.setToolTip("Elapsed scrape time")
        self.elapsed_label.hide()
        layout.addWidget(self.elapsed_label)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        self.auth_chip = _HealthChipLabel()
        self.config_chip = _HealthChipLabel()
        self.key_chip = _HealthChipLabel()
        for chip in (self.auth_chip, self.config_chip, self.key_chip):
            layout.addWidget(chip)

        self.status_label = QLabel("Ready")
        self.status_label.setProperty("muted", True)
        self.status_label.setMinimumWidth(100)
        self.status_label.setMaximumWidth(320)
        self.status_label.setToolTip("")
        layout.addWidget(self.status_label, stretch=0)

        self.progress_summary = ProgressSummaryBar()
        layout.addWidget(self.progress_summary, stretch=1)

        self.last_run_label = QLabel("")
        self.last_run_label.setObjectName("statusLastRunChip")
        self.last_run_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.last_run_label.setFixedHeight(22)
        self.last_run_label.hide()
        layout.addWidget(self.last_run_label)

        self.daemon_label = QLabel("")
        self.daemon_label.setObjectName("statusDaemonChip")
        self.daemon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.daemon_label.setFixedHeight(22)
        self.daemon_label.hide()
        layout.addWidget(self.daemon_label)

        self.row_count_label = QLabel("0 rows")
        self.row_count_label.setProperty("muted", True)
        layout.addWidget(self.row_count_label)

        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip("Open table help")
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setAutoRaise(True)
        help_btn.setFixedSize(18, 18)
        help_btn.setStyleSheet(_help_btn_qss())
        help_btn.clicked.connect(self._on_help_clicked)
        layout.addWidget(help_btn)

    def _connect_signals(self):
        # Use bound methods (not lambdas) so PyQt keeps the slot alive.
        app_signals.scrape_phase_changed.connect(self.set_phase)
        app_signals.status_message.connect(self._on_status_message)
        app_signals.daemon_next_run.connect(self._on_daemon_text)
        app_signals.daemon_last_run.connect(self._on_daemon_last_run)
        app_signals.daemon_run_starting.connect(self._on_daemon_run_starting)
        app_signals.daemon_stopped.connect(self._on_daemon_stopped)
        app_signals.scrape_started.connect(self._on_scrape_started)
        app_signals.scraping_finished.connect(self._on_scraping_finished)
        app_signals.overall_progress_updated.connect(self._on_progress_updated)
        app_signals.theme_changed.connect(self._on_theme_changed)
        app_signals.config_updated.connect(self.refresh_health)
        app_signals.auth_updated.connect(self.refresh_health)
        app_signals.health_refresh_requested.connect(self.refresh_health)

    def apply_theme(self):
        # Scope to this widget so child badge styles are not wiped out.
        self.setStyleSheet(
            f"StatusStrip {{ background-color: {c('mantle')}; }}"
        )
        self._apply_phase_badge_style()
        self._apply_daemon_chip_styles()
        self.refresh_health()
        try:
            for btn in self.findChildren(QToolButton):
                if btn.text() == "?":
                    btn.setStyleSheet(_help_btn_qss())
        except Exception:
            pass

    def _apply_phase_badge_style(self):
        color_key = _PHASE_COLORS.get(self._phase, "overlay1")
        accent = c(color_key)
        base = c("base")
        self.phase_badge.setStyleSheet(
            f"QLabel#statusPhaseBadge {{"
            f" background-color: {accent}; color: {base};"
            f" border-radius: 6px; padding: 2px 10px; font-weight: bold;"
            f" font-size: {scale_px(11)}px; }}"
        )

    def _apply_daemon_chip_styles(self):
        yellow = c("yellow")
        base = c("base")
        surface = c("surface1")
        text = c("text")
        self.daemon_label.setStyleSheet(
            f"QLabel#statusDaemonChip {{"
            f" background-color: {yellow}; color: {base};"
            f" border-radius: 6px; padding: 2px 10px; font-weight: bold;"
            f" font-size: {scale_px(11)}px; }}"
        )
        self.last_run_label.setStyleSheet(
            f"QLabel#statusLastRunChip {{"
            f" background-color: {surface}; color: {text};"
            f" border-radius: 6px; padding: 2px 10px; font-weight: bold;"
            f" font-size: {scale_px(11)}px; }}"
        )
        self.elapsed_label.setStyleSheet(
            f"QLabel#statusElapsedChip {{"
            f" background-color: {surface}; color: {text};"
            f" border-radius: 6px; padding: 2px 8px; font-weight: bold;"
            f" font-size: {scale_px(11)}px; font-family: Consolas, 'Courier New', monospace; }}"
        )

    def _start_elapsed(self):
        """Begin (or restart) the live scrape elapsed clock."""
        self._scrape_t0 = time.monotonic()
        self._tick_elapsed()
        self.elapsed_label.show()
        if not self._elapsed_timer.isActive():
            self._elapsed_timer.start()

    def _stop_elapsed(self, *, keep_visible: bool = True):
        """Stop ticking; optionally keep the final elapsed value visible."""
        try:
            self._elapsed_timer.stop()
        except Exception:
            pass
        if self._scrape_t0 is not None:
            self._tick_elapsed()
        if not keep_visible:
            self.elapsed_label.hide()
            self.elapsed_label.setText("")
            self._scrape_t0 = None

    @pyqtSlot()
    def _tick_elapsed(self):
        if self._scrape_t0 is None:
            return
        try:
            elapsed = int(time.monotonic() - self._scrape_t0)
            text = _format_elapsed(elapsed)
            self.elapsed_label.setText(text)
            self.elapsed_label.setToolTip(f"Elapsed scrape time: {text}")
        except Exception:
            pass

    @pyqtSlot()
    def refresh_health(self):
        """Recheck auth / config / key-mode and update the three chips."""
        try:
            from ofscraper.gui.utils.health_check import gather_health

            chips = {item.key: item for item in gather_health()}
        except Exception:
            chips = {}

        mapping = {
            "auth": self.auth_chip,
            "config": self.config_chip,
            "key": self.key_chip,
        }
        defaults = {
            "auth": ("Auth ?", "warn", "Health check unavailable", "auth"),
            "config": ("Config ?", "warn", "Health check unavailable", "config"),
            "key": ("Key ?", "warn", "Health check unavailable", "config"),
        }
        for key, widget in mapping.items():
            item = chips.get(key)
            if item is None:
                text, level, detail, nav = defaults[key]
                widget.set_chip(text, level, detail, nav)
            else:
                widget.set_chip(item.text, item.level, item.detail, item.navigate)

    @pyqtSlot(str)
    def set_phase(self, phase: str):
        phase = (phase or "ready").strip().lower()
        if phase == "scraping":
            phase = "running"
        if phase not in _PHASE_LABELS:
            phase = "ready"
        # Store canonical phase (scraping alias already mapped to running).
        self._phase = "running" if phase == "running" else phase
        self.phase_badge.setText(_PHASE_LABELS[self._phase])
        self._apply_phase_badge_style()
        if self._phase in ("running", "cancelling"):
            if self._scrape_t0 is None:
                self._start_elapsed()
        elif self._phase == "complete":
            self._stop_elapsed(keep_visible=True)
        elif self._phase in ("ready", "daemon"):
            self._stop_elapsed(keep_visible=False)

    @pyqtSlot()
    def _on_scrape_started(self):
        self._start_elapsed()
        self.set_phase("running")
        self.refresh_health()

    @pyqtSlot()
    def _on_help_clicked(self):
        app_signals.help_anchor_requested.emit("table-columns")

    @pyqtSlot(bool)
    def _on_theme_changed(self, _is_dark: bool):
        self.apply_theme()

    @pyqtSlot(str)
    def _on_status_message(self, message: str):
        text = (message or "").strip() or "Ready"
        try:
            from ofscraper.gui.utils.privacy_mode import redact_status_message

            text = redact_status_message(text)
        except Exception:
            pass
        display = text if len(text) <= 64 else text[:61] + "…"
        self.status_label.setText(display)
        self.status_label.setToolTip(text)

    @pyqtSlot(str)
    def _on_daemon_text(self, text: str):
        t = (text or "").strip()
        if not t:
            self.daemon_label.hide()
            return
        self.daemon_label.setText(t)
        self.daemon_label.setToolTip(t)
        self.daemon_label.show()
        if self._phase not in ("running", "cancelling"):
            self.set_phase("daemon")

    @pyqtSlot(str)
    def _on_daemon_last_run(self, text: str):
        t = (text or "").strip()
        if not t:
            self.last_run_label.hide()
            return
        self.last_run_label.setText(t)
        self.last_run_label.setToolTip(t)
        self.last_run_label.show()

    @pyqtSlot(int)
    def _on_daemon_run_starting(self, run_number: int):
        self.daemon_label.setText(f"Daemon run #{int(run_number)}…")
        self.daemon_label.setToolTip(self.daemon_label.text())
        self.daemon_label.show()
        self._start_elapsed()
        self.set_phase("running")

    @pyqtSlot()
    def _on_daemon_stopped(self):
        self.daemon_label.hide()
        self.last_run_label.hide()
        if self._phase == "daemon":
            self.set_phase("ready")

    @pyqtSlot()
    def _on_scraping_finished(self):
        self._stop_elapsed(keep_visible=True)
        if self.daemon_label.isVisible() and self.daemon_label.text():
            self.set_phase("daemon")
        elif self.last_run_label.isVisible():
            # Between runs: keep Daemon badge so wait state is obvious.
            self.set_phase("daemon")
        elif self._phase == "cancelling":
            self.set_phase("ready")
        elif self._phase in ("running", "scraping"):
            self.set_phase("complete")
        self.refresh_health()

    @pyqtSlot(int, int)
    def _on_progress_updated(self, completed: int, total: int):
        """If downloads are actively progressing, never leave the badge on Ready."""
        try:
            if total > 0 and completed < total and self._phase in (
                "ready",
                "complete",
            ):
                self.set_phase("running")
        except Exception:
            pass

    def clear_progress(self):
        try:
            self.progress_summary.clear_all()
        except Exception:
            pass

    def set_row_count(self, visible: int, total: int | None = None):
        if total is not None and total != visible:
            self.row_count_label.setText(f"{visible} / {total} rows")
        else:
            self.row_count_label.setText(f"{visible} rows")
