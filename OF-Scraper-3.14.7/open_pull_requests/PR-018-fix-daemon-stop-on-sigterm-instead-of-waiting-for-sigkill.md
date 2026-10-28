# PR #18: fix(daemon): stop on SIGTERM instead of waiting for SIGKILL

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/18
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/daemon-sigterm` → `main`
- **Created:** 2026-10-23T02:46:47Z  ·  **Updated:** 2026-10-23T03:19:49Z
- **Draft:** False
- **Changes:** 3 files, +85 / -1

## Description

**Upstream issue:** datawhores/OF-Scraper#644

Two problems kept 'docker stop' from stopping a daemon-mode container:

- The entrypoint execs ofscraper, so it runs as PID 1. Python installs
  no SIGTERM handler and the kernel ignores default-handled signals
  sent to PID 1, so SIGTERM did nothing. daemon_process now installs a
  handler that raises KeyboardInterrupt, taking the existing Ctrl+C
  shutdown path.
- The scheduler thread was non-daemon and blocks forever in
  jobqueue.join(), so even after an interrupt the interpreter waited on
  it at exit. It only queues jobs (the main thread runs them), so it is
  now a daemon thread.

Adds POSIX-only tests (skipped on Windows) for the handler and for a
main thread blocked on the job queue exiting on SIGTERM.

## Tested
- **Unit (Linux, in Docker):** `test_signals.py`: 2 passed with the change, 2 failed without it. The signal tests are skipped on Windows, where SIGTERM can't be delivered in-process.
- **Full `test/unit`** on this branch: 42 passed, 3 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py`
- `OF-Scraper-3.14.7/ofscraper/utils/context/exit.py`
- `OF-Scraper-3.14.7/test/unit/test_signals.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
index 2a9f58b..1e50d29 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
@@ -240,6 +240,7 @@ def main():
 
 
 def daemon_process():
+    exit.sigterm_as_keyboard_interrupt()
     checkers.check_auth()
     worker_thread = None
     scrapingManager = scraperManager()
@@ -251,8 +252,11 @@ def daemon_process():
     manager.Manager.current_model_manager.sync_models()
     actions.select_areas()
     try:
+        # The scheduler only queues jobs; the main thread runs them. As a
+        # non-daemon thread it sat in jobqueue.join() forever and kept the
+        # process alive after Ctrl+C/SIGTERM.
         worker_thread = threading.Thread(
-            target=set_schedule, args=[scrapingManager.runner], daemon=False
+            target=set_schedule, args=[scrapingManager.runner], daemon=True
         )
         worker_thread.start()
         while True:
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/context/exit.py b/OF-Scraper-3.14.7/ofscraper/utils/context/exit.py
index 85c739f..27bbf83 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/context/exit.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/context/exit.py
@@ -5,6 +5,7 @@
 
 import os
 import signal
+import threading
 
 __all__ = [
     "SIGNAL_TRANSLATION_MAP",
@@ -79,6 +80,22 @@ def _handler(self, sig, frame):
         )
 
 
+def _raise_keyboard_interrupt(signum, frame):
+    raise KeyboardInterrupt
+
+
+def sigterm_as_keyboard_interrupt():
+    """
+    Make SIGTERM take the same shutdown path as Ctrl+C.
+
+    Python installs no SIGTERM handler, and the kernel ignores default-handled
+    signals sent to PID 1, so in a container (where ofscraper is PID 1 via the
+    entrypoint's exec) `docker stop` was ignored until SIGKILL.
+    """
+    if threading.current_thread() is threading.main_thread():
+        signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
+
+
 def exit_wrapper(func):
     def inner(*args, **kwargs):
         try:
diff --git a/OF-Scraper-3.14.7/test/unit/test_signals.py b/OF-Scraper-3.14.7/test/unit/test_signals.py
new file mode 100644
index 0000000..ca88dd5
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_signals.py
@@ -0,0 +1,63 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import os
+import signal
+import subprocess
+import sys
+import textwrap
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.utils.context.exit as exit_ctx
+
+posix_only = pytest.mark.skipif(
+    sys.platform == "win32", reason="SIGTERM cannot be delivered in-process on Windows"
+)
+
+
+@posix_only
+def test_sigterm_raises_keyboard_interrupt():
+    old = signal.getsignal(signal.SIGTERM)
+    try:
+        exit_ctx.sigterm_as_keyboard_interrupt()
+        with pytest.raises(KeyboardInterrupt):
+            os.kill(os.getpid(), signal.SIGTERM)
+            signal.pause()  # the handler raises before this returns
+    finally:
+        signal.signal(signal.SIGTERM, old)
+
+
+@posix_only
+def test_sigterm_interrupts_blocked_main_thread_and_exits():
+    # Mirrors daemon_process: main thread blocked on the job queue, scheduler
+    # thread blocked in jobqueue.join(). SIGTERM must unblock and exit promptly.
+    script = textwrap.dedent(
+        """
+        import os, queue, signal, threading
+        import ofscraper.utils.context.exit as exit_ctx
+
+        exit_ctx.sigterm_as_keyboard_interrupt()
+        jobs = queue.Queue()
+        jobs.put(lambda: None)
+        threading.Thread(target=jobs.join, daemon=True).start()
+        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
+        try:
+            jobs.get()
+            jobs.get()  # blocks until SIGTERM
+        except KeyboardInterrupt:
+            print("interrupted")
+        """
+    )
+    result = subprocess.run(
+        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
+    )
+    assert result.returncode == 0, result.stderr
+    assert result.stdout.strip() == "interrupted"
```
