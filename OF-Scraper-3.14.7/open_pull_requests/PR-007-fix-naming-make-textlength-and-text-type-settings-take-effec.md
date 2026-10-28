# PR #7: fix(naming): make textlength and text type settings take effect

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/7
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/textlength` → `main`
- **Created:** 2026-10-23T02:46:27Z  ·  **Updated:** 2026-10-23T03:19:34Z
- **Draft:** False
- **Changes:** 4 files, +103 / -6

## Description

**Upstream issue:** datawhores/OF-Scraper#634

* fix(naming): make textlength and text type settings take effect

--textlength was stored as args.textlength but settings read
args.text_length, so the flag was ignored. --text-type defaulted to
"word", which always overrode text_type_default from config, so a
textlength meant for letters was applied as a word count. Word mode also
kept separators as tokens (about half the requested words) and split on
spaces after file_cleanup had already swapped them for space_replacer.

* docs(naming): note that word mode splits on existing replacer characters

Once file_cleanup has swapped spaces for space_replacer, a replacer
character that was already in the caption counts as a word break too.
Comment it and pin the behaviour in a test.

---------

## Tested
- **Unit:** `test_textlength.py`: 10 passed with the change; against the code before it: 5 failed, 5 passed.
- **Full `test/unit`** on this branch: 52 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/classes/of/base.py`
- `OF-Scraper-3.14.7/ofscraper/utils/args/parse/arguments/file.py`
- `OF-Scraper-3.14.7/ofscraper/utils/settings.py`
- `OF-Scraper-3.14.7/test/unit/test_textlength.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/classes/of/base.py b/OF-Scraper-3.14.7/ofscraper/classes/of/base.py
index 5190dd5..9a809fd 100644
--- a/OF-Scraper-3.14.7/ofscraper/classes/of/base.py
+++ b/OF-Scraper-3.14.7/ofscraper/classes/of/base.py
@@ -24,10 +24,16 @@ def text_trunicate(self, text):
         elif settings.get_settings().text_type == "letter":
             return f"{''.join(list(text)[:length])}"
         else:
-            # split and reduce
-            wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", text)))
-            splitArray = wordarray[: length + 1]
-            text = f"{''.join(splitArray)}"
+            # text has usually been through file_cleanup already, which swaps
+            # spaces for space_replacer, so words are split on that. If the
+            # original text already contained that character (e.g. "_" in a
+            # caption with "_" as the replacer), it also counts as a word
+            # break; the original spaces can't be told apart at this point.
+            sep = settings.get_settings().space_replacer or " "
+            if sep not in text:
+                sep = " "
+            words = [x for x in text.split(sep) if x]
+            text = sep.join(words[:length])
         text = re.sub(" +$", "", text)
         return text
 
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/args/parse/arguments/file.py b/OF-Scraper-3.14.7/ofscraper/utils/args/parse/arguments/file.py
index d32feae..0dce414 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/args/parse/arguments/file.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/args/parse/arguments/file.py
@@ -12,7 +12,6 @@
     "--text-type",
     help="set length based on word or letter",
     type=click.Choice(["word", "letter"], case_sensitive=False),
-    default="word",
 )
 
 space_replacer_option = click.option(
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/settings.py b/OF-Scraper-3.14.7/ofscraper/utils/settings.py
index 654d57c..2e3f8e6 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/settings.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/settings.py
@@ -141,7 +141,11 @@ def _listhelper(out):
     # --- File & Download Settings ---
     merged.text_type = args.text_type or config_data.get_textType()
     merged.space_replacer = args.space_replacer or config_data.get_spacereplacer()
-    merged.text_length = args.text_length or config_data.get_textlength()
+    merged.text_length = (
+        args.textlength
+        if args.textlength is not None
+        else config_data.get_textlength()
+    )
     merged.size_max = args.size_max or config_data.get_filesize_max()
     merged.size_min = args.size_min or config_data.get_filesize_min()
     merged.download_sems = args.download_sem or config_data.get_download_semaphores()
diff --git a/OF-Scraper-3.14.7/test/unit/test_textlength.py b/OF-Scraper-3.14.7/test/unit/test_textlength.py
new file mode 100644
index 0000000..eda1bc2
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_textlength.py
@@ -0,0 +1,88 @@
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
+import click
+import pytest
+
+pytestmark = pytest.mark.unit
+from click.testing import CliRunner
+
+import ofscraper.utils.args.accessors.read as read_args
+import ofscraper.utils.config.data as config_data
+import ofscraper.utils.settings as settings
+from ofscraper.classes.of.base import base
+from ofscraper.utils.args.parse.arguments.file import text_type_option
+
+
+@pytest.fixture
+def fake_settings(monkeypatch):
+    def apply(**kw):
+        ns = SimpleNamespace(text_length=0, text_type="letter", space_replacer=" ")
+        ns.__dict__.update(kw)
+        monkeypatch.setattr(settings, "get_settings", lambda: ns)
+
+    return apply
+
+
+def test_letter_mode_truncates(fake_settings):
+    fake_settings(text_length=5, text_type="letter")
+    assert base().text_trunicate("abcdefghij") == "abcde"
+
+
+def test_zero_length_keeps_text(fake_settings):
+    fake_settings(text_length=0)
+    assert base().text_trunicate("a b c") == "a b c"
+
+
+@pytest.mark.parametrize("n,expected", [(1, "one"), (2, "one two"), (3, "one two three")])
+def test_word_mode_counts_words(fake_settings, n, expected):
+    fake_settings(text_length=n, text_type="word")
+    assert base().text_trunicate("one two three four") == expected
+
+
+def test_word_mode_uses_space_replacer(fake_settings):
+    fake_settings(text_length=2, text_type="word", space_replacer="_")
+    assert base().text_trunicate("one_two_three") == "one_two"
+
+
+def test_text_type_option_has_no_default():
+    # a CLI default would always override text_type_default from config
+    @click.command()
+    @text_type_option
+    def cmd(text_type):
+        click.echo(repr(text_type))
+
+    assert CliRunner().invoke(cmd, []).output.strip() == "None"
+
+
+def test_settings_reads_textlength_arg(monkeypatch):
+    args = settings.get_args(copy=True)
+    args.textlength = 7
+    args.text_type = None
+    monkeypatch.setattr(read_args, "retriveArgs", lambda: args)
+    monkeypatch.setattr(config_data, "get_textType", lambda *a, **k: "letter")
+    merged = settings.merged_settings()
+    assert merged.text_length == 7
+    assert merged.text_type == "letter"
+
+
+def test_settings_falls_back_to_config_textlength(monkeypatch):
+    args = settings.get_args(copy=True)
+    args.textlength = None
+    monkeypatch.setattr(read_args, "retriveArgs", lambda: args)
+    monkeypatch.setattr(config_data, "get_textlength", lambda *a, **k: 75)
+    assert settings.merged_settings().text_length == 75
+
+
+def test_word_mode_counts_existing_replacer_chars_as_breaks(fake_settings):
+    # documented limitation: "_" already in the caption ("snake_case title")
+    # can't be told apart from a replaced space once file_cleanup has run
+    fake_settings(text_length=2, text_type="word", space_replacer="_")
+    assert base().text_trunicate("snake_case_title_here") == "snake_case"
```
