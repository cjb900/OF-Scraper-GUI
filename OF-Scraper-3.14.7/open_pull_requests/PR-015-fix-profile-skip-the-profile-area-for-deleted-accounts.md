# PR #15: fix(profile): skip the profile area for deleted accounts

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/15
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/profile-deleted-model` → `main`
- **Created:** 2026-10-23T02:46:42Z  ·  **Updated:** 2026-10-23T02:46:42Z
- **Draft:** False
- **Changes:** 2 files, +57 / -0

## Description

A 404 profile returns only the deleted-model placeholder, which
process_profile passed to parse_profile. That raised KeyError: 'name'
and logged a traceback for every deleted account. Skip it instead:
a deleted account has no avatar or header to download.

## Tested
- **Unit:** `test_profile_deleted_model.py`: 2 passed with the change; against the code before it: 1 failed, 1 passed.
- **Full `test/unit`** on this branch: 44 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/data/posts/post.py`
- `OF-Scraper-3.14.7/test/unit/test_profile_deleted_model.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/data/posts/post.py b/OF-Scraper-3.14.7/ofscraper/data/posts/post.py
index 23dddc7..86afc9e 100644
--- a/OF-Scraper-3.14.7/ofscraper/data/posts/post.py
+++ b/OF-Scraper-3.14.7/ofscraper/data/posts/post.py
@@ -294,6 +294,11 @@ async def process_profile(username) -> list:
         user_profile = profile.scrape_profile(username)
         if not user_profile:
             return [], profile.API
+        # a 404 returns only this placeholder: the account is gone, so there's
+        # no avatar or header to download
+        if user_profile.get("username") == of_env.getattr("DELETED_MODEL_PLACEHOLDER"):
+            log.info(f"Skipping profile for {username}: the account no longer exists")
+            return [], profile.API
 
         # standardized_dicts now contains the correctly nested 'media' keys,
         standardized_dicts, info = profile.parse_profile(user_profile)
diff --git a/OF-Scraper-3.14.7/test/unit/test_profile_deleted_model.py b/OF-Scraper-3.14.7/test/unit/test_profile_deleted_model.py
new file mode 100644
index 0000000..a13b14f
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_profile_deleted_model.py
@@ -0,0 +1,52 @@
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
+import asyncio
+from types import SimpleNamespace
+
+import ofscraper.data.posts.post as post
+import ofscraper.utils.of_env.of_env as of_env
+
+
+def _process(monkeypatch, scraped):
+    monkeypatch.setattr(post.profile, "scrape_profile", lambda username: scraped)
+    monkeypatch.setattr(
+        post.free.settings, "get_settings", lambda: SimpleNamespace(system_free_min=0)
+    )
+    tracebacks = []
+    monkeypatch.setattr(post.log, "traceback_", tracebacks.append, raising=False)
+    result = asyncio.run(post.process_profile("gone"))
+    return result, tracebacks
+
+
+def test_deleted_model_profile_is_skipped_without_error(monkeypatch):
+    placeholder = {"username": of_env.getattr("DELETED_MODEL_PLACEHOLDER")}
+    result, tracebacks = _process(monkeypatch, placeholder)
+    assert result == ([], post.profile.API)
+    assert tracebacks == []
+
+
+def test_existing_profile_still_yields_its_media(monkeypatch):
+    scraped = {
+        "id": 1,
+        "username": "model",
+        "name": "Model",
+        "avatar": "https://example.invalid/avatar.jpg",
+        "joinDate": "2020-01-01T00:00:00+00:00",
+        "postsCount": 0,
+        "photosCount": 0,
+        "videosCount": 0,
+        "audiosCount": 0,
+        "archivedPostsCount": 0,
+    }
+    (posts, api), tracebacks = _process(monkeypatch, scraped)
+    assert api == post.profile.API and tracebacks == []
+    assert len(posts) == 1 and posts[0].model_id == 1
```
