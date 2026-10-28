# PR #4: fix(download): don't treat the filename as a regex when hiding it in logs

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/4
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/url-log-regex` → `main`
- **Created:** 2026-10-23T02:46:22Z  ·  **Updated:** 2026-10-23T02:46:22Z
- **Draft:** False
- **Changes:** 2 files, +34 / -1

## Description

get_url_log hid the filename with re.sub(ele.filename, ...). A file
uploaded as "Untitled design (7).png" has the filename
"Untitled design (7" once Media.filename strips trailing punctuation,
so the unbalanced "(" raised re.error and aborted the download before
it started. Use a plain string replace.

## Tested
- **Unit:** `test_url_log.py`: 2 passed with the change; against the code before it: 1 failed, 1 passed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/log.py`
- `OF-Scraper-3.14.7/test/unit/test_url_log.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/log.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/log.py
index 02a3ad9..aab604a 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/log.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/log.py
@@ -42,7 +42,8 @@ def get_url_log(ele):
     url = ele.url or ele.mpd
     url = re.sub(r"/\w{5}\w+", "/{hidden}", url)
     if ele.url:
-        url = re.sub(ele.filename, "{hidden}", url)
+        # plain replace: a filename such as "design (7)" isn't a valid pattern
+        url = url.replace(ele.filename, "{hidden}")
     return url
 
 
diff --git a/OF-Scraper-3.14.7/test/unit/test_url_log.py b/OF-Scraper-3.14.7/test/unit/test_url_log.py
new file mode 100644
index 0000000..277bb58
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_url_log.py
@@ -0,0 +1,32 @@
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
+from types import SimpleNamespace
+
+import ofscraper.commands.scraper.actions.utils.log as log_utils
+
+
+def _media(url, filename):
+    return SimpleNamespace(url=url, mpd=None, filename=filename)
+
+
+def test_filename_with_regex_characters_is_hidden():
+    # a profile header uploaded as "Untitled design (7).png": Media.filename
+    # strips the trailing ")", leaving an unbalanced "(" at position 16
+    url = "https://public.onlyfans.com/files/a/ab/abc/123/Untitled design (7).png"
+    logged = log_utils.get_url_log(_media(url, "Untitled design (7"))
+    assert "Untitled design (7" not in logged and "{hidden}" in logged
+
+
+def test_ordinary_filename_is_hidden():
+    url = "https://cdn2.onlyfans.com/files/a/ab/abc/1000x1800_cb46.jpeg"
+    logged = log_utils.get_url_log(_media(url, "1000x1800_cb46"))
+    assert "1000x1800_cb46" not in logged
```
