# PR #25: fix(gui): cancel the scrape and quit cleanly on SIGTERM

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/25
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/gui-sigterm-shutdown` → `main`
- **Created:** 2026-10-23T03:10:17Z  ·  **Updated:** 2026-10-23T03:10:17Z
- **Draft:** False
- **Changes:** 3 files, +203 / -0

## Description

Makes the GUI shut down cleanly when it receives SIGTERM: from `docker stop`, systemd, or `kill`.

## Cause
The GUI installs no SIGTERM handler. Python's default action ends the process immediately, cutting off in-flight downloads and database writes.

## Change
New `ofscraper/gui/utils/shutdown.py`, installed from `launch_gui` once the main window exists. On SIGTERM it:
1. **Cancels any running scrape** through the same `GUIWorkflow._on_cancel_scrape` path as the Cancel button: a cooperative stop, then the existing force-stop after its grace period. It also sets `_daemon_stop`, so a daemon loop waiting between runs ends too.
2. **Waits for the scraper thread** to finish, up to 20s.
3. **Closes every window, like a user closing the app.**
   - I first quit the event loop directly. With the main window still open, that segfaulted in Qt's teardown at exit (exit 139; faulthandler showed a native crash with no Python frame).
   - Closing the windows instead avoided it in 3/3 runs, the same as Alt+F4 does.
   - `app.quit()` remains as a fallback after 2s, in case a window refuses to close.

A second SIGTERM closes immediately. Signal handlers only run when Python executes bytecode, so a 250ms no-op `QTimer` keeps the handler responsive while Qt's event loop runs in C++.

With the current Docker entrypoint, the signal never reaches the GUI. The companion PR "pass docker stop on to the GUI" fixes that, and the two merge cleanly together.

## Tested
- **Unit:** `test/unit/test_gui_shutdown.py` was run on Linux inside the Docker image with real PyQt6 (3 passed). It covers:
  - a real SIGTERM cancelling a running scraper thread, then quitting;
  - quitting when no scrape is running;
  - quitting after the wait when the scraper doesn't stop.

  It's skipped on Windows, which can't deliver SIGTERM in-process.
- **Docker, together with the entrypoint PR:**
  - **Idle:** stopped in 0.5s with GUI exit code 0, 3/3 runs.
  - **During an images scrape:** stopped in 1.6s. The logs show `Stop requested — cancelling the current scrape before exit`, each download consumer stopping on the GUI cancel, then `Scraper stopped — quitting`.
  - **After the scrape stop:** no `.part` files were left. The database passed `integrity_check`, and every file it records as downloaded exists with the recorded size.
  - **The same scrape on `main`:** SIGKILLed after 30s, leaving 14 partial downloads.

`patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/gui/app.py`
- `OF-Scraper-3.14.7/ofscraper/gui/utils/shutdown.py`
- `OF-Scraper-3.14.7/test/unit/test_gui_shutdown.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/app.py b/OF-Scraper-3.14.7/ofscraper/gui/app.py
index aeb12d0..d31b588 100644
--- a/OF-Scraper-3.14.7/ofscraper/gui/app.py
+++ b/OF-Scraper-3.14.7/ofscraper/gui/app.py
@@ -448,6 +448,14 @@ def launch_gui(manager=None):
     window = MainWindow(manager=manager)
     window.show()
 
+    # docker stop / SIGTERM: cancel the scrape and quit instead of dying mid-write.
+    try:
+        from ofscraper.gui.utils.shutdown import install_sigterm_handler
+
+        install_sigterm_handler(app, window.workflow)
+    except Exception as e:
+        log.warning(f"Could not install SIGTERM handler: {e}")
+
     # Set up a persistent system tray icon for notifications.
     # Must be created on the main thread and kept alive for the app lifetime.
     try:
