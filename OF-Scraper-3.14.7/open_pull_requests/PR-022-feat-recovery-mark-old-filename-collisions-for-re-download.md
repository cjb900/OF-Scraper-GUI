# PR #22: feat(recovery): mark old filename collisions for re-download

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/22
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:feat/collision-recovery` → `main`
- **Created:** 2026-10-23T02:46:54Z  ·  **Updated:** 2026-10-23T03:20:10Z
- **Draft:** False
- **Changes:** 10 files, +1077 / -21

## Description

**Upstream issue (follow-up):** datawhores/OF-Scraper#635. Marks files lost to that bug for re-download.

**Depends on #19; merge that first.** Until it's merged, this PR's diff also shows its commit.

* feat(recovery): mark media sharing old download paths for retry

Add an offline preview/apply command with a SQLite backup and transactional download-flag reset. Treat shared paths as suspected loss, preserve all files and other metadata, and document prevention-first recovery. Test rollback, idempotence, case semantics, and duplicate post rows in rollback-journal and WAL modes.

* refactor(recovery): save changed flags in a compact undo file

---------

## Tested
- **Unit:** `test_collision_recovery.py`: 22 passed with the change; against the code before it: the tests can't import (the module is new).
- **Full `test/unit`** on this branch: 92 passed, 1 skipped.
- **Live:** this PR was checked together with the others in this batch on one combined tree, against real accounts: DRM and non-DRM, messages, timeline and purchased. All runs had 0 failures, a repeat run re-downloaded nothing, and every file matched a copy downloaded separately.

Ported from my fork of OF-Scraper. `patch_ofscraper_3.14.7_gui.py` isn't regenerated here.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py`
- `OF-Scraper-3.14.7/ofscraper/commands/recover_collisions.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/alt_download.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/main_download.py`
- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py`
- `OF-Scraper-3.14.7/ofscraper/utils/config/data.py`
- `OF-Scraper-3.14.7/ofscraper/utils/config/schema.py`
- `OF-Scraper-3.14.7/ofscraper/utils/of_env/values/main.py`
- `OF-Scraper-3.14.7/test/unit/test_collision_recovery.py`
- `OF-Scraper-3.14.7/test/unit/test_filename_collisions.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py b/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
index 196e3da..60c08f7 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/metadata/manager.py
@@ -60,6 +60,31 @@ async def _change_metadata(self, c, ele, username, model_id, placeholderObj=None
                 )
                 or {}
             )
