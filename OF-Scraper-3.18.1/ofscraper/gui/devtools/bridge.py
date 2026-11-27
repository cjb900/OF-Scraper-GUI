"""Run a function on the Qt main thread and wait for its result.

The MCP server answers on its own threads, and Qt widgets may only be used
from the main thread: touching them from another one is what crashed the GUI
before (see crash_diagnostics). Every tool call goes through here.
"""

from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot


class CallTimeout(Exception):
    pass


class _Call:
    __slots__ = ("fn", "done", "result", "error")

    def __init__(self, fn):
        self.fn = fn
        self.done = threading.Event()
        self.result = None
        self.error = None


class MainThreadBridge(QObject):
    """Create it on the main thread. ``run(fn)`` from any thread runs ``fn``
    there; a call made on the main thread runs at once."""

    _requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        # the receiver lives on the main thread, so the signal is queued there
        self._requested.connect(self._run)

    @pyqtSlot(object)
    def _run(self, call):
        try:
            call.result = call.fn()
        except BaseException as e:  # handed back to the caller's thread
            call.error = e
        finally:
            call.done.set()

    def run(self, fn, timeout: float = 20.0):
        if QThread.currentThread() is self.thread():
            return fn()
        call = _Call(fn)
        self._requested.emit(call)
        if not call.done.wait(timeout):
            raise CallTimeout(
                f"the GUI didn't answer within {timeout:g} s (it may be busy or showing a modal dialog)"
            )
        if call.error is not None:
            raise call.error
        return call.result
