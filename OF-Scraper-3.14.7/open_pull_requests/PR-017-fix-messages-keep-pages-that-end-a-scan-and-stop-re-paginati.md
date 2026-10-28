# PR #17: fix(messages): keep pages that end a scan and stop re-paginating chunk 0

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/17
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/messages-chunk-boundary` → `main`
- **Created:** 2026-10-23T02:46:45Z  ·  **Updated:** 2026-10-23T03:19:47Z
- **Draft:** False
- **Changes:** 2 files, +154 / -15

## Description

**Upstream issues (related):** datawhores/OF-Scraper#638, datawhores/OF-Scraper#600. Likely the same bug, not confirmed against the reporter's case.  
Same fix as upstream PR datawhores/OF-Scraper#654.

Two bugs in message pagination:

- When a non-final chunk had found all of its cached messages, it
  stopped before yielding the page that contained them. The next chunk
  starts below that chunk's tail, so the page was never fetched again.
  (The page that crosses the "after" date was handled already; this keeps
  that behaviour, filtered to messages at or after "after".)
- Chunk 1 started at anchor_id, which is newer than everything in chunk
  0, so it re-paginated all of chunk 0 on every cached run. Chunk 0 now
  uses the anchor only when --before is set, and every later chunk
  continues from the previous chunk's oldest message.

## Tested
- **Unit:** `test_messages_pagination.py`: 7 passed with the change; against the code before it: 3 failed, 4 passed.
- **Full `test/unit`** on this branch: 49 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/data/api/messages.py`
- `OF-Scraper-3.14.7/test/unit/test_messages_pagination.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/data/api/messages.py b/OF-Scraper-3.14.7/ofscraper/data/api/messages.py
index caa71bf..99ad6b6 100644
--- a/OF-Scraper-3.14.7/ofscraper/data/api/messages.py
+++ b/OF-Scraper-3.14.7/ofscraper/data/api/messages.py
@@ -210,12 +210,11 @@ def get_tasks(splitArrays, anchor_id, c, model_id, username, after):
         
         # --- 1. Define the Start ID ---
         if i == 0:
-            start_id = None  # Chunk 0: Teleport to the absolute newest message
-        elif i == 1:
-            start_id = anchor_id  # Chunk 1: Pick up at the cached anchor
+            # Chunk 0: start at the 'before' anchor if set, otherwise the newest message
+            start_id = anchor_id if settings.get_settings().before else None
         else:
-            # Chunk 2+: Pick up at the tail of the previous chunk
-            start_id = splitArrays[i - 1][-1].get("post_id")  
+            # Chunk 1+: Pick up at the tail of the previous chunk
+            start_id = splitArrays[i - 1][-1].get("post_id")
 
         # --- 2. Define the Start Timestamp ---
         start_timestamp = (
@@ -326,18 +325,16 @@ async def scrape_messages(
                     for g_id in ghosts_in_batch:
                         required_ids.discard(g_id)
 
-                if not is_last_chunk and len(required_ids) == 0:
+                # Boundary condition: this page reaches past the "after" date limit.
+                # Keep its in-range messages before stopping.
+                if min_ts < after:
+                    yield [x for x, ts in zip(batch, batch_timestamps) if ts >= after]
                     break
 
-                # Boundary condition: We hit our "after" date limit
-                if min_ts < after:
-                    # Yield any messages in this batch that are within the date range
-                    in_range = [
-                        x for x in batch
-                        if float(arrow.get(x.get("createdAt") or x.get("postedAt")).float_timestamp) >= after
-                    ]
-                    if in_range:
-                        yield in_range
+                # This chunk has found all of its cached messages. Keep the page
+                # that contained them; the next chunk only starts below its tail.
+                if not is_last_chunk and len(required_ids) == 0:
+                    yield batch
                     break
 
                 # Prevent stuck loop
diff --git a/OF-Scraper-3.14.7/test/unit/test_messages_pagination.py b/OF-Scraper-3.14.7/test/unit/test_messages_pagination.py
new file mode 100644
index 0000000..a903873
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_messages_pagination.py
@@ -0,0 +1,142 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import asyncio
+from types import SimpleNamespace
+from urllib.parse import parse_qs, urlsplit
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.data.api.messages as messages
+
+
+class FakeResponse:
+    def __init__(self, data):
+        self.status = 200
+        self._data = data
+
+    async def json_(self):
+        return self._data
+
+    async def __aenter__(self):
+        return self
+
+    async def __aexit__(self, *exc):
+        return False
+
+
+class FakeClient:
+    """Paginates newest-first like the chats API: ?id=X returns messages older than X."""
+
+    def __init__(self, ids, page_size=3):
+        # createdAt equals the id, so ordering by id and by time agree
+        self.messages = [{"id": i, "createdAt": i} for i in sorted(ids, reverse=True)]
+        self.page_size = page_size
+        self.cursors = []
+
+    def requests_async(self, url, **kwargs):
+        cursor = parse_qs(urlsplit(url).query).get("id", [None])[0]
+        self.cursors.append(cursor)
+        older = [
+            m for m in self.messages if cursor is None or m["id"] < int(cursor)
+        ]
+        page = older[: self.page_size]
+        has_more = len(older) > self.page_size
+        return FakeResponse({"list": page, "hasMore": has_more})
+
+
+def collect(client, **kwargs):
+    async def run():
+        out = []
+        async for batch in messages.scrape_messages(client, 1, "user", **kwargs):
+            out.extend(m["id"] for m in batch)
+        return out
+
+    return asyncio.run(run())
+
+
+def test_full_scan_returns_every_message():
+    client = FakeClient(range(1, 21))
+    assert collect(client, is_last_chunk=True, after=0) == list(range(20, 0, -1))
+
+
+def test_page_crossing_after_boundary_keeps_in_range_messages():
+    # The page [11, 10, 9] straddles after=10; 11 and 10 must not be dropped
+    client = FakeClient(range(1, 21))
+    assert collect(client, is_last_chunk=True, after=10) == list(range(20, 9, -1))
+
+
+def test_completed_chunk_keeps_the_page_that_completed_it():
+    client = FakeClient(range(1, 21))
+    ids = collect(
+        client,
+        required_posts=[{"post_id": 17, "timestamp": 17}],
+        is_last_chunk=False,
+        after=0,
+    )
+    assert ids == [20, 19, 18, 17, 16, 15]
+
+
+def test_scan_resumes_from_message_id():
+    client = FakeClient(range(1, 21))
+    ids = collect(client, message_id=12, is_last_chunk=True, after=0)
+    assert ids == list(range(11, 0, -1))
+    assert client.cursors[0] == "12"
+
+
+@pytest.fixture
+def recorded_tasks(monkeypatch):
+    calls = []
+
+    def fake_scrape_messages(c, model_id, username, **kwargs):
+        calls.append(kwargs)
+
+    monkeypatch.setattr(messages, "scrape_messages", fake_scrape_messages)
+    return calls
+
+
+def chunks():
+    # Newest-first chunks, as get_split_array produces them
+    return [
+        [{"post_id": 9, "created_at": 900}, {"post_id": 8, "created_at": 800}],
+        [{"post_id": 7, "created_at": 700}, {"post_id": 6, "created_at": 600}],
+        [{"post_id": 5, "created_at": 500}],
+    ]
+
+
+def set_before(monkeypatch, before):
+    monkeypatch.setattr(
+        messages.settings, "get_settings", lambda: SimpleNamespace(before=before)
+    )
+
+
+def test_chunks_continue_from_previous_tail(monkeypatch, recorded_tasks):
+    set_before(monkeypatch, None)
+    messages.get_tasks(chunks(), "ANCHOR", None, 1, "user", 0)
+
+    assert [t["message_id"] for t in recorded_tasks] == [None, 8, 6]
+    assert [t["is_last_chunk"] for t in recorded_tasks] == [False, False, True]
+    assert [t["start_timestamp"] for t in recorded_tasks][1:] == [800.0, 600.0]
+
+
+def test_first_chunk_starts_at_anchor_when_before_is_set(monkeypatch, recorded_tasks):
+    set_before(monkeypatch, 5000)
+    messages.get_tasks(chunks(), "ANCHOR", None, 1, "user", 0)
+
+    assert [t["message_id"] for t in recorded_tasks] == ["ANCHOR", 8, 6]
+
+
+def test_empty_cache_scans_from_anchor(monkeypatch, recorded_tasks):
+    set_before(monkeypatch, None)
+    messages.get_tasks([], "ANCHOR", None, 1, "user", 0)
+
+    assert len(recorded_tasks) == 1
+    assert recorded_tasks[0]["message_id"] == "ANCHOR"
+    assert recorded_tasks[0]["is_last_chunk"] is True
```
