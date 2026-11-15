"""Post-run dialog listing download failures from the current scrape."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton


class FailureSummaryDialog(QDialog):
    """Shows failed downloads and optional table/cart actions."""

    filter_requested = pyqtSignal(list)  # list of media_id strings
    add_to_cart_requested = pyqtSignal(list)  # list of media_id strings

    def __init__(self, failures: list[dict], parent=None, *, show_cart_actions: bool = True):
        super().__init__(parent)
        self._failures = list(failures or [])
        self._show_cart_actions = bool(show_cart_actions)
        self.setWindowTitle("Download failures")
        self.setMinimumSize(720, 420)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel(f"Download failures ({len(self._failures)})")
        apply_font(header, "Segoe UI", 16, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        if self._show_cart_actions:
            subtitle_text = (
                "These items failed during the last scrape. "
                "You can filter the results table to them or add them to the "
                "download cart for >> Send Downloads (check mode)."
            )
        else:
            subtitle_text = (
                "These items failed during the last scrape. "
                "You can filter the results table to them. "
                "Cart / Send Downloads is only available in check mode."
            )
        subtitle = QLabel(subtitle_text)
        subtitle.setWordWrap(True)
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Model", "Media ID", "Type", "Post ID", "Reason"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            f"QTableWidget {{ background-color: {c('base')}; color: {c('text')};"
            f" gridline-color: {c('surface1')}; }}"
            f" QHeaderView::section {{ background-color: {c('mantle')}; color: {c('text')};"
            f" padding: 6px; border: 1px solid {c('surface1')}; }}"
        )

        try:
            from ofscraper.gui.utils.privacy_mode import mask_username
        except Exception:
            mask_username = lambda u: "" if u is None else str(u)  # noqa: E731

        for row, item in enumerate(self._failures):
            self.table.insertRow(row)
            values = [
                mask_username(item.get("username", "")),
                str(item.get("media_id", "")),
                str(item.get("mediatype", "")),
                str(item.get("post_id", "")),
                str(item.get("reason", "")),
            ]
            for col, val in enumerate(values):
                cell = QTableWidgetItem(val)
                cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, cell)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        filter_btn = StyledButton("Filter table to failures")
        filter_btn.setToolTip("Show only these media IDs in the results table")
        filter_btn.clicked.connect(self._on_filter)
        btn_row.addWidget(filter_btn)

        if self._show_cart_actions:
            cart_btn = StyledButton("Add failures to cart")
            cart_btn.setToolTip(
                "Mark matching table rows as [added] for >> Send Downloads"
            )
            cart_btn.clicked.connect(self._on_add_cart)
            btn_row.addWidget(cart_btn)

        btn_row.addStretch()

        close_btn = StyledButton("Close", primary=True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _media_ids(self) -> list[str]:
        ids = []
        for item in self._failures:
            mid = item.get("media_id", "")
            if mid is None or mid == "":
                continue
            ids.append(str(mid))
        return ids

    def _on_filter(self):
        self.filter_requested.emit(self._media_ids())
        self.accept()

    def _on_add_cart(self):
        self.add_to_cart_requested.emit(self._media_ids())
        self.accept()
