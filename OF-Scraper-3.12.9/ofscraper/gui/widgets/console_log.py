from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QColor, QTextCharFormat, QFont
from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from ofscraper.gui.signals import app_signals

LEVEL_COLORS = {
    "DEBUG": "#6c7086",
    "INFO": "#a6e3a1",
    "WARNING": "#f9e2af",
    "ERROR": "#f38ba8",
    "CRITICAL": "#f38ba8",
}


class ConsoleLogWidget(QWidget):
    """Log viewer widget that displays application logs with color-coded levels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(10000)
        self.text_edit.setFont(QFont("Consolas", 11))
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text_edit)

    def _connect_signals(self):
        app_signals.log_message.connect(self._append_log)

    @pyqtSlot(str, str)
    def _append_log(self, level, message):
        color = LEVEL_COLORS.get(level.upper(), "#cdd6f4")
        cursor = self.text_edit.textCursor()
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)

        # Auto-scroll to bottom
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_log(self):
        self.text_edit.clear()
