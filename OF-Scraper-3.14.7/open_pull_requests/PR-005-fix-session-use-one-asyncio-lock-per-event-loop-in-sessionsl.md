# PR #5: fix(session): use one asyncio.Lock per event loop in SessionSleep

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/5
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/session-sleep-lock` → `main`
- **Created:** 2026-10-23T02:46:24Z  ·  **Updated:** 2026-10-23T03:19:31Z
- **Draft:** False
- **Changes:** 2 files, +69 / -1

## Description

**Upstream issue:** datawhores/OF-Scraper#616

SessionSleep created a single asyncio.Lock in __init__, but ofscraper
runs async code in several event loops (@run starts a new loop per call,
plus worker threads). An asyncio.Lock binds to the first loop that waits
on it, so the first contended acquire in any other loop raised
'... is bound to a different event loop', e.g. while backing off after
a 429.

Keep a WeakKeyDictionary of locks keyed by the running loop, guarded by
its own threading.Lock (not self._lock, which do_sleep holds through
time.sleep). Adds a test that reproduces the error on the old code.

## Tested
- **Unit:** `test_session_sleep.py`: 2 passed with the change; against the code before it: 2 failed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py`
- `OF-Scraper-3.14.7/test/unit/test_session_sleep.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
index 4b59370..015bcec 100644
--- a/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
+++ b/OF-Scraper-3.14.7/ofscraper/managers/sessionmanager/sessionmanager.py
@@ -7,6 +7,7 @@
 import certifi
 import contextlib
 import traceback
+import weakref
 from typing import Optional, Dict, Union, AsyncGenerator, Any, Generator
 
 import arrow
@@ -73,7 +74,10 @@ def __init__(
         self._last_request_time = arrow.get(
             0
         )  # <-- NEW: Tracks when the API was last hit
-        self._alock = asyncio.Lock()
+        # One asyncio.Lock per event loop: ofscraper runs async code in several
+        # loops, and a single asyncio.Lock binds to the first loop that waits on it
+        self._alocks = weakref.WeakKeyDictionary()
+        self._alocks_guard = threading.Lock()
         self._lock = threading.Lock()
         self._init_sleep = (
             sleep if sleep is not None else of_env.getattr("SESSION_SLEEP_INIT")
@@ -118,6 +122,16 @@ def _maybe_decay_sleep(self):
                 f"[{self.error_name}] Sleep decay => Reducing sleep to [{self._sleep:.2f} seconds]"
             )
 
+    @property
+    def _alock(self) -> asyncio.Lock:
+        loop = asyncio.get_running_loop()
+        # Not self._lock: do_sleep holds that through time.sleep
+        with self._alocks_guard:
+            lock = self._alocks.get(loop)
+            if lock is None:
+                lock = self._alocks[loop] = asyncio.Lock()
+        return lock
+
     async def async_do_sleep(self):
         async with self._alock:
             self._maybe_decay_sleep()
diff --git a/OF-Scraper-3.14.7/test/unit/test_session_sleep.py b/OF-Scraper-3.14.7/test/unit/test_session_sleep.py
new file mode 100644
index 0000000..6bd8703
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_session_sleep.py
@@ -0,0 +1,54 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import asyncio
+
+from ofscraper.managers.sessionmanager.sessionmanager import SessionSleep
+
+
+def make_sleeper():
+    # A current sleep above min_sleep is backoff mode, so async_do_sleep awaits
+    # while holding the async lock and a second caller has to wait on it
+    sleeper = SessionSleep(
+        sleep=0.02,
+        min_sleep=0.01,
+        difmin=0,
+        max_sleep=0.05,
+        decay_threshold=60,
+        decay_factor=1.5,
+        increase_factor=1.5,
+        error_name="test",
+    )
+    sleeper.sleep = 0.02
+    return sleeper
+
+
+def contend(sleeper, second_method):
+    async def run():
+        await asyncio.gather(
+            sleeper.async_do_sleep(), getattr(sleeper, second_method)()
+        )
+
+    asyncio.run(run())
+
+
+def test_do_sleep_works_across_event_loops():
+    # ofscraper runs async code in several loops (@run starts a new one per
+    # call); a shared asyncio.Lock binds to the first loop that contends on it.
+    sleeper = make_sleeper()
+    contend(sleeper, "async_do_sleep")
+    contend(sleeper, "async_do_sleep")
+
+
+def test_toomany_req_works_across_event_loops():
+    sleeper = make_sleeper()
+    contend(sleeper, "async_toomany_req")
+    contend(sleeper, "async_toomany_req")
```
