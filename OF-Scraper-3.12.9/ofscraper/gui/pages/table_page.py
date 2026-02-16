import logging

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.console_log import ConsoleLogWidget
from ofscraper.gui.widgets.data_table import MediaDataTable
from ofscraper.gui.widgets.progress_panel import ProgressSummaryBar
from ofscraper.gui.widgets.sidebar import FilterSidebar
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(
        """
        QToolButton {
            border: 1px solid #45475a;
            border-radius: 9px;
            background-color: #313244;
            color: #cdd6f4;
            font-weight: bold;
        }
        QToolButton:hover {
            border-color: #89b4fa;
            background-color: #45475a;
        }
        """
    )
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b


class TablePage(QWidget):
    """Main workspace page combining data table, filter sidebar,
    console log, and progress panel. Replaces the Textual InputApp."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._scrape_active = False
        self._pending_new_scrape_nav = False
        self._setup_ui()
        self._connect_signals()

    def _reset_scrape_controls(self):
        """Reset toolbar state to a ready-to-scrape baseline."""
        try:
            self._scrape_active = False
            self.start_scraping_btn.setEnabled(True)
            self.start_scraping_btn.setText("Start Scraping >>")
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

    def _navigate_to_action_page(self):
        main_window = self.window()
        scraper_stack = getattr(main_window, "scraper_stack", None)
        if scraper_stack:
            scraper_stack.setCurrentIndex(0)  # action page

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # -- Top toolbar --
        toolbar = QWidget()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet("background-color: #181825;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 4, 12, 4)

        self.toggle_sidebar_btn = StyledButton("Filters")
        self.toggle_sidebar_btn.setCheckable(True)
        self.toggle_sidebar_btn.setChecked(True)
        self.toggle_sidebar_btn.clicked.connect(self._toggle_sidebar)
        toolbar_layout.addWidget(self.toggle_sidebar_btn)

        toolbar_layout.addSpacing(12)

        self.reset_btn = StyledButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        toolbar_layout.addWidget(self.reset_btn)

        self.filter_btn = StyledButton("Apply Filters", primary=True)
        self.filter_btn.setStyleSheet(
            "QPushButton { background-color: #89b4fa; color: #1e1e2e;"
            " font-weight: bold; border: none; border-radius: 6px;"
            " padding: 6px 16px; }"
            " QPushButton:hover { background-color: #74c7ec; }"
        )
        self.filter_btn.clicked.connect(self._on_filter)
        toolbar_layout.addWidget(self.filter_btn)

        toolbar_layout.addSpacing(12)

        self.start_scraping_btn = StyledButton("Start Scraping >>", primary=True)
        self.start_scraping_btn.setFixedHeight(36)
        self.start_scraping_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_scraping_btn.setStyleSheet(
            "QPushButton { background-color: #a6e3a1; color: #1e1e2e;"
            " font-weight: bold; border: none; border-radius: 6px;"
            " padding: 6px 20px; }"
            " QPushButton:hover { background-color: #94e2d5; }"
            " QPushButton:disabled { background-color: #45475a; color: #6c7086; }"
        )
        self.start_scraping_btn.clicked.connect(self._on_start_scraping)
        toolbar_layout.addWidget(self.start_scraping_btn)

        self.new_scrape_btn = StyledButton("New Scrape")
        self.new_scrape_btn.setFixedHeight(36)
        self.new_scrape_btn.setStyleSheet(
            "QPushButton { background-color: #cba6f7; color: #1e1e2e;"
            " font-weight: bold; border: none; border-radius: 6px;"
            " padding: 6px 16px; }"
            " QPushButton:hover { background-color: #b4befe; }"
        )
        self.new_scrape_btn.clicked.connect(self._on_new_scrape)
        # Always visible; clicking during an active scrape will prompt to cancel.
        toolbar_layout.addWidget(self.new_scrape_btn)

        # Stop Daemon button (hidden until daemon is running)
        self.stop_daemon_btn = StyledButton("Stop Daemon")
        self.stop_daemon_btn.setFixedHeight(36)
        self.stop_daemon_btn.setStyleSheet(
            "QPushButton { background-color: #f38ba8; color: #1e1e2e;"
            " font-weight: bold; border: none; border-radius: 6px;"
            " padding: 6px 16px; }"
            " QPushButton:hover { background-color: #eba0ac; }"
        )
        self.stop_daemon_btn.clicked.connect(self._on_stop_daemon)
        self.stop_daemon_btn.hide()
        toolbar_layout.addWidget(self.stop_daemon_btn)

        toolbar_layout.addSpacing(8)

        # Daemon countdown label (hidden until daemon is waiting)
        self.daemon_status_label = QLabel("")
        self.daemon_status_label.setFont(QFont("Segoe UI", 10))
        self.daemon_status_label.setStyleSheet("color: #f9e2af;")
        self.daemon_status_label.hide()
        toolbar_layout.addWidget(self.daemon_status_label)

        toolbar_layout.addStretch()

        self.cart_label = QLabel("Cart: 0 items")
        self.cart_label.setProperty("subheading", True)
        toolbar_layout.addWidget(self.cart_label)

        toolbar_layout.addSpacing(8)

        self.select_all_cart_btn = StyledButton("Select All")
        self.select_all_cart_btn.clicked.connect(self._on_select_all_cart)
        toolbar_layout.addWidget(self.select_all_cart_btn)

        self.deselect_all_cart_btn = StyledButton("Deselect All")
        self.deselect_all_cart_btn.clicked.connect(self._on_deselect_all_cart)
        toolbar_layout.addWidget(self.deselect_all_cart_btn)

        toolbar_layout.addSpacing(12)

        self.send_btn = StyledButton(">> Send Downloads", primary=True)
        self.send_btn.setStyleSheet(
            "QPushButton { background-color: #fab387; color: #1e1e2e;"
            " font-weight: bold; border: none; border-radius: 6px;"
            " padding: 6px 16px; }"
            " QPushButton:hover { background-color: #f9e2af; }"
        )
        self.send_btn.clicked.connect(self._on_send_downloads)
        toolbar_layout.addWidget(self.send_btn)

        layout.addWidget(toolbar)

        # -- Main content area: sidebar + table --
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Sidebar
        self.sidebar = FilterSidebar()
        # Give the sidebar enough width to show controls by default.
        # Users can still resize via the splitter handle.
        self.sidebar.setMinimumWidth(320)
        self.sidebar.setMaximumWidth(520)
        content_splitter.addWidget(self.sidebar)

        # Right side: table + bottom tabs
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Data table
        self.data_table = MediaDataTable()
        right_layout.addWidget(self.data_table, stretch=3)

        # Bottom console (keep logs available, but avoid a large empty panel)
        self.console_widget = ConsoleLogWidget()
        self.console_widget.setMaximumHeight(220)
        right_layout.addWidget(self.console_widget, stretch=1)

        content_splitter.addWidget(right_widget)
        content_splitter.setStretchFactor(0, 0)
        content_splitter.setStretchFactor(1, 1)
        # Default widths: sidebar fully visible without dragging.
        content_splitter.setSizes([420, 780])

        layout.addWidget(content_splitter)

        # -- Status info at bottom --
        status_bar = QWidget()
        status_bar.setFixedHeight(34)
        status_bar.setStyleSheet("background-color: #181825;")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(12, 2, 12, 2)
        status_layout.setSpacing(10)

        self.row_count_label = QLabel("0 rows")
        self.row_count_label.setProperty("muted", True)
        status_layout.addWidget(self.row_count_label)

        # Overall progress embedded in the footer to use the empty space.
        self.progress_summary = ProgressSummaryBar()
        status_layout.addWidget(self.progress_summary, stretch=1)

        hint_label = QLabel(
            "Click Download_Cart cell to toggle  |  Right-click cell to filter  |  Click header to sort"
        )
        hint_label.setProperty("muted", True)
        status_layout.addWidget(hint_label)

        # Quick link to table column/label documentation
        status_layout.addWidget(_make_help_btn("table-columns"))

        layout.addWidget(status_bar)

    def _connect_signals(self):
        self.data_table.cart_count_changed.connect(self._on_cart_count_changed)
        self.data_table.cell_filter_requested.connect(
            self._on_cell_filter_requested
        )
        app_signals.scraping_finished.connect(self._on_scraping_finished)
        app_signals.daemon_next_run.connect(self._on_daemon_countdown)
        app_signals.daemon_run_starting.connect(self._on_daemon_run_starting)
        app_signals.daemon_stopped.connect(self._on_daemon_stopped)

    def _toggle_sidebar(self, checked):
        self.sidebar.setVisible(checked)

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

    def _on_send_downloads(self):
        """Send all [added] items to the download queue."""
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
        main_window = self.window()
        area_page = getattr(main_window, "area_page", None)

        if not area_page:
            app_signals.error_occurred.emit(
                "Error", "Could not find area configuration."
            )
            return

        selected_areas = area_page.get_selected_areas()
        if not selected_areas:
            app_signals.error_occurred.emit(
                "No Areas Selected",
                "No content areas were configured. Go back and select areas.",
            )
            return

        # New scrape run: clear table + progress UI immediately so purges/rescrapes
        # don't leave stale rows/progress visible when the DB is deleted.
        try:
            self.data_table.clear_all()
        except Exception:
            # Don't block scraping if the UI reset fails
            pass
        try:
            self.progress_summary.clear_all()
        except Exception:
            pass
        self._update_row_count()

        # Disable the button to prevent double-starts
        self.start_scraping_btn.setEnabled(False)
        self.start_scraping_btn.setText("Scraping...")
        self._scrape_active = True

        # Emit additional options from the area page
        if area_page.scrape_paid_check.isChecked():
            app_signals.scrape_paid_toggled.emit(True)
        if area_page.scrape_labels_check.isChecked():
            app_signals.scrape_labels_toggled.emit(True)
        # Discord webhook updates (only if configured + user enabled)
        try:
            enabled = bool(
                getattr(area_page, "discord_updates_check", None)
                and area_page.discord_updates_check.isEnabled()
                and area_page.discord_updates_check.isChecked()
            )
            app_signals.discord_configured.emit(enabled)
        except Exception:
            pass

        # Emit advanced scrape options
        try:
            advanced = {
                "allow_dupe_downloads": bool(
                    getattr(area_page, "allow_dupes_check", None)
                    and area_page.allow_dupes_check.isChecked()
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

        log.info(f"Starting scrape with areas: {selected_areas}")
        app_signals.areas_selected.emit(selected_areas)

    @pyqtSlot()
    def _on_scraping_finished(self):
        """Re-enable the Start Scraping button and show New Scrape option.
        If daemon mode is active, don't show New Scrape yet — the daemon
        will re-trigger scraping after the wait interval."""
        self._scrape_active = False
        # If user requested "New Scrape" during an active run, wait until the
        # scraper actually finishes/cancels, then reset UI and navigate.
        if self._pending_new_scrape_nav:
            self._pending_new_scrape_nav = False
            self._reset_scrape_controls()
            self._navigate_to_action_page()
            return
        if self.stop_daemon_btn.isVisible():
            # Daemon mode — keep the button disabled and show waiting status
            self.start_scraping_btn.setText("Daemon waiting...")
            # Still allow user to go back to start; they'll be prompted by Stop Daemon flow.
            return
        self.start_scraping_btn.setEnabled(True)
        self.start_scraping_btn.setText("Start Scraping >>")
        self.daemon_status_label.hide()

    @pyqtSlot(str)
    def _on_daemon_countdown(self, text):
        """Update the daemon countdown label with remaining time."""
        self.daemon_status_label.setText(text)
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
            self.progress_summary.clear_all()
        except Exception:
            pass
        self._update_row_count()
        self.start_scraping_btn.setText(f"Scraping (run #{run_number})...")
        self.daemon_status_label.setText(f"Daemon run #{run_number}")
        self.daemon_status_label.show()

    @pyqtSlot()
    def _on_daemon_stopped(self):
        """Reset UI when daemon mode is stopped."""
        self.stop_daemon_btn.hide()
        self.daemon_status_label.hide()
        self.start_scraping_btn.setEnabled(True)
        self.start_scraping_btn.setText("Start Scraping >>")
        self._scrape_active = False

    def _on_stop_daemon(self):
        """Request the daemon loop to stop."""
        app_signals.stop_daemon_requested.emit()
        self.stop_daemon_btn.setEnabled(False)
        self.stop_daemon_btn.setText("Stopping...")
        self.daemon_status_label.setText("Stopping daemon...")

    def _on_new_scrape(self):
        """Navigate back to the action page to start a new scrape."""
        # If a scrape is in progress, confirm cancellation.
        if self._scrape_active:
            reply = QMessageBox.question(
                self,
                "Cancel current scrape?",
                "Content is currently being scraped.\n\n"
                "Cancel the current scrape and return to the beginning?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                app_signals.cancel_scrape_requested.emit()
            except Exception:
                pass
            # Don't navigate immediately; wait for scraping_finished so the UI
            # doesn't get stuck disabled while cancellation is still in flight.
            self._pending_new_scrape_nav = True
            try:
                self.start_scraping_btn.setText("Cancelling...")
                self.start_scraping_btn.setEnabled(False)
            except Exception:
                pass
            try:
                self.daemon_status_label.setText("Cancelling current scrape...")
                self.daemon_status_label.show()
            except Exception:
                pass
            return

        # If daemon mode is active, stop it when the user starts a new workflow.
        try:
            if self.stop_daemon_btn.isVisible():
                app_signals.stop_daemon_requested.emit()
        except Exception:
            pass
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
        if count == total:
            self.row_count_label.setText(f"{count} rows")
        else:
            self.row_count_label.setText(f"{count} / {total} rows (filtered)")

    def load_data(self, table_data):
        """Load table data from the scraper pipeline (replaces existing)."""
        if not table_data:
            return
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
