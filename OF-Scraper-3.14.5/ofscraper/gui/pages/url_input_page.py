"""
URL / Post-ID input page for manual-URL scraping mode.

Shown when the user selects "Scrape individual posts by URL or Post ID"
from the action page.  Bypasses model and area selection entirely.
"""
import logging
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")


def _parse_url_input(text: str) -> list[str]:
    """Split raw text into a clean list of URLs / post IDs.

    Accepts newline or comma as separators.
    Ignores blank lines and lines starting with #.
    """
    tokens = re.split(r"[\n,]+", text)
    return [t.strip() for t in tokens if t.strip() and not t.strip().startswith("#")]


class UrlInputPage(QWidget):
    """Page for entering OnlyFans post URLs or post IDs for manual download.

    Skips model and area selection entirely.
    """

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        title = QLabel("Scrape by Post URL / ID")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        desc = QLabel(
            "Enter one or more OnlyFans post URLs or post IDs below.\n"
            "Separate multiple entries with newlines or commas.\n\n"
            "Accepted formats:\n"
            "  \u2022  Full post URL:   https://onlyfans.com/123456789/username\n"
            "  \u2022  Post ID only:    123456789\n"
            "  \u2022  Profile URL:     https://onlyfans.com/username"
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "https://onlyfans.com/123456789/creatorname\n"
            "987654321\n"
            "https://onlyfans.com/another_post/creator"
        )
        self.url_input.setMinimumHeight(160)
        layout.addWidget(self.url_input, stretch=1)

        self.count_label = QLabel("0 entries")
        try:
            self.count_label.setStyleSheet(f"color: {c('subtext0')};")
        except Exception:
            self.count_label.setStyleSheet("color: gray;")
        layout.addWidget(self.count_label)
        self.url_input.textChanged.connect(self._update_count)

        btn_row = QHBoxLayout()
        from ofscraper.gui.widgets.styled_button import StyledButton as _SB
        back_btn = _SB("\u2190 Back")
        back_btn.clicked.connect(self._on_back)
        btn_row.addWidget(back_btn)
        btn_row.addStretch()

        self.start_btn = StyledButton("\u25b6  Start Scraping", primary=True)
        self.start_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.start_btn.setFixedHeight(36)
        self.start_btn.clicked.connect(self._on_start)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

    def _update_count(self):
        urls = _parse_url_input(self.url_input.toPlainText())
        n = len(urls)
        self.count_label.setText(f"{n} entr{'y' if n == 1 else 'ies'}")

    def _on_back(self):
        parent_stack = self.parent()
        if parent_stack:
            parent_stack.setCurrentIndex(0)  # back to action page

    def _on_start(self):
        urls = _parse_url_input(self.url_input.toPlainText())
        if not urls:
            QMessageBox.warning(
                self,
                "No URLs entered",
                "Please enter at least one post URL or post ID.",
            )
            return
        log.info(f"[GUI] Manual URL scrape: {len(urls)} URL(s)")
        app_signals.manual_urls_confirmed.emit(urls)
