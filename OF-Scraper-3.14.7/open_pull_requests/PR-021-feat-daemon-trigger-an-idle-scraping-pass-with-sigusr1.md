# PR #21: feat(daemon): trigger an idle scraping pass with SIGUSR1

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/21
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:feat/daemon-sigusr1` → `main`
- **Created:** 2026-10-23T02:46:52Z  ·  **Updated:** 2026-10-23T03:19:54Z
- **Draft:** False
- **Changes:** 7 files, +494 / -10

## Description

**Upstream issue:** datawhores/OF-Scraper#645

**Depends on #20; merge that first.** Until it's merged, this PR's diff also shows its commit.



## Tested
- **Unit (Linux, in Docker):** `test_daemon_wakeup.py`: 13 passed (with the other daemon tests) with the change, the new test can't import without it. The signal tests are skipped on Windows, where SIGTERM can't be delivered in-process.
- **Full `test/unit`** on this branch: 50 passed, 6 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/utils/schedule.py`
- `OF-Scraper-3.14.7/ofscraper/utils/context/exit.py`
- `OF-Scraper-3.14.7/test/unit/daemon_signal_probe.py`
- `OF-Scraper-3.14.7/test/unit/test_daemon_shutdown.py`
- `OF-Scraper-3.14.7/test/unit/test_daemon_wakeup.py`
- `OF-Scraper-3.14.7/test/unit/test_signals.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
index 2a9f58b..d204d2c 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/scraper.py
@@ -23,7 +23,7 @@
 import ofscraper.utils.actions as actions
 import ofscraper.utils.checkers as checkers
 import ofscraper.managers.manager as manager
-from ofscraper.commands.scraper.utils.schedule import set_schedule
+from ofscraper.commands.scraper.utils.schedule import DaemonWakeup, set_schedule
 import ofscraper.utils.config.data as data
 import ofscraper.utils.menu as menu
 from ofscraper.commands.scraper.utils.jobqueue import jobqueue
@@ -240,6 +240,7 @@ def main():
 
 
 def daemon_process():
+    exit.sigterm_as_keyboard_interrupt()
     checkers.check_auth()
     worker_thread = None
     scrapingManager = scraperManager()
@@ -250,14 +251,21 @@ def daemon_process():
     log.info("[bold]Daemon mode on[/bold]")
     manager.Manager.current_model_manager.sync_models()
     actions.select_areas()
+    wakeup = DaemonWakeup()
+    wakeup.install()
     try:
+        # The scheduler only queues jobs; the main thread runs them. As a
+        # non-daemon thread it sat in jobqueue.join() forever and kept the
+        # process alive after Ctrl+C/SIGTERM.
         worker_thread = threading.Thread(
-            target=set_schedule, args=[scrapingManager.runner], daemon=False
+            target=set_schedule, args=[scrapingManager.runner],
+            kwargs={"wakeup": wakeup}, daemon=True
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
@@ -265,6 +273,7 @@ def daemon_process():
             finally:
                 jobqueue.task_done()
     except KeyboardInterrupt as E:
+        wakeup.stopped = True
         try:
             with exit.DelayedKeyboardInterrupt():
                 schedule.clear()
@@ -276,6 +285,7 @@ def daemon_process():
                 schedule.clear()
                 raise E
     except Exception as E:
+        wakeup.stopped = True
         try:
             with exit.DelayedKeyboardInterrupt():
                 schedule.clear()
@@ -286,6 +296,8 @@ def daemon_process():
             with exit.DelayedKeyboardInterrupt():
                 schedule.clear()
                 raise E
+    finally:
+        wakeup.restore()
 
 
 @exit.exit_wrapper
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/utils/schedule.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/utils/schedule.py
index c7398dd..53efc51 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/utils/schedule.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/utils/schedule.py
@@ -3,6 +3,7 @@
 import logging
 import time
 import traceback
+import signal
 
 import ofscraper.utils.args.mutators.before as before_arg
 import ofscraper.utils.logs.logs as logs
@@ -14,25 +15,68 @@
 log = logging.getLogger("shared")
 
 
-def set_schedule(*functs):
+class DaemonWakeup:
+    """The signal handler only records a request; the scheduler does the work."""
+
+    def __init__(self):
+        self.state = "busy"
+        self.stopped = False
+        self.installed = False
+        self.previous_handler = None
+
+    def request(self, signum, frame):
+        if self.state == "idle":
+            self.state = "requested"
+
+    def install(self):
+        if hasattr(signal, "SIGUSR1"):
+            self.previous_handler = signal.signal(signal.SIGUSR1, self.request)
+            self.installed = True
+
+    def restore(self):
+        self.stopped = True
+        self.state = "busy"
+        if self.installed:
+            signal.signal(signal.SIGUSR1, self.previous_handler)
+            self.installed = False
+
+
+def set_schedule(*functs, wakeup=None):
     sleep = min(max(settings.get_settings().daemon / 5, 1), 60)
-    while True:
+    # Poll a plain flag: setting an Event from a Python signal handler can
+    # re-enter a lock held by the interrupted main thread.
+    if wakeup is not None and wakeup.installed:
+        sleep = 0.1
+    while wakeup is None or not wakeup.stopped:
         try:
             jobqueue.join()
+            if wakeup is not None and wakeup.stopped:
+                return
             next = arrow.now().shift(minutes=settings.get_settings().daemon)
             log.debug(f"Next run at ~ {next.format('MM-DD hh:mm:ss A')}")
-            schedule.every().day.at(next.format("HH:mm:ss")).do(
-                schedule_helper, *functs
+            job = schedule.every().day.at(next.format("HH:mm:ss")).do(
+                schedule_helper, *functs, wakeup=wakeup
             )
-            while len(schedule.jobs) > 0:
-                schedule.run_pending()
+            if wakeup is not None:
+                wakeup.state = "idle"
+            while len(schedule.jobs) > 0 and (wakeup is None or not wakeup.stopped):
+                if wakeup is not None and wakeup.state == "requested":
+                    # Remove the scheduled run before queuing its replacement;
+                    # a signal at the deadline must not enqueue a second pass.
+                    schedule.cancel_job(job)
+                    schedule_helper(*functs, wakeup=wakeup)
+                    log.info("SIGUSR1 received while idle: starting the next daemon pass")
+                else:
+                    schedule.run_pending()
                 time.sleep(sleep)
         except Exception as E:
             log.traceback_(E)
             log.traceback_(traceback.format_exc())
 
 
-def schedule_helper(*functs):
+def schedule_helper(*functs, wakeup=None):
+    if wakeup is not None:
+        wakeup.state = "busy"
     jobqueue.put(logger.resetLogger)
     jobqueue.put(logs.printStartValues)
     jobqueue.put(manager.Manager.current_model_manager.sync_models)
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
diff --git a/OF-Scraper-3.14.7/test/unit/daemon_signal_probe.py b/OF-Scraper-3.14.7/test/unit/daemon_signal_probe.py
new file mode 100644
index 0000000..5c47c90
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/daemon_signal_probe.py
@@ -0,0 +1,73 @@
+"""Offline Linux container probe: real daemon loop, controlled scraping jobs."""
+
+import logging
+import os
+from pathlib import Path
+import threading
+import time
+from types import SimpleNamespace
+
+import ofscraper.main.open.load
+import ofscraper.commands.scraper.scraper as scraper
+import ofscraper.commands.scraper.utils.schedule as scheduler
+
+logging.basicConfig(level=logging.INFO)
+scraper.checkers.check_auth = lambda: None
+scraper.actions.select_areas = lambda: None
+scraper.manager.Manager = SimpleNamespace(
+    current_model_manager=SimpleNamespace(sync_models=lambda: None)
+)
+scraper.settings.get_settings = lambda: SimpleNamespace(daemon=60, output_level="NORMAL")
+scheduler.logger.resetLogger = lambda: None
+scheduler.logs.printStartValues = lambda: None
+scheduler.before_arg.update_before = lambda: None
+
+state = {}
+base = scheduler.DaemonWakeup
+
+
+class ObservedWakeup(base):
+    def install(self):
+        super().install()
+        state["wakeup"] = self
+
+
+scraper.DaemonWakeup = ObservedWakeup
+
+
+class Runner:
+    count = 0
+
+    def runner(self):
+        self.count += 1
+        print(f"START {self.count}", flush=True)
+        release = Path(os.environ.get("OFS_SIGNAL_PROBE_DIR", "/tmp")) / f"release-{self.count}"
+        while not release.exists():
+            time.sleep(0.02)
+        print(f"END {self.count}", flush=True)
+
+
+runner = Runner()
+scraper.scraperManager = lambda: runner
+
+
+def observe():
+    last = None
+    while True:
+        wakeup = state.get("wakeup")
+        current = (wakeup.state, runner.count) if wakeup else None
+        if current != last and current and current[0] == "idle":
+            print(f"IDLE {runner.count}", flush=True)
+        last = current
+        time.sleep(0.02)
+
+
+threading.Thread(target=observe, daemon=True).start()
+try:
+    scraper.daemon_process()
+except KeyboardInterrupt:
+    print("STOPPED", flush=True)
+finally:
+    wakeup = state.get("wakeup")
+    if wakeup is not None:
+        print(f"HANDLER_RESTORED {not wakeup.installed}", flush=True)
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
diff --git a/OF-Scraper-3.14.7/test/unit/test_daemon_wakeup.py b/OF-Scraper-3.14.7/test/unit/test_daemon_wakeup.py
new file mode 100644
index 0000000..d290bfc
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_daemon_wakeup.py
@@ -0,0 +1,170 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import datetime
+import queue
+from types import SimpleNamespace
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import schedule
+
+import ofscraper.commands.scraper.utils.schedule as daemon_schedule
+
+
+def test_request_is_only_accepted_while_idle():
+    wakeup = daemon_schedule.DaemonWakeup()
+    wakeup.request(None, None)
+    assert wakeup.state == "busy"
+    wakeup.state = "idle"
+    for _ in range(10):
+        wakeup.request(None, None)
+    assert wakeup.state == "requested"
+    wakeup.state = "busy"
+    wakeup.request(None, None)
+    assert wakeup.state == "busy"
+
+
+@pytest.mark.parametrize("trigger", ["signal", "timer", "both"])
+def test_one_pass_and_fresh_interval_after_trigger(monkeypatch, trigger):
+    scheduler = schedule.Scheduler()
+    # Match the module API used by production code.
+    scheduler.CancelJob = schedule.CancelJob
+    jobs = queue.Queue()
+    wakeup = daemon_schedule.DaemonWakeup()
+    wakeup.installed = True
+    monkeypatch.setattr(daemon_schedule, "schedule", scheduler)
+    monkeypatch.setattr(daemon_schedule, "jobqueue", jobs)
+    monkeypatch.setattr(daemon_schedule.settings, "get_settings", lambda: SimpleNamespace(daemon=60))
+    monkeypatch.setattr(daemon_schedule.manager, "Manager", SimpleNamespace(
+        current_model_manager=SimpleNamespace(sync_models=lambda: None)))
+    def fail(error):
+        raise error
+    monkeypatch.setattr(daemon_schedule.log, "traceback_", fail, raising=False)
+    steps = []
+    runs = []
+
+    def runner():
+        runs.append("pass")
+
+    def tick(delay):
+        assert delay == 0.1
+        steps.append(delay)
+        if len(steps) == 1:
+            assert wakeup.state == "idle" and jobs.empty()
+            if trigger in ("timer", "both"):
+                scheduler.jobs[0].next_run = datetime.datetime.now() - datetime.timedelta(seconds=5)
+            if trigger in ("signal", "both"):
+                for _ in range(5):
+                    wakeup.request(None, None)
+        elif len(steps) == 2:
+            assert wakeup.state == "busy"
+            assert not scheduler.jobs
+            assert jobs.qsize() == 5  # four setup jobs, then the normal runner
+            for _ in range(5):
+                wakeup.request(None, None)
+            while not jobs.empty():
+                job = jobs.get_nowait()
+                if job is runner:
+                    job()
+                jobs.task_done()
+        else:
+            assert len(steps) == 3
+            assert runs == ["pass"] and jobs.empty()
+            assert wakeup.state == "idle"
+            assert len(scheduler.jobs) == 1
+            assert scheduler.jobs[0].next_run > datetime.datetime.now() + datetime.timedelta(minutes=59)
+            wakeup.stopped = True
+
+    monkeypatch.setattr(daemon_schedule.time, "sleep", tick)
+    daemon_schedule.set_schedule(runner, wakeup=wakeup)
+    assert runs == ["pass"]
+
+
+def test_install_and_restore_previous_handler(monkeypatch):
+    previous = object()
+    handlers = []
+    monkeypatch.setattr(daemon_schedule.signal, "SIGUSR1", 12345, raising=False)
+    def install(number, handler):
+        handlers.append((number, handler))
+        return previous
+    monkeypatch.setattr(daemon_schedule.signal, "signal", install)
+    wakeup = daemon_schedule.DaemonWakeup()
+    wakeup.install()
+    wakeup.restore()
+    wakeup.restore()
+    assert handlers == [(12345, wakeup.request), (12345, previous)]
+    assert wakeup.stopped and not wakeup.installed
+
+
+def test_platform_without_sigusr1_is_unchanged(monkeypatch):
+    monkeypatch.delattr(daemon_schedule.signal, "SIGUSR1", raising=False)
+    def unexpected(*args):
+        raise AssertionError("must not register an unavailable signal")
+    monkeypatch.setattr(daemon_schedule.signal, "signal", unexpected)
+    wakeup = daemon_schedule.DaemonWakeup()
+    wakeup.install()
+    assert not wakeup.installed
+    wakeup.restore()
+
+
+@pytest.mark.skipif(not hasattr(daemon_schedule.signal, "SIGUSR1"), reason="Unix signals required")
+@pytest.mark.parametrize("stop_signal", ["SIGTERM", "SIGINT"])
+def test_real_daemon_signal_lifecycle(tmp_path, stop_signal):
+    import os
+    from pathlib import Path
+    import signal
+    import subprocess
+    import sys
+    import time
+
+    repo = Path(__file__).resolve().parents[2]
+    output = tmp_path / "probe.log"
+    env = {**os.environ, "PYTHONPATH": str(repo), "HOME": str(tmp_path),
+           "OFS_SIGNAL_PROBE_DIR": str(tmp_path)}
+    with output.open("w") as stream:
+        process = subprocess.Popen(
+            [sys.executable, "-u", str(repo / "test/unit/daemon_signal_probe.py")],
+            cwd=repo, env=env, stdout=stream, stderr=stream,
+        )
+        def wait(marker):
+            deadline = time.monotonic() + 20
+            while time.monotonic() < deadline:
+                text = output.read_text()
+                if marker in text:
+                    return
+                assert process.poll() is None, text
+                time.sleep(0.02)
+            pytest.fail(output.read_text())
+
+        try:
+            wait("START 1")
+            process.send_signal(signal.SIGUSR1)  # ignored while active
+            (tmp_path / "release-1").touch()
+            wait("IDLE 1")
+            time.sleep(0.3)
+            assert "START 2" not in output.read_text()
+            process.send_signal(signal.SIGUSR1)
+            wait("START 2")
+            for _ in range(100):
+                process.send_signal(signal.SIGUSR1)
+            (tmp_path / "release-2").touch()
+            wait("IDLE 2")
+            time.sleep(0.3)
+            assert "START 3" not in output.read_text()
+            process.send_signal(signal.SIGUSR1)
+            wait("START 3")
+            process.send_signal(getattr(signal, stop_signal))
+            assert process.wait(timeout=10) == 0, output.read_text()
+            assert "STOPPED" in output.read_text()
+            assert "HANDLER_RESTORED True" in output.read_text()
+        finally:
+            if process.poll() is None:
+                process.kill()
+            process.wait(timeout=10)
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
