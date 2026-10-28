# PR #20: fix(daemon): only mark a job done after taking it from the queue

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/20
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/daemon-idle-task-done` → `main`
- **Created:** 2026-10-23T02:46:51Z  ·  **Updated:** 2026-10-23T03:20:08Z
- **Draft:** False
- **Changes:** 4 files, +192 / -2

## Description

**Upstream issue (follow-up):** datawhores/OF-Scraper#644. Fixes a traceback when SIGTERM arrives while the daemon is idle, after the main fix in the SIGTERM PR.

**Depends on #18; merge that first.** Until it's merged, this PR's diff also shows its commit.

* fix(daemon): only mark a job done after taking it from the queue

SIGTERM or Ctrl+C while the daemon waited on an empty job queue ran the
loop's finally: task_done() with no job taken. That raised ValueError,
which replaced the KeyboardInterrupt, so shutdown exited with status 1.
Take the job before the try so only obtained jobs are marked done.

* test(daemon): accept keyword arguments in the set_schedule stub

The SIGUSR1 change passes wakeup= to set_schedule; the positional-only stub raised in
the scheduler thread once both are merged.

---------

## Tested
- **Unit (Linux, in Docker):** `test_daemon_shutdown.py`: 5 passed (with the SIGTERM tests) with the change, 2 failed without it. The signal tests are skipped on Windows, where SIGTERM can't be delivered in-process.
- **Full `test/unit`** on this branch: 44 passed, 4 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py`
- `OF-Scraper-3.14.7/ofscraper/utils/context/exit.py`
- `OF-Scraper-3.14.7/test/unit/test_daemon_shutdown.py`
- `OF-Scraper-3.14.7/test/unit/test_signals.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
index 2a9f58b..0f6f481 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
@@ -240,6 +240,7 @@ def main():
 
 
 def daemon_process():
+    exit.sigterm_as_keyboard_interrupt()
     checkers.check_auth()
     worker_thread = None
     scrapingManager = scraperManager()
@@ -251,13 +252,17 @@ def daemon_process():
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
+            # outside the try: a signal while idle here has no job to mark done
+            job_func = jobqueue.get()
             try:
-                job_func = jobqueue.get()
                 job_func()
             except Exception as E:
                 log.traceback_(E)
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
diff --git a/OF-Scraper-3.14.7/test/unit/test_daemon_shutdown.py b/OF-Scraper-3.14.7/test/unit/test_daemon_shutdown.py
new file mode 100644
index 0000000..1a8f968
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_daemon_shutdown.py
@@ -0,0 +1,105 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import queue
+import subprocess
+import sys
+import textwrap
+from types import SimpleNamespace
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.commands.scraper.scraper as scraper
+
+
+class InterruptWhenIdle(queue.Queue):
+    # a signal arriving while the main thread waits for the next job
+    def get(self, *args, **kwargs):
+        if self.empty():
+            raise KeyboardInterrupt
+        return super().get(*args, **kwargs)
+
+
+def _stub_daemon(monkeypatch, jobs, runner):
+    monkeypatch.setattr(scraper, "jobqueue", jobs)
+    monkeypatch.setattr(scraper.exit, "sigterm_as_keyboard_interrupt", lambda: None)
+    monkeypatch.setattr(scraper.checkers, "check_auth", lambda: None)
+    monkeypatch.setattr(scraper, "scraperManager", lambda: SimpleNamespace(runner=runner))
+    monkeypatch.setattr(
+        scraper.settings, "get_settings", lambda: SimpleNamespace(output_level="NORMAL")
+    )
+    monkeypatch.setattr(
+        scraper.manager,
+        "Manager",
+        SimpleNamespace(current_model_manager=SimpleNamespace(sync_models=lambda: None)),
+    )
+    monkeypatch.setattr(scraper.actions, "select_areas", lambda: None)
+    monkeypatch.setattr(scraper, "set_schedule", lambda *args, **kwargs: None)
+
+
+def test_idle_interrupt_shuts_down_without_task_done_error(monkeypatch):
+    runs = []
+    jobs = InterruptWhenIdle()
+    _stub_daemon(monkeypatch, jobs, lambda: runs.append(1))
+
+    with pytest.raises(KeyboardInterrupt):
+        scraper.daemon_process()
+    assert runs == [1]
+    assert jobs.unfinished_tasks == 0
+
+
+def test_interrupt_during_a_job_still_marks_it_done(monkeypatch):
+    def runner():
+        raise KeyboardInterrupt
+
+    jobs = queue.Queue()
+    _stub_daemon(monkeypatch, jobs, runner)
+
+    with pytest.raises(KeyboardInterrupt):
+        scraper.daemon_process()
+    assert jobs.unfinished_tasks == 0
+
+
+@pytest.mark.skipif(
+    sys.platform == "win32", reason="SIGTERM cannot be delivered in-process on Windows"
+)
+def test_sigterm_while_idle_exits_with_keyboard_interrupt():
+    # the real daemon loop and SIGTERM handler; only auth and scraping are stubbed
+    script = textwrap.dedent(
+        """
+        import os, signal, threading
+        from types import SimpleNamespace
+        import ofscraper.main.open.load  # import order, as in conftest
+        import ofscraper.commands.scraper.scraper as scraper
+
+        ran = threading.Event()
+        def runner():
+            ran.set()
+            threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM)).start()
+
+        scraper.checkers.check_auth = lambda: None
+        scraper.scraperManager = lambda: SimpleNamespace(runner=runner)
+        scraper.settings.get_settings = lambda: SimpleNamespace(output_level="NORMAL")
+        scraper.manager.Manager = SimpleNamespace(
+            current_model_manager=SimpleNamespace(sync_models=lambda: None)
+        )
+        scraper.actions.select_areas = lambda: None
+        scraper.set_schedule = lambda *args, **kwargs: None
+        try:
+            scraper.daemon_process()
+        except KeyboardInterrupt:
+            print("interrupted" if ran.is_set() else "interrupted before the first run")
+        """
+    )
+    result = subprocess.run(
+        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
+    )
+    assert result.returncode == 0, result.stderr
+    assert result.stdout.strip().splitlines()[-1] == "interrupted"
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
