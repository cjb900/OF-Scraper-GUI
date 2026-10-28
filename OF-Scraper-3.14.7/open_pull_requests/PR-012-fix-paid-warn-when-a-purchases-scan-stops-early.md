# PR #12: fix(paid): warn when a Purchases scan stops early

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/12
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/paid-scan-warnings` → `main`
- **Created:** 2026-10-23T02:46:37Z  ·  **Updated:** 2026-10-23T03:19:44Z
- **Draft:** False
- **Changes:** 2 files, +111 / -7

## Description

**Upstream issue (related):** datawhores/OF-Scraper#600. Likely the same bug, not confirmed against the reporter's case.

An HTTP error from the purchased endpoint ended the scan with only a
debug line, and an exception with an info line, so a run could finish
with no purchases and nothing visible to say why. Log these, and an
unexpected response format, as warnings that name the model, the
offset and the reason. Scan behaviour is unchanged.

## Tested
- **Unit:** `test_paid_scan_warnings.py`: 8 passed with the change; against the code before it: 6 failed, 2 passed.
- **Full `test/unit`** on this branch: 50 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/data/api/paid.py`
- `OF-Scraper-3.14.7/test/unit/test_paid_scan_warnings.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/data/api/paid.py b/OF-Scraper-3.14.7/ofscraper/data/api/paid.py
index f3f49e9..c23aa15 100644
--- a/OF-Scraper-3.14.7/ofscraper/data/api/paid.py
+++ b/OF-Scraper-3.14.7/ofscraper/data/api/paid.py
@@ -108,13 +108,19 @@ async def scrape_paid(c, username, offset=0):
 
             async with c.requests_async(url) as r:
                 if not (200 <= r.status < 300):
-                    log.debug(f"Paid API Error at offset {current_offset}: {r.status}")
+                    # stopping here can leave a model's purchases empty or
+                    # incomplete, so say so outside debug logs
+                    log.warning(
+                        f"Purchased scan for {username} stopped at offset {current_offset}: "
+                        f"HTTP {r.status}. Purchases may be incomplete."
+                    )
                     break
 
                 data = await r.json_()
                 if not isinstance(data, dict):
-                    log.debug(
-                        f"API returned unexpected format at offset {current_offset}"
+                    log.warning(
+                        f"Purchased scan for {username} stopped at offset {current_offset}: "
+                        f"unexpected response format. Purchases may be incomplete."
                     )
                     break
 
@@ -141,7 +147,10 @@ async def scrape_paid(c, username, offset=0):
                 current_offset = new_offset
 
         except Exception as E:
-            log.info(f"Failed scrape paid offset {current_offset}")
+            log.warning(
+                f"Purchased scan for {username} failed at offset {current_offset}: "
+                f"{E!r}. Purchases may be incomplete."
+            )
             log.traceback_(E)
             log.traceback_(traceback.format_exc())
             break
@@ -240,13 +249,18 @@ async def scrape_all_paid(c, offset=0, required=None):
             )
             async with c.requests_async(url) as r:
                 if not (200 <= r.status < 300):
-                    log.debug(
-                        f"Global Paid API Error at offset {current_offset}: {r.status}"
+                    log.warning(
+                        f"Purchased scan (all models) stopped at offset {current_offset}: "
+                        f"HTTP {r.status}. Purchases may be incomplete."
                     )
                     break
 
                 data = await r.json_()
                 if not isinstance(data, dict):
+                    log.warning(
+                        f"Purchased scan (all models) stopped at offset {current_offset}: "
+                        f"unexpected response format. Purchases may be incomplete."
+                    )
                     break
 
                 trace_progress_log(f"{API} all users requests", data)
@@ -276,7 +290,10 @@ async def scrape_all_paid(c, offset=0, required=None):
                 current_offset = new_offset
 
         except Exception as E:
-            log.info(f"Scrape all paid failed at offset {current_offset}")
+            log.warning(
+                f"Purchased scan (all models) failed at offset {current_offset}: "
+                f"{E!r}. Purchases may be incomplete."
+            )
             log.traceback_(E)
             log.traceback_(traceback.format_exc())
             break
diff --git a/OF-Scraper-3.14.7/test/unit/test_paid_scan_warnings.py b/OF-Scraper-3.14.7/test/unit/test_paid_scan_warnings.py
new file mode 100644
index 0000000..4f4db70
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_paid_scan_warnings.py
@@ -0,0 +1,87 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import asyncio
+import logging
+from contextlib import asynccontextmanager
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.data.api.paid as paid
+
+
+class _Response:
+    def __init__(self, status, data):
+        self.status = status
+        self._data = data
+
+    async def json_(self):
+        return self._data
+
+
+class _Client:
+    def __init__(self, status=200, data=None, exc=None):
+        self.status, self.data, self.exc = status, data, exc
+
+    @asynccontextmanager
+    async def requests_async(self, url):
+        if self.exc:
+            raise self.exc
+        yield _Response(self.status, self.data)
+
+
+@pytest.fixture
+def warnings_seen(monkeypatch):
+    monkeypatch.setattr(paid.progress_utils.api, "add_job_task", lambda *a, **k: None, raising=False)
+    monkeypatch.setattr(paid.log, "traceback_", lambda *a, **k: None, raising=False)
+    seen = []
+
+    class Capture(logging.Handler):
+        def emit(self, record):
+            if record.levelno == logging.WARNING:
+                seen.append(record.getMessage())
+
+    handler = Capture()
+    paid.log.addHandler(handler)
+    yield seen
+    paid.log.removeHandler(handler)
+
+
+def _scans(client):
+    async def per_model():
+        return [b async for b in paid.scrape_paid(client, "model")]
+
+    async def all_models():
+        return [b async for b in paid.scrape_all_paid(client)]
+
+    return {"per-model": per_model, "all-models": all_models}
+
+
+@pytest.mark.parametrize("scan", ["per-model", "all-models"])
+@pytest.mark.parametrize(
+    "client,reason",
+    [
+        (_Client(status=403), "HTTP 403"),
+        (_Client(data=["not", "a", "dict"]), "unexpected response format"),
+        (_Client(exc=OSError("connection reset")), "connection reset"),
+    ],
+    ids=["http-error", "bad-format", "exception"],
+)
+def test_early_stop_warns(warnings_seen, scan, client, reason):
+    assert asyncio.run(_scans(client)[scan]()) == []
+    assert len(warnings_seen) == 1
+    assert reason in warnings_seen[0] and "Purchases may be incomplete" in warnings_seen[0]
+
+
+@pytest.mark.parametrize("scan", ["per-model", "all-models"])
+def test_normal_page_is_yielded_without_warning(warnings_seen, scan):
+    client = _Client(data={"list": [{"id": 1}], "hasMore": False})
+    assert asyncio.run(_scans(client)[scan]()) == [[{"id": 1}]]
+    assert warnings_seen == []
```
