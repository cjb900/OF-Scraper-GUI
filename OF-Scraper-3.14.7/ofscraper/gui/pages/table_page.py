import logging

import os
import subprocess as _subprocess
import sys as _sys

from PyQt6.QtCore import QEvent, Qt, QTimer, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font, scale_px
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.console_log import ConsoleLogWidget
from ofscraper.gui.widgets.data_table import MediaDataTable
from ofscraper.gui.widgets.flow_layout import FlowLayout
from ofscraper.gui.widgets.model_badge_bar import ModelBadgeBar
from ofscraper.gui.widgets.sidebar import FilterSidebar
from ofscraper.gui.widgets.status_strip import StatusStrip
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

# Cart / Send Downloads toolbar is only for check modes (manual queue).
_CHECK_MODES = {"post_check", "msg_check", "paid_check", "story_check"}
# Default console pane height (matches initial splitter sizes / old fixed panel).
_DEFAULT_CONSOLE_HEIGHT = 180

def _help_btn_qss():
    return (
        f"QToolButton {{ border: 1px solid {c('surface1')}; border-radius: 9px;"
        f" background-color: {c('surface0')}; color: {c('text')}; font-weight: bold; }}"
        f" QToolButton:hover {{ border-color: {c('blue')}; background-color: {c('surface1')}; }}"
    )

def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(_help_btn_qss())
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b