diff --git a/OF-Scraper-3.14.7/ofscraper/gui/utils/shutdown.py b/OF-Scraper-3.14.7/ofscraper/gui/utils/shutdown.py
new file mode 100644
index 0000000..0dc4741
--- /dev/null
+++ b/OF-Scraper-3.14.7/ofscraper/gui/utils/shutdown.py
@@ -0,0 +1,102 @@
+"""Quit the GUI cleanly when the process is asked to stop (SIGTERM).
+
+``docker stop`` (and service managers) send SIGTERM. Python's default action
+ends the process at once, which cuts off in-flight downloads and database
+writes. This hooks SIGTERM into the same cooperative cancel the Cancel button
+uses, waits for the scraper thread to finish, then quits the Qt event loop.
+"""
+from __future__ import annotations
+
+import logging
+import signal
+import time
+
+from PyQt6.QtCore import QTimer
+
+log = logging.getLogger("shared")
+
+# How long to wait for the scraper thread after SIGTERM before quitting anyway.
+# The cancel itself force-stops a stuck scraper after _CANCEL_FORCE_GRACE_SECONDS.
+SHUTDOWN_WAIT_SECONDS = 20.0
+_POLL_MS = 200
+
+
+def _close_app(app) -> None:
+    """Close every window the way a user would, which ends the event loop.
+
+    Quitting the loop with the main window still open crashed (SIGSEGV) in
+    Qt's teardown at interpreter exit; closing the windows first doesn't.
+    """
+    close_all = getattr(app, "closeAllWindows", None)
+    if close_all is None:  # QCoreApplication (no widgets)
+        app.quit()
+        return
+    close_all()
+    # In case a window refuses to close.
+    QTimer.singleShot(2000, app.quit)
+
+
+def _scraper_alive(workflow) -> bool:
+    thread = getattr(workflow, "_scraper_thread", None)
+    return bool(thread is not None and thread.is_alive())
+
+
+def request_shutdown(app, workflow, wait_seconds: float = SHUTDOWN_WAIT_SECONDS) -> None:
+    """Cancel any running scrape, then quit ``app`` once the scraper has stopped.
+
+    Runs on the Qt main thread (called via a zero-delay timer from the signal
+    handler). A second call while a shutdown is pending quits immediately.
+    """
+    if getattr(app, "_ofs_shutdown_requested", False):
+        log.warning("[GUI] Second stop request — quitting now")
+        _close_app(app)
+        return
+    app._ofs_shutdown_requested = True  # type: ignore[attr-defined]
+
+    if _scraper_alive(workflow):
+        log.warning("[GUI] Stop requested — cancelling the current scrape before exit")
+        try:
+            workflow._on_cancel_scrape()
+        except Exception as e:
+            log.warning(f"[GUI] Could not cancel the scrape cleanly: {e}")
+    else:
+        log.warning("[GUI] Stop requested — exiting")
+    # Also ends a daemon loop that is waiting between runs.
+    try:
+        workflow._daemon_stop.set()
+    except Exception:
+        pass
+
+    deadline = time.monotonic() + wait_seconds
+
+    def _quit_when_idle():
+        if _scraper_alive(workflow) and time.monotonic() < deadline:
+            QTimer.singleShot(_POLL_MS, _quit_when_idle)
+            return
+        if _scraper_alive(workflow):
+            log.warning("[GUI] Scraper still running after stop request — quitting anyway")
+        else:
+            log.info("[GUI] Scraper stopped — quitting")
+        _close_app(app)
+
+    _quit_when_idle()
+
+
+def install_sigterm_handler(app, workflow) -> None:
+    """Route SIGTERM to :func:`request_shutdown` on the Qt main thread."""
+    if not hasattr(signal, "SIGTERM"):
+        return
+
+    def _on_sigterm(signum, frame):
+        # Signal handlers run between Python bytecodes on the main thread;
+        # hand off to the event loop rather than touching Qt objects here.
+        QTimer.singleShot(0, lambda: request_shutdown(app, workflow))
+
+    signal.signal(signal.SIGTERM, _on_sigterm)
+
+    # While Qt's event loop runs in C++, Python only runs signal handlers when
+    # it next executes bytecode. A short no-op timer keeps that latency low.
+    wakeup = QTimer(app)
+    wakeup.timeout.connect(lambda: None)
+    wakeup.start(250)
+    app._ofs_signal_wakeup = wakeup  # type: ignore[attr-defined]
diff --git a/OF-Scraper-3.14.7/test/unit/test_gui_shutdown.py b/OF-Scraper-3.14.7/test/unit/test_gui_shutdown.py
new file mode 100644
index 0000000..8901e93
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_gui_shutdown.py
@@ -0,0 +1,93 @@
+"""SIGTERM (docker stop) cancels the scrape and quits the GUI event loop."""
+from __future__ import annotations
+
+import os
+import signal
+import sys
+import threading
+import time
+
+import pytest
+
+pytestmark = [
+    pytest.mark.unit,
+    pytest.mark.skipif(
+        sys.platform == "win32", reason="SIGTERM can't be delivered in-process on Windows"
+    ),
+]
+
+QtCore = pytest.importorskip("PyQt6.QtCore")
+
+from ofscraper.gui.utils import shutdown  # noqa: E402
+
+
+class _Workflow:
+    """Stand-in for GUIWorkflow: the scraper thread runs until cancelled."""
+
+    def __init__(self, stop_on_cancel=True):
+        self.cancel_calls = 0
+        self._cancelled = threading.Event()
+        self._daemon_stop = threading.Event()
+        self._scraper_thread = threading.Thread(
+            target=self._cancelled.wait if stop_on_cancel else lambda: time.sleep(30),
+            daemon=True,
+        )
+        self._scraper_thread.start()
+
+    def _on_cancel_scrape(self):
+        self.cancel_calls += 1
+        self._cancelled.set()
+
+
+@pytest.fixture
+def app(monkeypatch):
+    previous = signal.getsignal(signal.SIGTERM)
+    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
+    for attr in ("_ofs_shutdown_requested",):
+        if hasattr(app, attr):
+            delattr(app, attr)
+    yield app
+    signal.signal(signal.SIGTERM, previous)
+    if hasattr(app, "_ofs_signal_wakeup"):
+        app._ofs_signal_wakeup.stop()
+
+
+def _run(app, seconds=10.0):
+    # safety net so a broken handler can't hang the test run
+    QtCore.QTimer.singleShot(int(seconds * 1000), app.quit)
+    start = time.monotonic()
+    app.exec()
+    return time.monotonic() - start
+
+
+def test_sigterm_cancels_scrape_then_quits(app):
+    workflow = _Workflow()
+    shutdown.install_sigterm_handler(app, workflow)
+    QtCore.QTimer.singleShot(200, lambda: os.kill(os.getpid(), signal.SIGTERM))
+    elapsed = _run(app)
+    assert workflow.cancel_calls == 1
+    assert workflow._daemon_stop.is_set()
+    assert not workflow._scraper_thread.is_alive()
+    assert elapsed < 5
+
+
+def test_quits_without_a_running_scrape(app):
+    workflow = _Workflow()
+    workflow._on_cancel_scrape()  # thread already finished
+    workflow._scraper_thread.join(2)
+    workflow.cancel_calls = 0
+    shutdown.install_sigterm_handler(app, workflow)
+    QtCore.QTimer.singleShot(200, lambda: os.kill(os.getpid(), signal.SIGTERM))
+    assert _run(app) < 5
+    assert workflow.cancel_calls == 0
+
+
+def test_stuck_scraper_quits_after_the_wait(app, monkeypatch):
+    monkeypatch.setattr(shutdown, "SHUTDOWN_WAIT_SECONDS", 1.0)
+    workflow = _Workflow(stop_on_cancel=False)
+    QtCore.QTimer.singleShot(
+        200, lambda: shutdown.request_shutdown(app, workflow, wait_seconds=1.0)
+    )
+    elapsed = _run(app)
+    assert workflow.cancel_calls == 1
+    assert 1.0 <= elapsed < 5
```
