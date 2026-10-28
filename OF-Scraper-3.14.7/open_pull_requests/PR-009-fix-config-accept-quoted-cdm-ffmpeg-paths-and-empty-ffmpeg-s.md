# PR #9: fix(config): accept quoted CDM/ffmpeg paths and empty ffmpeg setting

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/9
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/quoted-paths` → `main`
- **Created:** 2026-10-23T02:46:31Z  ·  **Updated:** 2026-10-23T03:19:38Z
- **Draft:** False
- **Changes:** 4 files, +102 / -5

## Description

**Upstream issue:** datawhores/OF-Scraper#587

* fix(config): accept quoted CDM/ffmpeg paths and empty ffmpeg setting

Windows "Copy as path" wraps paths in double quotes, and pasting that
into config.json leaves the quotes inside the string. The manual CDM
then failed every key request with 'Errno 22 Invalid argument' and DRM
videos never downloaded. Strip one pair of surrounding quotes from the
private-key, client-id, ffmpeg and temp_dir settings.

The shipped config has "ffmpeg": "", which was returned as-is, so
OFSC_FFMPEG_DEFAULT could never apply. Treat an empty value as unset.

* fix(config): don't save OFSC_FFMPEG_DEFAULT into config.json

get_ffmpeg() mapped an empty ffmpeg setting to OFSC_FFMPEG_DEFAULT, and
auto_update_config builds the file it writes from these getters, so a
config rewrite stored the env default as the configured path. Keep ""
in the config and apply the env fallback when merging settings.

* fix(config): strip quotes from save_location too

It's the path most often pasted from Explorer's "Copy as path".

---------

## Tested
- **Unit:** `test_config_paths.py`: 12 passed with the change; against the code before it: 10 failed, 2 passed.
- **Full `test/unit`** on this branch: 54 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/utils/config/data.py`
- `OF-Scraper-3.14.7/ofscraper/utils/paths/common.py`
- `OF-Scraper-3.14.7/ofscraper/utils/settings.py`
- `OF-Scraper-3.14.7/test/unit/test_config_paths.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/config/data.py b/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
index ec16473..08b69c2 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
@@ -20,6 +20,16 @@
 import ofscraper.utils.const as const
 
 
+def strip_path_quotes(val):
+    # Windows "Copy as path" wraps paths in double quotes, which then end up
+    # literally inside the json string
+    if isinstance(val, str):
+        val = val.strip()
+        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
+            val = val[1:-1].strip()
+    return val
+
+
 @wrapper.config_reader
 def get_main_profile(config=None):
     if config is False:
@@ -449,6 +459,9 @@ def get_ffmpeg(config=None):
     if config is False:
         return of_env.getattr("FFMPEG_DEFAULT")
     val = config.get("ffmpeg") or config.get("binary_options", {}).get("ffmpeg")
+    val = strip_path_quotes(val)
+    # "" is kept as-is so a config rewrite doesn't save OFSC_FFMPEG_DEFAULT
+    # into the file; settings applies that fallback at runtime
     return val if val is not None else of_env.getattr("FFMPEG_DEFAULT")
 
 
@@ -603,14 +616,18 @@ def get_spacereplacer(config=None):
 def get_private_key(config=None):
     if not config:
         return None
-    return config.get("private-key") or config.get("cdm_options", {}).get("private-key")
+    return strip_path_quotes(
+        config.get("private-key") or config.get("cdm_options", {}).get("private-key")
+    )
 
 
 @wrapper.config_reader
 def get_client_id(config=None):
     if not config:
         return None
-    return config.get("client-id") or config.get("cdm_options", {}).get("client-id")
+    return strip_path_quotes(
+        config.get("client-id") or config.get("cdm_options", {}).get("client-id")
+    )
 
 
 @wrapper.config_reader
@@ -812,7 +829,7 @@ def get_TempDir(config=None):
     if config is False:
         return of_env.getattr("TEMP_FOLDER_DEFAULT")
     val = config.get("temp_dir") or config.get("advanced_options", {}).get("temp_dir")
-    return val if val is not None else of_env.getattr("TEMP_FOLDER_DEFAULT")
+    return strip_path_quotes(val) if val is not None else of_env.getattr("TEMP_FOLDER_DEFAULT")
 
 
 @wrapper.config_reader
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/paths/common.py b/OF-Scraper-3.14.7/ofscraper/utils/paths/common.py
index 5a57153..f63b022 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/paths/common.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/paths/common.py
@@ -128,7 +128,7 @@ def get_save_location(config=None):
     if config is False:
         return of_env.getattr("SAVE_PATH_DEFAULT")
     config = config or config_file.open_config()
-    return (
+    return data.strip_path_quotes(
         config.get("save_location")
         or config.get("file_options", {}).get("save_location")
         or of_env.getattr("SAVE_PATH_DEFAULT")
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/settings.py b/OF-Scraper-3.14.7/ofscraper/utils/settings.py
index 654d57c..bb7e737 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/settings.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/settings.py
@@ -154,7 +154,7 @@ def _listhelper(out):
         if hasattr(config_data, "get_drm_duration_match_threshold")
         else 0.98
     )
-    merged.ffmpeg = config_data.get_ffmpeg()
+    merged.ffmpeg = config_data.get_ffmpeg() or of_env.getattr("FFMPEG_DEFAULT")
     # GUI: name text (.txt) files from post caption instead of File Format / post id
     merged.text_filename_from_post = bool(
         getattr(args, "text_filename_from_post", False)
diff --git a/OF-Scraper-3.14.7/test/unit/test_config_paths.py b/OF-Scraper-3.14.7/test/unit/test_config_paths.py
new file mode 100644
index 0000000..1945043
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_config_paths.py
@@ -0,0 +1,80 @@
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
+import ofscraper.utils.config.data as data
+
+
+@pytest.mark.parametrize(
+    "raw,expected",
+    [
+        ('"C:\\keys\\private_key.pem"', "C:\\keys\\private_key.pem"),
+        ("'/keys/private_key.pem'", "/keys/private_key.pem"),
+        ('  "/keys/a b.pem"  ', "/keys/a b.pem"),
+        ("/keys/private_key.pem", "/keys/private_key.pem"),
+        ('"', '"'),
+        (None, None),
+    ],
+)
+def test_strip_path_quotes(raw, expected):
+    assert data.strip_path_quotes(raw) == expected
+
+
+def test_cdm_paths_are_unquoted():
+    config = {
+        "cdm_options": {
+            "private-key": '"C:\\keys\\private_key.pem"',
+            "client-id": '"C:\\keys\\client_id.bin"',
+        }
+    }
+    assert data.get_private_key(config=config) == "C:\\keys\\private_key.pem"
+    assert data.get_client_id(config=config) == "C:\\keys\\client_id.bin"
+
+
+def test_ffmpeg_path_is_unquoted():
+    config = {"binary_options": {"ffmpeg": '"C:\\ffmpeg\\bin\\ffmpeg.exe"'}}
+    assert data.get_ffmpeg(config=config) == "C:\\ffmpeg\\bin\\ffmpeg.exe"
+
+
+@pytest.fixture
+def ffmpeg_env(monkeypatch):
+    real = data.of_env.getattr
+    monkeypatch.setattr(
+        data.of_env,
+        "getattr",
+        lambda key, *a: "/opt/ffmpeg" if key == "FFMPEG_DEFAULT" else real(key),
+    )
+
+
+def test_empty_ffmpeg_is_not_replaced_by_env_default(ffmpeg_env):
+    assert data.get_ffmpeg(config={"binary_options": {"ffmpeg": ""}}) == ""
+
+
+def test_config_rewrite_keeps_empty_ffmpeg(ffmpeg_env):
+    # auto_update_config writes this schema back to config.json
+    import ofscraper.utils.config.schema as schema
+
+    new = schema.get_current_config_schema({"binary_options": {"ffmpeg": ""}})
+    assert new["binary_options"]["ffmpeg"] == ""
+
+
+def test_settings_falls_back_to_env_default_for_empty_ffmpeg(ffmpeg_env, monkeypatch):
+    import ofscraper.utils.settings as settings
+
+    monkeypatch.setattr(settings.config_data, "get_ffmpeg", lambda: "")
+    assert settings.merged_settings().ffmpeg == "/opt/ffmpeg"
+
+
+def test_save_location_is_unquoted():
+    import ofscraper.utils.paths.common as common_paths
+
+    config = {"file_options": {"save_location": '"D:\Media\OnlyFans"'}}
+    assert common_paths.get_save_location(config=config) == "D:\Media\OnlyFans"
```
