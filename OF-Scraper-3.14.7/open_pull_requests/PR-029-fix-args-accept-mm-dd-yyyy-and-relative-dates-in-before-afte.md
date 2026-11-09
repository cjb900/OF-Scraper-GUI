# PR #29: fix(args): accept MM/DD/YYYY and relative dates in --before/--after

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/29
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/dates-before-after` → `main`
- **Created:** 2026-11-06T12:18:50Z  ·  **Updated:** 2026-11-07T00:03:11Z
- **Draft:** False
- **Changes:** 2 files, +32 / -4

## Description

**What was broken:** `--before`/`--after` crashed on any non-ISO date (`re.error: bad escape \m`). The help says MM/DD/YYYY, but that format wasn't parsed, and the relative-date fallback had two bad patterns.

**What was fixed:** MM/DD/YYYY and M/D/YYYY are tried first, and the two patterns are corrected. ISO dates are unchanged.

Tested: `test_arrow_type.py` (8 tests).

## Files changed

- `OF-Scraper-3.14.7/ofscraper/utils/args/types/arrow.py`
- `OF-Scraper-3.14.7/test/unit/test_arrow_type.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/args/types/arrow.py b/OF-Scraper-3.14.7/ofscraper/utils/args/types/arrow.py
index 3796435..3e66d1f 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/args/types/arrow.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/args/types/arrow.py
@@ -16,18 +16,19 @@ def convert(self, value, param, ctx):
             t = arrow.get(str(out))
         except arrow.parser.ParserError:
             try:
+                # --before/--after document MM/DD/YYYY, which arrow.get() doesn't parse
+                t = arrow.get(str(out), ["MM/DD/YYYY", "M/D/YYYY"])
+            except arrow.parser.ParserError:
                 x = out
                 x = re.sub("\\byear\\b", "years", x)
                 x = re.sub("\\bday\\b", "days", x)
                 x = re.sub("\\bmonth\\b", "months", x)
                 x = re.sub("\\bweek\\b", "weeks", x)
-                x = re.sub("\\minute\\b", "minutes", x)
-                x = re.sub("\\second\\b", "seconds", x)
+                x = re.sub("\\bminute\\b", "minutes", x)
+                x = re.sub("\\bsecond\\b", "seconds", x)
 
                 arw = arrow.now()
                 t = arw.dehumanize(x)
-            except ValueError as E:
-                raise E
         return t
 
     @property
diff --git a/OF-Scraper-3.14.7/test/unit/test_arrow_type.py b/OF-Scraper-3.14.7/test/unit/test_arrow_type.py
new file mode 100644
index 0000000..ff58b59
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_arrow_type.py
@@ -0,0 +1,27 @@
+import arrow
+import pytest
+
+from ofscraper.utils.args.types.arrow import ArrowType
+
+
+@pytest.mark.parametrize("value", ["2021-05-01", "05/01/2021", "5/1/2021"])
+def test_absolute_dates_parse_including_the_documented_format(value):
+    # --before/--after document MM/DD/YYYY
+    assert ArrowType().convert(value, None, None).date() == arrow.get("2021-05-01").date()
+
+
+@pytest.mark.parametrize(
+    "value, shift",
+    [
+        ("1 minute ago", {"minutes": -1}),
+        ("2 minutes ago", {"minutes": -2}),
+        ("1 second ago", {"seconds": -1}),
+        ("3 weeks ago", {"weeks": -3}),
+        ("1 day ago", {"days": -1}),
+    ],
+)
+def test_relative_dates_parse(value, shift):
+    expected = arrow.now().shift(**shift)
+    result = ArrowType().convert(value, None, None)
+    # generous tolerance: the two clocks are read a moment apart
+    assert abs((result - expected).total_seconds()) < 30
```
