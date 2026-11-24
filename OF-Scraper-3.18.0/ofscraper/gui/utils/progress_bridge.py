"""GUI progress / cell update helpers with throttling + batching.

Download loops can finish thousands of items per second. Emitting a Qt signal
per item floods the UI thread. Overall progress is rate-limited; cell updates
are coalesced into ``batch_cell_update`` flushes.
"""
from __future__ import annotations

import logging
import threading
import time

from ofscraper.gui.signals import app_signals

log = logging.getLogger("shared")

# Overall progress: emit when % moves enough OR enough time passes.
_PROGRESS_MIN_PCT = 0.005  # 0.5%
_PROGRESS_MIN_INTERVAL_S = 0.25

# Cell updates: flush buffered patches on this cadence.
_CELL_FLUSH_INTERVAL_S = 0.2
_CELL_FLUSH_MAX = 400  # force flush if buffer grows large

_lock = threading.Lock()
_task_start_times: dict = {}

_last_progress_pct = 0.0
_last_progress_time = 0.0
_last_completed = -1
_last_total = -1
_pending_bytes: float | None = None
_last_bytes_emit = 0.0

_cell_buffer: list[tuple[str, str, str]] = []
_last_cell_flush = 0.0


def reset_throttle_state() -> None:
    """Clear throttle state at scrape start so the first update always paints."""
    global _last_progress_pct, _last_progress_time, _last_completed, _last_total
    global _pending_bytes, _last_bytes_emit, _last_cell_flush
    with _lock:
        _last_progress_pct = 0.0
        _last_progress_time = 0.0
        _last_completed = -1
        _last_total = -1
        _pending_bytes = None
        _last_bytes_emit = 0.0
        _cell_buffer.clear()
        _last_cell_flush = 0.0


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


def update_overall_progress(completed, total, *, force: bool = False):
    """Update overall download progress (throttled unless ``force``)."""
    global _last_progress_pct, _last_progress_time, _last_completed, _last_total
    global _pending_bytes, _last_bytes_emit

    try:
        completed_i = int(completed)
        total_i = int(total)
    except Exception:
        return

    now = time.monotonic()
    pct = (completed_i / total_i) if total_i > 0 else 0.0
    done = total_i > 0 and completed_i >= total_i

    with _lock:
        should = bool(force or done)
        if not should:
            pct_moved = abs(pct - _last_progress_pct) >= _PROGRESS_MIN_PCT
            time_ok = now - _last_progress_time >= _PROGRESS_MIN_INTERVAL_S
            first_total = _last_total <= 0 and total_i > 0
            should = first_total or pct_moved or time_ok

        if not should:
            return

        _last_progress_pct = pct
        _last_progress_time = now
        _last_completed = completed_i
        _last_total = total_i
        bytes_to_emit = _pending_bytes
        _pending_bytes = None
        if bytes_to_emit is not None:
            _last_bytes_emit = now

    try:
        app_signals.overall_progress_updated.emit(completed_i, total_i)
    except Exception:
        pass

    if bytes_to_emit is not None:
        try:
            app_signals.total_bytes_updated.emit(float(bytes_to_emit))
        except Exception:
            pass


def update_total_bytes(total_bytes, *, force: bool = False):
    """Update total bytes downloaded (coalesced with progress throttle)."""
    global _pending_bytes, _last_bytes_emit
    try:
        value = float(total_bytes)
    except Exception:
        return

    now = time.monotonic()
    with _lock:
        _pending_bytes = value
        if force or now - _last_bytes_emit >= _PROGRESS_MIN_INTERVAL_S:
            to_emit = _pending_bytes
            _pending_bytes = None
            _last_bytes_emit = now
        else:
            to_emit = None

    if to_emit is not None:
        try:
            app_signals.total_bytes_updated.emit(to_emit)
        except Exception:
            pass


def update_cell_status(row_key, column_name, value):
    """Queue a cell update; flushed in batches to the table."""
    queue_cell_updates([(str(row_key), str(column_name), str(value))])


def queue_cell_updates(updates: list[tuple[str, str, str]], *, force: bool = False):
    """Buffer many cell patches and flush as ``batch_cell_update``."""
    global _last_cell_flush
    if not updates:
        return

    now = time.monotonic()
    batch: list[tuple[str, str, str]] = []
    with _lock:
        _cell_buffer.extend((str(k), str(c), str(v)) for k, c, v in updates)
        if (
            force
            or len(_cell_buffer) >= _CELL_FLUSH_MAX
            or now - _last_cell_flush >= _CELL_FLUSH_INTERVAL_S
        ):
            batch = list(_cell_buffer)
            _cell_buffer.clear()
            _last_cell_flush = now

    if batch:
        try:
            app_signals.batch_cell_update.emit(batch)
        except Exception:
            for row_key, column_name, value in batch:
                try:
                    app_signals.cell_update.emit(row_key, column_name, value)
                except Exception:
                    pass


def flush_pending(*, progress: tuple[int, int] | None = None) -> None:
    """Force-emit any buffered progress / cell updates (end of model or scrape)."""
    global _pending_bytes
    if progress is not None:
        try:
            update_overall_progress(progress[0], progress[1], force=True)
        except Exception:
            pass
    with _lock:
        bytes_to_emit = _pending_bytes
        batch = list(_cell_buffer)
        _cell_buffer.clear()
        _pending_bytes = None
    if bytes_to_emit is not None:
        try:
            app_signals.total_bytes_updated.emit(float(bytes_to_emit))
        except Exception:
            pass
    if batch:
        try:
            app_signals.batch_cell_update.emit(batch)
        except Exception:
            pass


def log_to_gui(level, message):
    """Send a log message to the GUI console."""
    try:
        app_signals.log_message.emit(level, message)
    except RuntimeError:
        pass


class GUILogHandler(logging.Handler):
    """Logging handler that forwards records to the GUI console widget."""

    def emit(self, record):
        try:
            # During model-list fetch, suppress worker→GUI log signals (AV race).
            try:
                from ofscraper.gui.utils import model_fetch as _mf
                import threading

                if getattr(_mf, "_suppress_worker_gui_logs", False) and (
                    threading.current_thread() is not threading.main_thread()
                ):
                    return
            except Exception:
                pass
            msg = self.format(record)
            app_signals.log_message.emit(record.levelname, msg)
        except RuntimeError:
            # AppSignals C++ peer gone (app shutting down / pre-QApp import).
            pass
        except Exception:
            # Avoid logging.handleError recursion spam from worker threads.
            pass