+            recorded = self._metadata_recorded_file(prevData)
+            if recorded:
+                # this media's file can be under another name than the
+                # template's when that name held a different file
+                await mark_media_as_downloaded(
+                    ele,
+                    filepath=recorded,
+                    model_id=model_id,
+                    username=username,
+                    downloaded=1,
+                    hashdata=(
+                        hash.get_hash(recorded)
+                        if settings.get_settings().hash
+                        else prevData.get("hash")
+                    ),
+                    size=recorded.stat().st_size,
+                )
+                return (
+                    ele.mediatype
+                    if prevData
+                    != await prev_download_media_data(
+                        ele, model_id=model_id, username=username
+                    )
+                    else "Forced_skipped"
+                )
             await mark_media_as_downloaded(
                 ele,
                 filename=self._metadata_file_helper(placeholderObj, prevData),
@@ -75,6 +100,13 @@ async def _change_metadata(self, c, ele, username, model_id, placeholderObj=None
             )
         return ele.mediatype if effected else "Forced_skipped"
 
+    def _metadata_recorded_file(self, prevData):
+        """In update mode, this media's previously recorded file, if it's still there."""
+        if settings.get_settings().metadata != "update" or not prevData.get("filename"):
+            return None
+        recorded = pathlib.Path(prevData.get("directory") or "", prevData["filename"])
+        return recorded if recorded.is_file() else None
+
     def _metadata_downloaded_helper(self, placeholderObj, prevData):
         if settings.get_settings().metadata == "check":
             return prevData["downloaded"] if prevData else None
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/recover_collisions.py b/OF-Scraper-3.14.7/ofscraper/commands/recover_collisions.py
new file mode 100644
index 0000000..bc5f0bc
--- /dev/null
+++ b/OF-Scraper-3.14.7/ofscraper/commands/recover_collisions.py
@@ -0,0 +1,156 @@
+"""Offline recovery of ambiguous shared download paths; preview unless --apply."""
+
+import argparse
+import json
+import os
+from pathlib import Path
+import sqlite3
+import stat
+import uuid
+from collections import defaultdict
+from contextlib import closing
+
+
+def find_collisions(conn, path_root=None):
+    """Group distinct media by their recorded path or existing file identity."""
+    groups = defaultdict(list)
+    rows = conn.execute(
+        "SELECT model_id, media_id, directory, filename, downloaded FROM medias "
+        "WHERE media_id IS NOT NULL AND filename IS NOT NULL AND filename != ''"
+    )
+    for model, media, directory, filename, downloaded in rows:
+        path = Path(directory or "", filename)
+        if not path.is_absolute():
+            if path_root is None:
+                raise ValueError("Relative recorded paths require --path-root (the original working directory)")
+            path = Path(path_root) / path
+        path = Path(os.path.abspath(path))
+        try:
+            info = path.stat()
+        except FileNotFoundError:
+            # Preserve case when there is no file to establish filesystem identity.
+            key = ("path", str(path))
+        else:
+            if not stat.S_ISREG(info.st_mode):
+                continue
+            key = ("file", info.st_dev, info.st_ino) if info.st_ino else ("path", str(path))
+        groups[key].append((model, media, str(path), downloaded))
+    return [
+        rows for rows in groups.values()
+        if len({(r[0], r[1]) for r in rows}) > 1
+    ]
+
+
+def recover(database, apply=False, path_root=None):
+    """Record changed rows in an undo file, then reset their download flags."""
+    database = Path(database).resolve(strict=True)
+    uri = database.as_uri()
+    mode = "rw" if apply else "ro"
+    with closing(sqlite3.connect(f"{uri}?mode={mode}", uri=True)) as conn:
+        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
+        undo_file = None
+        undo_created = False
+        try:
+            groups = find_collisions(conn, path_root)
+            owners = {(r[0], r[1]) for group in groups for r in group}
+            pending = [
+                owner for owner in owners
+                if conn.execute(
+                    "SELECT 1 FROM medias WHERE model_id IS ? AND media_id = ? "
+                    "AND downloaded = 1 LIMIT 1", owner
+                ).fetchone()
+            ]
+            result = {
+                "groups": [
+                    {"paths": sorted({r[2] for r in group}),
+                     "media": [{"model_id": model, "media_id": media}
+                               for model, media in sorted(
+                                   {(r[0], r[1]) for r in group}, key=str)]}
+                    for group in groups
+                ],
+                "media_to_mark": len(pending),
+                "rows_marked": 0,
+                "undo_file": None,
+                "applied": apply,
+            }
+            if apply and pending:
+                changed_rows = []
+                for owner in pending:
+                    changed_rows.extend(conn.execute(
+                        "SELECT id, model_id, media_id, post_id, downloaded FROM medias "
+                        "WHERE model_id IS ? AND media_id = ? AND downloaded = 1", owner
+                    ).fetchall())
+                undo_file = database.with_name(
+                    f"{database.name}.collision-undo-{uuid.uuid4().hex}.json"
+                )
+                # Persist the small undo record before committing any flag changes.
+                with undo_file.open("x", encoding="utf-8") as output:
+                    undo_created = True
+                    json.dump({"version": 1, "database": str(database),
+                               "rows": sorted(changed_rows)}, output)
+                    output.flush()
+                    os.fsync(output.fileno())
+                result["undo_file"] = str(undo_file)
+                for owner in pending:
+                    result["rows_marked"] += conn.execute(
+                        "UPDATE medias SET downloaded = 0 "
+                        "WHERE model_id IS ? AND media_id = ? AND downloaded = 1",
+                        owner,
+                    ).rowcount
+            conn.commit()
+            return result
+        except BaseException:
+            conn.rollback()
+            if undo_created:
+                undo_file.unlink(missing_ok=True)
+            raise
+
+
+def undo(database, undo_file, apply=False):
+    """Restore recorded flags only for matching rows that are still pending."""
+    database = Path(database).resolve(strict=True)
+    record = json.loads(Path(undo_file).read_text(encoding="utf-8"))
+    if record.get("version") != 1 or record.get("database") != str(database):
+        raise ValueError("Undo file does not belong to this database")
+    rows = record.get("rows")
+    if not isinstance(rows, list) or any(
+        not isinstance(row, list) or len(row) != 5 or row[4] != 1 for row in rows
+    ):
+        raise ValueError("Invalid undo rows")
+    mode = "rw" if apply else "ro"
+    with closing(sqlite3.connect(f"{database.as_uri()}?mode={mode}", uri=True)) as conn:
+        with conn:
+            conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
+            count = 0
+            for row_id, model, media, post, previous in rows:
+                params = (row_id, model, media, post)
+                condition = "id = ? AND model_id IS ? AND media_id = ? AND post_id = ? AND downloaded = 0"
+                if apply:
+                    count += conn.execute(
+                        f"UPDATE medias SET downloaded = ? WHERE {condition}",
+                        (previous, *params),
+                    ).rowcount
+                else:
+                    count += conn.execute(
+                        f"SELECT COUNT(*) FROM medias WHERE {condition}", params
+                    ).fetchone()[0]
+            return {"applied": apply, "rows_to_restore": count}
+
+
+def main(argv=None):
+    parser = argparse.ArgumentParser(description=__doc__)
+    parser.add_argument("database", type=Path, help="One model's user_data.db")
+    parser.add_argument("--apply", action="store_true", help="Apply the previewed recovery or undo operation")
+    parser.add_argument("--undo", type=Path, help="Preview restoring flags from a recovery undo file")
+    parser.add_argument("--path-root", type=Path, help="Original working directory for relative recorded paths")
+    args = parser.parse_args(argv)
+    try:
+        result = (undo(args.database, args.undo, apply=args.apply) if args.undo
+                  else recover(args.database, apply=args.apply, path_root=args.path_root))
+    except (OSError, sqlite3.Error, ValueError) as error:
+        parser.exit(1, f"Recovery failed: {error}\n")
+    print(json.dumps(result, indent=2))
+
+
+if __name__ == "__main__":
+    main()
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/alt_download.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/alt_download.py
index ab12f1e..66342ab 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/alt_download.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/alt_download.py
@@ -436,8 +436,9 @@ async def _handle_result_alt(
             f"Moving intermediate path {temp_path} to {alt_path_to_file}"
         )
 
-        # Thread executor for disk I/O move operation
-        await asyncio.get_event_loop().run_in_executor(
+        # Thread executor for disk I/O move operation; the file can end up
+        # under another name if a different file already has this one
+        final_path = await asyncio.get_event_loop().run_in_executor(
             common_globals.thread,
             partial(
                 common_paths.moveHelper,
@@ -447,7 +448,7 @@ async def _handle_result_alt(
             ),
         )
 
-        (common_paths.addGlobalDir(sharedPlaceholderObj.filedir))
+        (common_paths.addGlobalDir(final_path.parent))
 
         if ele.postdate:
             newDate = dates.convert_local_time(ele.postdate)
@@ -458,7 +459,7 @@ async def _handle_result_alt(
                 common_globals.thread,
                 partial(
                     common_paths.set_time,
-                    alt_path_to_file,
+                    final_path,
                     newDate,
                 ),
             )
@@ -466,21 +467,21 @@ async def _handle_result_alt(
         if ele.id:
             await mark_media_as_downloaded(
                 ele,
-                filepath=alt_path_to_file,
+                filepath=final_path,
                 model_id=model_id,
                 username=username,
                 downloaded=True,
-                hashdata=await common.get_hash(sharedPlaceholderObj),
-                size=sharedPlaceholderObj.size,
+                hashdata=await common.get_hash(final_path),
+                size=final_path.stat().st_size,
             )
-        ele.add_filepath(alt_path_to_file)
+        ele.add_filepath(final_path)
 
-        await self._after_download_script(alt_path_to_file)
+        await self._after_download_script(final_path)
 
         try:
             from ofscraper.plugins.manager import plugin_manager
 
-            _final = sharedPlaceholderObj.trunicated_filepath
+            _final = final_path
             _final_s = str(pathlib.Path(_final)) if _final is not None else _final
             _n = len(plugin_manager.plugins)
             _name = pathlib.Path(_final_s).name if _final_s else "?"
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/main_download.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/main_download.py
index 99165ca..7baff1c 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/main_download.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/managers/main_download.py
@@ -346,13 +346,14 @@ async def _handle_result_main(self, result, ele, username, model_id):
             f"{common_logs.get_medialog(ele)} renaming {pathlib.Path(temp).absolute()} -> {path_to_file}"
         )
 
-        # 3. Move the verified file to final path
-        await asyncio.get_event_loop().run_in_executor(
+        # 3. Move the verified file to final path; it can end up under another
+        # name if a different file already has this one
+        path_to_file = await asyncio.get_event_loop().run_in_executor(
             common_globals.thread,
             partial(common_paths.moveHelper, temp, path_to_file, ele),
         )
 
-        (common_paths.addGlobalDir(placeholderObj.filedir))
+        (common_paths.addGlobalDir(path_to_file.parent))
 
         # 4. Set File Dates
         if ele.postdate:
@@ -371,11 +372,11 @@ async def _handle_result_main(self, result, ele, username, model_id):
                 username=username,
                 downloaded=True,
                 hashdata=await common.get_hash(path_to_file),
-                size=placeholderObj.size,
+                size=path_to_file.stat().st_size,
             )
 
         await set_profile_cache(ele, common_globals.thread)
-        ele.add_filepath(placeholderObj.trunicated_filepath)
+        ele.add_filepath(path_to_file)
 
         # 6. Run Post-Download Scripts
         await self._after_download_script(path_to_file)
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
index c4a3bf5..afdebc5 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/utils/paths.py
@@ -2,12 +2,20 @@
 import os
 import pathlib
 import platform
+import errno
 import shutil
+import tempfile
+import time
 from collections.abc import Iterable
 
+import xxhash
+
 import ofscraper.commands.scraper.actions.utils.globals as common_globals
+import ofscraper.utils.config.data as config_data
 import ofscraper.utils.dates as dates
+import ofscraper.utils.of_env.of_env as of_env
 import ofscraper.utils.paths.common as common_paths
+import ofscraper.utils.paths.paths as path_utils
 from ofscraper.commands.scraper.actions.utils.log import get_medialog
 
 try:
@@ -15,20 +23,160 @@
 except ModuleNotFoundError:
     pass
 
+MAX_CANDIDATES = 1000
+STALE_STAGING_SECONDS = 24 * 60 * 60
+
 
 def moveHelper(temp, path_to_file, ele, log_=None):
-    if not path_to_file.exists():
-        shutil.move(temp, path_to_file)
-    elif (
+    """
+    Move a finished download into place and return the path it ended up at.
+
+    A filename template (e.g. one built on {text}) can give different media
+    the same path. A free name is reserved by creating it exclusively
+    (O_EXCL), which only one download can do, across threads and processes,
+    and then replaced with the download. An existing nonempty file with
+    identical content is this download already, so it's kept. Anything else at that
+    name, including another download's reservation, is left alone and the
+    download goes to name_<media_id>, then name_<media_id>_2 and so on. The
+    filesystem decides whether a name is taken, so its own case rules apply.
+    Callers must record the returned path. filename_collision "overwrite"
+    keeps the old behaviour: the larger file wins.
+    """
+    log_ = log_ or logging.getLogger("shared")
+    path_to_file = pathlib.Path(path_to_file)
+    if str(config_data.get_filename_collision()).lower() == "overwrite":
+        return _move_overwrite(temp, path_to_file, ele, log_)
+    for candidate in _candidates(path_to_file, ele.id):
+        if _reserve(candidate):
+            _replace_reserved(temp, candidate)
+            break
+        if _same_content(temp, candidate):
+            pathlib.Path(temp).unlink(missing_ok=True)
+            break
+    else:
+        raise RuntimeError(f"{get_medialog(ele)} no free path found for {path_to_file}")
+    if candidate != path_to_file:
+        log_.debug(
+            f"{get_medialog(ele)} {path_to_file.name} holds another file; saved as {candidate.name}"
+        )
+    return candidate
+
+
+def _reserve(path):
+    """Create path if nothing is there; False if something already is."""
+    try:
+        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0))
+    except FileExistsError:
+        return False
+    os.close(fd)
+    return True
+
+
+def _replace_reserved(temp, path):
+    try:
+        _replace(temp, path)
+    except OSError as E:
+        # Copy privately on the destination drive, then publish atomically.
+        # Other downloads must never hash a partially copied destination.
+        if E.errno == errno.EXDEV or getattr(E, "winerror", None) == 17:
+            staged = None
+            _sweep_staging(pathlib.Path(path).parent)
+            try:
+                fd, staged = tempfile.mkstemp(
+                    prefix=".ofs-move-", dir=pathlib.Path(path).parent
+                )
+                os.close(fd)
+                # Copy times only once published: an old .part's mtime on the
+                # staging file would let another download's sweep remove it.
+                shutil.copyfile(temp, staged)
+                _replace(staged, path)
+            except BaseException:
+                pathlib.Path(path).unlink(missing_ok=True)
+                raise
+            finally:
+                if staged is not None:
+                    pathlib.Path(staged).unlink(missing_ok=True)
+            shutil.copystat(temp, path)
+            pathlib.Path(temp).unlink(missing_ok=True)
+        else:
+            pathlib.Path(path).unlink(missing_ok=True)
+            raise
+
+
+def _sweep_staging(directory):
+    # A hard kill mid-copy leaves a staging file behind. A live copy is
+    # seconds or minutes old, so anything a day old is abandoned.
+    cutoff = time.time() - STALE_STAGING_SECONDS
+    for leftover in directory.glob(".ofs-move-*"):
+        try:
+            if leftover.stat().st_mtime < cutoff:
+                leftover.unlink()
+        except OSError:
+            pass
+
+
+def _replace(source, destination):
+    # Windows can briefly deny replacement while a competing exclusive-open
+    # or stat checks the reservation. Keep owning it while retrying.
+    for attempt in range(6):
+        try:
+            os.replace(source, destination)
+            return
+        except PermissionError as error:
+            if getattr(error, "winerror", None) not in (5, 32, 33) or attempt == 5:
+                raise
+            time.sleep(0.02 * (attempt + 1))
+
+
+def _move_overwrite(temp, path_to_file, ele, log_):
+    if not path_to_file.exists() or (
         pathlib.Path(temp).absolute().stat().st_size
-        >= pathlib.Path(path_to_file).absolute().stat().st_size
+        >= path_to_file.absolute().stat().st_size
     ):
         shutil.move(temp, path_to_file)
     else:
         pathlib.Path(temp).unlink(missing_ok=True)
-        log_ = log_ or logging.getLogger("shared")
         log_.debug(f"{get_medialog(ele)} smaller then previous file")
-    # set variables based on parent process
+    return path_to_file
+
+
+def with_media_id(path, media_id, n=1):
+    path = pathlib.Path(path)
+    tail = f"_{media_id}" if n == 1 else f"_{media_id}_{n}"
+    return path.with_name(f"{path.stem}{tail}{path.suffix}")
+
+
+def _candidates(path, media_id):
+    yield path
+    for n in range(1, MAX_CANDIDATES):
+        # a trailing _<digits> survives truncation, but check the result anyway
+        yield pathlib.Path(path_utils.truncate(with_media_id(path, media_id, n)))
+
+
+def _same_content(a, b):
+    a, b = pathlib.Path(a), pathlib.Path(b)
+    try:
+        # Empty files may be reservations, so never deduplicate against them.
+        if (
+            not b.is_file()
+            or not b.stat().st_size
+            or a.stat().st_size != b.stat().st_size
+        ):
+            return False
+        return _file_hash(a) == _file_hash(b)
+    except FileNotFoundError:
+        # A competing failed move can remove its reservation during this check.
+        return False
+
+
+def _file_hash(path):
+    # not hash.get_hash: that caches by path, and these files are replaced
+    hasher = xxhash.xxh128()
+    size = of_env.getattr("BUF_SIZE")
+    with open(path, "rb") as f:
+        for block in iter(lambda: f.read(size), b""):
+            hasher.update(block)
+    return hasher.hexdigest()
 
 
 def addGlobalDir(path):
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/config/data.py b/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
index ec16473..c1c46a6 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/config/data.py
@@ -815,6 +815,16 @@ def get_TempDir(config=None):
     return val if val is not None else of_env.getattr("TEMP_FOLDER_DEFAULT")
 
 
+@wrapper.config_reader
+def get_filename_collision(config=None):
+    if config is False:
+        return of_env.getattr("FILENAME_COLLISION_DEFAULT")
+    val = config.get("filename_collision") or config.get("file_options", {}).get(
+        "filename_collision"
+    )
+    return val if val is not None else of_env.getattr("FILENAME_COLLISION_DEFAULT")
+
+
 @wrapper.config_reader
 def get_truncation(config=None):
     if config is False:
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/config/schema.py b/OF-Scraper-3.14.7/ofscraper/utils/config/schema.py
index 2f67192..f7d1afd 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/config/schema.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/config/schema.py
@@ -33,6 +33,7 @@ def get_current_config_schema(config: dict = None) -> dict:
             "image_extension": data.get_image_extension(config=config),
             "video_extension": data.get_video_extension(config=config),
             "audio_extension": data.get_audio_extension(config=config),
+            "filename_collision": data.get_filename_collision(config=config),
         },
         "download_options": {
             "filter": data.get_filter(config=config),
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/main.py b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/main.py
index 3a44fdd..5308003 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/main.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/of_env/values/main.py
@@ -115,6 +115,14 @@ def load_main_config():
         "OFSC_TRUNCATION_DEFAULT", "True"
     ).lower() in ("true", "1")
 
+    # FILENAME_COLLISION_DEFAULT: What to do when a download's path is already
+    # taken by a different media. "media_id" appends _<media_id>; "overwrite"
+    # keeps the old behaviour (one file replaces the other).
+    # Default: media_id
+    config["FILENAME_COLLISION_DEFAULT"] = os.getenv(
+        "OFSC_FILENAME_COLLISION_DEFAULT", "media_id"
+    )
+
     # MAX_COUNT_DEFAULT: Default maximum count for certain operations.
     # Default: 0 (no limit)
     config["MAX_COUNT_DEFAULT"] = int(os.getenv("OFSC_MAX_COUNT_DEFAULT", "0"))
diff --git a/OF-Scraper-3.14.7/test/unit/test_collision_recovery.py b/OF-Scraper-3.14.7/test/unit/test_collision_recovery.py
new file mode 100644
index 0000000..abcbdd9
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_collision_recovery.py
@@ -0,0 +1,205 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import json
+import sqlite3
+import subprocess
+import sys
+from pathlib import Path
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+from ofscraper.commands.recover_collisions import recover, undo
+from ofscraper.db.operations_.media import mediaCreate
+
+
+@pytest.fixture(params=["DELETE", "WAL"])
+def database(tmp_path, request):
+    db = tmp_path / "user_data.db"
+    with sqlite3.connect(db) as conn:
+        conn.execute(f"PRAGMA journal_mode={request.param}")
+        conn.execute(mediaCreate)
+    return db
+
+
+def add(db, media, path, post=None, downloaded=1):
+    with sqlite3.connect(db) as conn:
+        conn.execute(
+            "INSERT INTO medias (media_id,model_id,post_id,directory,filename,downloaded,size,hash) "
+            "VALUES (?,10,?,?,?,?,100,'old-hash')",
+            (media, post or media, str(path.parent), path.name, downloaded),
+        )
+
+
+def rows(db):
+    with sqlite3.connect(db) as conn:
+        return conn.execute("SELECT * FROM medias ORDER BY id").fetchall()
+
+
+def flags(db):
+    with sqlite3.connect(db) as conn:
+        return conn.execute("SELECT media_id,downloaded FROM medias ORDER BY id").fetchall()
+
+
+def test_preview_and_apply_only_reset_ambiguous_media(database, tmp_path):
+    shared = tmp_path / "shared.jpg"
+    shared.write_bytes(b"surviving content")
+    add(database, 1, shared)
+    add(database, 2, shared)
+    add(database, 2, tmp_path / "other-post.jpg", post=20)
+    add(database, 3, tmp_path / "unshared-missing.jpg")
+    original = rows(database)
+    assert recover(database)["media_to_mark"] == 2
+    assert rows(database) == original
+    assert not list(tmp_path.glob("*.collision-undo-*"))
+    result = recover(database, apply=True)
+    assert result["rows_marked"] == 3
+    record = json.loads(Path(result["undo_file"]).read_text())
+    assert len(record["rows"]) == 3
+    assert all(len(row) == 5 and row[-1] == 1 for row in record["rows"])
+    assert not list(tmp_path.glob("*.sqlite"))
+    assert flags(database) == [(1, 0), (2, 0), (2, 0), (3, 1)]
+    with sqlite3.connect(database) as conn:
+        columns = [r[1] for r in conn.execute("PRAGMA table_info(medias)")]
+    index = columns.index("downloaded")
+    for old, new in zip(original, rows(database)):
+        assert old[:index] + old[index + 1:] == new[:index] + new[index + 1:]
+    assert shared.read_bytes() == b"surviving content"
+    again = recover(database, apply=True)
+    assert again["rows_marked"] == 0 and again["undo_file"] is None
+
+
+def test_same_media_in_two_posts_is_not_a_collision(database, tmp_path):
+    add(database, 1, tmp_path / "same.jpg", post=1)
+    add(database, 1, tmp_path / "same.jpg", post=2)
+    assert recover(database, apply=True)["groups"] == []
+    assert flags(database) == [(1, 1), (1, 1)]
+
+
+def test_missing_shared_path_and_pending_owner(database, tmp_path):
+    add(database, 1, tmp_path / "missing.jpg", downloaded=0)
+    add(database, 2, tmp_path / "missing.jpg")
+    assert recover(database, apply=True)["media_to_mark"] == 1
+    assert flags(database) == [(1, 0), (2, 0)]
+
+
+def test_case_aliases_follow_real_filesystem(database, tmp_path):
+    upper, lower = tmp_path / "File.JPG", tmp_path / "file.jpg"
+    upper.write_bytes(b"one")
+    aliases = lower.exists()
+    if not aliases:
+        lower.write_bytes(b"two")
+    add(database, 1, upper)
+    add(database, 2, lower)
+    assert recover(database)["media_to_mark"] == (2 if aliases else 0)
+
+
+def test_windows_sensitive_directory_keeps_distinct_files(database, tmp_path):
+    if sys.platform != "win32":
+        pytest.skip("Windows per-directory case sensitivity")
+    folder = tmp_path / "cs"
+    folder.mkdir()
+    command = subprocess.run(
+        ["fsutil", "file", "setCaseSensitiveInfo", str(folder), "enable"],
+        capture_output=True,
+    )
+    if command.returncode:
+        pytest.skip("Case-sensitive directories unavailable")
+    for media, name in [(1, "A.jpg"), (2, "a.jpg")]:
+        path = folder / name
+        path.write_bytes(str(media).encode())
+        add(database, media, path)
+    assert recover(database)["groups"] == []
+
+
+def test_relative_paths_require_explicit_root(database, tmp_path):
+    add(database, 1, Path("relative.jpg"))
+    add(database, 2, Path("relative.jpg"))
+    with pytest.raises(ValueError, match="path-root"):
+        recover(database, apply=True)
+    assert flags(database) == [(1, 1), (2, 1)]
+    assert recover(database, path_root=tmp_path)["media_to_mark"] == 2
+
+
+def test_apply_rolls_back_all_flags_when_update_fails(database, tmp_path):
+    add(database, 1, tmp_path / "same.jpg")
+    add(database, 2, tmp_path / "same.jpg")
+    with sqlite3.connect(database) as conn:
+        conn.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON medias "
+                     "WHEN NEW.media_id=2 BEGIN SELECT RAISE(ABORT,'test failure'); END")
+    with pytest.raises(sqlite3.IntegrityError):
+        recover(database, apply=True)
+    assert flags(database) == [(1, 1), (2, 1)]
+    assert not list(tmp_path.glob("*.collision-undo-*"))
+
+
+def test_cli_defaults_to_preview_and_never_creates_missing_db(database, tmp_path):
+    add(database, 1, tmp_path / "same.jpg")
+    add(database, 2, tmp_path / "same.jpg")
+    command = [sys.executable, "-m", "ofscraper.commands.recover_collisions"]
+    result = subprocess.run(command + [str(database)], capture_output=True, text=True)
+    assert result.returncode == 0, result.stderr
+    assert json.loads(result.stdout)["applied"] is False
+    assert flags(database) == [(1, 1), (2, 1)]
+    applied = subprocess.run(command + [str(database), "--apply"], capture_output=True, text=True)
+    assert applied.returncode == 0, applied.stderr
+    undo_path = json.loads(applied.stdout)["undo_file"]
+    restored = subprocess.run(
+        command + [str(database), "--undo", undo_path, "--apply"],
+        capture_output=True, text=True,
+    )
+    assert restored.returncode == 0, restored.stderr
+    assert flags(database) == [(1, 1), (2, 1)]
+    missing = tmp_path / "absent.db"
+    result = subprocess.run(command + [str(missing), "--apply"], capture_output=True)
+    assert result.returncode != 0 and not missing.exists()
+
+
+def test_undo_file_failure_does_not_change_flags(database, tmp_path, monkeypatch):
+    add(database, 1, tmp_path / "same.jpg")
+    add(database, 2, tmp_path / "same.jpg")
+    original = Path.open
+
+    def deny_undo(path, *args, **kwargs):
+        if ".collision-undo-" in path.name:
+            raise PermissionError("undo file denied")
+        return original(path, *args, **kwargs)
+
+    monkeypatch.setattr(Path, "open", deny_undo)
+    with pytest.raises(PermissionError, match="undo file denied"):
+        recover(database, apply=True)
+    assert flags(database) == [(1, 1), (2, 1)]
+
+
+def test_undo_restores_only_changed_rows_and_is_repeatable(database, tmp_path):
+    add(database, 1, tmp_path / "same.jpg")
+    add(database, 2, tmp_path / "same.jpg")
+    add(database, 3, tmp_path / "other.jpg", downloaded=0)
+    original = rows(database)
+    result = recover(database, apply=True)
+    assert undo(database, result["undo_file"])["rows_to_restore"] == 2
+    assert flags(database) == [(1, 0), (2, 0), (3, 0)]
+    assert undo(database, result["undo_file"], apply=True)["rows_to_restore"] == 2
+    assert rows(database) == original
+    assert undo(database, result["undo_file"], apply=True)["rows_to_restore"] == 0
+
+
+def test_undo_checks_database_and_row_identity(database, tmp_path):
+    add(database, 1, tmp_path / "same.jpg")
+    add(database, 2, tmp_path / "same.jpg")
+    result = recover(database, apply=True)
+    other = tmp_path / "other.db"
+    other.touch()
+    with pytest.raises(ValueError, match="does not belong"):
+        undo(other, result["undo_file"], apply=True)
+    with sqlite3.connect(database) as conn:
+        conn.execute("UPDATE medias SET media_id=99 WHERE media_id=1")
+    assert undo(database, result["undo_file"], apply=True)["rows_to_restore"] == 1
+    assert flags(database) == [(99, 0), (2, 1)]
diff --git a/OF-Scraper-3.14.7/test/unit/test_filename_collisions.py b/OF-Scraper-3.14.7/test/unit/test_filename_collisions.py
new file mode 100644
index 0000000..24d1b19
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_filename_collisions.py
@@ -0,0 +1,494 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import subprocess
+import sys
+import threading
+from types import SimpleNamespace
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.commands.scraper.actions.utils.paths as action_paths
+import ofscraper.utils.paths.paths as path_utils
+
+
+def _media(media_id):
+    return SimpleNamespace(id=media_id, post_id=1, model_id=10, username="model")
+
+
+@pytest.fixture(autouse=True)
+def collision_mode(monkeypatch):
+    mode = {"value": "media_id"}
+    monkeypatch.setattr(
+        action_paths.config_data, "get_filename_collision", lambda: mode["value"]
+    )
+    return mode
+
+
+def _download(tmp_path, data, name="dl.part"):
+    temp = tmp_path / name
+    temp.write_bytes(data)
+    return temp
+
+
+def _move(tmp_path, target, media_id, data):
+    return action_paths.moveHelper(_download(tmp_path, data), target, _media(media_id))
+
+
+def test_free_path_is_used(tmp_path):
+    target = tmp_path / "caption.jpg"
+    assert _move(tmp_path, target, 1, b"media 1") == target
+    assert target.read_bytes() == b"media 1"
+
+
+def test_different_file_keeps_its_name(tmp_path):
+    target = tmp_path / "caption.jpg"
+    _move(tmp_path, target, 1, b"media 1")
+    got = _move(tmp_path, target, 2, b"media 2, larger than media 1")
+    assert got == tmp_path / "caption_2.jpg"
+    assert target.read_bytes() == b"media 1"
+    assert got.read_bytes() == b"media 2, larger than media 1"
+
+
+def test_identical_file_is_this_download(tmp_path):
+    # a re-download (e.g. --force-all) of the same content
+    target = tmp_path / "caption.jpg"
+    _move(tmp_path, target, 1, b"media 1")
+    temp = _download(tmp_path, b"media 1")
+    assert action_paths.moveHelper(temp, target, _media(1)) == target
+    assert not temp.exists()
+    assert sorted(p.name for p in tmp_path.iterdir()) == ["caption.jpg"]
+
+
+def test_stable_across_runs(tmp_path):
+    target = tmp_path / "caption.jpg"
+    first = [_move(tmp_path, target, 1, b"media 1"), _move(tmp_path, target, 2, b"media 2")]
+    again = [_move(tmp_path, target, 2, b"media 2"), _move(tmp_path, target, 1, b"media 1")]
+    assert again == first[::-1]
+    assert len(list(tmp_path.iterdir())) == 2
+
+
+def test_fallback_holding_another_file_is_skipped(tmp_path):
+    # media 3's own file sits at caption_2.jpg, media 2's first fallback
+    (tmp_path / "caption.jpg").write_bytes(b"media 1")
+    (tmp_path / "caption_2.jpg").write_bytes(b"media 3")
+    got = _move(tmp_path, tmp_path / "caption.jpg", 2, b"media 2, larger than media 3")
+    assert got == tmp_path / "caption_2_2.jpg"
+    assert (tmp_path / "caption_2.jpg").read_bytes() == b"media 3"
+
+
+def test_existing_different_content_is_preserved(tmp_path):
+    # Prevention preserves an existing file without interpreting database ownership.
+    target = tmp_path / "caption.jpg"
+    target.write_bytes(b"media 9, the larger image")
+    assert _move(tmp_path, target, 9, b"media 9, the larger image") == target
+    got = _move(tmp_path, target, 5, b"media 5")
+    assert got == tmp_path / "caption_5.jpg" and got.read_bytes() == b"media 5"
+
+
+def test_concurrent_moves_to_one_name_keep_every_file(tmp_path):
+    target = tmp_path / "caption.jpg"
+    temps = [_download(tmp_path, f"media {i}".encode(), f"{i}.part") for i in range(1, 9)]
+    results = [None] * 8
+
+    def move(i):
+        results[i] = action_paths.moveHelper(temps[i], target, _media(i + 1))
+
+    threads = [threading.Thread(target=move, args=(i,)) for i in range(8)]
+    for t in threads:
+        t.start()
+    for t in threads:
+        t.join()
+    assert len(set(results)) == 8
+    assert sorted(p.read_bytes() for p in results) == sorted(f"media {i}".encode() for i in range(1, 9))
+
+
+def test_overwrite_setting_keeps_old_behaviour(tmp_path, collision_mode):
+    collision_mode["value"] = "overwrite"
+    target = tmp_path / "caption.jpg"
+    _move(tmp_path, target, 1, b"media 1")
+    assert _move(tmp_path, target, 2, b"media 2, larger") == target
+    assert target.read_bytes() == b"media 2, larger"
+    # and the smaller download is dropped, as before
+    assert _move(tmp_path, target, 3, b"tiny") == target
+    assert target.read_bytes() == b"media 2, larger"
+
+
+def test_suffix_survives_truncation(tmp_path):
+    long = tmp_path / ("x" * 400 + ".mp4")
+    out = path_utils.truncate(action_paths.with_media_id(long, 3784819492))
+    assert out.name.endswith("_3784819492.mp4")
+
+
+def test_case_variant_follows_the_filesystem(tmp_path):
+    existing = tmp_path / "CaseName.JPG"
+    existing.write_bytes(b"media 1")
+    same_file = (tmp_path / "casename.jpg").exists()
+    got = _move(tmp_path, tmp_path / "casename.jpg", 2, b"media 2")
+    assert got == (tmp_path / "casename_2.jpg" if same_file else tmp_path / "casename.jpg")
+    assert existing.read_bytes() == b"media 1"
+
+
+@pytest.fixture
+def case_sensitive_dir(tmp_path):
+    """A Windows directory with per-directory case sensitivity (as WSL uses)."""
+    if sys.platform != "win32":
+        pytest.skip("per-directory case sensitivity is a Windows feature")
+    d = tmp_path / "cs"
+    d.mkdir()
+    r = subprocess.run(
+        ["fsutil", "file", "setCaseSensitiveInfo", str(d), "enable"],
+        capture_output=True, text=True,
+    )
+    if r.returncode != 0:
+        pytest.skip(f"can't enable case sensitivity here: {r.stdout or r.stderr}")
+    return d
+
+
+@pytest.mark.parametrize("populated", [False, True])
+def test_case_sensitive_windows_dir(case_sensitive_dir, tmp_path, populated):
+    # distinct names in a case-sensitive directory, empty or not
+    if populated:
+        (case_sensitive_dir / "other.txt").write_bytes(b"x")
+    upper, lower = case_sensitive_dir / "A.jpg", case_sensitive_dir / "a.jpg"
+    assert _move(tmp_path, upper, 1, b"media 1") == upper
+    assert _move(tmp_path, lower, 2, b"media 2") == lower
+    assert not upper.samefile(lower)
+    # next run: same names
+    assert _move(tmp_path, lower, 2, b"media 2") == lower
+    assert _move(tmp_path, upper, 1, b"media 1") == upper
+    assert not (case_sensitive_dir / "a_2.jpg").exists()
+
+
+def test_metadata_update_keeps_a_recorded_file_under_another_name(tmp_path, monkeypatch):
+    # media 2 was saved as caption_2.jpg because caption.jpg held media 1;
+    # update mode must not re-point it at caption.jpg
+    import ofscraper.commands.metadata.manager as metadata_manager
+
+    (tmp_path / "caption.jpg").write_bytes(b"media 1")
+    (tmp_path / "caption_2.jpg").write_bytes(b"media 2")
+    prev = {"directory": str(tmp_path), "filename": "caption_2.jpg"}
+    manager = metadata_manager.MetaDataManager()
+    for mode, expected in [("update", tmp_path / "caption_2.jpg"), ("check", None)]:
+        monkeypatch.setattr(metadata_manager.settings, "get_settings", lambda: SimpleNamespace(metadata=mode))
+        assert manager._metadata_recorded_file(prev) == expected
+    monkeypatch.setattr(metadata_manager.settings, "get_settings", lambda: SimpleNamespace(metadata="update"))
+    assert manager._metadata_recorded_file({"directory": str(tmp_path), "filename": "gone.jpg"}) is None
+
+
+_MOVE_IN_PROCESS = """
+import os, sys
+from types import SimpleNamespace
+temp, target, media_id, gate = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # import order, as in conftest
+import ofscraper.commands.scraper.actions.utils.paths as ap
+ap.config_data.get_filename_collision = lambda: "media_id"
+open(gate + f".ready{media_id}", "w").close()
+while not os.path.exists(gate):  # released together
+    pass
+media = SimpleNamespace(id=media_id, post_id=1, model_id=10, username="model")
+print(ap.moveHelper(temp, target, media))
+"""
+
+
+def test_concurrent_processes_reserve_distinct_names(tmp_path):
+    # reservation has to hold across processes, not just threads
+    import os
+    import pathlib
+    import time
+
+    target = tmp_path / "caption.jpg"
+    temps = [_download(tmp_path, f"media {i}".encode(), f"{i}.part") for i in range(1, 7)]
+    repo = pathlib.Path(__file__).resolve().parents[2]
+    env = {**os.environ, "PYTHONPATH": str(repo)}
+    gate = tmp_path / "go"
+    procs = [
+        subprocess.Popen(
+            [sys.executable, "-c", _MOVE_IN_PROCESS, str(t), str(target), str(i + 1), str(gate)],
+            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env, cwd=repo,
+        )
+        for i, t in enumerate(temps)
+    ]
+    deadline = time.time() + 90
+    while len(list(tmp_path.glob("go.ready*"))) < len(procs):
+        assert time.time() < deadline and all(p.poll() is None for p in procs), "a worker failed to start"
+        time.sleep(0.05)
+    gate.write_bytes(b"")
+    results = []
+    for p in procs:
+        out, err = p.communicate(timeout=90)
+        assert p.returncode == 0, err[-2000:]
+        results.append(out.strip().splitlines()[-1])
+    assert len(set(results)) == 6
+    contents = sorted(open(r, "rb").read() for r in results)
+    assert contents == sorted(f"media {i}".encode() for i in range(1, 7))
+
+
+def test_another_downloads_reservation_is_left_alone(tmp_path):
+    target = tmp_path / "caption.jpg"
+    target.write_bytes(b"")  # reserved by another download, not filled yet
+    got = _move(tmp_path, target, 2, b"media 2")
+    assert got == tmp_path / "caption_2.jpg"
+    assert target.read_bytes() == b""
+
+
+def test_temp_on_another_drive_is_copied(tmp_path, monkeypatch):
+    import errno
+    import os
+
+    replace = os.replace
+    temp = _download(tmp_path, b"media 1")
+
+    def cross_device(src, dst):
+        if src == temp:
+            raise OSError(errno.EXDEV, "cross-device link")
+        return replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", cross_device)
+    got = action_paths.moveHelper(temp, tmp_path / "caption.jpg", _media(1))
+    assert got.read_bytes() == b"media 1" and not temp.exists()
+
+
+def test_cross_drive_move_sweeps_abandoned_staging_files(tmp_path, monkeypatch):
+    import errno
+    import os
+    import time
+
+    stale = tmp_path / ".ofs-move-killed"
+    fresh = tmp_path / ".ofs-move-in-progress"
+    stale.write_bytes(b"partial")
+    fresh.write_bytes(b"partial")
+    old = time.time() - action_paths.STALE_STAGING_SECONDS - 60
+    os.utime(stale, (old, old))
+    replace = os.replace
+    temp = _download(tmp_path, b"media 1")
+
+    def cross_device(src, dst):
+        if src == temp:
+            raise OSError(errno.EXDEV, "cross-device link")
+        return replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", cross_device)
+    action_paths.moveHelper(temp, tmp_path / "caption.jpg", _media(1))
+    assert not stale.exists() and fresh.exists()
+
+
+def test_sweep_spares_a_live_copy_of_an_old_download(tmp_path, monkeypatch):
+    import errno
+    import os
+    import time
+
+    # A .part completed by a killed run is moved without being rewritten, so
+    # its mtime can be days old. Another download moving into the same folder
+    # sweeps it while this copy is about to be published.
+    temp = _download(tmp_path, b"media 1")
+    old = time.time() - 2 * action_paths.STALE_STAGING_SECONDS
+    os.utime(temp, (old, old))
+    replace, publish = os.replace, action_paths._replace
+
+    def cross_device(src, dst):
+        if src == temp:
+            raise OSError(errno.EXDEV, "cross-device link")
+        return replace(src, dst)
+
+    def publish_after_concurrent_sweep(src, dst):
+        if ".ofs-move-" in str(src):
+            action_paths._sweep_staging(dst.parent)
+        return publish(src, dst)
+
+    monkeypatch.setattr(os, "replace", cross_device)
+    monkeypatch.setattr(action_paths, "_replace", publish_after_concurrent_sweep)
+    got = action_paths.moveHelper(temp, tmp_path / "caption.jpg", _media(1))
+    assert got.read_bytes() == b"media 1"
+    assert abs(got.stat().st_mtime - old) < 1 and not temp.exists()
+
+
+def test_failed_move_removes_its_reservation(tmp_path, monkeypatch):
+    import os
+
+    def denied(src, dst):
+        raise PermissionError("denied")
+
+    monkeypatch.setattr(os, "replace", denied)
+    with pytest.raises(PermissionError):
+        _move(tmp_path, tmp_path / "caption.jpg", 1, b"media 1")
+    assert not (tmp_path / "caption.jpg").exists()
+
+
+def test_failed_move_leaves_other_files_alone(tmp_path, monkeypatch):
+    # the planned name holds another file; only the fallback was reserved
+    import os
+
+    (tmp_path / "caption.jpg").write_bytes(b"media 1")
+
+    def denied(src, dst):
+        raise PermissionError("denied")
+
+    monkeypatch.setattr(os, "replace", denied)
+    with pytest.raises(PermissionError):
+        _move(tmp_path, tmp_path / "caption.jpg", 2, b"media 2")
+    assert (tmp_path / "caption.jpg").read_bytes() == b"media 1"
+    assert not (tmp_path / "caption_2.jpg").exists()
+
+
+@pytest.mark.parametrize("fail_copy", [False, True])
+def test_cross_drive_partial_copy_is_not_deduplicated(tmp_path, monkeypatch, fail_copy):
+    import errno
+    import os
+    from pathlib import Path
+
+    target = tmp_path / "caption.jpg"
+    temp = _download(tmp_path, b"prefix and remainder", "first.part")
+    second = _download(tmp_path, b"prefix", "second.part")
+    replace = os.replace
+    results = []
+
+    def cross_device(src, dst):
+        if src == temp:
+            raise OSError(errno.EXDEV, "cross-device link")
+        return replace(src, dst)
+
+    def interrupted_copy(src, dst):
+        Path(dst).write_bytes(b"prefix")
+        # Deterministically interleave a second completed download mid-copy.
+        results.append(action_paths.moveHelper(second, target, _media(2)))
+        if fail_copy:
+            raise OSError("copy interrupted")
+        Path(dst).write_bytes(Path(src).read_bytes())
+
+    monkeypatch.setattr(os, "replace", cross_device)
+    monkeypatch.setattr(action_paths.shutil, "copyfile", interrupted_copy)
+    if fail_copy:
+        with pytest.raises(OSError, match="copy interrupted"):
+            action_paths.moveHelper(temp, target, _media(1))
+        assert temp.exists() and not target.exists()
+    else:
+        assert action_paths.moveHelper(temp, target, _media(1)) == target
+        assert target.read_bytes() == b"prefix and remainder"
+    assert results == [tmp_path / "caption_2.jpg"]
+    assert results[0].read_bytes() == b"prefix"
+    assert not list(tmp_path.glob(".ofs-move-*"))
+
+
+def test_empty_download_does_not_consume_another_reservation(tmp_path):
+    target = tmp_path / "caption.jpg"
+    assert action_paths._reserve(target)
+    assert _move(tmp_path, target, 2, b"") == tmp_path / "caption_2.jpg"
+    assert target.exists()
+
+
+@pytest.mark.parametrize("permanent", [False, True])
+def test_windows_sharing_error_keeps_reservation_during_retry(tmp_path, monkeypatch, permanent):
+    import os
+    replace = os.replace
+    target = tmp_path / "caption.jpg"
+    temp = _download(tmp_path, b"media")
+    attempts = []
+
+    def busy(src, dst):
+        assert target.is_file() and target.stat().st_size == 0
+        attempts.append(dst)
+        if permanent or len(attempts) == 1:
+            error = PermissionError("sharing conflict")
+            error.winerror = 5
+            raise error
+        return replace(src, dst)
+
+    monkeypatch.setattr(os, "replace", busy)
+    monkeypatch.setattr(action_paths.time, "sleep", lambda delay: None)
+    if permanent:
+        with pytest.raises(PermissionError):
+            action_paths.moveHelper(temp, target, _media(1))
+        assert len(attempts) == 6
+        assert temp.exists() and not target.exists()
+    else:
+        assert action_paths.moveHelper(temp, target, _media(1)) == target
+        assert len(attempts) == 2 and target.read_bytes() == b"media"
+
+
+def test_disappearing_reservation_is_not_an_error(tmp_path, monkeypatch):
+    target = tmp_path / "caption.jpg"
+    target.write_bytes(b"same size")
+    temp = _download(tmp_path, b"same size")
+    original = action_paths._file_hash
+
+    def disappear(path):
+        if path == target:
+            target.unlink()
+        return original(path)
+
+    monkeypatch.setattr(action_paths, "_file_hash", disappear)
+    assert not action_paths._same_content(temp, target)
+    assert temp.exists()
+
+
+@pytest.mark.parametrize("downloader", ["normal", "drm"])
+def test_downloaders_record_and_use_final_path(tmp_path, monkeypatch, downloader):
+    import asyncio
+    from unittest.mock import AsyncMock, Mock
+    import ofscraper.commands.scraper.actions.download.managers.main_download as normal
+    import ofscraper.commands.scraper.actions.download.managers.alt_download as drm
+
+    module = normal if downloader == "normal" else drm
+    target = tmp_path / "caption.jpg"
+    target.write_bytes(b"existing owner")
+    final = tmp_path / "caption_2.jpg"
+    payload = b"new download"
+    temp = tmp_path / "download.part"
+    placeholder = SimpleNamespace(trunicated_filepath=target, size=999)
+    ele = _media(2)
+    ele.mediatype, ele.postdate, ele.duration = "Images", "2020-01-01", 1
+    ele.add_filepath = Mock()
+
+    async def filename():
+        return target.name
+
+    ele.final_filename = filename() if downloader == "normal" else None
+    manager = SimpleNamespace(_size_checker=AsyncMock(), _after_download_script=AsyncMock())
+    database = AsyncMock()
+    hashing = AsyncMock(return_value="new-hash")
+    dating = Mock()
+    monkeypatch.setattr(module.common_globals, "thread", None, raising=False)
+    monkeypatch.setattr(module.common_globals, "log", Mock())
+    monkeypatch.setattr(module, "mark_media_as_downloaded", database)
+    monkeypatch.setattr(module.common, "get_hash", hashing)
+    monkeypatch.setattr(module.common_paths, "set_time", dating)
+    monkeypatch.setattr(module.common_paths, "addGlobalDir", Mock())
+    if downloader == "normal":
+        temp.write_bytes(payload)
+        monkeypatch.setattr(normal, "set_profile_cache", AsyncMock())
+        asyncio.run(normal.MainDownloadManager._handle_result_main(
+            manager, (len(payload), temp, placeholder), ele, "model", 10
+        ))
+    else:
+        monkeypatch.setattr(drm.placeholder, "tempFilePlaceholder", lambda *a: SimpleNamespace(
+            init=AsyncMock(return_value=SimpleNamespace(tempfilepath=temp))
+        ))
+
+        async def merge(*args, **kwargs):
+            temp.write_bytes(payload)
+            return SimpleNamespace(stderr=b"", stdout=b"")
+
+        monkeypatch.setattr(drm, "async_run", merge)
+        monkeypatch.setattr(drm, "get_ffmpeg", lambda: "ffmpeg")
+        monkeypatch.setattr(drm, "verify_media_integrity", lambda *a, **k: True)
+        asyncio.run(drm.AltDownloadManager._handle_result_alt(
+            manager, placeholder, ele, None, None, "model", 10
+        ))
+    assert target.read_bytes() == b"existing owner"
+    assert final.read_bytes() == payload
+    assert database.await_args.kwargs["filepath"] == final
+    assert database.await_args.kwargs["size"] == len(payload)
+    assert database.await_args.kwargs["hashdata"] == "new-hash"
+    hashing.assert_awaited_once_with(final)
+    assert dating.call_args.args[0] == final
+    ele.add_filepath.assert_called_once_with(final)
+    manager._after_download_script.assert_awaited_once_with(final)
```
