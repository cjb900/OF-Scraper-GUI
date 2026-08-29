"""Browse / filter / re-run / delete recent scrape history entries."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton
from ofscraper.gui.utils.scrape_history import (
    clear_history,
    delete_entry,
    duration_seconds,
    format_bytes,
    format_details_html,
    format_duration,
    format_models_short,
    format_short_ts,
    load_history,
)


class HistoryDialog(QDialog):
    """Table browser for scrape_history.json entries."""

    rerun_requested = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scrape history")
        self.setMinimumSize(860, 480)
        self.setModal(True)
        self._runs: list[dict] = []
        self._filtered: list[dict] = []
        self._setup_ui()
        self.reload()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        header = QLabel("Scrape history")
        apply_font(header, "Segoe UI", 16, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Recent scrape / check runs. Filter by status or model, open details, "
            "re-run a job, or delete entries. Re-run never restores delete options."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItem("All", "all")
        self.status_filter.addItem("OK", "ok")
        self.status_filter.addItem("Cancelled", "cancelled")
        self.status_filter.addItem("Error", "error")
        self.status_filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self.status_filter)

        filters.addWidget(QLabel("Search:"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Model name…")
        self.search.textChanged.connect(self._apply_filters)
        filters.addWidget(self.search, 1)

        self.count_lbl = QLabel("")
        self.count_lbl.setProperty("subheading", True)
        filters.addWidget(self.count_lbl)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["When", "Status", "Models", "Action", "Downloads", "Size", "Duration"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {c('base')}; color: {c('text')};"
            f" gridline-color: {c('surface1')}; }}"
            f" QHeaderView::section {{ background-color: {c('mantle')}; color: {c('text')};"
            f" padding: 6px; border: 1px solid {c('surface1')}; }}"
        )
        self.table.doubleClicked.connect(self._on_details)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.details_btn = StyledButton("Details")
        self.details_btn.clicked.connect(self._on_details)
        buttons.addWidget(self.details_btn)

        self.rerun_btn = StyledButton("Re-run this", primary=True)
        self.rerun_btn.clicked.connect(self._on_rerun)
        buttons.addWidget(self.rerun_btn)

        self.delete_btn = StyledButton("Delete")
        self.delete_btn.clicked.connect(self._on_delete)
        buttons.addWidget(self.delete_btn)

        self.clear_btn = StyledButton("Clear all…")
        self.clear_btn.clicked.connect(self._on_clear)
        buttons.addWidget(self.clear_btn)

        buttons.addStretch(1)
        close_btn = StyledButton("Close")
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._update_buttons()

    def reload(self):
        self._runs = load_history()
        self._apply_filters()

    def _apply_filters(self):
        status = self.status_filter.currentData()
        q = (self.search.text() or "").strip().lower()
        rows = []
        for entry in self._runs:
            st = str(entry.get("status") or "ok")
            if status and status != "all" and st != status:
                continue
            if q:
                models = " ".join(str(m) for m in (entry.get("models") or [])).lower()
                actions = " ".join(str(a) for a in (entry.get("actions") or [])).lower()
                hay = f"{models} {actions}"
                if q not in hay:
                    continue
            rows.append(entry)
        self._filtered = rows
        self._populate_table()
        self._update_buttons()

    def _populate_table(self):
        self.table.setRowCount(0)
        for row, entry in enumerate(self._filtered):
            self.table.insertRow(row)
            status = str(entry.get("status") or "ok")
            actions = entry.get("actions") or []
            act = (
                actions[0]
                if len(actions) == 1
                else (",".join(actions[:2]) + ("…" if len(actions) > 2 else ""))
            ) or "download"
            dl = int(entry.get("run_dl") or 0)
            fail = int(entry.get("failed") or 0)
            dl_txt = f"{dl}"
            if fail:
                dl_txt += f" ({fail} fail)"
            values = [
                format_short_ts(entry.get("ts_end") or entry.get("ts_start")),
                status,
                format_models_short(entry),
                act,
                dl_txt,
                format_bytes(int(entry.get("total_bytes") or 0)),
                format_duration(duration_seconds(entry)),
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(str(val))
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, entry)
                if col == 1:
                    color = {
                        "ok": c("green"),
                        "cancelled": c("yellow"),
                        "error": c("red"),
                    }.get(status)
                    if color:
                        cell.setForeground(QColor(color))
                self.table.setItem(row, col, cell)
        self.table.resizeColumnsToContents()
        shown = len(self._filtered)
        total = len(self._runs)
        self.count_lbl.setText(f"{shown} shown / {total} saved")

    def _selected_entry(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        if not item:
            return None
        entry = item.data(Qt.ItemDataRole.UserRole)
        return entry if isinstance(entry, dict) else None

    def _update_buttons(self):
        has = self._selected_entry() is not None
        self.details_btn.setEnabled(has)
        self.rerun_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)
        self.clear_btn.setEnabled(bool(self._runs))

    def _on_details(self):
        entry = self._selected_entry()
        if not entry:
            return
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle("Scrape run details")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText("<b>Scrape run</b>")
        msg.setInformativeText(format_details_html(entry))
        msg.addButton(QMessageBox.StandardButton.Close)
        msg.exec()

    def _on_rerun(self):
        entry = self._selected_entry()
        if not entry:
            return
        self.rerun_requested.emit(dict(entry))
        self.accept()

    def _on_delete(self):
        entry = self._selected_entry()
        if not entry:
            return
        reply = QMessageBox.question(
            self,
            "Delete history entry",
            "Remove this scrape run from history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        eid = str(entry.get("id") or "")
        if eid and delete_entry(eid):
            self.reload()

    def _on_clear(self):
        reply = QMessageBox.question(
            self,
            "Clear scrape history",
            "Delete all saved recent scrape runs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        clear_history()
        self.reload()
