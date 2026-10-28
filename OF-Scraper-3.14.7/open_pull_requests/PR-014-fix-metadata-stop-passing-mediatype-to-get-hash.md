# PR #14: fix(metadata): stop passing mediatype to get_hash

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/14
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/metadata-hash-arg` → `main`
- **Created:** 2026-10-23T02:46:40Z  ·  **Updated:** 2026-10-23T02:46:40Z
- **Draft:** False
- **Changes:** 2 files, +61 / -4

## Description

With hashing enabled, _metadata_hash_helper called
hash.get_hash(path, mediatype=...) when the planned file existed.
get_hash takes only the file, so this raised TypeError; metadata()
caught it and reported the media as skipped without updating its
database row.

## Tested
- **Unit:** `test_metadata_hash.py`: 3 passed with the change; against the code before it: 1 failed, 2 passed.
- **Full `test/unit`** on this branch: 45 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py`
- `OF-Scraper-3.14.7/test/unit/test_metadata_hash.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py b/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
index 196e3da..dd5d171 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
@@ -127,10 +127,7 @@ def _metadata_hash_helper(self, placeholderObj, prevData, ele):
         if not settings.get_settings().hash:
             return prevData.get("hash")
         elif pathlib.Path(placeholderObj.trunicated_filepath).is_file():
-            return hash.get_hash(
-                pathlib.Path(placeholderObj.trunicated_filepath),
-                mediatype=ele.mediatype,
-            )
+            return hash.get_hash(pathlib.Path(placeholderObj.trunicated_filepath))
         elif pathlib.Path(
             prevData.get("directory") or "", prevData.get("filename") or ""
         ).is_file():
diff --git a/OF-Scraper-3.14.7/test/unit/test_metadata_hash.py b/OF-Scraper-3.14.7/test/unit/test_metadata_hash.py
new file mode 100644
index 0000000..be1e302
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_metadata_hash.py
@@ -0,0 +1,60 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+from types import SimpleNamespace
+
+import pytest
+
+pytestmark = pytest.mark.unit
+import xxhash
+
+import ofscraper.commands.metadata.manager as metadata_manager
+import ofscraper.utils.hash as hash_utils
+import ofscraper.utils.settings as settings
+
+
+@pytest.fixture
+def hashing(monkeypatch):
+    monkeypatch.setattr(hash_utils, "fileHashes", {})
+
+    def enable(value):
+        monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(hash=value))
+
+    return enable
+
+
+def _helper(planned, prevData):
+    return metadata_manager.MetaDataManager()._metadata_hash_helper(
+        SimpleNamespace(trunicated_filepath=planned),
+        prevData,
+        SimpleNamespace(mediatype="videos"),
+    )
+
+
+def test_hashes_the_existing_planned_file(tmp_path, hashing):
+    hashing(True)
+    planned = tmp_path / "caption.mp4"
+    planned.write_bytes(b"media 1")
+
+    assert _helper(planned, {}) == xxhash.xxh128(b"media 1").hexdigest()
+
+
+def test_hashes_the_previously_recorded_file(tmp_path, hashing):
+    hashing(True)
+    (tmp_path / "old.mp4").write_bytes(b"media 2")
+    prevData = {"directory": str(tmp_path), "filename": "old.mp4"}
+
+    assert _helper(tmp_path / "missing.mp4", prevData) == xxhash.xxh128(b"media 2").hexdigest()
+
+
+def test_keeps_the_recorded_hash_when_hashing_is_off(tmp_path, hashing):
+    hashing(False)
+    planned = tmp_path / "caption.mp4"
+    planned.write_bytes(b"media 1")
+
+    assert _helper(planned, {"hash": "recorded"}) == "recorded"
```
