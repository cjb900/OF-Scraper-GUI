import asyncio
import logging
import traceback

from PyQt6.QtCore import QObject, QRunnable, QThread, pyqtSignal, pyqtSlot

log = logging.getLogger("shared")


def _safe_emit(signal, *args) -> None:
    """Emit a Qt signal, ignoring deleted C++ peers (shutdown / autoDelete races)."""
    try:
        signal.emit(*args)
    except RuntimeError:
        # wrapped C/C++ object of type … has been deleted
        pass
    except Exception:
        pass


class WorkerSignals(QObject):
    """Signals emitted by Worker threads."""
    started = pyqtSignal()
    finished = pyqtSignal(object)  # result
    error = pyqtSignal(str)  # error message
    progress = pyqtSignal(int)  # percent 0-100


class Worker(QRunnable):
    """Generic worker for running functions in QThreadPool.

    ``setAutoDelete(False)`` so WorkerSignals stays alive until queued
    cross-thread slots finish. Callers should keep a Python reference
    (e.g. ``self._worker = worker``) until the finished/error slot runs.

    Attributes set when the runnable completes:
      - ``result``: return value of ``fn`` (or None on error)
      - ``error_msg``: error string if failed
      - ``done``: True when finished (success or error)

    For model-list loads on Windows, prefer ``emit_signals=False`` and poll
    ``done`` from a main-thread ``QTimer`` — cross-thread Qt signal delivery
    after the OF API fetch was associated with access-violation crashes.
    """

    def __init__(
        self,
        fn,
        *args,
        emit_result: bool = True,
        emit_signals: bool = True,
        **kwargs,
    ):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.emit_result = bool(emit_result)
        self.emit_signals = bool(emit_signals)
        self.result = None
        self.error_msg = None
        self.done = False
        try:
            from PyQt6.QtCore import QCoreApplication

            parent = QCoreApplication.instance()
        except Exception:
            parent = None
        self.signals = WorkerSignals(parent)
        self.setAutoDelete(False)

    @pyqtSlot()
    def run(self):
        if self.emit_signals:
            _safe_emit(self.signals.started)
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.result = result
            self.error_msg = None
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb(
                    "worker_fn_returned",
                    f"emit_signals={self.emit_signals} type={type(result).__name__}",
                )
            except Exception:
                pass
            if self.emit_signals:
                if self.emit_result:
                    _safe_emit(self.signals.finished, result)
                else:
                    _safe_emit(self.signals.finished, True)
            # Set done LAST so the main-thread poll cannot tear down shared
            # fetch environment while this stack is still unwinding.
            self.done = True
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("worker_done")
            except Exception:
                pass
        except Exception as e:
            self.result = None
            self.error_msg = str(e)
            log.debug(traceback.format_exc())
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("worker_error", self.error_msg)
            except Exception:
                pass
            if self.emit_signals:
                _safe_emit(self.signals.error, str(e))
            self.done = True
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            self.result = None
            self.error_msg = f"{type(e).__name__}: {e}"
            log.debug(traceback.format_exc())
            if self.emit_signals:
                _safe_emit(self.signals.error, self.error_msg)
            self.done = True


class AsyncWorker(QRunnable):
    """Worker for running async coroutines in QThreadPool."""

    def __init__(self, coro_fn, *args, **kwargs):
        super().__init__()
        self.coro_fn = coro_fn
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.error_msg = None
        self.done = False
        try:
            from PyQt6.QtCore import QCoreApplication

            parent = QCoreApplication.instance()
        except Exception:
            parent = None
        self.signals = WorkerSignals(parent)
        self.setAutoDelete(False)

    @pyqtSlot()
    def run(self):
        _safe_emit(self.signals.started)
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.coro_fn(*self.args, **self.kwargs)
                )
                self.result = result
                self.done = True
                _safe_emit(self.signals.finished, result)
            finally:
                loop.close()
        except Exception as e:
            self.error_msg = str(e)
            self.done = True
            log.debug(traceback.format_exc())
            _safe_emit(self.signals.error, str(e))
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            self.error_msg = f"{type(e).__name__}: {e}"
            self.done = True
            log.debug(traceback.format_exc())
            _safe_emit(self.signals.error, self.error_msg)


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
        _safe_emit(self.started_signal)
        try:
            self._result = self.fn(*self.args, **self.kwargs)
            _safe_emit(self.finished_signal, self._result)
        except Exception as e:
            log.debug(traceback.format_exc())
            _safe_emit(self.error_signal, str(e))
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            log.debug(traceback.format_exc())
            _safe_emit(self.error_signal, f"{type(e).__name__}: {e}")
