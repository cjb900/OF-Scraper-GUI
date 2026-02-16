from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals


class ProgressSummaryBar(QWidget):
    """Compact overall progress bar for embedding in a status/footer area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.overall_label = QLabel("Downloads: 0 / 0")
        self.overall_label.setProperty("muted", True)
        layout.addWidget(self.overall_label)

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(True)
        self.overall_progress.setFixedHeight(18)
        # Keep % text legible even when the bar fills.
        # The key is a darker chunk color + bright text.
        self.overall_progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 4px;
                background-color: #313244;
                color: #f8fafc;
                text-align: center;
                padding: 0px;
            }
            QProgressBar::chunk {
                background-color: #1d4ed8;
                border-radius: 4px;
            }
            """
        )
        layout.addWidget(self.overall_progress, stretch=1)

        self.bytes_label = QLabel("Total: 0 B")
        self.bytes_label.setProperty("muted", True)
        layout.addWidget(self.bytes_label)

        self.setFixedHeight(22)

    def _connect_signals(self):
        app_signals.overall_progress_updated.connect(self._update_overall)
        app_signals.total_bytes_updated.connect(self._update_bytes)

    @pyqtSlot(int, int)
    def _update_overall(self, completed, total):
        self.overall_label.setText(f"Downloads: {completed} / {total}")
        if total > 0:
            self.overall_progress.setValue(int((completed / total) * 100))
        else:
            self.overall_progress.setValue(0)

    @pyqtSlot(int)
    def _update_bytes(self, total_bytes):
        self.bytes_label.setText(f"Total: {_format_bytes(total_bytes)}")

    def clear_all(self):
        self.overall_progress.setValue(0)
        self.overall_label.setText("Downloads: 0 / 0")
        self.bytes_label.setText("Total: 0 B")


class ProgressPanel(QWidget):
    """Panel displaying download progress bars and statistics."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks = {}  # task_id -> (QProgressBar, QLabel)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # Overall stats
        stats_layout = QHBoxLayout()
        self.overall_label = QLabel("Downloads: 0 / 0")
        self.overall_label.setProperty("subheading", True)
        stats_layout.addWidget(self.overall_label)

        self.bytes_label = QLabel("Total: 0 B")
        self.bytes_label.setProperty("muted", True)
        stats_layout.addWidget(self.bytes_label)
        stats_layout.addStretch()
        main_layout.addLayout(stats_layout)

        # Overall progress bar
        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(True)
        self.overall_progress.setFixedHeight(24)
        self.overall_progress.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 6px;
                background-color: #313244;
                color: #f8fafc;
                text-align: center;
                padding: 0px;
            }
            QProgressBar::chunk {
                background-color: #1d4ed8;
                border-radius: 6px;
            }
            """
        )
        main_layout.addWidget(self.overall_progress)

        # Scroll area for per-file progress bars
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.tasks_container = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.tasks_layout.setSpacing(4)
        scroll.setWidget(self.tasks_container)
        main_layout.addWidget(scroll)

    def _connect_signals(self):
        app_signals.progress_task_added.connect(self._add_task)
        app_signals.progress_task_updated.connect(self._update_task)
        app_signals.progress_task_removed.connect(self._remove_task)
        app_signals.overall_progress_updated.connect(self._update_overall)
        app_signals.total_bytes_updated.connect(self._update_bytes)

    @pyqtSlot(str, int)
    def _add_task(self, task_id, total):
        if task_id in self._tasks:
            return

        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.setSpacing(2)

        label = QLabel(task_id)
        label.setProperty("muted", True)
        row_layout.addWidget(label)

        bar = QProgressBar()
        bar.setRange(0, max(total, 1))
        bar.setValue(0)
        bar.setFixedHeight(16)
        bar.setTextVisible(True)
        bar.setStyleSheet(
            """
            QProgressBar {
                border: 1px solid #45475a;
                border-radius: 4px;
                background-color: #313244;
                color: #f8fafc;
                text-align: center;
                padding: 0px;
            }
            QProgressBar::chunk {
                background-color: #1d4ed8;
                border-radius: 4px;
            }
            """
        )
        row_layout.addWidget(bar)

        self.tasks_layout.addWidget(row)
        self._tasks[task_id] = (bar, row)

    @pyqtSlot(str, int)
    def _update_task(self, task_id, advance):
        if task_id not in self._tasks:
            return
        bar, _ = self._tasks[task_id]
        bar.setValue(min(bar.value() + advance, bar.maximum()))

    @pyqtSlot(str)
    def _remove_task(self, task_id):
        if task_id not in self._tasks:
            return
        _, row = self._tasks.pop(task_id)
        self.tasks_layout.removeWidget(row)
        row.deleteLater()

    @pyqtSlot(int, int)
    def _update_overall(self, completed, total):
        self.overall_label.setText(f"Downloads: {completed} / {total}")
        if total > 0:
            self.overall_progress.setValue(int((completed / total) * 100))
        else:
            self.overall_progress.setValue(0)

    @pyqtSlot(int)
    def _update_bytes(self, total_bytes):
        self.bytes_label.setText(f"Total: {_format_bytes(total_bytes)}")

    def clear_all(self):
        for task_id in list(self._tasks.keys()):
            self._remove_task(task_id)
        self.overall_progress.setValue(0)
        self.overall_label.setText("Downloads: 0 / 0")
        self.bytes_label.setText("Total: 0 B")


def _format_bytes(num_bytes):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"
