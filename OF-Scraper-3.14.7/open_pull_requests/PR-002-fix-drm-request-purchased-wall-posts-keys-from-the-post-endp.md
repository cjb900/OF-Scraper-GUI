# PR #2: fix(drm): request purchased wall posts' keys from the post endpoint

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/2
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/drm-license-paid-posts` → `main`
- **Created:** 2026-10-23T02:23:15Z  ·  **Updated:** 2026-10-23T03:19:27Z
- **Draft:** False
- **Changes:** 2 files, +46 / -1

## Description

**Upstream issue:** datawhores/OF-Scraper#636

Fixes the `403 "User have no permissions"` DRM error on purchased **wall posts**. A Discord user hit it on the 3.14.7 GUI patch, and upstream has it as datawhores/OF-Scraper#636.

## Cause
Media from the Purchased tab has `responsetype` `"Paid"`. `Media.license` treats anything that isn't a timeline type as a message, so a purchased wall post asks for its key at:

```
/api2/v2/users/media/<media_id>/drm/message/<post_id>
```

OnlyFans answers that with 403. Wall-post keys come from `/drm/post/<post_id>`.

## Fix
Message types still go to `message`. Anything else (Paid and similar) is decided by the post's raw `responseType` from the API: `post` goes to the post endpoint, and everything else to the message endpoint.

This is the same change as the standalone `fix-paid-post-drm-license-endpoint.patch` shared on Discord. The GUI patch overwrites `media.py`, so applying the GUI patch puts the bug back.

## Tested
- **Unit:** `test/unit/test_drm_license_url.py` covers 7 cases: timeline, message, archived, streams, and Paid with raw `post`, `message` or missing. The `Paid` + `post` case fails without the fix. All of `test/unit` passes (49 passed, 1 skipped).
- **Live, on this repo's `OF-Scraper-3.14.7` tree:**
  - Without the fix, a purchased wall post failed with 403 on `/drm/message/`.
  - With the fix, it used `/drm/post/` and downloaded. Its audio and video streams are hash-identical to a copy downloaded earlier.
  - Purchased PPV messages and a timeline post also still download.

`patch_ofscraper_3.14.7_gui.py` isn't regenerated here; it'll need rebuilding to ship this.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/classes/of/media.py`
- `OF-Scraper-3.14.7/test/unit/test_drm_license_url.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/classes/of/media.py b/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
index bf3a65f..b4ff37b 100644
--- a/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
+++ b/OF-Scraper-3.14.7/ofscraper/classes/of/media.py
@@ -496,8 +496,13 @@ def license(self):
         responsetype = self.post.responsetype.lower()
         if responsetype in ["timeline", "archived", "pinned", "posts", "streams"]:
             responsetype = "post"
-        else:
+        elif responsetype in ["messages", "message"]:
             responsetype = "message"
+        else:
+            # purchased items can be timeline posts or PPV messages; the raw
+            # responseType says which DRM endpoint OnlyFans expects
+            raw = str(self.post.post.get("responseType") or "").lower()
+            responsetype = "post" if raw == "post" else "message"
         return of_env.getattr("LICENCE_URL").format(self.id, responsetype, self.post_id)
 
     @property
diff --git a/OF-Scraper-3.14.7/test/unit/test_drm_license_url.py b/OF-Scraper-3.14.7/test/unit/test_drm_license_url.py
new file mode 100644
index 0000000..2bec2c0
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_drm_license_url.py
@@ -0,0 +1,40 @@
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
+import ofscraper.classes.of.posts as posts_
+from ofscraper.classes.of.media import Media
+
+
+def _media(post_data, responsetype=None):
+    post = posts_.Post(post_data, 1, "model", responsetype=responsetype)
+    media = Media({"id": 111}, 0, post)
+    media.mpd = "https://cdn/manifest.mpd"
+    return media
+
+
+@pytest.mark.parametrize(
+    "post_data,responsetype,kind",
+    [
+        ({"id": 5, "responseType": "post"}, None, "post"),
+        ({"id": 5, "responseType": "message"}, None, "message"),
+        ({"id": 5, "responseType": "post", "isArchived": True}, None, "post"),
+        ({"id": 5}, "streams", "post"),
+        # purchased tab: the raw responseType decides
+        ({"id": 5, "responseType": "post"}, "Paid", "post"),
+        ({"id": 5, "responseType": "message"}, "Paid", "message"),
+        ({"id": 5}, "Paid", "message"),
+    ],
+)
+def test_license_endpoint(post_data, responsetype, kind):
+    url = _media(post_data, responsetype).license
+    assert f"/users/media/111/drm/{kind}/5?" in url
+
```
