import asyncio
import logging
import traceback

from PyQt6.QtCore import QObject, QRunnable, QThread, pyqtSignal, pyqtSlot

log = logging.getLogger("shared")


class WorkerSignals(QObject):
    """Signals emitted by Worker threads."""
    started = pyqtSignal()
    finished = pyqtSignal(object)  # result
    error = pyqtSignal(str)  # error message
    progress = pyqtSignal(int)  # percent 0-100


class Worker(QRunnable):
    """Generic worker for running functions in QThreadPool."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        self.signals.started.emit()
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            log.debug(traceback.format_exc())
            self.signals.error.emit(str(e))


class AsyncWorker(QRunnable):
    """Worker for running async coroutines in QThreadPool."""

    def __init__(self, coro_fn, *args, **kwargs):
        super().__init__()
        self.coro_fn = coro_fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self):
        self.signals.started.emit()
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.coro_fn(*self.args, **self.kwargs)
                )
                self.signals.finished.emit(result)
            finally:
                loop.close()
        except Exception as e:
            log.debug(traceback.format_exc())
            self.signals.error.emit(str(e))


class LongRunningWorker(QThread):
    """QThread-based worker for long-running operations that need
    their own persistent thread (e.g., download processing loop)."""

    started_signal = pyqtSignal()
    finished_signal = pyqtSignal(object)
    error_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self._result = None

    def run(self):
        self.started_signal.emit()
        try:
            self._result = self.fn(*self.args, **self.kwargs)
            self.finished_signal.emit(self._result)
        except Exception as e:
            log.debug(traceback.format_exc())
            self.error_signal.emit(str(e))
