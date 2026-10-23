"""SIGTERM (docker stop) cancels the scrape and quits the GUI event loop."""
from __future__ import annotations

import os
import signal
import sys
import threading
import time

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        sys.platform == "win32", reason="SIGTERM can't be delivered in-process on Windows"
    ),
]

QtCore = pytest.importorskip("PyQt6.QtCore")

from ofscraper.gui.utils import shutdown  # noqa: E402


class _Workflow:
    """Stand-in for GUIWorkflow: the scraper thread runs until cancelled."""

    def __init__(self, stop_on_cancel=True):
        self.cancel_calls = 0
        self._cancelled = threading.Event()
        self._daemon_stop = threading.Event()
        self._scraper_thread = threading.Thread(
            target=self._cancelled.wait if stop_on_cancel else lambda: time.sleep(30),
            daemon=True,
        )
        self._scraper_thread.start()

    def _on_cancel_scrape(self):
        self.cancel_calls += 1
        self._cancelled.set()


@pytest.fixture
def app(monkeypatch):
    previous = signal.getsignal(signal.SIGTERM)
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    for attr in ("_ofs_shutdown_requested",):
        if hasattr(app, attr):
            delattr(app, attr)
    yield app
    signal.signal(signal.SIGTERM, previous)
    if hasattr(app, "_ofs_signal_wakeup"):
        app._ofs_signal_wakeup.stop()


def _run(app, seconds=10.0):
    # safety net so a broken handler can't hang the test run
    QtCore.QTimer.singleShot(int(seconds * 1000), app.quit)
    start = time.monotonic()
    app.exec()
    return time.monotonic() - start


def test_sigterm_cancels_scrape_then_quits(app):
    workflow = _Workflow()
    shutdown.install_sigterm_handler(app, workflow)
    QtCore.QTimer.singleShot(200, lambda: os.kill(os.getpid(), signal.SIGTERM))
    elapsed = _run(app)
    assert workflow.cancel_calls == 1
    assert workflow._daemon_stop.is_set()
    assert not workflow._scraper_thread.is_alive()
    assert elapsed < 5


def test_quits_without_a_running_scrape(app):
    workflow = _Workflow()
    workflow._on_cancel_scrape()  # thread already finished
    workflow._scraper_thread.join(2)
    workflow.cancel_calls = 0
    shutdown.install_sigterm_handler(app, workflow)
    QtCore.QTimer.singleShot(200, lambda: os.kill(os.getpid(), signal.SIGTERM))
    assert _run(app) < 5
    assert workflow.cancel_calls == 0


def test_stuck_scraper_quits_after_the_wait(app, monkeypatch):
    monkeypatch.setattr(shutdown, "SHUTDOWN_WAIT_SECONDS", 1.0)
    workflow = _Workflow(stop_on_cancel=False)
    QtCore.QTimer.singleShot(
        200, lambda: shutdown.request_shutdown(app, workflow, wait_seconds=1.0)
    )
    elapsed = _run(app)
    assert workflow.cancel_calls == 1
    assert 1.0 <= elapsed < 5
