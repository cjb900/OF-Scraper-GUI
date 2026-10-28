# PR #10: fix(prompts): keep model selector prompts visible and stdout intact

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/10
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/model-selector-stdout` → `main`
- **Created:** 2026-10-23T02:46:33Z  ·  **Updated:** 2026-10-23T03:19:40Z
- **Draft:** False
- **Changes:** 3 files, +102 / -36

## Description

**Upstream issues:** datawhores/OF-Scraper#551, datawhores/OF-Scraper#581

Range select (Alt+B) rebuilt its list with _get_choices(), which runs
the whole filter/sort menu first, and the helper ran inside nostdout()
so that menu was invisible. The keys meant for the range prompt went
into a menu nobody could see, and the selector looked hung.

nostdout() also re-yielded from a bare except: any exception in its body
(ctrl+c in a prompt, a prompt error) became "generator didn't stop after
throw()" and left sys.stdout at devnull for the rest of the session,
dropping the user back to the main menu with no output.

- Range select/deselect numbers the list already on screen
- The filter menu (Alt+X / Ctrl+B) is no longer run under nostdout
- nostdout/lowstdout restore stdout in a finally block

## Tested
- **Unit:** `test_model_selector.py`: 4 passed with the change; against the code before it: 3 failed, 1 passed.
- **Full `test/unit`** on this branch: 46 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/prompts/utils/prompt_helpers.py`
- `OF-Scraper-3.14.7/ofscraper/utils/context/stdout.py`
- `OF-Scraper-3.14.7/test/unit/test_model_selector.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/prompts/utils/prompt_helpers.py b/OF-Scraper-3.14.7/ofscraper/prompts/utils/prompt_helpers.py
index 5bba038..3113702 100644
--- a/OF-Scraper-3.14.7/ofscraper/prompts/utils/prompt_helpers.py
+++ b/OF-Scraper-3.14.7/ofscraper/prompts/utils/prompt_helpers.py
@@ -117,8 +117,8 @@ def sort_info(prompt_):
 
 def model_funct(prompt):
     while True:
-        with stdout.nostdout():
-            choices = _get_choices()
+        # _get_choices shows the filter menu, so keep stdout visible
+        choices = _get_choices()
         if len(choices) == 0:
             console.print("Current filters returned zero models")
             continue
@@ -142,30 +142,30 @@ def model_funct(prompt):
 
 
 def model_select_funct(prompt):
-    with stdout.nostdout():
-        try:
-            toggle = promptConvert.getChecklistSelection(
-                choices=[
-                    Choice(True, "Range Select"),
-                    Choice(False, "Range Deselect"),
-                ]
-            )
+    toggle = promptConvert.getChecklistSelection(
+        choices=[
+            Choice(True, "Range Select"),
+            Choice(False, "Range Deselect"),
+        ]
+    )
 
-            # select new
-            choices = _select_helper(prompt, toggle)
-            prompt.content_control._raw_choices = choices
-            prompt.content_control.choices = prompt.content_control._get_choices(
-                prompt.content_control._raw_choices, prompt.content_control._default
-            )
-            prompt.content_control._format_choices()
-            return prompt
-        except Exception as E:
-            raise E
+    # select new
+    choices = _select_helper(prompt, toggle)
+    prompt.content_control._raw_choices = choices
+    prompt.content_control.choices = prompt.content_control._get_choices(
+        prompt.content_control._raw_choices, prompt.content_control._default
+    )
+    prompt.content_control._format_choices()
+    return prompt
 
 
 def _select_helper(prompt, toggle=True):
     try:
-        choices = _get_choices()
+        # number against the list that is on screen; _get_choices() would
+        # send the user through the filter/sort menu again first
+        choices = list(prompt.content_control._raw_choices)
+        for model in choices:
+            model.enabled = False
         selectedSet = set(
             map(
                 lambda x: re.search("^[0-9]+: ([^ ]+)", x["name"]).group(1),
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/context/stdout.py b/OF-Scraper-3.14.7/ofscraper/utils/context/stdout.py
index f8e2bc5..c7dfd28 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/context/stdout.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/context/stdout.py
@@ -10,24 +10,21 @@
 @contextlib.contextmanager
 def lowstdout():
     if settings.get_settings().output_level in of_env.getattr("SUPRESS_OUTPUTS"):
-        save_stdout = sys.stdout
-        sys.stdout = open(os.devnull, "w")
-        yield
-        sys.stdout = save_stdout
+        with nostdout():
+            yield
     else:
-        None
         yield
-        None
 
 
 @contextlib.contextmanager
 def nostdout():
-    try:
-        save_stdout = sys.stdout
-        sys.stdout = open(os.devnull, "w")
-        yield
-        sys.stdout = save_stdout
-    except:
-        None
-        yield
-        None
+    # always put stdout back, also when the body raises (e.g. ctrl+c in a
+    # prompt); yielding a second time from an except block turned that into
+    # "generator didn't stop after throw()" and left stdout at devnull
+    save_stdout = sys.stdout
+    with open(os.devnull, "w") as devnull:
+        sys.stdout = devnull
+        try:
+            yield
+        finally:
+            sys.stdout = save_stdout
diff --git a/OF-Scraper-3.14.7/test/unit/test_model_selector.py b/OF-Scraper-3.14.7/test/unit/test_model_selector.py
new file mode 100644
index 0000000..a8dbf57
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_model_selector.py
@@ -0,0 +1,69 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import sys
+from types import SimpleNamespace
+
+import pytest
+
+pytestmark = pytest.mark.unit
+from InquirerPy.base import Choice
+
+import ofscraper.prompts.utils.prompt_helpers as prompt_helpers
+from ofscraper.utils.context import stdout
+
+
+def test_nostdout_restores_stdout_on_exception():
+    before = sys.stdout
+    with pytest.raises(KeyboardInterrupt):
+        with stdout.nostdout():
+            raise KeyboardInterrupt
+    assert sys.stdout is before
+
+
+def test_nostdout_hides_and_restores():
+    before = sys.stdout
+    with stdout.nostdout():
+        assert sys.stdout is not before
+    assert sys.stdout is before
+
+
+def _prompt(n, selected):
+    choices = [Choice(i, name=f"{i + 1}: m{i}   => details") for i in range(n)]
+    return SimpleNamespace(
+        content_control=SimpleNamespace(_raw_choices=choices),
+        selected_choices=[{"name": choices[i].name} for i in selected],
+    )
+
+
+@pytest.fixture
+def no_filter_menu(monkeypatch):
+    def boom():
+        raise AssertionError("range select must not reopen the filter menu")
+
+    monkeypatch.setattr(prompt_helpers, "_get_choices", boom)
+
+
+def _enabled(choices):
+    return [c.value for c in choices if c.enabled]
+
+
+def test_range_select_uses_visible_list(monkeypatch, no_filter_menu):
+    monkeypatch.setattr(
+        prompt_helpers.promptConvert, "multiline_input_prompt", lambda **k: "2-4,30"
+    )
+    out = prompt_helpers._select_helper(_prompt(30, selected=[0]), toggle=True)
+    assert _enabled(out) == [0, 1, 2, 3, 29]
+
+
+def test_range_deselect_keeps_the_rest(monkeypatch, no_filter_menu):
+    monkeypatch.setattr(
+        prompt_helpers.promptConvert, "multiline_input_prompt", lambda **k: "1"
+    )
+    out = prompt_helpers._select_helper(_prompt(5, selected=[0, 2]), toggle=False)
+    assert _enabled(out) == [2]
```