class TablePage(QWidget):
    """Main workspace page combining data table, filter sidebar,
    console log, and progress panel. Replaces the Textual InputApp."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._scrape_active = False
        self._cancelling = False
        self._pending_new_scrape_nav = False
        self._pending_reset = False
        self._live_rows_loaded = False
        self._check_mode_active = False
        self._setup_ui()
        self._connect_signals()
        self._update_cart_toolbar_visibility()

    def _reset_scrape_controls(self):
        """Reset toolbar state to a ready-to-scrape baseline."""
        try:
            self._scrape_active = False
            self._cancelling = False
            self.start_scraping_btn.setEnabled(True)
            self.start_scraping_btn.setText("Start Scraping >>")
        except Exception:
            pass
        try:
            self.cancel_scrape_btn.hide()
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.setText("Cancel")
        except Exception:
            pass
        try:
            self.stop_daemon_btn.hide()
            self.stop_daemon_btn.setEnabled(True)
            self.stop_daemon_btn.setText("Stop Daemon")
        except Exception:
            pass
        try:
            self.daemon_status_label.hide()
        except Exception:
            pass
        try:
            self._check_mode_active = False
            self._update_cart_toolbar_visibility()
        except Exception:
            pass

    def _enter_cancelling_ui(self, status_text="Cancelling… finishing current work"):
        """Disable Start and show Cancelling state until scraping_finished."""
        self._cancelling = True
        self._scrape_active = True
        try:
            self.start_scraping_btn.setEnabled(False)
            self.start_scraping_btn.setText("Cancelling...")
        except Exception:
            pass
        try:
            self.cancel_scrape_btn.show()
            self.cancel_scrape_btn.setEnabled(False)
            self.cancel_scrape_btn.setText("Cancelling...")
        except Exception:
            pass
        try:
            self.daemon_status_label.setText(status_text)
            self.daemon_status_label.show()
        except Exception:
            pass
        try:
            app_signals.scrape_phase_changed.emit("cancelling")
            app_signals.status_message.emit(status_text)
        except Exception:
            pass

    def _navigate_to_action_page(self):
        main_window = self.window()
        scraper_stack = getattr(main_window, "scraper_stack", None)
        if scraper_stack:
            scraper_stack.setCurrentIndex(0)  # action page

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Top toolbar (flow layout wraps to extra rows on narrow displays) --
        self._toolbar = toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {c('mantle')};")
        self._toolbar_flow = FlowLayout(toolbar, margin=8, h_spacing=6, v_spacing=4)

        self.toggle_sidebar_btn = StyledButton("◀  Filters")
        self.toggle_sidebar_btn.setCheckable(True)
        self.toggle_sidebar_btn.setChecked(True)
        self.toggle_sidebar_btn.setToolTip("Click to hide the filter sidebar")
        self.toggle_sidebar_btn.clicked.connect(self._toggle_sidebar)
        self._toolbar_flow.addWidget(self.toggle_sidebar_btn)

        self.reset_btn = StyledButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        self._toolbar_flow.addWidget(self.reset_btn)

        self.filter_btn = StyledButton("Apply Filters", primary=True)
        self.filter_btn.clicked.connect(self._on_filter)
        self._toolbar_flow.addWidget(self.filter_btn)

        self.start_scraping_btn = StyledButton("Start Scraping >>", primary=True)
        self.start_scraping_btn.setFixedHeight(36)
        apply_font(self.start_scraping_btn, "Segoe UI", 12, QFont.Weight.Bold)
        self.start_scraping_btn.clicked.connect(self._on_start_scraping)
        self._toolbar_flow.addWidget(self.start_scraping_btn)

        self.cancel_scrape_btn = StyledButton("Cancel")
        self.cancel_scrape_btn.setFixedHeight(36)
        self.cancel_scrape_btn.setToolTip(
            "Stop the current scrape. Waits for in-flight work, then force-stops if needed."
        )
        self.cancel_scrape_btn.clicked.connect(self._on_cancel_scrape_clicked)
        self.cancel_scrape_btn.hide()
        self._toolbar_flow.addWidget(self.cancel_scrape_btn)

        self.new_scrape_btn = StyledButton("New Scrape")
        self.new_scrape_btn.setFixedHeight(36)
        self.new_scrape_btn.clicked.connect(self._on_new_scrape)
        self._toolbar_flow.addWidget(self.new_scrape_btn)

        self.open_folder_btn = StyledButton("Open Downloads Folder")
        self.open_folder_btn.setFixedHeight(36)
        self.open_folder_btn.setToolTip(
            "Open the configured download save location in your file manager"
        )
        self.open_folder_btn.clicked.connect(self._on_open_downloads_folder)
        self._toolbar_flow.addWidget(self.open_folder_btn)

        self.history_btn = StyledButton("History")
        self.history_btn.setFixedHeight(36)
        self.history_btn.setToolTip(
            "Browse recent scrape runs — filter, details, re-run, or delete"
        )
        self.history_btn.clicked.connect(self._on_history_clicked)
        self._toolbar_flow.addWidget(self.history_btn)

        self.export_csv_btn = StyledButton("Export CSV")
        self.export_csv_btn.setFixedHeight(36)
        self.export_csv_btn.setToolTip(
            "Export visible (filtered) table rows to a CSV file — "
            "or only the current selection if you choose"
        )
        self.export_csv_btn.clicked.connect(self._on_export_csv)
        self._toolbar_flow.addWidget(self.export_csv_btn)

        self.stop_daemon_btn = StyledButton("Stop Daemon")
        self.stop_daemon_btn.setFixedHeight(36)
        self.stop_daemon_btn.clicked.connect(self._on_stop_daemon)
        self.stop_daemon_btn.hide()
        self._toolbar_flow.addWidget(self.stop_daemon_btn)

        self.daemon_status_label = QLabel("")
        apply_font(self.daemon_status_label, "Segoe UI", 10)
        self.daemon_status_label.hide()
        self._toolbar_flow.addWidget(self.daemon_status_label)

        # Check-mode cart controls (hidden for normal scrapes)
        self.cart_label = QLabel("Cart: 0 items")
        self.cart_label.setProperty("subheading", True)
        self._toolbar_flow.addWidget(self.cart_label)

        self.select_all_cart_btn = StyledButton("Select All")
        self.select_all_cart_btn.setToolTip(
            "Add all visible unlocked rows to the download cart"
        )
        self.select_all_cart_btn.clicked.connect(self._on_select_all_cart)
        self._toolbar_flow.addWidget(self.select_all_cart_btn)

        self.deselect_all_cart_btn = StyledButton("Deselect All")
        self.deselect_all_cart_btn.setToolTip(
            "Clear the download cart for all visible rows"
        )
        self.deselect_all_cart_btn.clicked.connect(self._on_deselect_all_cart)
        self._toolbar_flow.addWidget(self.deselect_all_cart_btn)

        self.add_selected_cart_btn = StyledButton("Add Selected")
        self.add_selected_cart_btn.setToolTip(
            "Add highlighted table rows to the cart "
            "(Ctrl/Shift-click to multi-select; Space toggles)"
        )
        self.add_selected_cart_btn.clicked.connect(self._on_add_selected_cart)
        self._toolbar_flow.addWidget(self.add_selected_cart_btn)

        self.remove_selected_cart_btn = StyledButton("Remove Selected")
        self.remove_selected_cart_btn.setToolTip(
            "Remove highlighted table rows from the cart"
        )
        self.remove_selected_cart_btn.clicked.connect(self._on_remove_selected_cart)
        self._toolbar_flow.addWidget(self.remove_selected_cart_btn)

        self.send_btn = StyledButton(">> Send Downloads", primary=True)
        self.send_btn.setToolTip(
            "Download cart items (check mode). Not used for normal scrapes."
        )
        self.send_btn.clicked.connect(self._on_send_downloads)
        self._toolbar_flow.addWidget(self.send_btn)

        self._cart_widgets = [
            self.cart_label,
            self.select_all_cart_btn,
            self.deselect_all_cart_btn,
            self.add_selected_cart_btn,
            self.remove_selected_cart_btn,
            self.send_btn,
        ]
        for w in self._cart_widgets:
            w.hide()

        self._toolbar_scroll = QScrollArea()
        self._toolbar_scroll.setWidget(toolbar)
        self._toolbar_scroll.setWidgetResizable(True)
        self._toolbar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._toolbar_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._toolbar_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._toolbar_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self._toolbar_scroll.setStyleSheet(
            f"QScrollArea {{ background-color: {c('mantle')}; border: none; }}"
        )
        self._sync_toolbar_scroll_geometry()
        layout.addWidget(self._toolbar_scroll)

        # -- Per-model live result badges (shown during / after scrape) --
        self.model_badge_bar = ModelBadgeBar()
        layout.addWidget(self.model_badge_bar)

        # -- Main content area: sidebar + table --
        self._content_splitter = content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar
        self.sidebar = FilterSidebar()
        # Give the sidebar enough width to show controls by default.
        # Users can still resize via the splitter handle.
        self.sidebar.setMinimumWidth(400)
        self.sidebar.setMaximumWidth(640)
        content_splitter.addWidget(self.sidebar)

        # Right side: table + bottom tabs
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Data table with centered empty-state guidance overlay
        self._table_host = QWidget()
        table_host_layout = QGridLayout(self._table_host)
        table_host_layout.setContentsMargins(0, 0, 0, 0)
        table_host_layout.setSpacing(0)

        self.data_table = MediaDataTable()
        table_host_layout.addWidget(self.data_table, 0, 0)

        self._empty_guide = QLabel()
        self._empty_guide.setObjectName("tableEmptyGuide")
        self._empty_guide.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_guide.setWordWrap(True)
        self._empty_guide.setTextFormat(Qt.TextFormat.RichText)
        self._empty_guide.setMaximumWidth(520)
        self._empty_guide.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )

        self._empty_guide_wrap = QWidget()
        self._empty_guide_wrap.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._empty_guide_wrap.setStyleSheet("background: transparent;")
        self._empty_guide_wrap.hide()
        guide_layout = QVBoxLayout(self._empty_guide_wrap)
        guide_layout.setContentsMargins(24, 24, 24, 24)
        guide_layout.addStretch(1)
        guide_layout.addWidget(
            self._empty_guide, 0, Qt.AlignmentFlag.AlignHCenter
        )
        guide_layout.addStretch(1)
        table_host_layout.addWidget(self._empty_guide_wrap, 0, 0)

        # Vertical splitter: table on top, console below — drag the handle to resize.
        self._vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self._vertical_splitter.setObjectName("tableConsoleSplitter")
        self._vertical_splitter.setChildrenCollapsible(False)
        self._vertical_splitter.setHandleWidth(8)
        self._table_host.setMinimumHeight(120)
        self._vertical_splitter.addWidget(self._table_host)

        self.console_widget = ConsoleLogWidget()
        self.console_widget.setMinimumHeight(72)
        self._vertical_splitter.addWidget(self.console_widget)
        # Table stretches on window resize; console keeps its absolute height.
        self._vertical_splitter.setStretchFactor(0, 1)
        self._vertical_splitter.setStretchFactor(1, 0)
        # Default similar to the old fixed ~220px console.
        self._vertical_splitter.setSizes([520, _DEFAULT_CONSOLE_HEIGHT])
        self._vertical_splitter.splitterMoved.connect(self._on_console_splitter_moved)
        self._console_save_timer = QTimer(self)
        self._console_save_timer.setSingleShot(True)
        self._console_save_timer.setInterval(1000)  # save ~1s after drag settles
        self._console_save_timer.timeout.connect(self._persist_console_height)
        self._pending_console_height = None
        self._console_restore_scheduled = False
        # Double-click the handle to restore the default console height.
        try:
            handle = self._vertical_splitter.handle(1)
            handle.setToolTip(
                "Drag to resize console · Double-click to reset to default height"
            )
            handle.installEventFilter(self)
            self._console_splitter_handle = handle
        except Exception:
            self._console_splitter_handle = None

        right_layout.addWidget(self._vertical_splitter, stretch=1)

        content_splitter.addWidget(right_widget)
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        # Default widths: sidebar fully visible without dragging.
        content_splitter.setSizes([520, 880])

        layout.addWidget(content_splitter)

        # -- Unified status strip (phase + message + progress + daemon + rows) --
        self.status_strip = StatusStrip()
        self._status_bar_widget = self.status_strip
        self.progress_summary = self.status_strip.progress_summary
        self.row_count_label = self.status_strip.row_count_label
        layout.addWidget(self.status_strip)

        # Apply themed styles (must be after all widgets are created)
        self._apply_toolbar_theme()
        self._refresh_empty_guide()
        # Construction-time restore often runs before the stack gives us a real
        # height; showEvent re-applies when the scrape page is actually shown.
        QTimer.singleShot(0, self._restore_console_splitter)

    def _apply_empty_guide_theme(self):
        """Theme the empty-table guidance label."""
        try:
            self._empty_guide.setStyleSheet(
                f"QLabel#tableEmptyGuide {{"
                f" color: {c('subtext')};"
                f" background-color: transparent;"
                f" font-size: {scale_px(13)}px;"
                f" }}"
            )
        except Exception:
            pass

    def _refresh_empty_guide(self):
        """Show/hide contextual tip when the media table has nothing visible."""
        guide = getattr(self, "_empty_guide", None)
        wrap = getattr(self, "_empty_guide_wrap", None)
        if guide is None or wrap is None:
            return
        try:
            table = self.data_table
            raw = len(getattr(table, "_raw_data", None) or [])
            visible = int(table.rowCount())
            deferred = bool(getattr(table, "_deferred", False))
        except Exception:
            wrap.hide()
            guide.hide()
            return

        # Visible rows mean the grid is useful — hide the tip and overlay.
        if visible > 0 and not deferred:
            wrap.hide()
            guide.hide()
            try:
                table.raise_()
            except Exception:
                pass
            return

        if deferred and raw > 0:
            title = "Loading table…"
            body = (
                f"Collected <b>{raw}</b> items so far — the grid fills when "
                "this scrape finishes."
            )
        elif self._scrape_active or self._cancelling:
            title = "Scraping in progress…"
            body = "Media rows will appear here as models are processed."
        elif raw > 0 and visible == 0:
            title = "No rows match the current filters"
            body = "Try <b>Reset</b> or adjust the Filters sidebar."
        elif self._live_rows_loaded and raw == 0:
            title = "No media found"
            body = (
                "Try different areas, date range, or models — "
                "or verify authentication."
            )
        else:
            title = "Ready to scrape"
            body = (
                "Click <b>Start Scraping &gt;&gt;</b> to fetch media for your "
                "selected models and areas.<br/><br/>"
                "Rows show up here as they are found. Use <b>Filters</b> on the "
                "left, then <b>Select All</b> / <b>&gt;&gt; Send Downloads</b> "
                "to download chosen items."
            )

        try:
            accent = c("text")
            muted = c("subtext")
        except Exception:
            accent, muted = "#cdd6f4", "#a6adc8"

        guide.setText(
            f"<p style='color:{accent}; font-size: {scale_px(16)}px; font-weight:600; "
            f"margin:0 0 10px 0;'>{title}</p>"
            f"<p style='color:{muted}; margin:0; line-height:1.45;'>{body}</p>"
        )
        guide.show()
        wrap.show()
        try:
            wrap.raise_()
        except Exception:
            pass

    def _apply_toolbar_theme(self):
        """Apply themed colors to toolbar buttons and bars."""
        base = c('base')
        self._toolbar.setStyleSheet(f"background-color: {c('mantle')};")
        try:
            self._toolbar_scroll.setStyleSheet(
                f"QScrollArea {{ background-color: {c('mantle')}; border: none; }}"
            )
        except Exception:
            pass
        try:
            self.status_strip.apply_theme()
        except Exception:
            self._status_bar_widget.setStyleSheet(f"background-color: {c('mantle')};")
        try:
            self.model_badge_bar.apply_theme()
        except Exception:
            pass
        try:
            self._apply_empty_guide_theme()
            self._refresh_empty_guide()
        except Exception:
            pass
        self.toggle_sidebar_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('surface1')}; color: {c('text')};"
            f" border: none; border-radius: 6px; padding: 6px 12px; }}"
            f" QPushButton:hover {{ background-color: {c('surface2')}; }}"
            f" QPushButton:!checked {{ background-color: {c('surface0')}; color: {c('overlay1')};"
            f" border: 1px solid {c('surface2')}; }}"
        )
        self.filter_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('blue')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('sky')}; }}"
        )
        self.start_scraping_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('green')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 20px; }}"
            f" QPushButton:hover {{ background-color: {c('teal')}; }}"
            f" QPushButton:disabled {{ background-color: {c('surface1')}; color: {c('muted')}; }}"
        )
        self.cancel_scrape_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('red')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('peach')}; }}"
            f" QPushButton:disabled {{ background-color: {c('surface1')}; color: {c('muted')}; }}"
        )
        self.new_scrape_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('mauve')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('lavender')}; }}"
        )
        self.open_folder_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('surface1')}; color: {c('text')};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('surface2')}; }}"
        )
        self.history_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('surface1')}; color: {c('text')};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('surface2')}; }}"
        )
        self.export_csv_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('surface1')}; color: {c('text')};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('surface2')}; }}"
        )
        self.stop_daemon_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('red')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('peach')}; }}"
        )
        self.daemon_status_label.setStyleSheet(f"color: {c('yellow')};")
        self.send_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('peach')}; color: {base};"
            f" font-weight: bold; border: none; border-radius: 6px; padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('yellow')}; }}"
        )
        # Update help buttons
        for btn in self.findChildren(QToolButton):
            if btn.text() == "?":
                btn.setStyleSheet(_help_btn_qss())
        self._sync_toolbar_scroll_geometry()

    def _is_check_mode(self) -> bool:
        """True when the current job is a check-mode action (manual cart downloads)."""
        if self._check_mode_active:
            return True
        try:
            main = self.window()
            workflow = getattr(main, "workflow", None)
            actions = getattr(workflow, "_selected_actions", None) or set()
            if set(actions) & _CHECK_MODES:
                return True
        except Exception:
            pass
        try:
            main = self.window()
            area = getattr(main, "area_selector_page", None)
            actions = getattr(area, "_current_actions", None) or set()
            if set(actions) & _CHECK_MODES:
                return True
        except Exception:
            pass
        return False

    def _update_cart_toolbar_visibility(self):
        """Show cart / Send Downloads only for check modes."""
        show = self._is_check_mode()
        for w in getattr(self, "_cart_widgets", []):
            try:
                w.setVisible(show)
            except Exception:
                pass
        self._sync_toolbar_scroll_geometry()

    def _sync_toolbar_scroll_geometry(self):
        """Grow/shrink the toolbar host to the flow layout's wrapped height."""
        try:
            toolbar = self._toolbar
            scroll = self._toolbar_scroll
            flow = self._toolbar_flow
        except Exception:
            return
        try:
            width = max(120, scroll.viewport().width())
            h = flow.heightForWidth(width)
            # Cap so a tiny window doesn't steal the whole table.
            h = max(44, min(h + 4, 140))
            scroll.setFixedHeight(h)
            toolbar.updateGeometry()
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_toolbar_scroll_geometry()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_cart_toolbar_visibility()
        self._sync_toolbar_scroll_geometry()
        try:
            self.status_strip.refresh_health()
        except Exception:
            pass
        # Re-apply saved console height once the page is visible with a real size.
        # (Construction-time restore often sees height=0 while still on another stack page.)
        if not self._console_restore_scheduled:
            self._console_restore_scheduled = True
            QTimer.singleShot(0, self._restore_console_splitter_after_show)
            QTimer.singleShot(120, self._restore_console_splitter_after_show)

    def hideEvent(self, event):
        # Don't lose a drag that hasn't hit the debounce yet.
        self._flush_console_height_save()
        self._console_restore_scheduled = False
        super().hideEvent(event)

    def _restore_console_splitter_after_show(self):
        self._restore_console_splitter()
        self._console_restore_scheduled = False

    def _connect_signals(self):
        self.data_table.cart_count_changed.connect(self._on_cart_count_changed)
        self.data_table.cell_filter_requested.connect(
            self._on_cell_filter_requested
        )
        app_signals.scraping_finished.connect(self._on_scraping_finished)
        app_signals.scrape_started.connect(self._on_scrape_started)
        app_signals.daemon_next_run.connect(self._on_daemon_countdown)
        app_signals.daemon_last_run.connect(self._on_daemon_last_run)
        app_signals.daemon_run_starting.connect(self._on_daemon_run_starting)
        app_signals.daemon_stopped.connect(self._on_daemon_stopped)
        app_signals.action_selected.connect(self._on_actions_selected)
        app_signals.theme_changed.connect(lambda _: self._apply_toolbar_theme())
        try:
            self.sidebar.filter_changed.connect(self._on_filter)
        except Exception:
            pass

    @pyqtSlot(object)
    def _on_actions_selected(self, actions):
        try:
            action_set = set(actions or [])
        except Exception:
            action_set = set()
        self._check_mode_active = bool(action_set & _CHECK_MODES)
        self._update_cart_toolbar_visibility()

    @pyqtSlot()
    def _on_scrape_started(self):
        """Show Cancel for any scrape start path (Start button, check mode, manual URL)."""
        if self._cancelling:
            return
        self._scrape_active = True
        try:
            self.start_scraping_btn.setEnabled(False)
            if self.start_scraping_btn.text() in (
                "Start Scraping >>",
                "Scrape cancelled",
            ):
                self.start_scraping_btn.setText("Scraping...")
        except Exception:
            pass
        try:
            self.cancel_scrape_btn.setText("Cancel")
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.show()
        except Exception:
            pass
        # Keep status-strip phase in sync (do not rely only on signal lambdas).
        try:
            self.status_strip.set_phase("running")
        except Exception:
            pass
        try:
            app_signals.scrape_phase_changed.emit("running")
        except Exception:
            pass
        self._refresh_empty_guide()

    def eventFilter(self, obj, event):
        handle = getattr(self, "_console_splitter_handle", None)
        if (
            handle is not None
            and obj is handle
            and event is not None
            and event.type() == QEvent.Type.MouseButtonDblClick
        ):
            self._reset_console_splitter_default()
            return True
        return super().eventFilter(obj, event)

    def _reset_console_splitter_default(self):
        """Restore the default console height (double-click splitter handle)."""
        try:
            self._console_save_timer.stop()
        except Exception:
            pass
        height = _DEFAULT_CONSOLE_HEIGHT
        try:
            total = max(int(self._vertical_splitter.height() or 0), 400)
            console = max(72, min(height, total - 120))
            table = max(120, total - console)
            self._vertical_splitter.setSizes([table, console])
            self._pending_console_height = None
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            s = load_gui_settings()
            s["console_height"] = int(console)
            save_gui_settings(s, quiet=True)
            log.info(f"[GUI] Console height reset to default ({console} px)")
        except Exception:
            pass

    def _restore_console_splitter(self):
        """Apply saved console height from gui_settings.json once layout has a size."""
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings

            saved = int(load_gui_settings().get("console_height") or 0)
        except Exception:
            saved = 0
        if saved < 72:
            return
        try:
            splitter = self._vertical_splitter
            total = int(splitter.height() or 0)
            if total < 200:
                # Layout not ready yet — showEvent retry will apply later.
                return
            console = max(72, min(saved, total - 120))
            table = max(120, total - console)
            # Keep console absolute; let the table absorb window growth/shrink.
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 0)
            splitter.setSizes([table, console])
        except Exception:
            pass

    def _on_console_splitter_moved(self, _pos: int = 0, _index: int = 0):
        """Queue a debounced save after the user stops dragging the splitter."""
        try:
            sizes = self._vertical_splitter.sizes()
            if len(sizes) < 2 or sizes[1] < 72:
                return
            self._pending_console_height = int(sizes[1])
            self._console_save_timer.start()  # restart debounce on each move
        except Exception:
            pass

    def _flush_console_height_save(self):
        """Write any pending console height immediately (hide / navigate away)."""
        try:
            self._console_save_timer.stop()
        except Exception:
            pass
        if getattr(self, "_pending_console_height", None) is not None:
            self._persist_console_height()

    def _persist_console_height(self):
        """Write console height once the splitter has been idle (or on flush)."""
        height = getattr(self, "_pending_console_height", None)
        self._pending_console_height = None
        if height is None or height < 72:
            return
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            s = load_gui_settings()
            prev = int(s.get("console_height") or 0)
            if prev == int(height):
                return
            s["console_height"] = int(height)
            # Quiet file write (no per-save spam); one INFO line after settle.
            if save_gui_settings(s, quiet=True):
                log.info(f"[GUI] Console height saved ({height} px)")
        except Exception:
            pass

    def _toggle_sidebar(self, checked):
        if checked:
            self.sidebar.setVisible(True)
            saved = getattr(self, "_sidebar_last_width", 520)
            total = self._content_splitter.width()
            self._content_splitter.setSizes([saved, max(0, total - saved)])
            self.toggle_sidebar_btn.setText("◀  Filters")
            self.toggle_sidebar_btn.setToolTip("Click to hide the filter sidebar")
        else:
            sizes = self._content_splitter.sizes()
            if sizes and sizes[0] > 0:
                self._sidebar_last_width = sizes[0]
            self.sidebar.setVisible(False)
            self.toggle_sidebar_btn.setText("▶  Filters")
            self.toggle_sidebar_btn.setToolTip("Click to show the filter sidebar")

    def _on_reset(self):
        """Reset all filters and show all data."""
        self.sidebar.reset_all()
        self.data_table.reset_filter()
        self._update_row_count()

    def _on_filter(self):
        """Apply current sidebar filter state to the table."""
        state = self.sidebar.collect_state()
        self.data_table.apply_filter(state)
        self._update_row_count()

    def _on_select_all_cart(self):
        self.data_table.select_all_cart()

    def _on_deselect_all_cart(self):
        self.data_table.deselect_all_cart()

    def _on_add_selected_cart(self):
        n = self.data_table.add_selected_to_cart()
        if n:
            app_signals.status_message.emit(f"Added {n} selected row(s) to cart")
        else:
            app_signals.status_message.emit(
                "Select one or more rows first (Ctrl/Shift-click), then Add Selected"
            )

    def _on_remove_selected_cart(self):
        n = self.data_table.remove_selected_from_cart()
        if n:
            app_signals.status_message.emit(f"Removed {n} selected row(s) from cart")
        else:
            app_signals.status_message.emit("No selected cart rows to remove")

    def _on_send_downloads(self):
        """Send all [added] items to the download queue."""
        # Peek first so confirm does not mark rows [downloading] on Cancel.
        try:
            from ofscraper.gui.utils.cart_confirm import (
                build_cart_summary,
                confirm_cart_downloads,
                peek_cart_rows,
            )

            peek_rows = peek_cart_rows(self.data_table)
        except Exception as e:
            log.debug(f"Cart confirm peek failed: {e}")
            peek_rows = None

        if peek_rows is not None and not peek_rows:
            app_signals.error_occurred.emit(
                "Empty Cart",
                "No items in the download cart. Click cells in the Download Cart column to add items.",
            )
            return

        if peek_rows is not None:
            try:
                summary = build_cart_summary(peek_rows)
                if not confirm_cart_downloads(self, summary):
                    app_signals.status_message.emit(
                        "Downloads not queued — cancelled at confirm"
                    )
                    return
            except Exception as e:
                log.debug(f"Cart confirm skipped: {e}")

        try:
            from ofscraper.gui.utils.disk_space_check import confirm_for_cart

            if not confirm_for_cart(self, rows=peek_rows, summary=None):
                app_signals.status_message.emit(
                    "Downloads not queued — cancelled at disk space check"
                )
                return
        except Exception as e:
            log.debug(f"Disk space cart check skipped: {e}")

        cart_items = self.data_table.get_cart_items()
        if not cart_items:
            app_signals.error_occurred.emit(
                "Empty Cart",
                "No items in the download cart. Click cells in the Download Cart column to add items.",
            )
            return

        log.info(f"Sending {len(cart_items)} downloads to queue")
        app_signals.status_message.emit(
            f"Queued {len(cart_items)} downloads"
        )

        # Put items into the row queue for processing
        for row_data, row_key in cart_items:
            self.data_table.row_queue.put((row_data, row_key))

        # Emit signal for the download processor
        app_signals.downloads_queued.emit(
            [item[0] for item in cart_items]
        )

    def _on_start_scraping(self):
        """Read areas from the area page and start scraping."""
        if self._cancelling:
            app_signals.status_message.emit(
                "Still cancelling previous scrape — please wait"
            )
            return
        if self._scrape_active:
            return

        # Warn before starting when remote DRM key helpers may send cookies.
        try:
            from ofscraper.gui.utils.key_mode_warning import confirm_remote_key_mode

            if not confirm_remote_key_mode(self, context="scrape"):
                app_signals.status_message.emit(
                    "Scrape not started — remote key mode declined"
                )
                return
        except Exception as e:
            log.debug(f"Remote key-mode scrape check skipped: {e}")

        main_window = self.window()
        area_page = getattr(main_window, "area_page", None)

        if not area_page:
            app_signals.error_occurred.emit(
                "Error", "Could not find area configuration."
            )
            return

        # Confirm large / high-impact jobs before clearing the table.
        try:
            from ofscraper.gui.utils.scrape_confirm import (
                build_summary_from_table_start,
                confirm_scrape_job,
            )

            summary = build_summary_from_table_start(self, area_page)
            if not confirm_scrape_job(self, summary, mark_ack=True):
                app_signals.status_message.emit("Scrape not started — cancelled at confirm")
                return
        except Exception as e:
            log.debug(f"Scrape confirm skipped: {e}")
            summary = None

        try:
            from ofscraper.gui.utils.disk_space_check import confirm_for_scrape
            from ofscraper.gui.utils.scrape_confirm import build_summary_from_table_start

            disk_summary = summary
            if disk_summary is None:
                disk_summary = build_summary_from_table_start(self, area_page)
            if not confirm_for_scrape(self, disk_summary, mark_ack=True):
                app_signals.status_message.emit(
                    "Scrape not started — cancelled at disk space check"
                )
                return
        except Exception as e:
            log.debug(f"Disk space check skipped: {e}")

        selected_areas = area_page.get_selected_areas()
        # Check modes that don't require area selection (msg/paid/story check)
        _current_actions = getattr(area_page, "_current_actions", set()) or set()
        self._check_mode_active = bool(set(_current_actions) & _CHECK_MODES)
        self._update_cart_toolbar_visibility()
        _skip_area_check = bool(set(_current_actions) & {"msg_check", "paid_check", "story_check"})
        # Also skip when scrape_paid is enabled — global paid endpoint needs no areas
        _scrape_paid_enabled = bool(
            getattr(area_page, "scrape_paid_check", None)
            and area_page.scrape_paid_check.isChecked()
        )
        if not selected_areas and not _skip_area_check and not _scrape_paid_enabled:
            app_signals.error_occurred.emit(
                "No Areas Selected",
                "No content areas were configured. Go back and select areas.",
            )
            return

        # New scrape run: clear table + progress UI + console log immediately so
        # purges/rescrapes don't leave stale rows/progress visible when the DB is
        # deleted, and so the version/startup messages appear at the top of a fresh log.
        self._live_rows_loaded = False
        try:
            self.data_table.clear_all()
        except Exception:
            # Don't block scraping if the UI reset fails
            pass
        try:
            self.console_widget.clear_log()
        except Exception:
            pass
        # Push the current filter state (including date range) into the table so
        # rows arriving via data_replace are filtered as they come in.
        # workflow.py pre-filters table_rows by date before emitting, so only
        # in-range rows arrive and this filter is consistent with the scrape scope.
        # IMPORTANT: use copy.copy() so we get an independent object — sidebar.collect_state()
        # returns a reference to the shared self.state singleton; without a copy, future
        # collect_state() calls would modify _current_filter in-place.
        try:
            import copy as _copy
            _pre_state = _copy.copy(self.sidebar.collect_state())
            self.data_table.apply_filter(_pre_state)
        except Exception:
            pass
        try:
            self.progress_summary.clear_all()
        except Exception:
            pass
        self._update_row_count()

        # Disable the button to prevent double-starts; show Cancel for stop UX
        self.start_scraping_btn.setEnabled(False)
        self.start_scraping_btn.setText("Scraping...")
        self._scrape_active = True
        self._cancelling = False
        try:
            self.cancel_scrape_btn.setText("Cancel")
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.show()
        except Exception:
            pass

        # Emit additional options from the area page
        # Always emit current state (not just when checked) so workflow._scrape_paid
        # resets to False when the checkbox is unchecked between runs.
        app_signals.scrape_paid_toggled.emit(area_page.scrape_paid_check.isChecked())
        if area_page.scrape_labels_check.isChecked():
            app_signals.scrape_labels_toggled.emit(True)
        # Discord webhook updates (only if configured + user enabled)
        try:
            discord_active = bool(
                getattr(area_page, "discord_updates_check", None)
                and area_page.discord_updates_check.isEnabled()
                and area_page.discord_updates_check.isChecked()
            )
            if discord_active:
                level = getattr(area_page, "discord_level_combo", None)
                discord_level = level.currentText() if level else "NORMAL"
            else:
                discord_level = "OFF"
            app_signals.discord_configured.emit(discord_level)
        except Exception:
            pass

        # Emit advanced scrape options
        try:
            advanced = {
                "allow_dupe_downloads": bool(
                    getattr(area_page, "allow_dupes_check", None)
                    and area_page.allow_dupes_check.isChecked()
                ),
                "keep_message_purchased_dupes": bool(
                    getattr(area_page, "allow_dupes_check", None)
                    and area_page.allow_dupes_check.isChecked()
                    and getattr(area_page, "keep_msg_purchased_dupes_check", None)
                    and area_page.keep_msg_purchased_dupes_check.isChecked()
                ),
                "rescrape_all": bool(
                    getattr(area_page, "rescrape_all_check", None)
                    and area_page.rescrape_all_check.isChecked()
                ),
                "delete_model_db": bool(
                    getattr(area_page, "delete_db_check", None)
                    and area_page.delete_db_check.isChecked()
                ),
                "delete_downloads": bool(
                    getattr(area_page, "delete_downloads_check", None)
                    and area_page.delete_downloads_check.isChecked()
                ),
                "quality": (
                    area_page.quality_combo.currentText()
                    if getattr(area_page, "quality_combo", None)
                    else "Default"
                ),
            }
            app_signals.advanced_scrape_configured.emit(advanced)
        except Exception:
            # Don't block scraping if advanced config can't be emitted
            pass

        # Emit daemon configuration
        daemon_enabled = area_page.is_daemon_enabled()
        if daemon_enabled:
            app_signals.daemon_configured.emit(
                True,
                area_page.get_daemon_interval(),
                area_page.is_notify_enabled(),
                area_page.is_sound_enabled(),
            )
            self.stop_daemon_btn.show()
            self.daemon_status_label.show()
            self.daemon_status_label.setText("Daemon mode active")
        else:
            app_signals.daemon_configured.emit(False, 30.0, False, False)

        # Emit date range from the filter sidebar — but ONLY when the sidebar
        # date filter is explicitly enabled.  If it is disabled, do NOT emit,
        # so any date range already set (e.g. by the LLM assistant) is preserved.
        # NOTE: read from self.sidebar (the table page's own filter panel, which
        # the user configures directly) — NOT area_page.filter_sidebar (which only
        # holds the state as it was when the area page was last visited).
        try:
            fs = getattr(self, "sidebar", None)
            if fs is not None:
                _after_enabled = bool(getattr(fs, "after_enabled", None) and fs.after_enabled.isChecked())
                _before_enabled = bool(getattr(fs, "before_enabled", None) and fs.before_enabled.isChecked())
                log.info(
                    f"[GUI] Date filter state: after_enabled={_after_enabled}, "
                    f"before_enabled={_before_enabled}"
                )
                if _after_enabled or _before_enabled:
                    # Use helper methods so relative dates are computed fresh at scrape start
                    from_date = fs.get_after_date_str() if _after_enabled else None
                    to_date = fs.get_before_date_str() if _before_enabled else None
                    log.info(
                        f"[GUI] Emitting date_range_configured: from={from_date}, to={to_date}"
                    )
                    app_signals.date_range_configured.emit(
                        {"enabled": True, "from_date": from_date, "to_date": to_date}
                    )
                else:
                    # Explicitly disable date range so workflow clears any stale value
                    app_signals.date_range_configured.emit({"enabled": False})
                    log.info("[GUI] Date filter disabled — emitting enabled=False")
        except Exception as _e:
            log.warning(f"[GUI] Exception reading date filter state: {_e}")

        # Defer Qt widget rebuilds only in daemon mode. Interactive scrapes use
        # incremental append_data so the table fills as each model is processed.
        # Daemon + Xvfb previously paid for a full viewport repaint per model;
        # one bulk rebuild on scraping_finished is cheaper there.
        if daemon_enabled:
            self.data_table.begin_deferred()

        try:
            app_signals.mediatypes_configured.emit(
                list(area_page.get_selected_mediatypes() or [])
            )
        except Exception:
            pass

        log.info(f"Starting scrape with areas: {selected_areas}")
        app_signals.areas_selected.emit(selected_areas)

    @pyqtSlot()
    def _on_scraping_finished(self):
        """Re-enable the Start Scraping button and show New Scrape option.
        If daemon mode is active, don't show New Scrape yet — the daemon
        will re-trigger scraping after the wait interval."""
        # Always exit deferred mode first so subsequent filter/rebuild calls work normally.
        self.data_table.end_deferred()
        self._scrape_active = False
        was_cancelling = self._cancelling
        self._cancelling = False
        try:
            self.cancel_scrape_btn.hide()
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.setText("Cancel")
        except Exception:
            pass
        # If user requested "New Scrape" during an active run, wait until the
        # scraper actually finishes/cancels, then reset UI and navigate.
        if self._pending_new_scrape_nav:
            self._pending_new_scrape_nav = False
            _pr = self._pending_reset
            self._pending_reset = False
            if _pr == "reset":
                self._reset_all_pages()
            elif _pr == "restore_saved":
                self._restore_saved_area_settings()
            self._reset_scrape_controls()
            self._navigate_to_action_page()
            return
        if self.stop_daemon_btn.isVisible():
            # Daemon mode — build the table now so the user can see results during the wait.
            self.start_scraping_btn.setText("Daemon waiting...")
            self._on_filter()
            # Still allow user to go back to start; they'll be prompted by Stop Daemon flow.
            return
        self.start_scraping_btn.setEnabled(True)
        self.start_scraping_btn.setText("Start Scraping >>")
        if was_cancelling:
            try:
                self.daemon_status_label.setText("Scrape cancelled")
                self.daemon_status_label.show()
            except Exception:
                pass
        else:
            self.daemon_status_label.hide()
        # Always apply sidebar filters after scraping finishes so the table
        # reflects the date range and other criteria.  For live-row scrapes
        # the pre-scrape filter intentionally had no dates (so rows could load
        # unfiltered); this call re-applies the date range after all rows are
        # in the table, trimming out-of-range label posts while keeping the
        # in-range duplicate rows that labels share with Timeline.
        self._on_filter()
        # Emit the Scrape Summary now that the date filter has been applied.
        # workflow.py stored the raw per-run counters in _pending_summary_data
        # and deferred emission so we can use the correct filtered row count.
        _hist_done = False
        try:
            import ofscraper.gui.utils.workflow as _wf_mod
            _psd = getattr(_wf_mod, "_pending_summary_data", None)
            _sum_failed = 0
            if _psd:
                _wf_mod._pending_summary_data = None  # consume
                _vis_rows = list(self.data_table._display_data)
                # Count duplicates among visible rows as fallback; per-model counts
                # from the DB-content-filtered subset take priority when available.
                _seen_ids = set()
                _v_dups = 0
                for _r in _vis_rows:
                    _mid = _r.get("media_id")
                    if _mid is not None:
                        if _mid in _seen_ids:
                            _v_dups += 1
                        else:
                            _seen_ids.add(_mid)
                _dup_counts = _psd.get("dup_counts", {})
                # Use actual per-run download counters from common_globals (stored by workflow.py).
                # These reflect only NEW files downloaded in this run, not previously-downloaded
                # items that are visible in the table but were filtered out by previous_download_filter.
                _sum_forced = _psd.get("forced", 0)
                _sum_failed = _psd.get("failed", 0)
                _run_dl = _psd.get("run_dl", 0)
                _run_videos = _psd.get("run_videos", 0)
                _run_photos = _psd.get("run_photos", 0)
                _run_audios = _psd.get("run_audios", 0)
                _db_info = _psd.get("db_info", {})
                # Sync progress bar to actual new downloads (not visible row count).
                _bar_total = _run_dl + _sum_forced
                if _bar_total > 0:
                    from ofscraper.gui.signals import app_signals as _as
                    _as.overall_progress_updated.emit(_bar_total, _bar_total)
                # Format bytes into a human-readable size string.
                def _fmt_bytes(n):
                    for _u in ["B", "KB", "MB", "GB", "TB"]:
                        if abs(n) < 1024.0:
                            return f"{n:.2f} {_u}"
                        n /= 1024.0
                    return f"{n:.2f} PB"

                _total_bytes = _psd.get("total_bytes", 0)
                _size_str = _fmt_bytes(_total_bytes)
                _model_names = _psd.get("model_names", [])
                _per_model = _psd.get("per_model") or {}

                # Build the TUI-style summary.
                _summary_lines = ["\n--- Final Stats Summary  ---"]
                if _model_names:
                    _summary_lines.append("\n--- Action Download ---")
                    for _mname in _model_names:
                        _mst = _per_model.get(_mname) or {}
                        if _mst:
                            _m_videos = int(_mst.get("videos", 0) or 0)
                            _m_photos = int(_mst.get("photos", 0) or 0)
                            _m_audios = int(_mst.get("audios", 0) or 0)
                            _m_forced = int(_mst.get("forced", 0) or 0)
                            _m_failed = int(_mst.get("failed", 0) or 0)
                            _m_bytes = int(_mst.get("bytes", 0) or 0)
                            _m_dl = _m_videos + _m_photos + _m_audios
                            _msz = _fmt_bytes(_m_bytes) if _m_bytes else ""
                        else:
                            # Legacy fallback: same global counters for every model
                            _m_videos = _run_videos
                            _m_photos = _run_photos
                            _m_audios = _run_audios
                            _m_forced = _sum_forced
                            _m_failed = _sum_failed
                            _m_dl = _run_dl
                            _msz = _size_str if len(_model_names) == 1 else ""
                        _pfx = f"[{_mname}][Action Download]"
                        _pfx += f" ({_msz})" if _msz else ""
                        _pfx += (
                            f" ({_m_dl} downloads total"
                            f" [{_m_videos} videos, {_m_audios} audios,"
                            f" {_m_photos} photos],"
                            f" {_m_forced} skipped, {_m_failed} failed)"
                        )
                        # Append GUI-specific extras (dup count, DB ref).
                        _dup_display = _dup_counts.get(_mname, _v_dups)
                        _pfx += f" | duplicates: {_dup_display}"
                        _db_total, _db_dl = _db_info.get(_mname, (0, 0))
                        _expected_db_dl = _m_dl + _m_forced
                        if _db_total > 0 and (
                            _db_dl != _expected_db_dl or _db_total != _db_dl
                        ):
                            _pfx += f" | DB: {_db_dl}/{_db_total}"
                        _summary_lines.append(_pfx)

                # Global totals block (matches TUI output).
                _summary_lines.append("\n" + "=" * 50)
                _summary_lines.append("📊 GLOBAL RUN TOTALS (ALL MODELS)")
                _summary_lines.append("=" * 50)
                if _run_dl > 0 or _sum_forced > 0 or _sum_failed > 0:
                    _summary_lines.append("\n--- MEDIA DOWNLOADS ---")
                    _summary_lines.append(f" ➜ TOTAL ITEMS: {_run_dl}")
                    _summary_lines.append(f" ➜ TOTAL DATA:  {_size_str}")
                    _summary_lines.append(f" ➜ VIDEOS:      {_run_videos} downloaded")
                    _summary_lines.append(f" ➜ AUDIOS:      {_run_audios} downloaded")
                    _summary_lines.append(f" ➜ IMAGES:      {_run_photos} downloaded")
                    _summary_lines.append(f" ➜ SKIPPED:     {_sum_forced} overall")
                    _summary_lines.append(f" ➜ FAILED:      {_sum_failed} overall")
                _summary_lines.append("\n" + "=" * 50)

                _summary_text = "\n".join(_summary_lines)

                # Write to log file; GUILogHandler routes this to the GUI console too.
                from ofscraper.gui.signals import app_signals as _as2
                log.warning(_summary_text)

                # Refresh the bytes label in the footer with the final total.
                if _total_bytes > 0:
                    _as2.total_bytes_updated.emit(float(_total_bytes))

                self._record_scrape_history(
                    status="cancelled" if was_cancelling else "ok",
                    run_dl=_run_dl,
                    failed=_sum_failed,
                    forced=_sum_forced,
                    total_bytes=int(_total_bytes or 0),
                    model_names=list(_model_names or []),
                )
                _hist_done = True
            else:
                self._record_scrape_history(
                    status="cancelled" if was_cancelling else "ok",
                )
                _hist_done = True

            # Post-run failure summary (details from failure_tracker, even if no _psd).
            if not was_cancelling:
                self._maybe_show_failure_summary(_sum_failed)
        except Exception as _e:
            log.debug(f"post-filter summary emission failed: {_e}")
            if not _hist_done:
                try:
                    self._record_scrape_history(
                        status="cancelled" if was_cancelling else "error",
                    )
                except Exception:
                    pass
            if not was_cancelling:
                try:
                    self._maybe_show_failure_summary(0)
                except Exception:
                    pass

    def _record_scrape_history(
        self,
        *,
        status: str = "ok",
        run_dl: int = 0,
        failed: int = 0,
        forced: int = 0,
        total_bytes: int = 0,
        model_names: list | None = None,
    ):
        """Persist this run into scrape_history.json."""
        try:
            from ofscraper.gui.utils.scrape_history import record_run

            main = self.window()
            workflow = getattr(main, "workflow", None)
            snap = None
            if workflow is not None:
                snap = getattr(workflow, "_active_history_snapshot", None)
                try:
                    workflow._active_history_snapshot = None
                except Exception:
                    pass
            # Ignore aborted starts (confirm/config declined) with no snapshot.
            if (
                snap is None
                and not model_names
                and int(run_dl or 0) == 0
                and int(failed or 0) == 0
                and status == "ok"
            ):
                return
            row_count = 0
            try:
                row_count = len(self.data_table._display_data or [])
            except Exception:
                pass
            record_run(
                snap,
                status=status,
                run_dl=run_dl,
                failed=failed,
                forced=forced,
                total_bytes=total_bytes,
                row_count=row_count,
                model_names=model_names,
            )
        except Exception as e:
            log.debug(f"[GUI] Scrape history record failed: {e}")

    def _on_history_clicked(self):
        """Open the scrape history browser dialog."""
        from ofscraper.gui.dialogs.history_dialog import HistoryDialog

        dlg = HistoryDialog(self)
        dlg.rerun_requested.connect(self._rerun_history_entry)
        dlg.exec()

    def _on_export_csv(self):
        """Export visible (or selected) table rows to a CSV file."""
        visible = len(getattr(self.data_table, "_display_data", None) or [])
        if visible <= 0:
            QMessageBox.information(
                self,
                "Export CSV",
                "No rows to export. Run a scrape or loosen filters first.",
            )
            return

        selected_n = len(self.data_table._selected_row_indexes())
        selected_only = False
        if selected_n > 0:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Question)
            msg.setWindowTitle("Export CSV")
            msg.setText(
                f"{selected_n} row(s) are selected.\n\n"
                f"Export the selection, or all {visible} visible (filtered) row(s)?"
            )
            sel_btn = msg.addButton(
                "Export selection", QMessageBox.ButtonRole.AcceptRole
            )
            all_btn = msg.addButton(
                "Export all visible", QMessageBox.ButtonRole.ActionRole
            )
            msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is None or clicked == msg.button(QMessageBox.StandardButton.Cancel):
                return
            selected_only = clicked is sel_btn
            if clicked is all_btn:
                selected_only = False

        from datetime import datetime

        default_name = f"ofscraper_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export table CSV",
            default_name,
            "CSV files (*.csv);;All files (*.*)",
        )
        if not path:
            return
        if not str(path).lower().endswith(".csv"):
            path = f"{path}.csv"

        try:
            n = self.data_table.write_csv(path, selected_only=selected_only)
        except Exception as e:
            QMessageBox.warning(self, "Export CSV", f"Could not write file:\n{e}")
            return

        app_signals.status_message.emit(f"Exported {n} row(s) to CSV")
        QMessageBox.information(
            self,
            "Export CSV",
            f"Wrote {n} row(s) to:\n{path}",
        )

    def _rerun_history_entry(self, entry: dict):
        if self._scrape_active or self._cancelling:
            app_signals.status_message.emit(
                "Cannot re-run while a scrape is active — cancel first"
            )
            return
        try:
            from ofscraper.gui.utils.scrape_history import apply_entry_to_pages

            ok, message = apply_entry_to_pages(entry, main_window=self.window())
        except Exception as e:
            log.debug(f"[GUI] History re-run apply failed: {e}")
            QMessageBox.warning(self, "Re-run failed", str(e))
            return

        if not ok:
            QMessageBox.warning(self, "Re-run failed", message)
            return

        app_signals.status_message.emit(message)

        actions = set(str(a) for a in (entry.get("actions") or []))
        if "manual_url" in actions or entry.get("manual_url_count"):
            # Manual URL path starts from workflow directly.
            try:
                main = self.window()
                workflow = getattr(main, "workflow", None)
                if workflow is not None:
                    workflow._start_scraping()
                    return
            except Exception as e:
                QMessageBox.warning(self, "Re-run failed", str(e))
                return

        # Normal / check path: use table Start so confirms + area emit run.
        self._on_start_scraping()

    def _maybe_show_failure_summary(self, summary_failed_count: int = 0):
        """Show the download-failure dialog when the scrape recorded failures."""
        try:
            from ofscraper.gui.utils.failure_tracker import get_failures

            failures = get_failures()
        except Exception:
            failures = []
        if not failures:
            # Fall back to counter-only notice when details were not captured.
            if int(summary_failed_count or 0) <= 0:
                return
            failures = [
                {
                    "username": "",
                    "media_id": "",
                    "mediatype": "",
                    "post_id": "",
                    "reason": f"{summary_failed_count} failed download(s) (details unavailable)",
                }
            ]
        try:
            from ofscraper.gui.dialogs.failure_summary_dialog import (
                FailureSummaryDialog,
            )
            from ofscraper.gui.utils.window_registry import get_open, register

            existing = get_open("failure_summary")
            if existing is not None:
                try:
                    existing.raise_()
                    existing.activateWindow()
                    return
                except RuntimeError:
                    pass

            dlg = FailureSummaryDialog(
                failures,
                parent=self,
                show_cart_actions=self._is_check_mode(),
            )
            dlg.filter_requested.connect(self._on_failure_filter)
            if self._is_check_mode():
                dlg.add_to_cart_requested.connect(self._on_failure_add_to_cart)
            register("failure_summary", dlg)
            dlg.exec()
        except Exception as e:
            log.debug(f"Failure summary dialog failed: {e}")

    def _on_failure_filter(self, media_ids):
        try:
            n = self.data_table.filter_to_media_ids(media_ids)
            self._update_row_count()
            app_signals.status_message.emit(
                f"Filtered table to {n} failed media item(s)"
            )
        except Exception as e:
            log.debug(f"Failure filter failed: {e}")

    def _on_failure_add_to_cart(self, media_ids):
        try:
            n = self.data_table.add_media_ids_to_cart(media_ids)
            self._update_row_count()
            app_signals.status_message.emit(
                f"Added {n} failed item(s) to the download cart"
            )
        except Exception as e:
            log.debug(f"Failure add-to-cart failed: {e}")

    @pyqtSlot(str)
    def _on_daemon_countdown(self, text):
        """Update the daemon countdown label with remaining time + ETA."""
        self.daemon_status_label.setText(text)
        self.daemon_status_label.setToolTip(text)
        self.daemon_status_label.show()

    @pyqtSlot(str)
    def _on_daemon_last_run(self, text):
        """Keep last-run summary visible on the toolbar during daemon waits."""
        t = (text or "").strip()
        if not t:
            return
        # Prefer showing countdown when present; otherwise show last-run text.
        current = (self.daemon_status_label.text() or "").strip()
        if current.startswith("Next run"):
            self.daemon_status_label.setToolTip(f"{t}\n{current}")
        else:
            self.daemon_status_label.setText(t)
            self.daemon_status_label.setToolTip(t)
            self.daemon_status_label.show()

    @pyqtSlot(int)
    def _on_daemon_run_starting(self, run_number):
        """Update UI when a daemon re-run begins."""
        # Daemon re-run: treat as a fresh scrape cycle in the UI.
        self._scrape_active = True
        try:
            self.data_table.clear_all()
        except Exception:
            pass
        try:
            self.data_table.apply_filter(self.sidebar.collect_state())
        except Exception:
            pass
        try:
            self.progress_summary.clear_all()
        except Exception:
            pass
        # Defer Qt widget ops until this daemon run's scraping_finished fires.
        self.data_table.begin_deferred()
        self._update_row_count()
        self.start_scraping_btn.setText(f"Scraping (run #{run_number})...")
        self.daemon_status_label.setText(f"Daemon run #{run_number}")
        self.daemon_status_label.show()
        try:
            self.cancel_scrape_btn.setText("Cancel")
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.show()
        except Exception:
            pass

    @pyqtSlot()
    def _on_daemon_stopped(self):
        """Reset UI when daemon mode is stopped."""
        self.stop_daemon_btn.hide()
        self.daemon_status_label.hide()
        self.start_scraping_btn.setEnabled(True)
        self.start_scraping_btn.setText("Start Scraping >>")
        self._scrape_active = False
        self._cancelling = False
        try:
            self.cancel_scrape_btn.hide()
            self.cancel_scrape_btn.setEnabled(True)
            self.cancel_scrape_btn.setText("Cancel")
        except Exception:
            pass

    def _on_stop_daemon(self):
        """Request the daemon loop to stop."""
        app_signals.stop_daemon_requested.emit()
        self.stop_daemon_btn.setEnabled(False)
        self.stop_daemon_btn.setText("Stopping...")
        self.daemon_status_label.setText("Stopping daemon...")

    def _ask_reset_options(self):
        """Ask what to do with area settings when starting a new scrape.
        Returns: 'reset', 'restore_saved', 'keep', or 'cancel'."""
        # Check whether the user has any area settings saved in gui_settings.json
        has_saved = False
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings
            gs = load_gui_settings()
            main_window = self.window()
            area_page = getattr(main_window, "area_page", None)
            area_keys = getattr(area_page, "_AREA_SETTINGS_KEYS", ())
            has_saved = any(k in gs for k in area_keys)
        except Exception:
            pass

        if has_saved:
            # Offer three choices: load saved, reset to defaults, or cancel
            msg = QMessageBox(self)
            msg.setWindowTitle("New Scrape — Area Settings")
            msg.setText(
                "You have saved settings in gui_settings.json.\n\n"
                "What would you like to do with Select Content Areas & Filters?"
            )
            load_btn = msg.addButton("Load Saved Settings", QMessageBox.ButtonRole.AcceptRole)
            reset_btn = msg.addButton("Reset to Defaults", QMessageBox.ButtonRole.DestructiveRole)
            msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked is load_btn:
                return "restore_saved"
            elif clicked is reset_btn:
                return "reset"
            else:
                return "cancel"

        # No saved settings — ask the original yes/no question
        reply = QMessageBox.question(
            self,
            "Reset options?",
            "Do you want to reset all scrape options and selected models\n"
            "back to their defaults?\n\n"
            "Yes = start fresh (like opening the GUI for the first time)\n"
            "No = keep your current selections",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return "reset" if reply == QMessageBox.StandardButton.Yes else "keep"

    def _reset_all_pages(self):
        """Reset action, area, and model pages to their defaults,
        and clear the table/progress panel so the next scrape starts fresh."""
        main_window = self.window()
        for attr in ("action_page", "area_page", "model_page"):
            page = getattr(main_window, attr, None)
            if page and hasattr(page, "reset_to_defaults"):
                try:
                    page.reset_to_defaults()
                except Exception:
                    pass
        # Clear the table and progress panel so old results don't linger
        try:
            self.data_table.clear_all()
        except Exception:
            pass
        try:
            self.progress_panel.clear_all()
        except Exception:
            pass
        try:
            self.console_widget.clear_log()
        except Exception:
            pass
        try:
            self._live_rows_loaded = False
            self._update_row_count()
        except Exception:
            try:
                self.row_count_label.setText("0 rows")
            except Exception:
                pass
        try:
            self.dl_count_label.setText("Downloads: 0 / 0")
        except Exception:
            pass

    def _restore_saved_area_settings(self):
        """Reset action/model pages to defaults and clear table, but restore
        area page from gui_settings.json instead of wiping to hardcoded defaults."""
        main_window = self.window()
        for attr in ("action_page", "model_page"):
            page = getattr(main_window, attr, None)
            if page and hasattr(page, "reset_to_defaults"):
                try:
                    page.reset_to_defaults()
                except Exception:
                    pass
        area_page = getattr(main_window, "area_page", None)
        if area_page:
            try:
                area_page._load_area_settings()
                area_page._models_loaded = False
                area_page._models_loading = False
                if hasattr(area_page, "_refresh_discord_option_state"):
                    area_page._refresh_discord_option_state()
            except Exception:
                pass
        try:
            self.data_table.clear_all()
        except Exception:
            pass
        try:
            self.progress_panel.clear_all()
        except Exception:
            pass
        try:
            self.console_widget.clear_log()
        except Exception:
            pass
        try:
            self._live_rows_loaded = False
            self._update_row_count()
        except Exception:
            try:
                self.row_count_label.setText("0 rows")
            except Exception:
                pass
        try:
            self.dl_count_label.setText("Downloads: 0 / 0")
        except Exception:
            pass

    def _on_open_downloads_folder(self):
        """Open the configured save_location in the system file manager."""
        try:
            from ofscraper.utils.config.file import open_config
            config = open_config()
            folder = config.get("file_options", {}).get("save_location", "")
            if not folder:
                folder = config.get("save_location", "")
        except Exception:
            folder = ""

        if not folder:
            QMessageBox.warning(
                self,
                "No Download Folder",
                "No save location is configured.\n"
                "Set one in Configuration → File Options → Save Location.",
            )
            return

        folder = os.path.expandvars(os.path.expanduser(folder))
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self,
                "Folder Not Found",
                f"The configured download folder does not exist:\n{folder}",
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_cancel_scrape_clicked(self):
        """Dedicated Cancel control — cooperative stop with Cancelling UI state."""
        if not self._scrape_active or self._cancelling:
            return
        reply = QMessageBox.question(
            self,
            "Cancel scrape?",
            "Stop the current scrape?\n\n"
            "In-flight downloads will finish or abort cooperatively.\n"
            "Start Scraping stays disabled until cancel completes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._enter_cancelling_ui()
        try:
            app_signals.cancel_scrape_requested.emit()
        except Exception:
            pass

    def _on_new_scrape(self):
        """Navigate back to the action page to start a new scrape."""
        # If a scrape is in progress, confirm cancellation.
        if self._scrape_active:
            if self._cancelling:
                app_signals.status_message.emit(
                    "Already cancelling — UI will return when stop completes"
                )
                self._pending_new_scrape_nav = True
                return
            reply = QMessageBox.question(
                self,
                "Cancel current scrape?",
                "Content is currently being scraped.\n\n"
                "Cancel the current scrape and return to the beginning?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Ask about resetting now, before cancellation begins
            _reset_action = self._ask_reset_options()
            # Store action string; treat "cancel" as "keep" since cancel is already in flight
            self._pending_reset = _reset_action if _reset_action != "cancel" else "keep"
            self._enter_cancelling_ui("Cancelling current scrape...")
            try:
                app_signals.cancel_scrape_requested.emit()
            except Exception:
                pass
            # Don't navigate immediately; wait for scraping_finished so the UI
            # doesn't get stuck disabled while cancellation is still in flight.
            self._pending_new_scrape_nav = True
            return

        # If daemon mode is active, stop it when the user starts a new workflow.
        try:
            if self.stop_daemon_btn.isVisible():
                app_signals.stop_daemon_requested.emit()
        except Exception:
            pass

        # Ask about resetting options
        _reset_action = self._ask_reset_options()
        if _reset_action == "cancel":
            return
        if _reset_action == "reset":
            self._reset_all_pages()
        elif _reset_action == "restore_saved":
            self._restore_saved_area_settings()

        self._reset_scrape_controls()
        self._navigate_to_action_page()

    @pyqtSlot(int)
    def _on_cart_count_changed(self, count):
        self.cart_label.setText(f"Cart: {count} items")

    @pyqtSlot(str, str)
    def _on_cell_filter_requested(self, col_name, value):
        """When user right-clicks a cell to filter by that value."""
        self.sidebar.update_field(col_name, value)
        self._on_filter()

    def _update_row_count(self):
        count = self.data_table.rowCount()
        total = len(self.data_table._raw_data)
        if getattr(self.data_table, "_deferred", False):
            # Table widget is empty during deferred mode; show raw count as loading progress.
            self.row_count_label.setText(f"Loading… {total} items")
        elif count == total:
            self.row_count_label.setText(f"{count} rows")
        else:
            self.row_count_label.setText(f"{count} rows (filtered)")
        self._refresh_empty_guide()

    def load_data(self, table_data):
        """Load table data from the scraper pipeline (replaces existing)."""
        if not table_data:
            return
        self._live_rows_loaded = True
        if isinstance(table_data[0], dict):
            self.data_table.load_data(table_data)
        else:
            self.data_table.load_data(table_data[1:])
        self._update_row_count()
        app_signals.status_message.emit(
            f"Loaded {len(self.data_table._raw_data)} items"
        )

    def append_data(self, table_data):
        """Append new rows to the table (for incremental per-user updates)."""
        if not table_data:
            return
        self.data_table.append_data(table_data)
        self._update_row_count()
        app_signals.status_message.emit(
            f"{len(self.data_table._raw_data)} total items"
        )
