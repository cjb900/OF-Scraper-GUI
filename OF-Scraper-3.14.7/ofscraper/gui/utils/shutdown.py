"""Quit the GUI cleanly when the process is asked to stop (SIGTERM).

``docker stop`` (and service managers) send SIGTERM. Python's default action
ends the process at once, which cuts off in-flight downloads and database
writes. This hooks SIGTERM into the same cooperative cancel the Cancel button
uses, waits for the scraper thread to finish, then quits the Qt event loop.
"""
from __future__ import annotations

import logging
import signal
import time

from PyQt6.QtCore import QTimer

log = logging.getLogger("shared")

# How long to wait for the scraper thread after SIGTERM before quitting anyway.
# The cancel itself force-stops a stuck scraper after _CANCEL_FORCE_GRACE_SECONDS.
SHUTDOWN_WAIT_SECONDS = 20.0
_POLL_MS = 200


def _close_app(app) -> None:
    """Close every window the way a user would, which ends the event loop.

    Quitting the loop with the main window still open crashed (SIGSEGV) in
    Qt's teardown at interpreter exit; closing the windows first doesn't.
    """
    close_all = getattr(app, "closeAllWindows", None)
    if close_all is None:  # QCoreApplication (no widgets)
        app.quit()
        return
    close_all()
    # In case a window refuses to close.
    QTimer.singleShot(2000, app.quit)


def _scraper_alive(workflow) -> bool:
    thread = getattr(workflow, "_scraper_thread", None)
    return bool(thread is not None and thread.is_alive())


def request_shutdown(app, workflow, wait_seconds: float = SHUTDOWN_WAIT_SECONDS) -> None:
    """Cancel any running scrape, then quit ``app`` once the scraper has stopped.

    Runs on the Qt main thread (called via a zero-delay timer from the signal
    handler). A second call while a shutdown is pending quits immediately.
    """
    if getattr(app, "_ofs_shutdown_requested", False):
        log.warning("[GUI] Second stop request — quitting now")
        _close_app(app)
        return
    app._ofs_shutdown_requested = True  # type: ignore[attr-defined]

    if _scraper_alive(workflow):
        log.warning("[GUI] Stop requested — cancelling the current scrape before exit")
        # Puts the scrape table into its Cancelling state (as the Cancel
        # button does) so the finished run is recorded as cancelled.
        try:
            from ofscraper.gui.signals import app_signals

            app_signals.stop_cancel_requested.emit()
        except Exception:
            pass
        try:
            workflow._on_cancel_scrape()
        except Exception as e:
            log.warning(f"[GUI] Could not cancel the scrape cleanly: {e}")
    else:
        log.warning("[GUI] Stop requested — exiting")
    # Also ends a daemon loop that is waiting between runs.
    try:
        workflow._daemon_stop.set()
    except Exception:
        pass

    deadline = time.monotonic() + wait_seconds

    def _quit_when_idle():
        if _scraper_alive(workflow) and time.monotonic() < deadline:
            QTimer.singleShot(_POLL_MS, _quit_when_idle)
            return
        if _scraper_alive(workflow):
            log.warning("[GUI] Scraper still running after stop request — quitting anyway")
        else:
            log.info("[GUI] Scraper stopped — quitting")
        _close_app(app)

    _quit_when_idle()


def install_sigterm_handler(app, workflow) -> None:
    """Route SIGTERM to :func:`request_shutdown` on the Qt main thread."""
    if not hasattr(signal, "SIGTERM"):
        return

    def _on_sigterm(signum, frame):
        # Signal handlers run between Python bytecodes on the main thread;
        # hand off to the event loop rather than touching Qt objects here.
        QTimer.singleShot(0, lambda: request_shutdown(app, workflow))

    signal.signal(signal.SIGTERM, _on_sigterm)

    # While Qt's event loop runs in C++, Python only runs signal handlers when
    # it next executes bytecode. A short no-op timer keeps that latency low.
    wakeup = QTimer(app)
    wakeup.timeout.connect(lambda: None)
    wakeup.start(250)
    app._ofs_signal_wakeup = wakeup  # type: ignore[attr-defined]
