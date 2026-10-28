# PR #11: fix(models): don't drop to the main menu after 'Yes Update Selection'

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/11
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/update-selection-menu` → `main`
- **Created:** 2026-10-23T02:46:35Z  ·  **Updated:** 2026-10-23T03:19:42Z
- **Draft:** False
- **Changes:** 3 files, +44 / -2

## Description

**Upstream issue:** datawhores/OF-Scraper#560

On a second run the reset-username prompt's 'Yes Update Selection'
called resetUserSelect(), which set args.usernames to None.
_select_models_scraper then did `"ALL" in usernames` and raised
TypeError, which the menu caught, so the user was sent back to the main
menu instead of getting the model list. Reset usernames to an empty
list, as the CLI default is, and treat a missing value as empty.

## Tested
- **Unit:** `test_update_selection.py`: 2 passed with the change; against the code before it: 2 failed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/managers/model.py`
- `OF-Scraper-3.14.7/ofscraper/utils/args/mutators/user.py`
- `OF-Scraper-3.14.7/test/unit/test_update_selection.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/managers/model.py b/OF-Scraper-3.14.7/ofscraper/managers/model.py
index f7b309f..183b4a8 100644
--- a/OF-Scraper-3.14.7/ofscraper/managers/model.py
+++ b/OF-Scraper-3.14.7/ofscraper/managers/model.py
@@ -261,7 +261,7 @@ def _select_models_scraper(self) -> List["Model"]:
 
         Note: This is NOT used by 'add_models' (Check modes), which injects targets directly.
         """
-        usernames = settings.get_settings().usernames
+        usernames = settings.get_settings().usernames or []
         is_daemon = settings.get_settings().daemon
 
         # Guard Clause 1: Daemon mode with a specific list of users.
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/args/mutators/user.py b/OF-Scraper-3.14.7/ofscraper/utils/args/mutators/user.py
index 6eaad28..63b5aa5 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/args/mutators/user.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/args/mutators/user.py
@@ -24,5 +24,6 @@ def resetUserFilters():
 
 def resetUserSelect():
     args = read_args.retriveArgs()
-    args.usernames = None
+    # an empty list, like the CLI default; None broke "ALL" in usernames
+    args.usernames = []
     return args
diff --git a/OF-Scraper-3.14.7/test/unit/test_update_selection.py b/OF-Scraper-3.14.7/test/unit/test_update_selection.py
new file mode 100644
index 0000000..45236e7
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_update_selection.py
@@ -0,0 +1,41 @@
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
+import ofscraper.data.models.utils.retriver as retriver
+import ofscraper.utils.args.accessors.read as read_args
+from ofscraper.classes.of.models import Model
+from ofscraper.managers import model as model_manager
+from ofscraper.utils.args.mutators.user import resetUserSelect
+
+
+def test_reset_user_select_clears_to_empty_list(monkeypatch):
+    monkeypatch.setattr(
+        read_args, "retriveArgs", lambda: SimpleNamespace(usernames=["a", "b"])
+    )
+    assert resetUserSelect().usernames == []
+
+
+def test_selection_after_reset_opens_selector(monkeypatch):
+    # "Yes Update Selection" left usernames=None, and `"ALL" in None`
+    # dropped the user back to the main menu
+    mm = model_manager.ModelManager()
+    models = [Model({"id": i, "username": f"m{i}"}) for i in range(3)]
+    mm._update_all_subs(models)
+    monkeypatch.setattr(
+        model_manager.settings,
+        "get_settings",
+        lambda: SimpleNamespace(usernames=None, daemon=None),
+    )
+    monkeypatch.setattr(mm, "_filter_and_prompt_for_selection", lambda: {m.name: m for m in models})
+    monkeypatch.setattr(retriver, "get_selected_model", lambda found, existing: found[:1])
+    assert [m.name for m in mm._select_models_scraper()] == ["m0"]
```
