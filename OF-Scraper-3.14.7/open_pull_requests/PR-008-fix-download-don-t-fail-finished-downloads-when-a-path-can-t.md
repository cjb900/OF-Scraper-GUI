# PR #8: fix(download): don't fail finished downloads when a path can't be resolved

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/8
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/resolve-network-drive` → `main`
- **Created:** 2026-10-23T02:46:29Z  ·  **Updated:** 2026-10-23T03:19:36Z
- **Draft:** False
- **Changes:** 2 files, +138 / -37

## Description

**Upstream issue:** datawhores/OF-Scraper#619

* fix(download): don't fail finished downloads when a path can't be resolved

After a file was moved into place, addGlobalDir called Path.resolve on
its folder to remember it for dating later. On some mapped/virtual
Windows drives resolve raises WinError 1005, so every download on such a
drive was reported as failed even though the file was saved.

Fall back to an absolute path when resolve fails, treat a str path as
one path instead of iterating its characters, and log instead of raise
if a folder's date can't be set at the end of the run.

* fix(download): guard the folder-dating walk and resolve the save root

os.path.samefile stats both paths and can raise the same OSError as
resolve() on mapped/virtual drives, so catch it per element. Resolve
rootDir the same way as dirSet entries; a drive-letter rootDir next to
resolved UNC entries made is_relative_to stop the walk early.

---------

## Tested
- **Unit:** `test_dir_bookkeeping.py`: 7 passed with the change; against the code before it: 4 failed, 3 passed.
- **Full `test/unit`** on this branch: 49 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py`
- `OF-Scraper-3.14.7/test/unit/test_dir_bookkeeping.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
index c4a3bf5..ea3ec57 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
@@ -31,34 +31,34 @@ def moveHelper(temp, path_to_file, ele, log_=None):
     # set variables based on parent process
 
 
+def _resolve(path):
+    path = pathlib.Path(path)
+    try:
+        return path.resolve()
+    except OSError:
+        # some network/virtual drives (e.g. WinError 1005 on mapped Windows
+        # volumes) can't be resolved; the directory set is only used to
+        # date folders afterwards, so an absolute path is enough
+        return path.absolute()
+
+
+def _resolve_dir(path):
+    path = _resolve(path)
+    return path if path.is_dir() else path.parent
+
+
 def addGlobalDir(path):
-    paths = [path] if not isinstance(path, Iterable) else path
-    paths = list(
-        map(
-            lambda x: (
-                path.resolve(x).parent
-                if not pathlib.Path(x).is_dir()
-                else path.resolve(x)
-            ),
-            paths,
-        )
+    paths = (
+        [path]
+        if isinstance(path, (str, os.PathLike)) or not isinstance(path, Iterable)
+        else path
     )
-    common_globals.dirSet.update(paths)
+    common_globals.dirSet.update(map(_resolve_dir, paths))
 
 
 def addLocalDir(path):
     paths = [path] if not isinstance(path, list) else path
-    paths = list(
-        map(
-            lambda x: (
-                path.resolve(x).parent
-                if not pathlib.Path(x).is_dir()
-                else path.resolve(x)
-            ),
-            paths,
-        )
-    )
-    common_globals.dirSet.update(paths)
+    common_globals.dirSet.update(map(_resolve_dir, paths))
 
 
 def set_time(path, timestamp):
@@ -71,25 +71,34 @@ def setDirectoriesDate(log=None):
     log = log or common_globals.log
     log.info("Setting Date for modified directories")
     output = set()
-    rootDir = pathlib.Path(common_paths.get_save_location())
+    # resolved the same way as dirSet so is_relative_to compares like with like
+    # (resolve() can turn a mapped drive letter into a UNC path)
+    rootDir = _resolve(common_paths.get_save_location())
     log.debug(f"Original DirSet {list(common_globals.dirSet)}")
     log.debug(f"rootDir {rootDir}")
 
     for ele in common_globals.dirSet:
         output.add(ele)
-        while not os.path.samefile(ele, rootDir) and not os.path.samefile(
-            ele.parent, rootDir
-        ):
-            if ele.parent in output:
-                # We already added all subsequent paths in this tree
-                break
-            if not pathlib.PurePath(ele.parent).is_relative_to(rootDir):
-                # Don't descend if the parent path is outside rootDir such as
-                # when a symlink was used somewhere in the path
-                break
-            common_globals.log.debug(f"Setting Dates ele:{ele} rootDir:{rootDir}")
-            output.add(ele.parent)
-            ele = ele.parent
+        try:
+            while not os.path.samefile(ele, rootDir) and not os.path.samefile(
+                ele.parent, rootDir
+            ):
+                if ele.parent in output:
+                    # We already added all subsequent paths in this tree
+                    break
+                if not pathlib.PurePath(ele.parent).is_relative_to(rootDir):
+                    # Don't descend if the parent path is outside rootDir such as
+                    # when a symlink was used somewhere in the path
+                    break
+                common_globals.log.debug(f"Setting Dates ele:{ele} rootDir:{rootDir}")
+                output.add(ele.parent)
+                ele = ele.parent
+        except OSError as E:
+            # samefile stats both paths, which fails on the same drives
+            log.debug(f"could not walk up from {ele}: {E}")
     log.debug(f"Directories list {output}")
     for ele in output:
-        set_time(ele, dates.get_current_time())
+        try:
+            set_time(ele, dates.get_current_time())
+        except OSError as E:
+            log.debug(f"could not set date on {ele}: {E}")
diff --git a/OF-Scraper-3.14.7/test/unit/test_dir_bookkeeping.py b/OF-Scraper-3.14.7/test/unit/test_dir_bookkeeping.py
new file mode 100644
index 0000000..e3b5058
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_dir_bookkeeping.py
@@ -0,0 +1,92 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import logging
+import pathlib
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.commands.scraper.actions.utils.globals as common_globals
+from ofscraper.commands.scraper.actions.utils import paths
+
+
+@pytest.fixture(autouse=True)
+def empty_dirset(monkeypatch):
+    monkeypatch.setattr(common_globals, "dirSet", set(), raising=False)
+
+
+def test_file_path_records_parent(tmp_path):
+    f = tmp_path / "a.jpg"
+    f.write_bytes(b"x")
+    paths.addGlobalDir(f)
+    assert common_globals.dirSet == {tmp_path.resolve()}
+
+
+def test_dir_path_records_itself(tmp_path):
+    paths.addGlobalDir(tmp_path)
+    assert common_globals.dirSet == {tmp_path.resolve()}
+
+
+def test_str_path_is_one_path(tmp_path):
+    paths.addGlobalDir(str(tmp_path))
+    assert common_globals.dirSet == {tmp_path.resolve()}
+
+
+def test_unresolvable_path_does_not_raise(tmp_path, monkeypatch):
+    # WinError 1005 from Path.resolve on some mapped/virtual drives
+    def boom(self, *a, **k):
+        raise OSError(1005, "The volume does not contain a recognized file system")
+
+    monkeypatch.setattr(pathlib.Path, "resolve", boom)
+    paths.addGlobalDir(tmp_path)
+    paths.addLocalDir(tmp_path / "missing.jpg")
+    assert common_globals.dirSet == {tmp_path.absolute()}
+
+
+@pytest.fixture
+def save_root(tmp_path, monkeypatch):
+    root = tmp_path / "root"
+    (root / "model" / "Posts").mkdir(parents=True)
+    monkeypatch.setattr(paths.common_paths, "get_save_location", lambda: str(root))
+    dated = []
+    monkeypatch.setattr(paths, "set_time", lambda p, t: dated.append(pathlib.Path(p)))
+    monkeypatch.setattr(common_globals, "log", logging.getLogger("test"), raising=False)
+    return root, dated
+
+
+def test_dates_folders_up_to_save_root(save_root):
+    root, dated = save_root
+    paths.addGlobalDir(root / "model" / "Posts")
+    paths.setDirectoriesDate()
+    assert set(dated) == {(root / "model" / "Posts").resolve(), (root / "model").resolve()}
+
+
+def test_unnormalized_save_root_still_walks_up(save_root, monkeypatch):
+    # dirSet holds resolved paths; an unresolved rootDir made is_relative_to
+    # fail and stopped the walk early
+    root, dated = save_root
+    monkeypatch.setattr(
+        paths.common_paths, "get_save_location", lambda: str(root / "model" / "..")
+    )
+    paths.addGlobalDir(root / "model" / "Posts")
+    paths.setDirectoriesDate()
+    assert (root / "model").resolve() in dated
+
+
+def test_samefile_error_does_not_raise(save_root, monkeypatch):
+    root, dated = save_root
+
+    def boom(*a):
+        raise OSError(1005, "The volume does not contain a recognized file system")
+
+    monkeypatch.setattr(paths.os.path, "samefile", boom)
+    paths.addGlobalDir(root / "model" / "Posts")
+    paths.setDirectoriesDate()
+    assert dated == [(root / "model" / "Posts").resolve()]
```
