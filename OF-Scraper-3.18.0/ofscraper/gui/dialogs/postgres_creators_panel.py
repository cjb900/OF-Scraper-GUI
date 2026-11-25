"""Merge DBs > Creators: each creator PostgreSQL holds for a site, with their
counts, and deleting a creator's rows so they are scraped from scratch (what
deleting their user_data.db did with SQLite files).

The data comes from gui/utils/postgres_creators.py, read in the background
from the database this window uses.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.utils import postgres_creators as data
from ofscraper.gui.utils import postgres_setup as pg
from ofscraper.gui.utils.privacy_mode import is_privacy_mode, mask_username
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

SITES = (("OnlyFans", "onlyfans"), ("Fansly", "fansly"))
COLUMNS = (
    "Creator", "ID", "Media", "Downloaded", "Not downloaded", "Size",
    "Posts", "Messages", "Stories", "Other", "Newest post", "Last seen",
)
DETAIL_COLUMNS = ("Area", "Type", "Media", "Downloaded", "Size")


def format_size(size) -> str:
    from humanfriendly import format_size as fmt

    return fmt(int(size or 0)) if size else "0 bytes"


def _day(iso: str) -> str:
    return (iso or "")[:10]


class _Item(QTableWidgetItem):
    """A cell that sorts by its value, not its text (sizes, counts, dates)."""

    def __init__(self, text, value):
        super().__init__(text)
        self.setData(Qt.ItemDataRole.UserRole, value)
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def __lt__(self, other):
        mine = self.data(Qt.ItemDataRole.UserRole)
        theirs = other.data(Qt.ItemDataRole.UserRole)
        try:
            return mine < theirs
        except TypeError:
            return str(mine) < str(theirs)


def _number(value) -> _Item:
    item = _Item(f"{value:,}", value)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


class PostgresCreatorsPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._creators: list[data.Creator] = []
        self._worker = None
        self._scraping = False
        self._loaded = False
        self._url = ""
        self._site = "onlyfans"
        self._setup_ui()
        self._update_buttons()
        app_signals.scrape_started.connect(lambda: self._set_scraping(True))
        app_signals.scraping_finished.connect(lambda: self._set_scraping(False))
        app_signals.privacy_mode_changed.connect(lambda *_: self._fill_table())

    def showEvent(self, event):
        if not self._loaded:
            self._loaded = True
            self.refresh()
        super().showEvent(event)

    # --- layout ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 4)
        layout.setSpacing(10)

        intro = QLabel(
            "Each creator PostgreSQL holds for a site, with what was found and "
            "downloaded. Deleting a creator here removes their rows so the next "
            "scrape starts from scratch, as deleting their user_data.db did. "
            "Downloaded files on disk are not touched."
        )
        intro.setWordWrap(True)
        intro.setProperty("subheading", True)
        layout.addWidget(intro)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Site:"))
        self.site_combo = QComboBox()
        for label, site in SITES:
            self.site_combo.addItem(label, site)
        self.site_combo.currentIndexChanged.connect(lambda *_: self.refresh())
        bar.addWidget(self.site_combo)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by name or ID")
        self.filter_input.setClearButtonEnabled(True)
        self.filter_input.textChanged.connect(lambda *_: self._apply_filter())
        bar.addWidget(self.filter_input, 1)
        self.refresh_btn = StyledButton("Refresh")
        self.refresh_btn.clicked.connect(lambda: self.refresh())
        bar.addWidget(self.refresh_btn)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self.table)

        details = QGroupBox("Selected creator")
        details_layout = QVBoxLayout(details)
        self.names_label = QLabel("Select a creator to see their names and media by area.")
        self.names_label.setWordWrap(True)
        details_layout.addWidget(self.names_label)
        self.detail_table = QTableWidget(0, len(DETAIL_COLUMNS))
        self.detail_table.setHorizontalHeaderLabels(DETAIL_COLUMNS)
        self.detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.detail_table.verticalHeader().setVisible(False)
        self.detail_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        details_layout.addWidget(self.detail_table)
        splitter.addWidget(details)
        splitter.setSizes([400, 220])

        bottom = QHBoxLayout()
        self.summary_label = QLabel()
        bottom.addWidget(self.summary_label, 1)
        self.forget_names = QCheckBox("Also forget their usernames")
        self.forget_names.setChecked(True)
        self.forget_names.setToolTip(
            "On: everything about the creator goes, as deleting their user_data.db did, "
            "and they leave this list until they are scraped again.\n"
            "Off: their usernames stay, so they stay listed with no media."
        )
        bottom.addWidget(self.forget_names)
        self.delete_btn = StyledButton("Delete selected creators…", danger=True)
        self.delete_btn.clicked.connect(self._on_delete)
        bottom.addWidget(self.delete_btn)
        layout.addLayout(bottom)

    # --- state -------------------------------------------------------------------

    def _set_scraping(self, on):
        self._scraping = bool(on)
        self._update_buttons()

    def _selected(self) -> list[data.Creator]:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        chosen = []
        for row in sorted(rows):
            item = self.table.item(row, 1)
            if item is None:
                continue
            model_id = item.data(Qt.ItemDataRole.UserRole)
            chosen += [c for c in self._creators if c.model_id == model_id]
        return chosen

    def _update_buttons(self):
        busy = self._worker is not None
        self.refresh_btn.setEnabled(not busy)
        self.site_combo.setEnabled(not busy)
        self.delete_btn.setEnabled(
            not busy and not self._scraping and bool(self._url) and bool(self._selected())
        )
        self.delete_btn.setToolTip(
            "Wait for the scrape to finish first." if self._scraping else ""
        )

    def _run(self, fn, done):
        worker = Worker(fn)

        def finished(result):
            self._worker = None
            self._update_buttons()
            done(result, None)

        def failed(message):
            self._worker = None
            self._update_buttons()
            done(None, message)

        worker.signals.finished.connect(finished)
        worker.signals.error.connect(failed)
        self._worker = worker
        self._update_buttons()
        QThreadPool.globalInstance().start(worker)

    def _status(self, text, warn=False):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {c('warning')};" if warn else "")

    # --- reading -----------------------------------------------------------------

    def refresh(self, *_, note=""):
        if self._worker is not None:
            return
        self._url = pg.active_url()
        self._site = self.site_combo.currentData()
        if not self._url:
            self._creators = []
            self._fill_table()
            saved = pg.saved_url()
            self._status(
                "PostgreSQL is saved but not in use yet: restart the GUI first."
                if saved else
                "This window uses user_data.db files, not PostgreSQL. Turn PostgreSQL "
                "on in the PostgreSQL tab to see and manage creators here.",
                warn=True,
            )
            self._update_buttons()
            return
        if not pg.driver_installed():
            self._status(pg.driver_missing_text(), warn=True)
            return
        self._status(f"Reading {self.site_combo.currentText()} creators from {pg.describe(self._url)}…")
        url, site = self._url, self._site

        def done(result, error):
            if error:
                self._status(f"Couldn't read the creators: {pg.masked(error, url)}", warn=True)
                return
            self._creators = result or []
            said = f"{self.site_combo.currentText()} creators in PostgreSQL at {pg.describe(url)}."
            self._status(f"{note} {said}" if note else said)
            self._fill_table()

        self._run(lambda: data.list_creators(url, site), done)

    def _name(self, creator) -> str:
        return mask_username(creator.username) if creator.username else "(no name saved)"

    def _fill_table(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        privacy = is_privacy_mode()
        for creator in self._creators:
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = _Item(self._name(creator), creator.username.lower())
            name.setData(Qt.ItemDataRole.UserRole + 1, creator.username)
            self.table.setItem(row, 0, name)
            id_item = _Item("•••" if privacy else str(creator.model_id), creator.model_id)
            self.table.setItem(row, 1, id_item)
            self.table.setItem(row, 2, _number(creator.media))
            self.table.setItem(row, 3, _number(creator.downloaded))
            self.table.setItem(row, 4, _number(creator.missing))
            size = _Item(format_size(creator.size), creator.size)
            size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 5, size)
            self.table.setItem(row, 6, _number(creator.posts))
            self.table.setItem(row, 7, _number(creator.messages))
            self.table.setItem(row, 8, _number(creator.stories))
            self.table.setItem(row, 9, _number(creator.other))
            self.table.setItem(row, 10, _Item(_day(creator.newest_post), creator.newest_post))
            self.table.setItem(row, 11, _Item(_day(creator.last_seen), creator.last_seen))
        self.table.setSortingEnabled(True)
        self._apply_filter()
        total = len(self._creators)
        media = sum(c.media for c in self._creators)
        done = sum(c.downloaded for c in self._creators)
        size = sum(c.size for c in self._creators)
        self.summary_label.setText(
            f"{total:,} creator{'s' if total != 1 else ''} · {media:,} media · "
            f"{done:,} downloaded · {format_size(size)}" if total else ""
        )
        self._on_selection()

    def _apply_filter(self):
        wanted = self.filter_input.text().strip().lower()
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 0)
            ident = self.table.item(row, 1)
            actual = str(name.data(Qt.ItemDataRole.UserRole + 1) or "").lower()
            model_id = str(ident.data(Qt.ItemDataRole.UserRole))
            self.table.setRowHidden(row, bool(wanted) and wanted not in actual and wanted not in model_id)

    def _on_selection(self):
        self._update_buttons()
        chosen = self._selected()
        self.detail_table.setRowCount(0)
        if len(chosen) != 1:
            self.names_label.setText(
                f"{len(chosen)} creators selected." if chosen
                else "Select a creator to see their names and media by area."
            )
            return
        creator = chosen[0]
        if self._worker is not None or not self._url:
            return
        url, site = self._url, self._site
        self.names_label.setText(f"Reading {self._name(creator)}…")

        def done(result, error):
            if self._selected() != [creator]:
                return  # the selection moved on meanwhile
            if error:
                self.names_label.setText(f"Couldn't read the details: {pg.masked(error, url)}")
                return
            self._show_details(creator, result)

        self._run(lambda: data.creator_details(url, site, creator.model_id), done)

    def _show_details(self, creator, details):
        if details.names:
            names = "; ".join(
                mask_username(n)
                + (f" (seen {_day(first) or '?'} to {_day(last) or '?'})" if first or last else "")
                for n, first, last in details.names
            )
            self.names_label.setText(f"Usernames: {names}")
        else:
            self.names_label.setText("No username saved for this creator.")
        for area, kind, media, done, size in details.breakdown:
            row = self.detail_table.rowCount()
            self.detail_table.insertRow(row)
            self.detail_table.setItem(row, 0, _Item(area, area))
            self.detail_table.setItem(row, 1, _Item(kind, kind))
            self.detail_table.setItem(row, 2, _number(media))
            self.detail_table.setItem(row, 3, _number(done))
            self.detail_table.setItem(row, 4, _Item(format_size(size), size))

    # --- deleting ----------------------------------------------------------------

    def _on_delete(self):
        chosen = self._selected()
        if not chosen or not self._url:
            return
        if self._scraping:
            QMessageBox.warning(self, "Delete creators", "Wait for the scrape to finish first.")
            return
        names = "\n".join(
            f"  • {self._name(c)}" + ("" if is_privacy_mode() else f" ({c.model_id})")
            + f": {c.media:,} media, {c.downloaded:,} downloaded"
            for c in chosen[:15]
        )
        if len(chosen) > 15:
            names += f"\n  … and {len(chosen) - 15} more"
        forget = self.forget_names.isChecked()
        answer = QMessageBox.warning(
            self,
            "Delete creators",
            f"Delete {len(chosen)} {self.site_combo.currentText()} creator"
            f"{'s' if len(chosen) != 1 else ''} from PostgreSQL?\n\n{names}\n\n"
            "Their records go (what was found, downloaded and unlocked), so the next "
            "scrape treats everything as new and downloads it all again. A file "
            "already there with the same content is kept, not doubled. Downloaded "
            "files are not deleted."
            + ("\nTheir usernames are forgotten too." if forget else "\nTheir usernames are kept.")
            + "\n\nThis can't be undone (back up with pg_dump first if unsure). Make sure "
            "no scrape is running in either tab, including daemon mode.\n\nDelete?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        url, site = self._url, self._site
        ids = [c.model_id for c in chosen]
        self._status("Deleting…")

        def done(result, error):
            if error:
                self._status(f"Nothing was deleted: {pg.masked(error, url)}", warn=True)
                QMessageBox.warning(self, "Delete creators", f"Nothing was deleted.\n\n{pg.masked(error, url)}")
                return
            rows = sum((result or {}).values())
            log.info(f"[PostgreSQL] deleted {len(ids)} {site} creator(s): {rows} rows")
            self.refresh(note=f"Deleted {len(ids)} creator{'s' if len(ids) != 1 else ''} ({rows:,} rows).")

        self._run(lambda: data.delete_creators(url, site, ids, forget_names=forget), done)
