# PR #30: fix(main): exit with status 1 when a run fails

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/30
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/run-exit-status` → `main`
- **Created:** 2026-11-06T12:18:53Z  ·  **Updated:** 2026-11-07T00:03:13Z
- **Draft:** False
- **Changes:** 2 files, +34 / -1

## Description

**What was broken:** A run that failed with an unexpected error exited with status 0, and the console showed only "Finished Script".

**What was fixed:** The error is logged at error level, and the run exits with status 1. Successful runs and Ctrl+C are unchanged.

Tested: `test_run_exit_status.py`.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/main/open/run.py`
- `OF-Scraper-3.14.7/test/unit/test_run_exit_status.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/main/open/run.py b/OF-Scraper-3.14.7/ofscraper/main/open/run.py
index 843ff4e..6f2415d 100644
--- a/OF-Scraper-3.14.7/ofscraper/main/open/run.py
+++ b/OF-Scraper-3.14.7/ofscraper/main/open/run.py
@@ -20,7 +20,7 @@ def main():
                 exit_manager.forcedShutDown()
     except Exception as E:
         logging.getLogger("shared").debug(traceback.format_exc())
-        logging.getLogger("shared").debug(E)
+        logging.getLogger("shared").error(E)
         try:
             with exit_context.DelayedKeyboardInterrupt():
                 exit_manager.shutdown()
@@ -28,3 +28,5 @@ def main():
             with exit_context.DelayedKeyboardInterrupt():
                 exit_manager.forcedShutDown()
                 raise E
+        # The run failed; don't report success to scripts and schedulers
+        raise SystemExit(1)
diff --git a/OF-Scraper-3.14.7/test/unit/test_run_exit_status.py b/OF-Scraper-3.14.7/test/unit/test_run_exit_status.py
new file mode 100644
index 0000000..d241a0b
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_run_exit_status.py
@@ -0,0 +1,31 @@
+import logging
+
+import pytest
+
+import ofscraper.main.open.run as run
+
+
+def _fail():
+    raise RuntimeError("simulated failure")
+
+
+def test_failed_run_exits_with_status_1_and_logs_the_error(monkeypatch):
+    monkeypatch.setattr(run, "start_manager", _fail)
+    monkeypatch.setattr(run.exit_manager, "shutdown", lambda: None)
+    records = []
+    handler = logging.Handler(level=logging.ERROR)
+    handler.emit = records.append
+    logger = logging.getLogger("shared")
+    logger.addHandler(handler)
+    try:
+        with pytest.raises(SystemExit) as exit_info:
+            run.main()
+    finally:
+        logger.removeHandler(handler)
+    assert exit_info.value.code == 1
+    assert any("simulated failure" in r.getMessage() for r in records)
+
+
+def test_successful_run_returns_normally(monkeypatch):
+    monkeypatch.setattr(run, "start_manager", lambda: None)
+    run.main()
```
