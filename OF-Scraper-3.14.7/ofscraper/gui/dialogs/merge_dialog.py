import asyncio
import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.utils.thread_worker import AsyncWorker
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")


class MergePage(QWidget):
    """Database merge page — replaces the InquirerPy merge prompts."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Header
        header = QLabel("Merge Databases")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Recursively search a folder for user_data.db files and merge them "
            "into a single destination database."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Source folder
        src_layout = QHBoxLayout()
        src_layout.addWidget(QLabel("Source Folder:"))
        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("Folder to search for .db files...")
        self.source_input.setClearButtonEnabled(True)
        self.source_input.setToolTip(
            "Root folder to recursively search for user_data.db files.\n"
            "All matching databases found under this path will be merged."
        )
        src_layout.addWidget(self.source_input)
        src_browse = StyledButton("Browse")
        src_browse.clicked.connect(self._browse_source)
        src_layout.addWidget(src_browse)
        layout.addLayout(src_layout)

        # Destination
        dst_layout = QHBoxLayout()
        dst_layout.addWidget(QLabel("Destination:"))
        self.dest_input = QLineEdit()
        self.dest_input.setPlaceholderText("Folder for merged database...")
        self.dest_input.setClearButtonEnabled(True)
        self.dest_input.setToolTip(
            "Destination folder where the merged database will be written.\n"
            "A new user_data.db file will be created here."
        )
        dst_layout.addWidget(self.dest_input)
        dst_browse = StyledButton("Browse")
        dst_browse.clicked.connect(self._browse_dest)
        dst_layout.addWidget(dst_browse)
        layout.addLayout(dst_layout)

        layout.addSpacing(8)

        # Warning
        self._warning_label = QLabel(
            "WARNING: Make sure you have backed up your databases before merging!"
        )
        self._warning_label.setStyleSheet(f"color: {c('warning')}; font-weight: bold;")
        layout.addWidget(self._warning_label)

        app_signals.theme_changed.connect(self._apply_theme)

        # Merge button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.merge_btn = StyledButton("Start Merge", primary=True)
        self.merge_btn.setFixedWidth(180)
        self.merge_btn.clicked.connect(self._on_merge)
        btn_layout.addWidget(self.merge_btn)
        layout.addLayout(btn_layout)

        # Output log
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumBlockCount(500)
        self.output_text.setPlaceholderText("Merge output will appear here...")
        layout.addWidget(self.output_text)

    def _apply_theme(self, _is_dark=True):
        self._warning_label.setStyleSheet(f"color: {c('warning')}; font-weight: bold;")

    def _browse_source(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_input.setText(folder)

    def _browse_dest(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Destination Folder"
        )
        if folder:
            self.dest_input.setText(folder)

    def _on_merge(self):
        source = self.source_input.text().strip()
        dest = self.dest_input.text().strip()

        if not source:
            QMessageBox.warning(self, "Missing", "Please select a source folder.")
            return
        if not dest:
            QMessageBox.warning(self, "Missing", "Please select a destination folder.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Merge",
            f"Merge databases from:\n{source}\n\nInto:\n{dest}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.output_text.clear()
        self.output_text.appendPlainText(f"Starting merge from {source} to {dest}...")
        self.merge_btn.setEnabled(False)
        app_signals.status_message.emit("Merge in progress...")

        # Run merge in background thread
        from PyQt6.QtCore import QThreadPool

        worker = AsyncWorker(self._run_merge, source, dest)
        worker.signals.finished.connect(self._on_merge_finished)
        worker.signals.error.connect(self._on_merge_error)
        QThreadPool.globalInstance().start(worker)

    async def _run_merge(self, source, dest):
        from ofscraper.db.merge import MergeDatabase
        merger = MergeDatabase()
        return await merger(source, dest)

    def _on_merge_finished(self, result):
        self.merge_btn.setEnabled(True)
        if result:
            failures, successes, _ = result
            self.output_text.appendPlainText(
                f"\nMerge complete!\n"
                f"Successes: {len(successes) if successes else 0}\n"
                f"Failures: {len(failures) if failures else 0}"
            )
            if failures:
                for f in failures:
                    self.output_text.appendPlainText(f"  FAILED: {f}")
        else:
            self.output_text.appendPlainText("Merge completed (no details returned).")
        app_signals.status_message.emit("Merge complete")

    def _on_merge_error(self, error_msg):
        self.merge_btn.setEnabled(True)
        self.output_text.appendPlainText(f"\nERROR: {error_msg}")
        app_signals.status_message.emit("Merge failed")
        QMessageBox.critical(self, "Merge Error", error_msg)
