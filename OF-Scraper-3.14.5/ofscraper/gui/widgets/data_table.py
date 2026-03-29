import logging
import queue
import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c

log = logging.getLogger("shared")

# Column definitions matching the TUI's ROW_NAMES
COLUMNS = [
    "Number",
    "Download_Cart",
    "UserName",
    "Downloaded",
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
        self._row_queue = queue.Queue()
        self._sort_column = 0
        self._sort_order = Qt.SortOrder.AscendingOrder

        self._setup_ui()
        self._connect_internal()

    def _setup_ui(self):
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels(
            [c.replace("_", " ") for c in COLUMNS]
        )
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSortingEnabled(False)  # We handle sorting manually
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().setVisible(False)

        # Header sizing
        header = self.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.sectionClicked.connect(self._on_header_clicked)

        # Set minimum column widths
        for i, col in enumerate(COLUMNS):
            if col == "Text":
                self.setColumnWidth(i, 300)
            elif col in ("Download_Cart", "Number"):
                self.setColumnWidth(i, 100)
            else:
                self.setColumnWidth(i, 120)

    def _connect_internal(self):
        self.cellClicked.connect(self._on_cell_clicked)
        self.customContextMenuRequested.connect(self._on_context_menu)
        app_signals.cell_update.connect(self._on_external_cell_update)
        app_signals.posts_liked_updated.connect(self._on_posts_liked_updated)
        app_signals.theme_changed.connect(lambda _: self._rebuild_table())

    def load_data(self, table_data):
        """Load raw table data (list of dicts) into the table, replacing existing data."""
        self._raw_data = table_data
        self._display_data = list(table_data)
        self._rebuild_table()

    def clear_all(self):
        """Clear all table data and reset internal state for a new scrape run."""
        self._raw_data = []
        self._display_data = []

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
        """Append new rows to existing data (for incremental per-user updates).
        Deduplicates by media_id to prevent duplicate entries when loading
        from both the live scraper pipeline and the DB fallback."""
        def _row_identity(r: dict) -> tuple[str, str, str, str]:
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
        self._display_data.extend(deduped)
        self._rebuild_table()

    def apply_filter(self, filter_state):
        """Apply the filter state and rebuild the table with filtered data."""
        filtered = []
        for row in self._raw_data:
            passes = True
            for col in COLUMNS:
                col_lower = col.lower()
                if col_lower in ("number", "download_cart"):
                    continue
                val = row.get(col_lower, row.get(col, ""))
                if not filter_state.validate(col_lower, val):
                    passes = False
                    break
            if passes:
                filtered.append(row)
        self._display_data = filtered
        self._rebuild_table()

    def reset_filter(self):
        """Reset to show all data."""
        self._display_data = list(self._raw_data)
        self._rebuild_table()

    def _rebuild_table(self):
        """Clear and repopulate the table from _display_data."""
        self.setRowCount(0)
        self.setSortingEnabled(False)

        for row_idx, row_data in enumerate(self._display_data):
            self.insertRow(row_idx)
            for col_idx, col_name in enumerate(COLUMNS):
                col_lower = col_name.lower()
                if col_lower == "number":
                    value = str(row_idx + 1)
                else:
                    value = row_data.get(col_lower, row_data.get(col_name, ""))

                # Format display value
                if isinstance(value, list):
                    display = str(len(value))
                elif isinstance(value, bool):
                    display = str(value)
                else:
                    display = str(value)

                item = QTableWidgetItem(display)
                item.setFont(QFont("Consolas", 11))

                # Style the download cart column
                if col_lower == "download_cart":
                    item.setForeground(QColor(_cart_color(display)))
                    item.setFont(QFont("Consolas", 11, QFont.Weight.Bold))

                # Style downloaded/unlocked/price columns
                if col_lower == "downloaded":
                    if display == "True":
                        item.setForeground(QColor(c("green")))
                    elif display == "N/A":
                        item.setForeground(QColor(c("surface2")))
                    else:
                        item.setForeground(QColor(c("red")))
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

                # Truncate long text
                if col_lower == "text" and len(display) > 80:
                    item.setToolTip(display)
                    item.setText(display[:80] + "...")

                self.setItem(row_idx, col_idx, item)

        self._update_cart_count()

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
        """Handle cell clicks — toggle download cart."""
        if col != COLUMNS.index("Download_Cart"):
            return

        item = self.item(row, col)
        if not item:
            return

        current = item.text()
        if current == "Locked":
            return
        elif current == "[]":
            new_val = "[added]"
        elif current == "[added]":
            new_val = "[]"
        elif current in ("[downloaded]", "[failed]"):
            new_val = "[]"
        else:
            return

        item.setText(new_val)
        item.setForeground(QColor(_cart_color(new_val)))

        # Update raw data
        if row < len(self._display_data):
            self._display_data[row]["download_cart"] = new_val
            # Also update in _raw_data
            idx = self._display_data[row].get("index", row)
            for rd in self._raw_data:
                if rd.get("index") == idx:
                    rd["download_cart"] = new_val
                    break

        self._update_cart_count()

    def _on_context_menu(self, pos):
        """Right-click context menu to filter by cell value."""
        item = self.itemAt(pos)
        if not item:
            return

        col_idx = item.column()
        col_name = COLUMNS[col_idx]
        value = item.text()

        menu = QMenu(self)
        filter_action = QAction(f'Filter by "{value}"', self)
        filter_action.triggered.connect(
            lambda: self.cell_filter_requested.emit(col_name, value)
        )
        menu.addAction(filter_action)
        menu.exec(self.mapToGlobal(pos))

    def _on_external_cell_update(self, row_key, column_name, new_value):
        """Handle cell updates from external sources (e.g., download completion).
        row_key matches against media_id (preferred) or index."""
        col_lower = column_name.lower()
        try:
            col_idx = [c.lower() for c in COLUMNS].index(col_lower)
        except ValueError:
            return

        for row_idx in range(self.rowCount()):
            if row_idx >= len(self._display_data):
                break
            row_data = self._display_data[row_idx]
            # Match by media_id first, fallback to index
            if str(row_data.get("media_id", "")) == row_key or str(
                row_data.get("index", "")
            ) == row_key:
                item = self.item(row_idx, col_idx)
                if item:
                    item.setText(new_value)
                    # Style download_cart and downloaded columns
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
                # Also update the backing data
                row_data[col_lower] = new_value
                # If this update was keyed by index, only update that row.
                # If keyed by media_id, update all rows that share that media_id.
                if str(row_data.get("index", "")) == row_key:
                    break

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
        """Count and emit the number of [added] items."""
        cart_col = COLUMNS.index("Download_Cart")
        count = 0
        for row_idx in range(self.rowCount()):
            item = self.item(row_idx, cart_col)
            if item and item.text() == "[added]":
                count += 1
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

    @property
    def row_queue(self):
        return self._row_queue
