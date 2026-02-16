import logging
import time

from ofscraper.gui.signals import app_signals

log = logging.getLogger("shared")

_task_start_times = {}


def add_download_task(task_id, total):
    """Mirror of updater.add_download_task — emits Qt signal."""
    _task_start_times[task_id] = time.time()
    app_signals.progress_task_added.emit(str(task_id), total)


def update_download_task(task_id, advance):
    """Mirror of updater.increment — emits Qt signal."""
    app_signals.progress_task_updated.emit(str(task_id), advance)


def remove_download_task(task_id):
    """Mirror of updater.remove_download_job_task — emits Qt signal."""
    _task_start_times.pop(str(task_id), None)
    app_signals.progress_task_removed.emit(str(task_id))


def update_overall_progress(completed, total):
    """Update overall progress counts."""
    app_signals.overall_progress_updated.emit(completed, total)


def update_total_bytes(total_bytes):
    """Update total bytes downloaded."""
    app_signals.total_bytes_updated.emit(total_bytes)


def update_cell_status(row_key, column_name, value):
    """Update a cell in the table (e.g., download_cart status)."""
    app_signals.cell_update.emit(str(row_key), column_name, str(value))


def log_to_gui(level, message):
    """Send a log message to the GUI console."""
    app_signals.log_message.emit(level, message)


class GUILogHandler(logging.Handler):
    """Logging handler that forwards records to the GUI console widget."""

    def emit(self, record):
        try:
            msg = self.format(record)
            app_signals.log_message.emit(record.levelname, msg)
        except Exception:
            self.handleError(record)
