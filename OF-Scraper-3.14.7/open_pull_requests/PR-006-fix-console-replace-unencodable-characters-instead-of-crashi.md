# PR #6: fix(console): replace unencodable characters instead of crashing

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/6
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/console-encoding` → `main`
- **Created:** 2026-10-23T02:46:26Z  ·  **Updated:** 2026-10-23T03:19:33Z
- **Draft:** False
- **Changes:** 2 files, +58 / -0

## Description

**Upstream issue (related):** datawhores/OF-Scraper#558. Likely the same bug, not confirmed against the reporter's case.

Model names and post text can contain emoji. When stdout/stderr is not
UTF-8 (cp1252 on Windows when output is redirected, some terminals, the
bundled exe), rich's Console.print raised UnicodeEncodeError ('... You
may need to add PYTHONIOENCODING=utf-8 ...') and the run stopped, e.g.
after selecting a model whose name has an emoji.

When the shared console module loads, reconfigure any non-UTF stdout or
stderr with errors='replace' so such characters print as '?'. UTF-8
streams are left untouched.

## Tested
- **Unit:** `test_console_encoding.py`: 2 passed with the change; against the code before it: 2 failed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/utils/console.py`
- `OF-Scraper-3.14.7/test/unit/test_console_encoding.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/console.py b/OF-Scraper-3.14.7/ofscraper/utils/console.py
index 6123e43..19247be 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/console.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/console.py
@@ -1,8 +1,30 @@
+import sys
+
 from rich.console import Console
 from rich.theme import Theme
 
 from ofscraper.utils.args.accessors.output import low_output
 
+
+def replace_unencodable_output(streams=None):
+    """
+    Model names and post text can contain emoji. On a stdout/stderr that is not
+    UTF-8 (e.g. cp1252 on Windows when output is redirected, or in the bundled
+    exe), printing them raised UnicodeEncodeError and aborted the run. Print a
+    replacement character instead.
+    """
+    for stream in streams or (sys.stdout, sys.stderr):
+        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
+        if encoding in {"utf8", "utf16", "utf32"}:
+            continue
+        try:
+            stream.reconfigure(errors="replace")
+        except (AttributeError, ValueError):
+            pass  # not a TextIOWrapper (e.g. replaced by a test runner)
+
+
+replace_unencodable_output()
+
 theme = Theme(
     {
         "logging.level.error": "green",
diff --git a/OF-Scraper-3.14.7/test/unit/test_console_encoding.py b/OF-Scraper-3.14.7/test/unit/test_console_encoding.py
new file mode 100644
index 0000000..5a4336c
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_console_encoding.py
@@ -0,0 +1,36 @@
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
+
+
+
+def test_unencodable_output_is_replaced_not_raised():
+    import io
+
+    from rich.console import Console
+
+    from ofscraper.utils.console import replace_unencodable_output
+
+    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
+    replace_unencodable_output([stream])
+    Console(file=stream, force_terminal=False).print("Cherry \U0001F352 model")
+    stream.flush()
+    assert stream.buffer.getvalue().decode("cp1252").strip() == "Cherry ? model"
+
+
+def test_utf8_output_is_left_alone():
+    import io
+
+    from ofscraper.utils.console import replace_unencodable_output
+
+    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
+    replace_unencodable_output([stream])
+    assert stream.errors == "strict"
```
