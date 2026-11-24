from PyQt6.QtCore import pyqtSlot
from PyQt6.QtGui import QColor, QTextCharFormat, QFont
from PyQt6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c

# Keep enough history to recolor when the theme toggles (matches QPlainTextEdit cap).
_MAX_LINES = 10000


def _level_color(level: str) -> str:
    """Foreground color for a log level using the active theme palette."""
    key = (level or "").upper()
    return {
        "DEBUG": c("subtext"),
        "INFO": c("green"),
        "WARNING": c("yellow"),
        "ERROR": c("red"),
        "CRITICAL": c("red"),
    }.get(key, c("text"))


class ConsoleLogWidget(QWidget):
    """Log viewer widget that displays application logs with color-coded levels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lines: list[tuple[str, str]] = []
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(_MAX_LINES)
        apply_font(self.text_edit, "Consolas", 11)
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text_edit)

    def _connect_signals(self):
        app_signals.log_message.connect(self._append_log)
        app_signals.theme_changed.connect(self._on_theme_changed)

    def _insert_line(self, level: str, message: str):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_level_color(level)))
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(message + "\n", fmt)

    def _scroll_to_bottom(self):
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @pyqtSlot(str, str)
    def _append_log(self, level, message):
        try:
            from ofscraper.gui.utils.privacy_mode import redact_log_message

            message = redact_log_message(message)
        except Exception:
            pass
        self._lines.append((level, message))
        if len(self._lines) > _MAX_LINES:
            self._lines = self._lines[-_MAX_LINES:]
        self._insert_line(level, message)
        self._scroll_to_bottom()

    @pyqtSlot(bool)
    def _on_theme_changed(self, _is_dark: bool):
        """Re-render stored lines so baked-in light/dark colors don't stick."""
        if not self._lines:
            return
        at_bottom = True
        try:
            sb = self.text_edit.verticalScrollBar()
            at_bottom = sb.value() >= sb.maximum() - 4
        except Exception:
            pass
        self.text_edit.clear()
        for level, message in self._lines:
            self._insert_line(level, message)
        if at_bottom:
            self._scroll_to_bottom()

    def clear_log(self):
        self._lines.clear()
        self.text_edit.clear()
