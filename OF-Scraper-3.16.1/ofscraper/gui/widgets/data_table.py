import logging
import queue
import re

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
)

# Left-edge columns that sticky mode pins (by count).
_STICKY_COLUMNS = ("Number", "Download_Cart", "UserName")
_DEFAULT_FROZEN_COUNT = 2

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c

log = logging.getLogger("shared")

# Column definitions matching the TUI's ROW_NAMES
COLUMNS = [
    "Number",
    "Download_Cart",
    "UserName",
    "Downloaded",
    "Duplicate",
    "Unlocked",
    "other_posts_with_media",
    "Length",
    "Mediatype",
    "Post_Date",
    "Post_Media_Count",
    "Responsetype",
    "Price",
    "Liked",
    "Post_ID",
    "Media_ID",
    "Text",
]

CART_STATES = ["[]", "[added]", "[downloading]", "[downloaded]", "[failed]"]


def _cart_color(key):
    """Get cart/status color for the current theme."""
    _MAP = {
        "[]": "muted",
        "[added]": "green",
        "[downloading]": "yellow",
        "[downloaded]": "blue",
        "[failed]": "red",
        "Locked": "surface2",
        "Preview": "sky",
        "Included": "teal",
    }
    name = _MAP.get(key)
    return c(name) if name else c("text")


