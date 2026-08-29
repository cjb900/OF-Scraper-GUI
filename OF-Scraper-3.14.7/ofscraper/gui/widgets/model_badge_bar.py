"""Live per-model success/fail badges during a scrape."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import scale_px
from ofscraper.gui.styles import c

_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_OK = "ok"
_STATUS_FAIL = "fail"

_STATUS_MARK = {
    _STATUS_PENDING: "○",
    _STATUS_RUNNING: "●",
    _STATUS_OK: "✓",
    _STATUS_FAIL: "✗",
}

_STATUS_COLOR = {
    _STATUS_PENDING: "overlay1",
    _STATUS_RUNNING: "blue",
    _STATUS_OK: "green",
    _STATUS_FAIL: "red",
}


def _display_name(username: str) -> str:
    try:
        from ofscraper.gui.utils.privacy_mode import mask_username

        masked = mask_username(username)
        return masked if masked else (username or "?")
    except Exception:
        return username or "?"


class ModelBadgeBar(QWidget):
    """Compact scrollable chip row: one badge per selected model.

    Updated live via ``model_badges_reset`` / ``model_item_started`` /
    ``model_item_result``. Hidden when idle (no models tracked).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._order: list[str] = []
        self._status: dict[str, str] = {}
        self._errors: dict[str, str] = {}
        self._chips: dict[str, QLabel] = {}
        self._setup_ui()
        self._connect_signals()
        self.apply_theme()
        self.hide()

    def _setup_ui(self):
        self.setFixedHeight(30)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 2, 12, 2)
        root.setSpacing(8)

        self.summary_label = QLabel("Models")
        self.summary_label.setProperty("muted", True)
        self.summary_label.setMinimumWidth(120)
        root.addWidget(self.summary_label)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setFixedHeight(26)

        self._chip_host = QWidget()
        self._chip_layout = QHBoxLayout(self._chip_host)
        self._chip_layout.setContentsMargins(0, 0, 0, 0)
        self._chip_layout.setSpacing(6)
        self._chip_layout.addStretch(1)
        self._scroll.setWidget(self._chip_host)
        root.addWidget(self._scroll, stretch=1)

    def _connect_signals(self):
        # QueuedConnection: scrape thread emits these; slots must run on the GUI thread.
        queued = Qt.ConnectionType.QueuedConnection
        app_signals.model_badges_reset.connect(self.reset_models, queued)
        app_signals.model_item_started.connect(self.set_running, queued)
        app_signals.model_item_result.connect(self.set_result, queued)
        app_signals.scrape_started.connect(self._on_scrape_started, queued)
        app_signals.scraping_finished.connect(self._on_scraping_finished, queued)
        app_signals.theme_changed.connect(self._on_theme_changed)
        app_signals.privacy_mode_changed.connect(self._on_privacy_changed)

    def apply_theme(self):
        self.setStyleSheet(f"ModelBadgeBar {{ background-color: {c('mantle')}; }}")
        self._refresh_all_chips()
        self._update_summary()

    @pyqtSlot(bool)
    def _on_theme_changed(self, _is_dark: bool):
        self.apply_theme()

    @pyqtSlot(bool)
    def _on_privacy_changed(self, _enabled: bool):
        self._refresh_all_chips()

    @pyqtSlot()
    def _on_scrape_started(self):
        # Keep visible once models are registered; reset alone may race.
        if self._order:
            self.show()

    @pyqtSlot()
    def _on_scraping_finished(self):
        # Safety net: any model still "running" when the scrape ends → ok
        # (result emit may have been lost); leave true failures as-is.
        for name, status in list(self._status.items()):
            if status == _STATUS_RUNNING:
                self._status[name] = _STATUS_OK
                self._style_chip(name)
        self._update_summary()

    @pyqtSlot(list)
    def reset_models(self, usernames):
        names = []
        for u in usernames or []:
            name = str(u or "").strip()
            if name and name not in names:
                names.append(name)
        self._clear_chips()
        self._order = names
        self._status = {n: _STATUS_PENDING for n in names}
        self._errors = {}
        for name in names:
            self._add_chip(name)
        self._update_summary()
        if names:
            self.show()
        else:
            self.hide()

    @pyqtSlot(str)
    def set_running(self, username: str):
        name = str(username or "").strip()
        if not name:
            return
        if name not in self._status:
            self._order.append(name)
            self._status[name] = _STATUS_PENDING
            self._add_chip(name)
            self.show()
        self._status[name] = _STATUS_RUNNING
        self._errors.pop(name, None)
        self._style_chip(name)
        self._update_summary()

    @pyqtSlot(str, bool, str)
    def set_result(self, username: str, ok: bool, error: str = ""):
        name = str(username or "").strip()
        if not name:
            return
        if name not in self._status:
            self._order.append(name)
            self._add_chip(name)
            self.show()
        self._status[name] = _STATUS_OK if ok else _STATUS_FAIL
        err = (error or "").strip()
        if ok:
            self._errors.pop(name, None)
        elif err:
            self._errors[name] = err[:300]
        else:
            self._errors[name] = "One or more downloads failed"
        self._style_chip(name)
        self._update_summary()

    def _clear_chips(self):
        for chip in list(self._chips.values()):
            self._chip_layout.removeWidget(chip)
            chip.deleteLater()
        self._chips.clear()

    def _add_chip(self, name: str):
        if name in self._chips:
            return
        chip = QLabel()
        chip.setObjectName("modelResultChip")
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setFixedHeight(22)
        # Insert before the trailing stretch
        idx = max(0, self._chip_layout.count() - 1)
        self._chip_layout.insertWidget(idx, chip)
        self._chips[name] = chip
        self._style_chip(name)

    def _refresh_all_chips(self):
        for name in self._order:
            self._style_chip(name)

    def _style_chip(self, name: str):
        chip = self._chips.get(name)
        if chip is None:
            return
        status = self._status.get(name, _STATUS_PENDING)
        mark = _STATUS_MARK.get(status, "○")
        color_key = _STATUS_COLOR.get(status, "overlay1")
        accent = c(color_key)
        base = c("base")
        surface = c("surface0")
        shown = _display_name(name)
        chip.setText(f"{mark} {shown}")
        try:
            from ofscraper.gui.utils.privacy_mode import is_privacy_mode

            private = is_privacy_mode()
        except Exception:
            private = False
        tip_name = shown if private else name
        err = self._errors.get(name)
        if err:
            tip = f"{tip_name}: failed — {err}"
        elif status == _STATUS_OK:
            tip = f"{tip_name}: ok"
        elif status == _STATUS_RUNNING:
            tip = f"{tip_name}: in progress"
        else:
            tip = f"{tip_name}: waiting"
        chip.setToolTip(tip)
        if status in (_STATUS_OK, _STATUS_FAIL):
            bg, fg = accent, base
        else:
            bg, fg = surface, accent
        chip.setStyleSheet(
            f"QLabel#modelResultChip {{"
            f" background-color: {bg}; color: {fg};"
            f" border: 1px solid {accent}; border-radius: 6px;"
            f" padding: 1px 8px; font-size: {scale_px(11)}px; font-weight: bold; }}"
        )

    def _update_summary(self):
        total = len(self._order)
        if total == 0:
            self.summary_label.setText("Models")
            self.summary_label.setToolTip("")
            return
        ok_n = sum(1 for s in self._status.values() if s == _STATUS_OK)
        fail_n = sum(1 for s in self._status.values() if s == _STATUS_FAIL)
        run_n = sum(1 for s in self._status.values() if s == _STATUS_RUNNING)
        pend_n = sum(1 for s in self._status.values() if s == _STATUS_PENDING)
        done = ok_n + fail_n
        self.summary_label.setText(
            f"Models {done}/{total}  ✓{ok_n}  ✗{fail_n}"
            + (f"  ●{run_n}" if run_n else "")
            + (f"  ○{pend_n}" if pend_n else "")
        )
        self.summary_label.setToolTip(
            f"Per-model results this scrape: {ok_n} ok, {fail_n} failed, "
            f"{run_n} running, {pend_n} waiting"
        )
