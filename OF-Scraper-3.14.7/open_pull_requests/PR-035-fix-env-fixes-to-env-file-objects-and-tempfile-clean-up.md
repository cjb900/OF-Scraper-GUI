# PR #35: fix(env): Fixes to env-file objects and tempfile clean up

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/35
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/env-file-json` → `main`
- **Created:** 2026-11-06T22:20:57Z  ·  **Updated:** 2026-11-07T00:03:22Z
- **Draft:** False
- **Changes:** 6 files, +343 / -3

## Description

**What was broken:**
- JSON/YAML env files stored objects as Python text, so a manual dynamic rule from an env file failed.
- `OFSC_BATCH_TEMPFILE_CLEANUP=true` was ignored (typo).
- The temp cleanup never removed `temp_` files.

**What was fixed:**
- Objects and lists are stored as JSON.
- The typo is corrected.
- The `temp_` prefix is matched against the file name.

Tested: 24 new tests; full suite 876 passed, 11 skipped. Patched installs get this once #32 is merged and the patch rebuilt.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/utils/of_env/load.py`
- `OF-Scraper-3.14.7/ofscraper/utils/of_env/values/path/general.py`
- `OF-Scraper-3.14.7/ofscraper/utils/paths/paths.py`
- `OF-Scraper-3.14.7/test/unit/test_batch_tempfile_cleanup_env.py`
- `OF-Scraper-3.14.7/test/unit/test_env_files.py`
- `OF-Scraper-3.14.7/test/unit/test_temp_cleanup_prefix.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/of_env/load.py b/OF-Scraper-3.14.7/ofscraper/utils/of_env/load.py
index 8f8e7b7..7f9d15a 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/of_env/load.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/of_env/load.py
@@ -7,6 +7,24 @@
 log = logging.getLogger("shared")
 
 
+def _env_text(key, value):
+    """
+    Objects and lists are stored as JSON so settings that expect JSON can
+    parse them; str() would give Python syntax. YAML-only types inside them
+    (dates, sets, binary) become text, and anything json can't write at all,
+    such as a list that contains itself, keeps the old str() form.
+    """
+    if isinstance(value, (dict, list)):
+        try:
+            return json.dumps(value, default=str)
+        except (TypeError, ValueError) as e:
+            log.warning(
+                f"{key}: couldn't store the value as JSON ({e}), "
+                "stored as Python text instead"
+            )
+    return str(value)
+
+
 def load_env_files(values: list[str] | None):
     """
     Loads environment variables from a list of file paths.
@@ -56,7 +74,7 @@ def load_env_files(values: list[str] | None):
 
             if data:
                 # Update os.environ, ensuring all keys and values are strings
-                os.environ.update({str(k): str(v) for k, v in data.items()})
+                os.environ.update({str(k): _env_text(k, v) for k, v in data.items()})
                 log.info(
                     f"Successfully loaded environment variables from '{file_path}'"
                 )
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/path/general.py b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/path/general.py
index 6170da0..7bb3f2e 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/path/general.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/path/general.py
@@ -29,6 +29,6 @@ def load_general_paths_config():
     # Default: False
     config["BATCH_TEMPFILE_CLEANUP"] = os.getenv(
         "OFSC_BATCH_TEMPFILE_CLEANUP", "False"
-    ).lower() in ("tPostCollectionrue", "1")
+    ).lower() in ("true", "1")
 
     return config
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/paths/paths.py b/OF-Scraper-3.14.7/ofscraper/utils/paths/paths.py
index f85b826..9885474 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/paths/paths.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/paths/paths.py
@@ -46,7 +46,8 @@ def temp_cleanup():
         if root is None:
             return
         for file in filter(
-            lambda x: re.search(r"\.part$|^temp_", str(x)) is not None,
+            lambda x: x.is_file()
+            and re.search(r"\.part$|^temp_", x.name) is not None,
             pathlib.Path(root).glob("**/*"),
         ):
             file.unlink(missing_ok=True)
diff --git a/OF-Scraper-3.14.7/test/unit/test_batch_tempfile_cleanup_env.py b/OF-Scraper-3.14.7/test/unit/test_batch_tempfile_cleanup_env.py
new file mode 100644
index 0000000..ed5bfd2
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_batch_tempfile_cleanup_env.py
@@ -0,0 +1,29 @@
+"""OFSC_BATCH_TEMPFILE_CLEANUP accepts "true" like the other flags."""
+
+import pytest
+
+from ofscraper.utils.of_env.values.path.general import load_general_paths_config
+
+pytestmark = pytest.mark.unit
+
+
+@pytest.mark.parametrize(
+    "value,expected",
+    [
+        ("true", True),
+        ("True", True),
+        ("TRUE", True),
+        ("1", True),
+        ("false", False),
+        ("0", False),
+        ("", False),
+    ],
+)
+def test_batch_tempfile_cleanup_flag(monkeypatch, value, expected):
+    monkeypatch.setenv("OFSC_BATCH_TEMPFILE_CLEANUP", value)
+    assert load_general_paths_config()["BATCH_TEMPFILE_CLEANUP"] is expected
+
+
+def test_batch_tempfile_cleanup_defaults_to_off(monkeypatch):
+    monkeypatch.delenv("OFSC_BATCH_TEMPFILE_CLEANUP", raising=False)
+    assert load_general_paths_config()["BATCH_TEMPFILE_CLEANUP"] is False
diff --git a/OF-Scraper-3.14.7/test/unit/test_env_files.py b/OF-Scraper-3.14.7/test/unit/test_env_files.py
new file mode 100644
index 0000000..4b1dca9
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_env_files.py
@@ -0,0 +1,210 @@
+"""Objects and lists in JSON/YAML env files are stored as JSON text."""
+
+import json
+import logging
+import os
+
+import pytest
+
+import ofscraper.utils.auth.request as auth_request
+import ofscraper.utils.config.data as config_data
+import ofscraper.utils.of_env.of_env as of_env
+from ofscraper.utils.of_env.load import load_env_files
+
+pytestmark = pytest.mark.unit
+
+KEYS = (
+    "OFSC_TEST_OBJECT",
+    "OFSC_TEST_LIST",
+    "OFSC_TEST_STRING",
+    "OFSC_TEST_INT",
+    "OFSC_TEST_FLOAT",
+    "OFSC_TEST_BOOL",
+    "OFSC_TEST_NULL",
+    "OFSC_TEST_DATE_MAP",
+    "OFSC_TEST_DATETIME_LIST",
+    "OFSC_TEST_SET_MAP",
+    "OFSC_TEST_BINARY_LIST",
+    "OFSC_TEST_SELF_LIST",
+    "OFSC_TEST_DATE_KEY",
+)
+
+
+@pytest.fixture
+def clean_env(tmp_path, monkeypatch):
+    # load_env_files also reads a .env from the working directory
+    monkeypatch.chdir(tmp_path)
+    for key in KEYS:
+        monkeypatch.delenv(key, raising=False)
+    return tmp_path
+
+
+JSON_FILE = """{
+  "OFSC_TEST_OBJECT": {"static_param": "abc", "checksum_indexes": [1, 2]},
+  "OFSC_TEST_LIST": ["a", "b"],
+  "OFSC_TEST_STRING": "plain",
+  "OFSC_TEST_INT": 5,
+  "OFSC_TEST_FLOAT": 1.5,
+  "OFSC_TEST_BOOL": true,
+  "OFSC_TEST_NULL": null
+}
+"""
+
+YAML_FILE = """OFSC_TEST_OBJECT:
+  static_param: abc
+  checksum_indexes: [1, 2]
+OFSC_TEST_LIST:
+  - a
+  - b
+OFSC_TEST_STRING: plain
+OFSC_TEST_INT: 5
+OFSC_TEST_FLOAT: 1.5
+OFSC_TEST_BOOL: true
+OFSC_TEST_NULL: null
+"""
+
+
+@pytest.mark.parametrize("name,text", [("env.json", JSON_FILE), ("env.yaml", YAML_FILE)])
+def test_objects_and_lists_are_stored_as_json(clean_env, name, text):
+    path = clean_env / name
+    path.write_text(text, encoding="utf-8")
+
+    load_env_files([str(path)])
+
+    assert json.loads(os.environ["OFSC_TEST_OBJECT"]) == {
+        "static_param": "abc",
+        "checksum_indexes": [1, 2],
+    }
+    assert json.loads(os.environ["OFSC_TEST_LIST"]) == ["a", "b"]
+
+
+@pytest.mark.parametrize("name,text", [("env.json", JSON_FILE), ("env.yaml", YAML_FILE)])
+def test_other_values_are_stored_as_before(clean_env, name, text):
+    path = clean_env / name
+    path.write_text(text, encoding="utf-8")
+
+    load_env_files([str(path)])
+
+    assert os.environ["OFSC_TEST_STRING"] == "plain"
+    assert os.environ["OFSC_TEST_INT"] == "5"
+    assert os.environ["OFSC_TEST_FLOAT"] == "1.5"
+    assert os.environ["OFSC_TEST_BOOL"] == "True"
+    assert os.environ["OFSC_TEST_NULL"] == "None"
+
+
+# YAML types that JSON doesn't have, inside an object or list. They loaded
+# (as Python text) before objects and lists were stored as JSON, and the
+# rest of the file must still load.
+def _date_map(text):
+    assert json.loads(text) == {"since": "2024-01-02"}
+
+
+def _datetime_list(text):
+    assert json.loads(text) == ["2024-01-02 10:00:00"]
+
+
+def _set_map(text):
+    # a set has no order and no JSON form: it is stored as text in the object
+    assert json.loads(text)["s"] in ("{'a', 'b'}", "{'b', 'a'}")
+
+
+def _binary_list(text):
+    assert len(json.loads(text)) == 1
+
+
+def _self_list(text):
+    # json can't write a list that contains itself; it keeps the str() form
+    assert text == "[1, [...]]"
+
+
+@pytest.mark.parametrize(
+    "key,yaml_value,check",
+    [
+        ("OFSC_TEST_DATE_MAP", "{since: 2024-01-02}", _date_map),
+        ("OFSC_TEST_DATETIME_LIST", "[2024-01-02 10:00:00]", _datetime_list),
+        ("OFSC_TEST_SET_MAP", "{s: !!set {a, b}}", _set_map),
+        ("OFSC_TEST_BINARY_LIST", "[!!binary aGVsbG8=]", _binary_list),
+        ("OFSC_TEST_SELF_LIST", "&r [1, *r]", _self_list),
+    ],
+    ids=["nested-date", "datetime-list", "set", "binary", "circular-anchor"],
+)
+def test_yaml_only_types_inside_objects_still_load(clean_env, key, yaml_value, check):
+    path = clean_env / "env.yaml"
+    path.write_text(f"{key}: {yaml_value}\nOFSC_TEST_STRING: plain\n", encoding="utf-8")
+
+    load_env_files([str(path)])
+
+    check(os.environ[key])
+    assert os.environ["OFSC_TEST_STRING"] == "plain"
+
+
+@pytest.mark.parametrize(
+    "key,yaml_value,stored",
+    [
+        ("OFSC_TEST_SELF_LIST", "&r [1, *r]", "[1, [...]]"),
+        # JSON keys must be text, and default=str doesn't apply to keys
+        ("OFSC_TEST_DATE_KEY", "{2024-01-02: a}", "{datetime.date(2024, 1, 2): 'a'}"),
+    ],
+    ids=["circular-anchor", "date-key"],
+)
+def test_python_text_fallback_warns_with_the_key(
+    clean_env, caplog, key, yaml_value, stored
+):
+    path = clean_env / "env.yaml"
+    path.write_text(f"{key}: {yaml_value}\nOFSC_TEST_STRING: plain\n", encoding="utf-8")
+
+    with caplog.at_level(logging.WARNING, logger="shared"):
+        load_env_files([str(path)])
+
+    assert os.environ[key] == stored
+    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
+    assert len(warnings) == 1
+    assert warnings[0].startswith(f"{key}: couldn't store the value as JSON")
+
+
+# The GUI's manual dynamic rules read OFSC_DYNAMIC_RULE_MANUAL as JSON text,
+# and a non-empty env value is used ahead of the config.json rules.
+RULES = {
+    "static_param": "fake_static_param",
+    "format": "1:{}:{:x}:2",
+    "checksum_indexes": [1, 2, 3],
+    "checksum_constant": 7,
+}
+
+
+@pytest.fixture
+def manual_rule_env(clean_env, monkeypatch):
+    monkeypatch.delenv("OFSC_DYNAMIC_RULE_MANUAL", raising=False)
+    monkeypatch.setattr(config_data, "get_dynamic_rules_manual", lambda *a, **k: None)
+    yield clean_env
+    # load_env_files writes os.environ directly; drop the value and reload the
+    # cached settings so later tests don't see it
+    os.environ.pop("OFSC_DYNAMIC_RULE_MANUAL", None)
+    of_env.get_all_configs(forced=True)
+
+
+@pytest.mark.parametrize("name", ["env.json", "env.yaml"])
+def test_manual_dynamic_rule_from_an_env_file_is_used(manual_rule_env, name):
+    path = manual_rule_env / name
+    if name.endswith(".json"):
+        path.write_text(json.dumps({"OFSC_DYNAMIC_RULE_MANUAL": RULES}), encoding="utf-8")
+    else:
+        path.write_text(
+            "OFSC_DYNAMIC_RULE_MANUAL:\n"
+            "  static_param: fake_static_param\n"
+            "  format: '1:{}:{:x}:2'\n"
+            "  checksum_indexes: [1, 2, 3]\n"
+            "  checksum_constant: 7\n",
+            encoding="utf-8",
+        )
+
+    # the same two steps settings.setup_settings() runs at start-up
+    load_env_files([str(path)])
+    of_env.get_all_configs(forced=True)
+
+    assert auth_request.get_request_auth_dynamic_rule_manual() == (
+        "fake_static_param",
+        "1:{}:{:x}:2",
+        [1, 2, 3],
+        7,
+    )
diff --git a/OF-Scraper-3.14.7/test/unit/test_temp_cleanup_prefix.py b/OF-Scraper-3.14.7/test/unit/test_temp_cleanup_prefix.py
new file mode 100644
index 0000000..91b5e8b
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_temp_cleanup_prefix.py
@@ -0,0 +1,82 @@
+"""temp_cleanup() removes temp_ files by file name, not by full path."""
+
+from types import SimpleNamespace
+
+import pytest
+
+import ofscraper.utils.paths.paths as paths
+
+pytestmark = pytest.mark.unit
+
+
+def _run_cleanup(monkeypatch, root):
+    real_getattr = paths.of_env.getattr
+
+    def fake_getattr(key, *args, **kwargs):
+        if key == "BATCH_TEMPFILE_CLEANUP":
+            return True
+        return real_getattr(key, *args, **kwargs)
+
+    monkeypatch.setattr(paths.of_env, "getattr", fake_getattr)
+    monkeypatch.setattr(
+        paths.settings, "get_settings", lambda: SimpleNamespace(auto_resume=False)
+    )
+    monkeypatch.setattr(paths.data, "get_TempDir", lambda *a, **k: str(root))
+    paths.temp_cleanup()
+
+
+def test_removes_temp_prefixed_files(monkeypatch, tmp_path):
+    # The DRM merge in alt_download.py writes temp_<id>.mp4, or
+    # temp_<id>_<seq>.mp4 for a duplicate, under the temp folder.
+    sub = tmp_path / "creator" / "Videos"
+    sub.mkdir(parents=True)
+    temp_top = tmp_path / "temp_123456.mp4"
+    temp_nested = sub / "temp_654321.mp4"
+    temp_seq = sub / "temp_654321_2.mp4"
+    part = sub / "video.mp4.part"
+    for f in (temp_top, temp_nested, temp_seq, part):
+        f.write_bytes(b"x")
+
+    _run_cleanup(monkeypatch, tmp_path)
+
+    assert not temp_top.exists()
+    assert not temp_nested.exists()
+    assert not temp_seq.exists()
+    assert not part.exists()
+
+
+def test_keeps_other_files_and_folders(monkeypatch, tmp_path):
+    # A folder named temp_ is left alone, and so is a file inside it or
+    # with temp_ in the middle of its name.
+    temp_dir = tmp_path / "temp_folder"
+    temp_dir.mkdir()
+    inside = temp_dir / "keep.mp4"
+    middle = tmp_path / "my_temp_clip.mp4"
+    done = tmp_path / "finished.mp4"
+    for f in (inside, middle, done):
+        f.write_bytes(b"x")
+
+    _run_cleanup(monkeypatch, tmp_path)
+
+    assert temp_dir.is_dir()
+    assert inside.exists()
+    assert middle.exists()
+    assert done.exists()
+
+
+def test_does_nothing_when_the_setting_is_off(monkeypatch, tmp_path):
+    temp_file = tmp_path / "temp_123456.mp4"
+    temp_file.write_bytes(b"x")
+    monkeypatch.setattr(paths.data, "get_TempDir", lambda *a, **k: str(tmp_path))
+    real_getattr = paths.of_env.getattr
+    monkeypatch.setattr(
+        paths.of_env,
+        "getattr",
+        lambda key, *a, **k: False
+        if key == "BATCH_TEMPFILE_CLEANUP"
+        else real_getattr(key, *a, **k),
+    )
+
+    paths.temp_cleanup()
+
+    assert temp_file.exists()
```