class MediaDataTable(QTableWidget):
    """QTableWidget for displaying media data — replaces the Textual DataTable.

    Supports sorting, download cart toggling, right-click filter-by-cell,
    and communicates with the download queue via signals.
    """

    cell_filter_requested = pyqtSignal(str, str)  # column_name, cell_value
    cart_count_changed = pyqtSignal(int)  # number of [added] items

    def __init__(self, parent=None):
        super().__init__(parent)
        self._raw_data = []  # list of dicts (original row data)
        self._display_data = []  # filtered subset
        self._current_filter = None  # active FilterState (None = show all)
        self._row_queue = queue.Queue()
        self._sort_column = 0
        self._sort_order = Qt.SortOrder.AscendingOrder
        # O(1) lookup: media_id (str) -> list of row indices in _display_data
        self._media_id_index: dict = {}
        # O(1) lookup: media_id (str) -> list of raw row dicts in _raw_data
        # Used by _on_batch_cell_update to avoid an O(n) linear scan over _raw_data.
        self._raw_data_by_media_id: dict = {}
        # When True, append_data/load_data update only Python data structures and skip
        # all Qt widget calls.  One bulk _rebuild_table() fires when end_deferred() +
        # apply_filter() run at scrape completion.  This eliminates N per-model widget
        # rebuilds (each causing a full Xvfb repaint) during a scrape run.
        self._deferred: bool = False
        self._layout_save_timer = QTimer(self)
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(500)
        self._layout_save_timer.timeout.connect(self._persist_column_layout)
        self._applying_column_layout = False
        self._frozen_count = _DEFAULT_FROZEN_COUNT
        self._frozen = None
        self._syncing_frozen_widths = False

        self._setup_ui()
        self._connect_internal()
        self._init_frozen_overlay()
        self._restore_column_layout()
        self._refresh_frozen()

    def _setup_ui(self):
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels(
            [c.replace("_", " ") for c in COLUMNS]
        )
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        # Ctrl/Shift click to select multiple rows for cart bulk actions.
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)  # We handle sorting manually
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().setVisible(False)

        # Header sizing
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionsMovable(True)
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.sectionClicked.connect(self._on_header_clicked)
        header.sectionResized.connect(self._on_section_resized)
        header.sectionMoved.connect(self._on_section_moved)
        header.customContextMenuRequested.connect(self._on_header_context_menu)

        # Set minimum column widths
        for i, col in enumerate(COLUMNS):
            if col == "Text":
                self.setColumnWidth(i, 300)
            elif col in ("Download_Cart", "Number"):
                self.setColumnWidth(i, 100)
            elif col == "Duplicate":
                self.setColumnWidth(i, 90)
            else:
                self.setColumnWidth(i, 120)

    def _connect_internal(self):
        self.cellClicked.connect(self._on_cell_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)
        app_signals.cell_update.connect(self._on_external_cell_update)
        app_signals.batch_cell_update.connect(self._on_batch_cell_update)
        app_signals.posts_liked_updated.connect(self._on_posts_liked_updated)
        app_signals.theme_changed.connect(lambda _: self._rebuild_table())
        app_signals.privacy_mode_changed.connect(lambda _: self._rebuild_table())

    def _rebuild_index(self):
        """Rebuild the media_id → [row_idx] lookup from _display_data."""
        idx: dict = {}
        for row_i, row in enumerate(self._display_data):
            mid = str(row.get("media_id", ""))
            if mid:
                idx.setdefault(mid, []).append(row_i)
        self._media_id_index = idx

    def begin_deferred(self):
        """Enter deferred rendering mode.

        While deferred, append_data/load_data update only the Python data structures
        (_raw_data, _raw_data_by_media_id) and skip all Qt widget operations.
        Call end_deferred() then apply_filter() (or _rebuild_table()) to render once.
        """
        self._deferred = True

    def end_deferred(self):
        """Exit deferred rendering mode.

        The caller is responsible for triggering a rebuild via apply_filter() or
        _rebuild_table() so accumulated rows become visible.
        """
        self._deferred = False

    def load_data(self, table_data):
        """Load raw table data (list of dicts) into the table, replacing existing data."""
        self._raw_data = table_data
        self._raw_data_by_media_id = {}
        for row in table_data:
            mid = str(row.get("media_id", ""))
            if mid:
                self._raw_data_by_media_id.setdefault(mid, []).append(row)
        if self._deferred:
            # Widget rebuild deferred — apply_filter() at scrape-end will do it.
            return
        self._display_data = self._apply_current_filter(table_data)
        self._rebuild_table()

    def clear_all(self):
        """Clear all table data and reset internal state for a new scrape run."""
        self._raw_data = []
        self._display_data = []
        self._media_id_index = {}
        self._raw_data_by_media_id = {}

        # Clear any queued download rows from a prior run (best-effort).
        try:
            while True:
                self._row_queue.get_nowait()
        except Exception:
            pass

        self.setRowCount(0)
        self.clearSelection()
        self._update_cart_count()

    def append_data(self, new_rows):
        """Append new rows to existing data (incremental — inserts at end, no full rebuild).

        Deduplicates by composite identity to prevent duplicate entries when
        loading from both the live scraper pipeline and the DB fallback.
        """
        def _row_identity(r: dict) -> tuple:
            # Media IDs are NOT unique across posts (creators can repost media).
            # Use a composite identity so new posts/messages still appear in the GUI.
            return (
                str(r.get("username", "")),
                str(r.get("media_id", "")),
                str(r.get("post_id", "")),
                str(r.get("responsetype", "")),
            )

        existing = {_row_identity(r) for r in self._raw_data}
        deduped = [r for r in new_rows if _row_identity(r) not in existing]
        if not deduped:
            return
        start_index = len(self._raw_data)
        for i, row in enumerate(deduped):
            row["index"] = start_index + i
        self._raw_data.extend(deduped)
        # Maintain O(1) raw-data index used by _on_batch_cell_update
        for row in deduped:
            mid = str(row.get("media_id", ""))
            if mid:
                self._raw_data_by_media_id.setdefault(mid, []).append(row)

        if self._deferred:
            # Deferred mode: Python data updated; Qt widget ops skipped.
            # apply_filter() at scrape-end builds _display_data + calls _rebuild_table().
            return

        new_display = self._apply_current_filter(deduped)
        if not new_display:
            return

        # Incremental path: pre-allocate all new rows at once (one setRowCount call)
        # instead of N insertRow calls, which is significantly faster for large batches.
        self.setUpdatesEnabled(False)
        try:
            start_row = len(self._display_data)
            self.setRowCount(start_row + len(new_display))
            for i, row_data in enumerate(new_display):
                actual_row = start_row + i
                self._fill_row(actual_row, row_data)
                # Maintain O(1) media_id index
                mid = str(row_data.get("media_id", ""))
                if mid:
                    self._media_id_index.setdefault(mid, []).append(actual_row)
            self._display_data.extend(new_display)
        finally:
            self.setUpdatesEnabled(True)
        self._update_cart_count()

    def _apply_current_filter(self, rows):
        """Return only the rows that pass self._current_filter (or all if no filter)."""
        if self._current_filter is None:
            return list(rows)
        result = []
        for row in rows:
            passes = True
            for col in COLUMNS:
                col_lower = col.lower()
                if col_lower in ("number", "download_cart"):
                    continue
                val = row.get(col_lower, row.get(col, ""))
                if not self._current_filter.validate(col_lower, val):
                    passes = False
                    break
            if passes:
                result.append(row)
        return result

    def apply_filter(self, filter_state):
        """Apply the filter state and rebuild the table with filtered data."""
        self._current_filter = filter_state
        self._display_data = self._apply_current_filter(self._raw_data)
        self._rebuild_table()

    def reset_filter(self):
        """Reset to show all data."""
        self._current_filter = None
        self._display_data = list(self._raw_data)
        self._rebuild_table()

    def _fill_row(self, row_idx, row_data):
        """Populate a single existing table row with data and styling.

        The row must already exist (insertRow already called). Keeps all
        colour/font/tooltip logic in one place so _rebuild_table and the
        incremental append_data path stay in sync.
        """
        for col_idx, col_name in enumerate(COLUMNS):
            col_lower = col_name.lower()
            if col_lower == "number":
                value = str(row_idx + 1)
            else:
                value = row_data.get(col_lower, row_data.get(col_name, ""))

            # Format display value
            if col_lower == "username":
                # Prefer string username; ignore bool/None mis-keys that would
                # become "False" and then get privacy-masked oddly.
                raw = row_data.get("username", row_data.get("UserName", ""))
                if isinstance(raw, bool) or raw is None:
                    raw = ""
                display = str(raw)
                try:
                    from ofscraper.gui.utils.privacy_mode import mask_username

                    display = mask_username(display)
                except Exception:
                    pass
            elif isinstance(value, list):
                display = str(len(value))
            elif isinstance(value, bool):
                display = str(value)
            else:
                display = str(value)

            item = QTableWidgetItem(display)
            apply_font(item, "Consolas", 11)

            # Style the download cart column
            if col_lower == "download_cart":
                item.setForeground(QColor(_cart_color(display)))
                apply_font(item, "Consolas", 11, QFont.Weight.Bold)

            # Style downloaded/duplicate/unlocked/price columns
            if col_lower == "downloaded":
                if display == "True":
                    item.setForeground(QColor(c("green")))
                elif display == "N/A":
                    item.setForeground(QColor(c("surface2")))
                else:
                    item.setForeground(QColor(c("red")))
            elif col_lower == "duplicate":
                if display == "Duplicate":
                    item.setForeground(QColor(c("peach")))
                    item.setToolTip("Same media_id already appears above — will be skipped by the download pipeline")
                else:
                    item.setForeground(QColor(c("surface2")))
            elif col_lower == "unlocked":
                if display == "Locked":
                    item.setForeground(QColor(c("surface2")))
                elif display == "Preview":
                    item.setForeground(QColor(c("sky")))
                elif display == "Included":
                    item.setForeground(QColor(c("teal")))
                elif display == "True":
                    item.setForeground(QColor(c("green")))
                else:
                    item.setForeground(QColor(c("red")))
            elif col_lower == "price":
                if display != "Free" and display != "0":
                    item.setForeground(QColor(c("peach")))
            elif col_lower == "liked":
                if display == "Liked":
                    item.setForeground(QColor(c("green")))
                elif display == "Unliked":
                    item.setForeground(QColor(c("peach")))
                elif display == "Failed":
                    item.setForeground(QColor(c("red")))
            elif col_lower in ("post_id", "media_id") and display and display not in ("", "None"):
                item.setForeground(QColor(c("blue")))
                item.setToolTip("Open this post on OnlyFans")

            # Truncate long text
            if col_lower == "text" and len(display) > 80:
                item.setToolTip(display)
                item.setText(display[:80] + "...")

            self.setItem(row_idx, col_idx, item)

    def _rebuild_table(self):
        """Clear and repopulate the table from _display_data.

        setUpdatesEnabled(False) batches all cell writes into a single repaint,
        which is critical in Docker/X11 where each Qt draw call is a network
        round-trip to the display server.
        Pre-allocating with setRowCount avoids N individual insertRow calls,
        each of which triggers internal Qt layout bookkeeping.
        """
        self.setUpdatesEnabled(False)
        try:
            self.setRowCount(0)
            self.setSortingEnabled(False)
            n = len(self._display_data)
            self.setRowCount(n)
            for row_idx, row_data in enumerate(self._display_data):
                self._fill_row(row_idx, row_data)
            self._rebuild_index()
            self._update_cart_count()
        finally:
            self.setUpdatesEnabled(True)
        self._refresh_frozen()

    def _init_frozen_overlay(self):
        """Qt-style overlay table that keeps the left columns visible while scrolling."""
        frozen = QTableView(self)
        frozen.setObjectName("mediaFrozenColumns")
        frozen.setModel(self.model())
        frozen.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        frozen.verticalHeader().setVisible(False)
        frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        frozen.setHorizontalScrollMode(self.horizontalScrollMode())
        frozen.setVerticalScrollMode(self.verticalScrollMode())
        frozen.setSelectionBehavior(self.selectionBehavior())
        frozen.setSelectionMode(self.selectionMode())
        frozen.setEditTriggers(self.editTriggers())
        frozen.setAlternatingRowColors(True)
        frozen.setShowGrid(self.showGrid())
        frozen.setSortingEnabled(False)
        frozen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        try:
            frozen.setSelectionModel(self.selectionModel())
        except Exception:
            pass

        fheader = frozen.horizontalHeader()
        fheader.setStretchLastSection(False)
        fheader.setSectionsMovable(False)
        fheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        fheader.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        fheader.sectionClicked.connect(self._on_header_clicked)
        fheader.sectionResized.connect(self._on_frozen_section_resized)
        fheader.customContextMenuRequested.connect(self._on_header_context_menu)

        frozen.clicked.connect(self._on_frozen_clicked)
        frozen.customContextMenuRequested.connect(self._on_frozen_context_menu)

        self.viewport().stackUnder(frozen)
        self.verticalScrollBar().valueChanged.connect(
            frozen.verticalScrollBar().setValue
        )
        frozen.verticalScrollBar().valueChanged.connect(
            self.verticalScrollBar().setValue
        )

        self._frozen = frozen
        self._style_frozen_overlay()

    def _style_frozen_overlay(self):
        frozen = self._frozen
        if frozen is None:
            return
        try:
            frozen.setStyleSheet(self.styleSheet() or "")
            frozen.setPalette(self.palette())
            frozen.setFont(self.font())
            # Subtle edge so sticky columns read as pinned.
            frozen.setFrameShape(self.frameShape())
            frozen.setStyleSheet(
                (self.styleSheet() or "")
                + " QTableView#mediaFrozenColumns {"
                " border-right: 1px solid %s; }" % c("surface2")
            )
        except Exception:
            pass

    def set_frozen_count(
        self, n: int, *, persist: bool = True, ensure_left: bool = True
    ):
        """Freeze the left *n* columns (0–3). Default sticky set is Number + Cart."""
        try:
            n = int(n)
        except Exception:
            n = _DEFAULT_FROZEN_COUNT
        n = max(0, min(n, len(_STICKY_COLUMNS)))
        self._frozen_count = n
        if n > 0 and ensure_left:
            self._ensure_sticky_columns_left(n)
        self._refresh_frozen()
        if persist:
            self._schedule_layout_save()

    def _ensure_sticky_columns_left(self, n: int):
        """Move Number / Download Cart / UserName to the far left for sticky mode."""
        header = self.horizontalHeader()
        names = list(_STICKY_COLUMNS[:n])
        was_applying = self._applying_column_layout
        self._applying_column_layout = True
        try:
            for visual_target, name in enumerate(names):
                try:
                    logical = COLUMNS.index(name)
                except ValueError:
                    continue
                if self.isColumnHidden(logical):
                    self.setColumnHidden(logical, False)
                current = header.visualIndex(logical)
                if current >= 0 and current != visual_target:
                    header.moveSection(current, visual_target)
        finally:
            self._applying_column_layout = was_applying

    def _frozen_pixel_width(self) -> int:
        if self._frozen_count <= 0:
            return 0
        header = self.horizontalHeader()
        total = 0
        for visual in range(self._frozen_count):
            logical = header.logicalIndex(visual)
            if logical < 0 or logical >= len(COLUMNS):
                continue
            if self.isColumnHidden(logical):
                continue
            total += int(self.columnWidth(logical))
        return total

    def _refresh_frozen(self):
        frozen = self._frozen
        if frozen is None:
            return
        n = self._frozen_count
        if n <= 0:
            frozen.hide()
            return

        self._style_frozen_overlay()
        header = self.horizontalHeader()
        self._syncing_frozen_widths = True
        try:
            for logical in range(len(COLUMNS)):
                visual = header.visualIndex(logical)
                hide = (
                    visual < 0
                    or visual >= n
                    or self.isColumnHidden(logical)
                )
                frozen.setColumnHidden(logical, hide)
                if not hide:
                    frozen.setColumnWidth(logical, self.columnWidth(logical))
            # Match row heights.
            for row in range(self.rowCount()):
                frozen.setRowHeight(row, self.rowHeight(row))
            frozen.horizontalHeader().setFixedHeight(header.height())
        finally:
            self._syncing_frozen_widths = False

        frozen.show()
        frozen.raise_()
        self._update_frozen_geometry()
        try:
            frozen.verticalScrollBar().setValue(self.verticalScrollBar().value())
        except Exception:
            pass

    def _update_frozen_geometry(self):
        frozen = self._frozen
        if frozen is None or self._frozen_count <= 0:
            return
        width = self._frozen_pixel_width()
        if width <= 0:
            frozen.hide()
            return
        fw = self.frameWidth()
        frozen.setGeometry(
            fw,
            fw,
            width,
            self.viewport().height() + self.horizontalHeader().height(),
        )

    def _on_frozen_section_resized(self, logical: int, _old: int, new: int):
        if self._syncing_frozen_widths or self._applying_column_layout:
            return
        if logical < 0:
            return
        self._syncing_frozen_widths = True
        try:
            self.setColumnWidth(logical, new)
        finally:
            self._syncing_frozen_widths = False
        self._update_frozen_geometry()
        self._schedule_layout_save()

    def _on_frozen_clicked(self, index):
        if index is None or not index.isValid():
            return
        self._on_cell_clicked(index.row(), index.column())

    def _on_frozen_context_menu(self, pos):
        frozen = self._frozen
        if frozen is None:
            return
        index = frozen.indexAt(pos)
        if not index.isValid():
            return
        item = self.item(index.row(), index.column())
        if not item:
            return
        rect = self.visualItemRect(item)
        self._on_context_menu(rect.center())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_frozen_geometry()

    def _schedule_layout_save(self):
        if self._applying_column_layout:
            return
        try:
            self._layout_save_timer.start()
        except Exception:
            pass

    def _on_section_resized(self, logical: int, _old: int = 0, new: int = 0):
        if (
            not self._syncing_frozen_widths
            and self._frozen is not None
            and self._frozen_count > 0
            and 0 <= logical < len(COLUMNS)
        ):
            header = self.horizontalHeader()
            if header.visualIndex(logical) < self._frozen_count:
                self._syncing_frozen_widths = True
                try:
                    self._frozen.setColumnWidth(logical, self.columnWidth(logical))
                finally:
                    self._syncing_frozen_widths = False
                self._update_frozen_geometry()
        self._schedule_layout_save()

    def _on_section_moved(self, *_args):
        if self._applying_column_layout:
            return
        self._refresh_frozen()
        self._schedule_layout_save()

    def _persist_column_layout(self):
        try:
            from ofscraper.gui.utils.column_layout import (
                capture_from_table,
                save_layout,
            )

            layout = capture_from_table(self, COLUMNS)
            save_layout(layout)
        except Exception as e:
            log.debug(f"[GUI] Persist column layout failed: {e}")

    def _restore_column_layout(self):
        try:
            from ofscraper.gui.utils.column_layout import apply_to_table, load_layout

            layout = load_layout()
            if not layout:
                # Still apply default sticky columns.
                self.set_frozen_count(
                    _DEFAULT_FROZEN_COUNT, persist=False, ensure_left=True
                )
                return
            self._applying_column_layout = True
            try:
                apply_to_table(self, COLUMNS, layout)
            finally:
                self._applying_column_layout = False
            self._refresh_frozen()
        except Exception as e:
            log.debug(f"[GUI] Restore column layout failed: {e}")
            self._applying_column_layout = False

    def _reset_column_layout(self):
        """Restore default widths, show all columns, reset order."""
        try:
            from ofscraper.gui.utils.column_layout import clear_layout

            clear_layout()
        except Exception:
            pass
        header = self.horizontalHeader()
        self._applying_column_layout = True
        try:
            # Reset visual order to logical order.
            for logical in range(header.count()):
                visual = header.visualIndex(logical)
                if visual != logical:
                    header.moveSection(visual, logical)
            for i, col in enumerate(COLUMNS):
                self.setColumnHidden(i, False)
                if col == "Text":
                    self.setColumnWidth(i, 300)
                elif col in ("Download_Cart", "Number"):
                    self.setColumnWidth(i, 100)
                elif col == "Duplicate":
                    self.setColumnWidth(i, 90)
                else:
                    self.setColumnWidth(i, 120)
            self._frozen_count = _DEFAULT_FROZEN_COUNT
            self._ensure_sticky_columns_left(self._frozen_count)
        finally:
            self._applying_column_layout = False
        self._refresh_frozen()
        try:
            app_signals.status_message.emit("Column layout reset to defaults")
        except Exception:
            pass

    def _on_header_context_menu(self, pos):
        """Right-click column header: hide / show / sticky / reset layout."""
        header = self.sender()
        if not isinstance(header, QHeaderView):
            header = self.horizontalHeader()
        logical = header.logicalIndexAt(pos)
        menu = QMenu(self)

        if logical >= 0 and 0 <= logical < len(COLUMNS):
            col_name = COLUMNS[logical].replace("_", " ")
            hide_act = QAction(f'Hide "{col_name}"', self)
            hide_act.triggered.connect(
                lambda _=False, idx=logical: self._hide_column(idx)
            )
            # Keep at least one column visible.
            visible_count = sum(
                1 for i in range(len(COLUMNS)) if not self.isColumnHidden(i)
            )
            hide_act.setEnabled(visible_count > 1)
            menu.addAction(hide_act)
            menu.addSeparator()

        show_menu = menu.addMenu("Show column")
        any_hidden = False
        for i, name in enumerate(COLUMNS):
            if not self.isColumnHidden(i):
                continue
            any_hidden = True
            label = name.replace("_", " ")
            act = QAction(label, self)
            act.triggered.connect(lambda _=False, idx=i: self._show_column(idx))
            show_menu.addAction(act)
        show_menu.setEnabled(any_hidden)

        show_all = QAction("Show all columns", self)
        show_all.setEnabled(any_hidden)
        show_all.triggered.connect(self._show_all_columns)
        menu.addAction(show_all)
        menu.addSeparator()

        sticky_menu = menu.addMenu("Sticky columns")
        sticky_options = [
            (0, "Off"),
            (2, "Number + Download Cart"),
            (3, "Number + Cart + UserName"),
        ]
        for count, label in sticky_options:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self._frozen_count == count)
            act.triggered.connect(
                lambda _=False, n=count: self.set_frozen_count(n, ensure_left=True)
            )
            sticky_menu.addAction(act)

        menu.addSeparator()
        reset_act = QAction("Reset column layout", self)
        reset_act.triggered.connect(self._reset_column_layout)
        menu.addAction(reset_act)

        menu.exec(header.mapToGlobal(pos))

    def _hide_column(self, logical_index: int):
        visible_count = sum(
            1 for i in range(len(COLUMNS)) if not self.isColumnHidden(i)
        )
        if visible_count <= 1:
            return
        self.setColumnHidden(logical_index, True)
        self._refresh_frozen()
        self._schedule_layout_save()

    def _show_column(self, logical_index: int):
        self.setColumnHidden(logical_index, False)
        self._refresh_frozen()
        self._schedule_layout_save()

    def _show_all_columns(self):
        for i in range(len(COLUMNS)):
            self.setColumnHidden(i, False)
        self._refresh_frozen()
        self._schedule_layout_save()

    def _on_header_clicked(self, logical_index):
        """Sort by clicked column header."""
        if logical_index == self._sort_column:
            # Toggle sort order
            self._sort_order = (
                Qt.SortOrder.DescendingOrder
                if self._sort_order == Qt.SortOrder.AscendingOrder
                else Qt.SortOrder.AscendingOrder
            )
        else:
            self._sort_column = logical_index
            self._sort_order = Qt.SortOrder.AscendingOrder

        col_name = COLUMNS[logical_index].lower()
        reverse = self._sort_order == Qt.SortOrder.DescendingOrder

        def sort_key(row):
            val = row.get(col_name, row.get(COLUMNS[logical_index], ""))
            if isinstance(val, bool):
                return (1 if val else 0,)
            if isinstance(val, list):
                return (len(val),)
            if col_name == "price":
                try:
                    return (0.0 if str(val).lower() == "free" else float(val),)
                except (ValueError, TypeError):
                    return (0.0,)
            if col_name == "number":
                try:
                    return (int(val),)
                except (ValueError, TypeError):
                    return (0,)
            try:
                return (float(val),)
            except (ValueError, TypeError):
                return (str(val).lower(),)

        try:
            self._display_data.sort(key=sort_key, reverse=reverse)
        except TypeError:
            self._display_data.sort(
                key=lambda r: str(
                    r.get(col_name, r.get(COLUMNS[logical_index], ""))
                ).lower(),
                reverse=reverse,
            )
        self._rebuild_table()

    def _on_cell_clicked(self, row, col):
        """Handle cell clicks — cart toggle, or open post URL for Post/Media ID."""
        if col in (COLUMNS.index("Post_ID"), COLUMNS.index("Media_ID")):
            self._open_onlyfans_post(row)
            return

        if col != COLUMNS.index("Download_Cart"):
            return

        item = self.item(row, col)
        if not item:
            return

        current = item.text()
        if current == "Locked":
            return
        # Determine target from the clicked cell, then apply to selection.
        if current == "[]":
            new_val = "[added]"
        elif current in ("[added]", "[downloaded]", "[failed]"):
            new_val = "[]"
        else:
            return

        rows = self._selected_row_indexes()
        if row not in rows:
            rows = [row]
        changed = 0
        for r in rows:
            if self._set_cart_value(r, new_val):
                changed += 1
        if changed:
            self._update_cart_count()

    def _open_onlyfans_post(self, row: int):
        """Open https://onlyfans.com/{post_id}/{username} for the given table row."""
        if row < 0 or row >= len(self._display_data):
            return
        data = self._display_data[row]
        post_id = data.get("post_id", data.get("Post_ID", ""))
        username = data.get("username", data.get("UserName", ""))
        if isinstance(username, bool) or username is None:
            username = ""
        post_id = str(post_id or "").strip()
        username = str(username or "").strip()
        if not post_id or not username:
            app_signals.status_message.emit(
                "Cannot open OnlyFans link — missing post ID or username"
            )
            return
        url = f"https://onlyfans.com/{post_id}/{username}"
        QDesktopServices.openUrl(QUrl(url))
        app_signals.status_message.emit(f"Opened {url}")

    def _selected_row_indexes(self) -> list[int]:
        """Unique visual row indexes currently selected (sorted)."""
        seen = set()
        rows = []
        for idx in self.selectionModel().selectedRows():
            r = idx.row()
            if r not in seen:
                seen.add(r)
                rows.append(r)
        return rows

    def _set_cart_value(self, row: int, new_val: str) -> bool:
        """Set cart cell/backing store for one row. Returns True if changed."""
        cart_col = COLUMNS.index("Download_Cart")
        item = self.item(row, cart_col)
        if not item:
            return False
        current = item.text()
        if current == "Locked":
            return False
        if current in ("[downloading]",):
            return False
        if current == new_val:
            return False
        # Only allow toggle between empty/added/downloaded/failed ↔ target
        if current not in ("[]", "[added]", "[downloaded]", "[failed]"):
            return False

        item.setText(new_val)
        item.setForeground(QColor(_cart_color(new_val)))

        if row < len(self._display_data):
            self._display_data[row]["download_cart"] = new_val
            idx = self._display_data[row].get("index", row)
            for rd in self._raw_data:
                if rd.get("index") == idx:
                    rd["download_cart"] = new_val
                    break
        return True

    def add_selected_to_cart(self) -> int:
        """Add all selected unlocked rows to the cart. Returns count changed."""
        rows = self._selected_row_indexes()
        changed = 0
        for r in rows:
            if self._set_cart_value(r, "[added]"):
                changed += 1
        if changed:
            self._update_cart_count()
        return changed

    def remove_selected_from_cart(self) -> int:
        """Remove selected rows from the cart (unlock downloadable states)."""
        rows = self._selected_row_indexes()
        changed = 0
        for r in rows:
            if self._set_cart_value(r, "[]"):
                changed += 1
        if changed:
            self._update_cart_count()
        return changed

    def toggle_selected_cart(self) -> int:
        """Toggle cart for selected rows based on the first selected cell."""
        rows = self._selected_row_indexes()
        if not rows:
            return 0
        cart_col = COLUMNS.index("Download_Cart")
        first = self.item(rows[0], cart_col)
        if not first:
            return 0
        cur = first.text()
        if cur == "Locked" or cur == "[downloading]":
            return 0
        new_val = "[]" if cur == "[added]" else "[added]"
        if cur not in ("[]", "[added]", "[downloaded]", "[failed]"):
            return 0
        changed = 0
        for r in rows:
            if self._set_cart_value(r, new_val):
                changed += 1
        if changed:
            self._update_cart_count()
        return changed

    def keyPressEvent(self, event):
        """Space toggles cart on the current multi-selection."""
        if event.key() == Qt.Key.Key_Space and not event.modifiers():
            n = self.toggle_selected_cart()
            if n:
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_context_menu(self, pos):
        """Right-click: cart actions for selection + filter by cell value."""
        item = self.itemAt(pos)
        if not item:
            return

        col_idx = item.column()
        col_name = COLUMNS[col_idx]
        value = item.text()
        selected = self._selected_row_indexes()
        # Ensure the right-clicked row is part of the selection context.
        if item.row() not in selected:
            self.selectRow(item.row())
            selected = [item.row()]

        menu = QMenu(self)
        n = len(selected)
        add_act = QAction(f"Add selected to cart ({n})", self)
        add_act.triggered.connect(self.add_selected_to_cart)
        menu.addAction(add_act)
        rem_act = QAction(f"Remove selected from cart ({n})", self)
        rem_act.triggered.connect(self.remove_selected_from_cart)
        menu.addAction(rem_act)
        tog_act = QAction("Toggle selected cart", self)
        tog_act.triggered.connect(self.toggle_selected_cart)
        menu.addAction(tog_act)
        menu.addSeparator()
        filter_action = QAction(f'Filter by "{value}"', self)
        filter_action.triggered.connect(
            lambda: self.cell_filter_requested.emit(col_name, value)
        )
        menu.addAction(filter_action)
        menu.exec(self.mapToGlobal(pos))

    def _on_external_cell_update(self, row_key, column_name, new_value):
        """Handle cell updates from external sources (e.g., download completion).
        row_key matches against media_id (preferred) or index.

        In duplicate/repost mode, one media_id may appear in multiple rows.
        Update all matching rows when keyed by media_id so the table reflects
        completion state consistently.
        """
        col_lower = column_name.lower()
        try:
            col_idx = [c.lower() for c in COLUMNS].index(col_lower)
        except ValueError:
            return

        matched_indexes = set()
        update_by_index_only = False

        for row_idx in range(self.rowCount()):
            if row_idx >= len(self._display_data):
                break
            row_data = self._display_data[row_idx]
            media_match = str(row_data.get("media_id", "")) == row_key
            index_match = str(row_data.get("index", "")) == row_key
            if not media_match and not index_match:
                continue

            if index_match and not media_match:
                update_by_index_only = True

            item = self.item(row_idx, col_idx)
            if item:
                # Never overwrite a Locked cart via signal propagation — the row
                # is not accessible and marking it [downloaded] would be misleading.
                if col_lower == "download_cart" and item.text() == "Locked":
                    if index_match and not media_match:
                        break
                    continue
                # When duplicates are skipped by the pipeline, don't propagate
                # Downloaded=True to duplicate rows — the file was only downloaded
                # via the first occurrence, not by this row.
                if col_lower == "downloaded" and row_data.get("duplicate") == "Duplicate":
                    try:
                        import ofscraper.utils.settings as _sett
                        if not _sett.get_settings().allow_dupe_downloads:
                            if index_match and not media_match:
                                break
                            continue
                    except Exception:
                        pass
                item.setText(new_value)
                if col_lower == "download_cart":
                    item.setForeground(QColor(_cart_color(new_value)))
                elif col_lower == "downloaded":
                    if new_value == "True":
                        color = c("green")
                    elif new_value == "N/A":
                        color = c("surface2")
                    else:
                        color = c("red")
                    item.setForeground(QColor(color))
                elif col_lower == "unlocked":
                    if new_value == "Locked":
                        color = c("surface2")
                    elif new_value == "Preview":
                        color = c("sky")
                    elif new_value == "Included":
                        color = c("teal")
                    elif new_value == "True":
                        color = c("green")
                    else:
                        color = c("red")
                    item.setForeground(QColor(color))

            row_data[col_lower] = new_value
            matched_indexes.add(str(row_data.get("index", "")))
            if index_match and not media_match:
                break

        # Keep backing _raw_data in sync as well.
        for row_data in self._raw_data:
            if str(row_data.get("index", "")) in matched_indexes or (not update_by_index_only and str(row_data.get("media_id", "")) == row_key):
                # Don't overwrite Locked cart state in the backing store either.
                if col_lower == "download_cart" and row_data.get("download_cart") == "Locked":
                    continue
                # Don't propagate Downloaded=True to duplicate rows when dupes are skipped.
                if col_lower == "downloaded" and row_data.get("duplicate") == "Duplicate":
                    try:
                        import ofscraper.utils.settings as _sett
                        if not _sett.get_settings().allow_dupe_downloads:
                            continue
                    except Exception:
                        pass
                row_data[col_lower] = new_value

        if col_lower == "download_cart":
            self._update_cart_count()

    def _on_batch_cell_update(self, updates: list):
        """Handle a batch of (row_key, column_name, new_value) updates from the
        poll loop.  Uses the O(1) media_id index instead of a linear scan, so
        processing 500 updates on a 2000-row table takes microseconds instead of
        the 1,000,000 iterations the old per-signal O(n) path required.
        """
        if not updates:
            return

        col_map = {col.lower(): i for i, col in enumerate(COLUMNS)}
        cart_col = col_map.get("download_cart", -1)
        downloaded_col = col_map.get("downloaded", -1)
        unlocked_col = col_map.get("unlocked", -1)
        cart_dirty = False

        self.setUpdatesEnabled(False)
        try:
            for row_key, column_name, new_value in updates:
                col_lower = column_name.lower()
                col_idx = col_map.get(col_lower)
                if col_idx is None:
                    continue

                # O(1) lookup via the media_id index
                row_indices = self._media_id_index.get(row_key, [])
                for row_idx in row_indices:
                    if row_idx >= len(self._display_data):
                        continue
                    row_data = self._display_data[row_idx]

                    # Never overwrite Locked cart state
                    if col_lower == "download_cart" and row_data.get("download_cart") == "Locked":
                        continue
                    # Don't mark duplicate rows as Downloaded=True when dupes aren't enabled
                    if col_lower == "downloaded" and row_data.get("duplicate") == "Duplicate":
                        try:
                            import ofscraper.utils.settings as _sett
                            if not _sett.get_settings().allow_dupe_downloads:
                                continue
                        except Exception:
                            pass

                    # Update the visible cell
                    item = self.item(row_idx, col_idx)
                    if item:
                        item.setText(new_value)
                        if col_lower == "download_cart":
                            item.setForeground(QColor(_cart_color(new_value)))
                            cart_dirty = True
                        elif col_lower == "downloaded":
                            color = c("green") if new_value == "True" else (c("surface2") if new_value == "N/A" else c("red"))
                            item.setForeground(QColor(color))
                        elif col_lower == "unlocked":
                            _umap = {"Locked": "surface2", "Preview": "sky", "Included": "teal", "True": "green"}
                            color = c(_umap.get(new_value, "red"))
                            item.setForeground(QColor(color))

                    # Keep backing stores in sync
                    row_data[col_lower] = new_value

                # Also sync _raw_data via O(1) index (avoids linear scan over 99k rows)
                for raw_row in self._raw_data_by_media_id.get(row_key, []):
                    if col_lower == "download_cart" and raw_row.get("download_cart") == "Locked":
                        continue
                    if col_lower == "downloaded" and raw_row.get("duplicate") == "Duplicate":
                        try:
                            import ofscraper.utils.settings as _sett
                            if not _sett.get_settings().allow_dupe_downloads:
                                continue
                        except Exception:
                            pass
                    raw_row[col_lower] = new_value
        finally:
            self.setUpdatesEnabled(True)

        if cart_dirty:
            self._update_cart_count()

    def _on_posts_liked_updated(self, results: dict):
        """Handle posts_liked_updated signal from a like/unlike action.
        results is {post_id (int): status_str} where status_str is one of
        'Liked', 'Unliked', or 'Failed'.  Updates the Liked column for every
        media row that shares a matching post_id."""
        if not results:
            return
        liked_col = COLUMNS.index("Liked")
        color_map = {
            "Liked": c("green"),
            "Unliked": c("peach"),
            "Failed": c("red"),
        }
        str_results = {str(k): v for k, v in results.items()}

        # Update _raw_data backing store
        for row in self._raw_data:
            pid = str(row.get("post_id", ""))
            if pid in str_results:
                row["liked"] = str_results[pid]

        # Update _display_data and the visible table cells
        for row_idx, row_data in enumerate(self._display_data):
            pid = str(row_data.get("post_id", ""))
            if pid in str_results:
                status = str_results[pid]
                row_data["liked"] = status
                item = self.item(row_idx, liked_col)
                if item:
                    item.setText(status)
                    color = color_map.get(status)
                    if color:
                        item.setForeground(QColor(color))

    def _update_cart_count(self):
        """Count and emit the number of [added] items.

        Reads from _display_data (Python dict lookups) instead of self.item()
        (X11 protocol round-trips) — eliminates the last O(n) X11 read scan on
        the main thread, which was a significant source of Docker GUI lag.
        """
        count = sum(1 for r in self._display_data if r.get("download_cart") == "[added]")
        self.cart_count_changed.emit(count)
        app_signals.download_cart_updated.emit(count)

    def get_cart_items(self):
        """Return list of (row_data, row_key) for all [added] items."""
        cart_col = COLUMNS.index("Download_Cart")
        result = []
        for row_idx in range(self.rowCount()):
            item = self.item(row_idx, cart_col)
            if item and item.text() == "[added]":
                if row_idx < len(self._display_data):
                    row_data = self._display_data[row_idx]
                    row_key = str(row_data.get("index", row_idx))
                    result.append((row_data, row_key))
                    # Mark as downloading
                    item.setText("[downloading]")
                    item.setForeground(
                        QColor(_cart_color("[downloading]"))
                    )
        self._update_cart_count()
        return result

    def select_all_cart(self):
        """Add all visible unlocked items to cart."""
        cart_col = COLUMNS.index("Download_Cart")
        for row_idx in range(self.rowCount()):
            item = self.item(row_idx, cart_col)
            if item and item.text() == "[]":
                item.setText("[added]")
                item.setForeground(QColor(_cart_color("[added]")))
                if row_idx < len(self._display_data):
                    self._display_data[row_idx]["download_cart"] = "[added]"
        self._update_cart_count()

    def deselect_all_cart(self):
        """Remove all items from cart."""
        cart_col = COLUMNS.index("Download_Cart")
        for row_idx in range(self.rowCount()):
            item = self.item(row_idx, cart_col)
            if item and item.text() == "[added]":
                item.setText("[]")
                item.setForeground(QColor(_cart_color("[]")))
                if row_idx < len(self._display_data):
                    self._display_data[row_idx]["download_cart"] = "[]"
        self._update_cart_count()

    def filter_to_media_ids(self, media_ids):
        """Show only rows whose media_id is in *media_ids* (post-run failure filter)."""
        id_set = {str(x) for x in (media_ids or []) if x is not None and str(x) != ""}
        if not id_set:
            return 0
        self._display_data = [
            r for r in self._raw_data if str(r.get("media_id", "")) in id_set
        ]
        self._rebuild_table()
        return len(self._display_data)

    def add_media_ids_to_cart(self, media_ids):
        """Mark matching rows as [added] in the download cart. Returns count added."""
        id_set = {str(x) for x in (media_ids or []) if x is not None and str(x) != ""}
        if not id_set:
            return 0
        added = 0
        for rd in self._raw_data:
            if str(rd.get("media_id", "")) not in id_set:
                continue
            if rd.get("download_cart") == "Locked":
                continue
            if rd.get("download_cart") != "[added]":
                rd["download_cart"] = "[added]"
                added += 1
        for rd in self._display_data:
            if str(rd.get("media_id", "")) in id_set and rd.get("download_cart") != "Locked":
                rd["download_cart"] = "[added]"
        if added and not any(
            str(r.get("media_id", "")) in id_set for r in self._display_data
        ):
            self._display_data = [
                r for r in self._raw_data if str(r.get("media_id", "")) in id_set
            ]
        self._rebuild_table()
        return added

    def _cell_value_for_export(self, row_data: dict, col_name: str, row_idx: int) -> str:
        """Format one cell the same way the table displays it (incl. privacy)."""
        col_lower = col_name.lower()
        if col_lower == "number":
            return str(row_idx + 1)
        if col_lower == "username":
            raw = row_data.get("username", row_data.get("UserName", ""))
            if isinstance(raw, bool) or raw is None:
                raw = ""
            display = str(raw)
            try:
                from ofscraper.gui.utils.privacy_mode import mask_username

                display = mask_username(display)
            except Exception:
                pass
            return display
        value = row_data.get(col_lower, row_data.get(col_name, ""))
        if isinstance(value, list):
            return str(len(value))
        if isinstance(value, bool):
            return str(value)
        return "" if value is None else str(value)

    def rows_for_csv_export(self, *, selected_only: bool = False) -> list[dict]:
        """Return row dicts to export (visible filter, or current selection)."""
        if selected_only:
            rows = []
            for r in self._selected_row_indexes():
                if 0 <= r < len(self._display_data):
                    rows.append(self._display_data[r])
            return rows
        return list(self._display_data)

    def write_csv(self, path, *, selected_only: bool = False) -> int:
        """Write UTF-8 CSV (with BOM for Excel). Returns number of data rows written."""
        import csv
        from pathlib import Path

        rows = self.rows_for_csv_export(selected_only=selected_only)
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        headers = [c.replace("_", " ") for c in COLUMNS]
        with open(out, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for i, row_data in enumerate(rows):
                writer.writerow(
                    [self._cell_value_for_export(row_data, col, i) for col in COLUMNS]
                )
        return len(rows)

    @property
    def row_queue(self):
        return self._row_queue
