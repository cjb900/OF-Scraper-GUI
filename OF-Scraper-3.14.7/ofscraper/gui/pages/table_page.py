import logging

import os
import subprocess as _subprocess
import sys as _sys

from PyQt6.QtCore import Qt, QUrl, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QFont
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
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.console_log import ConsoleLogWidget
from ofscraper.gui.widgets.data_table import MediaDataTable
from ofscraper.gui.widgets.progress_panel import ProgressSummaryBar
from ofscraper.gui.widgets.sidebar import FilterSidebar
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

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
        self._pending_new_scrape_nav = False
        self._pending_reset = False
        self._live_rows_loaded = False
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
        self._toolbar = toolbar = QWidget()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet(f"background-color: {c('mantle')};")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(12, 4, 12, 4)

        self.toggle_sidebar_btn = StyledButton("◀  Filters")
        self.toggle_sidebar_btn.setCheckable(True)
        self.toggle_sidebar_btn.setChecked(True)
        self.toggle_sidebar_btn.setToolTip("Click to hide the filter sidebar")
        self.toggle_sidebar_btn.clicked.connect(self._toggle_sidebar)
        toolbar_layout.addWidget(self.toggle_sidebar_btn)

        toolbar_layout.addSpacing(12)

        self.reset_btn = StyledButton("Reset")
        self.reset_btn.clicked.connect(self._on_reset)
        toolbar_layout.addWidget(self.reset_btn)

        self.filter_btn = StyledButton("Apply Filters", primary=True)
        self.filter_btn.clicked.connect(self._on_filter)
        toolbar_layout.addWidget(self.filter_btn)

        toolbar_layout.addSpacing(12)

        self.start_scraping_btn = StyledButton("Start Scraping >>", primary=True)
        self.start_scraping_btn.setFixedHeight(36)
        self.start_scraping_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_scraping_btn.clicked.connect(self._on_start_scraping)
        toolbar_layout.addWidget(self.start_scraping_btn)

        self.new_scrape_btn = StyledButton("New Scrape")
        self.new_scrape_btn.setFixedHeight(36)
        self.new_scrape_btn.clicked.connect(self._on_new_scrape)
        toolbar_layout.addWidget(self.new_scrape_btn)

        self.open_folder_btn = StyledButton("Open Downloads Folder")
        self.open_folder_btn.setFixedHeight(36)
        self.open_folder_btn.setToolTip("Open the configured download save location in your file manager")
        self.open_folder_btn.clicked.connect(self._on_open_downloads_folder)
        toolbar_layout.addWidget(self.open_folder_btn)

        # Stop Daemon button (hidden until daemon is running)
        self.stop_daemon_btn = StyledButton("Stop Daemon")
        self.stop_daemon_btn.setFixedHeight(36)
        self.stop_daemon_btn.clicked.connect(self._on_stop_daemon)
        self.stop_daemon_btn.hide()
        toolbar_layout.addWidget(self.stop_daemon_btn)

        toolbar_layout.addSpacing(8)

        # Daemon countdown label (hidden until daemon is waiting)
        self.daemon_status_label = QLabel("")
        self.daemon_status_label.setFont(QFont("Segoe UI", 10))
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
        self.send_btn.clicked.connect(self._on_send_downloads)
        toolbar_layout.addWidget(self.send_btn)

        layout.addWidget(toolbar)

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
        content_splitter.setSizes([520, 880])

        layout.addWidget(content_splitter)

        # -- Status info at bottom --
        self._status_bar_widget = status_bar = QWidget()
        status_bar.setFixedHeight(34)
        status_bar.setStyleSheet(f"background-color: {c('mantle')};")
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

        # Apply themed styles (must be after all widgets are created)
        self._apply_toolbar_theme()

    def _apply_toolbar_theme(self):
        """Apply themed colors to toolbar buttons and bars."""
        base = c('base')
        self._toolbar.setStyleSheet(f"background-color: {c('mantle')};")
        self._status_bar_widget.setStyleSheet(f"background-color: {c('mantle')};")
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

    def _connect_signals(self):
        self.data_table.cart_count_changed.connect(self._on_cart_count_changed)
        self.data_table.cell_filter_requested.connect(
            self._on_cell_filter_requested
        )
        app_signals.scraping_finished.connect(self._on_scraping_finished)
        app_signals.daemon_next_run.connect(self._on_daemon_countdown)
        app_signals.daemon_run_starting.connect(self._on_daemon_run_starting)
        app_signals.daemon_stopped.connect(self._on_daemon_stopped)
        app_signals.theme_changed.connect(lambda _: self._apply_toolbar_theme())

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
        # Check modes that don't require area selection (msg/paid/story check)
        _check_modes_no_area = {"msg_check", "paid_check", "story_check"}
        _current_actions = getattr(area_page, "_current_actions", set()) or set()
        _skip_area_check = bool(_current_actions & _check_modes_no_area)
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

        # Disable the button to prevent double-starts
        self.start_scraping_btn.setEnabled(False)
        self.start_scraping_btn.setText("Scraping...")
        self._scrape_active = True

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
            # Daemon mode — keep the button disabled and show waiting status
            self.start_scraping_btn.setText("Daemon waiting...")
            # Still allow user to go back to start; they'll be prompted by Stop Daemon flow.
            return
        self.start_scraping_btn.setEnabled(True)
        self.start_scraping_btn.setText("Start Scraping >>")
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
        try:
            import ofscraper.gui.utils.workflow as _wf_mod
            _psd = getattr(_wf_mod, "_pending_summary_data", None)
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

                # Build the TUI-style summary.
                _summary_lines = ["\n--- Final Stats Summary  ---"]
                if _model_names:
                    _summary_lines.append("\n--- Action Download ---")
                    for _mname in _model_names:
                        # Per-model size: use total when only one model, blank otherwise.
                        _msz = _size_str if len(_model_names) == 1 else ""
                        _pfx = f"[{_mname}][Action Download]"
                        _pfx += f" ({_msz})" if _msz else ""
                        _pfx += (
                            f" ({_run_dl} downloads total"
                            f" [{_run_videos} videos, {_run_audios} audios,"
                            f" {_run_photos} photos],"
                            f" {_sum_forced} skipped, {_sum_failed} failed)"
                        )
                        # Append GUI-specific extras (dup count, DB ref).
                        _dup_display = _dup_counts.get(_mname, _v_dups)
                        _pfx += f" | duplicates: {_dup_display}"
                        _db_total, _db_dl = _db_info.get(_mname, (0, 0))
                        _expected_db_dl = _run_dl + _sum_forced
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
        except Exception as _e:
            log.debug(f"post-filter summary emission failed: {_e}")

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
            self.data_table.apply_filter(self.sidebar.collect_state())
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
            # Ask about resetting now, before cancellation begins
            _reset_action = self._ask_reset_options()
            # Store action string; treat "cancel" as "keep" since cancel is already in flight
            self._pending_reset = _reset_action if _reset_action != "cancel" else "keep"
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
        if count == total:
            self.row_count_label.setText(f"{count} rows")
        else:
            self.row_count_label.setText(f"{count} rows (filtered)")

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
