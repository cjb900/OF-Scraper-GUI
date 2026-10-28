# PR #16: fix(models): keep deleted-account placeholders out of the normal scrape

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/16
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/paid-placeholder-models` → `main`
- **Created:** 2026-10-23T02:46:43Z  ·  **Updated:** 2026-10-23T02:46:43Z
- **Draft:** False
- **Changes:** 3 files, +51 / -3

## Description

--scrape-paid runs first and adds a placeholder model (username and id
only) for each deleted account. --username ALL then selected them too,
and the normal pass failed on each with KeyError: 'avatar'. Leave them
out of the scrape selection; only the paid pass can use them. Model
avatar/header now return None when missing, like the other properties.

## Tested
- **Unit:** `test_paid_placeholder_models.py`: 2 passed with the change; against the code before it: 2 failed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/classes/of/models.py`
- `OF-Scraper-3.14.7/ofscraper/managers/model.py`
- `OF-Scraper-3.14.7/test/unit/test_paid_placeholder_models.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/classes/of/models.py b/OF-Scraper-3.14.7/ofscraper/classes/of/models.py
index e31b3c2..f01b394 100644
--- a/OF-Scraper-3.14.7/ofscraper/classes/of/models.py
+++ b/OF-Scraper-3.14.7/ofscraper/classes/of/models.py
@@ -28,11 +28,11 @@ def id(self):
 
     @property
     def avatar(self):
-        return self._model["avatar"]
+        return self._model.get("avatar")
 
     @property
     def header(self):
-        return self._model["header"]
+        return self._model.get("header")
 
     @property
     def sub_price(self):
diff --git a/OF-Scraper-3.14.7/ofscraper/managers/model.py b/OF-Scraper-3.14.7/ofscraper/managers/model.py
index f7b309f..69312b7 100644
--- a/OF-Scraper-3.14.7/ofscraper/managers/model.py
+++ b/OF-Scraper-3.14.7/ofscraper/managers/model.py
@@ -391,7 +391,10 @@ def get_models_from_prompt(self):
 
     def _apply_filters(self) -> List["Model"]:
         """Runs the loaded models through the gauntlet of configured filters."""
-        models = self.all_subs
+        # --scrape-paid adds placeholders for deleted accounts; only the paid
+        # pass can use them, so keep them out of the normal scrape
+        placeholder = of_env.getattr("DELETED_MODEL_PLACEHOLDER")
+        models = [m for m in self.all_subs if not str(m.name).startswith(placeholder)]
         models = subtype.subType(models)
         models = price.pricePaidFreeFilterHelper(models)
         models = flags.promoFilterHelper(models)
diff --git a/OF-Scraper-3.14.7/test/unit/test_paid_placeholder_models.py b/OF-Scraper-3.14.7/test/unit/test_paid_placeholder_models.py
new file mode 100644
index 0000000..0065a0c
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_paid_placeholder_models.py
@@ -0,0 +1,45 @@
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
+import ofscraper.managers.model as model_manager
+import ofscraper.utils.of_env.of_env as of_env
+from ofscraper.classes.of.models import Model
+
+
+def _placeholder():
+    return f"{of_env.getattr('DELETED_MODEL_PLACEHOLDER')}_123"
+
+
+def test_placeholder_models_are_left_out_of_the_scrape_selection(monkeypatch):
+    for module, name in [
+        (model_manager.subtype, "subType"),
+        (model_manager.price, "pricePaidFreeFilterHelper"),
+        (model_manager.flags, "promoFilterHelper"),
+        (model_manager.date_, "dateFilters"),
+        (model_manager.other, "otherFilters"),
+    ]:
+        monkeypatch.setattr(module, name, lambda models: models)
+    manager = model_manager.ModelManager()
+    # what --scrape-paid adds for a deleted account, beside a real subscription
+    manager._update_all_subs(
+        [
+            Model({"username": "model", "id": 1, "avatar": None}),
+            Model({"username": _placeholder(), "id": _placeholder()}),
+        ]
+    )
+
+    assert [m.name for m in manager._apply_filters()] == ["model"]
+    assert manager.get_model(_placeholder()) is not None  # still there for the paid pass
+
+
+def test_placeholder_model_has_no_avatar_or_header():
+    placeholder = Model({"username": _placeholder(), "id": _placeholder()})
+    assert placeholder.avatar is None and placeholder.header is None
```
