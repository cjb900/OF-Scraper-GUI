# PR #3: fix(ffmpeg): accept ffmpeg 8 and newer for DRM

- **URL:** https://github.com/cjb900/OF-Scraper-GUI/pull/3
- **Author:** cloakedkeys
- **Branch:** `cloakedkeys:fix/ffmpeg-8-drm` → `main`
- **Created:** 2026-10-23T02:23:16Z  ·  **Updated:** 2026-10-23T03:19:29Z
- **Draft:** False
- **Changes:** 4 files, +180 / -3

## Description

**Upstream issue (related):** datawhores/OF-Scraper#614. Likely the same bug, not confirmed against the reporter's case.  
Upstream PR datawhores/OF-Scraper#618 also lifts the version limit.

Lets DRM downloads use ffmpeg 8 and newer.

## Change
- **`utils/system/ffmpeg.py`:** accept ffmpeg 6 or newer (was 6 and 7 only).
- **`keyhelpers.un_encrypt`:** after a successful decrypt, call a new `strip_pssh()`.
  - ffmpeg 8+ copies the source's `pssh` box (the DRM init data) into the decrypted file. 7.x didn't.
  - The audio and video are identical either way, but a clear file that still carries `pssh` can look protected to some players.
  - `strip_pssh()` renames those boxes to same-sized `free` boxes. Every offset stays valid and nothing else in the file changes.
  - On 6.x and 7.x there's no box to rename, so it does nothing.

There are no new dependencies. Upstream's datawhores/OF-Scraper#618 also lifts the limit, but it adds `ffmpeg-python` and leaves the `pssh` box in place.

## Tested
- **Unit:**
  - `test/unit/test_ffmpeg_version.py` checks version-string parsing from 5.x to 9.x, plus git builds.
  - `test/unit/test_drm_decrypt_output.py` encrypts a sample with ffmpeg, decrypts it through `un_encrypt` and checks that no `pssh` remains. It needs ffmpeg on `PATH`.
  - Without the change, the decrypt test can't import and the version test rejects 8+.
  - All of `test/unit` passes (52 passed, 1 skipped).
- **Live, on this repo's `OF-Scraper-3.14.7` tree with ffmpeg 9.0.2:**
  - A purchased wall-post video downloaded and decrypted, with 2 `pssh` boxes neutralised.
  - Its streams are hash-identical to a copy decrypted earlier with ffmpeg 7.1.1.

Not changed: the missing-deps dialog and docs still recommend FFmpeg 7.1.1, which keeps working. They could now say "6 or newer".

`patch_ofscraper_3.14.7_gui.py` isn't regenerated here; it'll need rebuilding to ship this.

## Files changed

- `OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/keyhelpers.py`
- `OF-Scraper-3.14.7/ofscraper/utils/system/ffmpeg.py`
- `OF-Scraper-3.14.7/test/unit/test_drm_decrypt_output.py`
- `OF-Scraper-3.14.7/test/unit/test_ffmpeg_version.py`

## Code changes (full diff)

```diff
diff --git a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/keyhelpers.py b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/keyhelpers.py
index e317f0c..c6afe72 100644
--- a/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/keyhelpers.py
+++ b/OF-Scraper-3.14.7/ofscraper/commands/scraper/actions/download/utils/keyhelpers.py
@@ -1,6 +1,7 @@
 import asyncio
 import pathlib
 import re
+import struct
 import traceback
 from functools import partial
 
@@ -31,6 +32,47 @@ def setLog(input_):
     log = input_
 
 
+def strip_pssh(path):
+    """
+    Turn pssh boxes in a decrypted file into same-sized 'free' boxes.
+
+    ffmpeg 8+ copies the source's pssh (DRM init data) into the decrypted
+    output; 7.x dropped it. The media is identical either way, but a clear
+    file still carrying pssh can look protected to some players. Renaming
+    keeps every offset valid, so nothing else in the file changes.
+    Returns the number of boxes changed.
+    """
+    changed = 0
+    with open(path, "r+b") as f:
+        f.seek(0, 2)
+        file_end = f.tell()
+
+        def walk(start, end, depth):
+            nonlocal changed
+            pos = start
+            while pos + 8 <= end:
+                f.seek(pos)
+                size, typ = struct.unpack(">I4s", f.read(8))
+                header = 8
+                if size == 1:
+                    size = struct.unpack(">Q", f.read(8))[0]
+                    header = 16
+                elif size == 0:
+                    size = end - pos
+                if size < header or pos + size > end:
+                    return
+                if typ == b"pssh":
+                    f.seek(pos + 4)
+                    f.write(b"free")
+                    changed += 1
+                elif depth == 0 and typ in (b"moov", b"moof"):
+                    walk(pos + header, pos + size, depth + 1)
+                pos += size
+
+        walk(0, file_end, 0)
+    return changed
+
+
 async def un_encrypt(item, c, ele, input_=None):
     try:
         setLog(input_ or common_globals.log)
@@ -91,6 +133,11 @@ async def un_encrypt(item, c, ele, input_=None):
             raise Exception(f"{get_medialog(ele)} ffmpeg decryption failed")
         else:
             log.debug(f"{get_medialog(ele)} ffmpeg  decrypt success {newpath}")
+            try:
+                if n := strip_pssh(newpath):
+                    log.debug(f"{get_medialog(ele)} removed {n} pssh box(es) from {newpath}")
+            except OSError as E:
+                log.debug(f"{get_medialog(ele)} could not strip pssh from {newpath}: {E}")
             pathlib.Path(item["path"]).unlink(missing_ok=True)
             item["path"] = newpath
             await asyncio.get_event_loop().run_in_executor(
diff --git a/OF-Scraper-3.14.7/ofscraper/utils/system/ffmpeg.py b/OF-Scraper-3.14.7/ofscraper/utils/system/ffmpeg.py
index 2d2e4b4..23daab1 100644
--- a/OF-Scraper-3.14.7/ofscraper/utils/system/ffmpeg.py
+++ b/OF-Scraper-3.14.7/ofscraper/utils/system/ffmpeg.py
@@ -19,7 +19,7 @@
 def _is_valid_ffmpeg(path: str | None) -> bool:
     """
     Checks if a given path is a real, executable FFmpeg binary and validates
-    that its version is >= 6 and < 8 for DRM compatibility. Logs the process.
+    that its version is >= 6 for DRM compatibility. Logs the process.
     """
     if not path or not shutil.which(path):
         log.debug(f"Path '{path}' is not a valid or executable file.")
@@ -44,10 +44,10 @@ def _is_valid_ffmpeg(path: str | None) -> bool:
             
             if version_match:
                 major_version = int(version_match.group(1))
-                if major_version < 6 or major_version >= 8:
+                if major_version < 6:
                     log.warning(
                         f"⚠️ Invalid FFmpeg version {major_version}.x detected at '{path}'.\n"
-                        f"DRM decryption requires FFmpeg version >= 6 and < 8.\n"
+                        f"DRM decryption requires FFmpeg version 6 or newer.\n"
                         f"Skipping this binary and looking for an alternative..."
                     )
                     return False
diff --git a/OF-Scraper-3.14.7/test/unit/test_drm_decrypt_output.py b/OF-Scraper-3.14.7/test/unit/test_drm_decrypt_output.py
new file mode 100644
index 0000000..2f1abdf
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_drm_decrypt_output.py
@@ -0,0 +1,90 @@
+import sys
+
+# ofscraper parses sys.argv when settings are first read, so hide pytest's
+# own command-line flags from it, then import the app's entry module first
+# (importing a leaf module first hits a circular import).
+sys.argv = sys.argv[:1]
+import ofscraper.main.open.load  # noqa: E402,F401
+
+import shutil
+import struct
+import subprocess
+
+import pytest
+
+pytestmark = pytest.mark.unit
+
+from ofscraper.commands.scraper.actions.download.utils.keyhelpers import strip_pssh
+
+
+def _box(typ, payload=b""):
+    return struct.pack(">I4s", 8 + len(payload), typ) + payload
+
+
+def _types(data, start=0, end=None):
+    end = len(data) if end is None else end
+    out, pos = [], start
+    while pos + 8 <= end:
+        size, typ = struct.unpack(">I4s", data[pos : pos + 8])
+        out.append(typ)
+        if typ in (b"moov", b"moof"):
+            out += [b"  " + t for t in _types(data, pos + 8, pos + size)]
+        pos += size
+    return out
+
+
+def test_strip_pssh_renames_in_place(tmp_path):
+    pssh = _box(b"pssh", b"\x00" * 40)
+    moov = _box(b"moov", _box(b"mvhd", b"\x00" * 100) + pssh + _box(b"trak", b"\x00" * 20))
+    # "pssh" inside mdat is media data, not a box, and must not change
+    mdat = _box(b"mdat", b"xxxxpsshyyyy")
+    data = _box(b"ftyp", b"isom\x00\x00\x02\x00") + pssh + moov + mdat
+    f = tmp_path / "a.mp4"
+    f.write_bytes(data)
+
+    assert strip_pssh(f) == 2
+    out = f.read_bytes()
+    assert len(out) == len(data)
+    assert b"pssh" not in b"".join(_types(out))
+    assert _types(out) == [t.replace(b"pssh", b"free") for t in _types(data)]
+    assert out.endswith(mdat)
+
+
+def test_strip_pssh_leaves_clean_file_alone(tmp_path):
+    data = _box(b"ftyp", b"isom") + _box(b"moov", _box(b"mvhd", b"\x00" * 100))
+    f = tmp_path / "a.mp4"
+    f.write_bytes(data)
+    assert strip_pssh(f) == 0
+    assert f.read_bytes() == data
+
+
+FFMPEG = shutil.which("ffmpeg")
+KEY = "00112233445566778899aabbccddeeff"
+
+
+def _ffmpeg(*args):
+    subprocess.run([FFMPEG, "-v", "error", "-y", *args], check=True)
+
+
+def _framemd5(path):
+    r = subprocess.run(
+        [FFMPEG, "-v", "error", "-i", str(path), "-map", "0:v", "-f", "framemd5", "-"],
+        capture_output=True, text=True,
+    )
+    # decoding still-encrypted data fails outright on ffmpeg 8+
+    return r.stdout if r.returncode == 0 else f"decode failed ({r.returncode})"
+
+
+@pytest.mark.skipif(not FFMPEG, reason="ffmpeg not installed")
+def test_installed_ffmpeg_decrypts_cenc_like_un_encrypt(tmp_path):
+    # end to end with whatever ffmpeg is installed: encrypt a clip with CENC,
+    # decrypt it with the same arguments as un_encrypt, and compare frames
+    plain, enc, dec = tmp_path / "plain.mp4", tmp_path / "enc.mp4", tmp_path / "dec.mp4"
+    _ffmpeg("-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=25",
+            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(plain))
+    _ffmpeg("-i", str(plain), "-c", "copy", "-encryption_scheme", "cenc-aes-ctr",
+            "-encryption_key", KEY, "-encryption_kid", "a7e61c373e219033c21091fa607bf3b8", str(enc))
+    assert _framemd5(enc) != _framemd5(plain)  # really encrypted
+    _ffmpeg("-decryption_key", KEY, "-i", str(enc), "-codec", "copy", str(dec))
+    strip_pssh(dec)
+    assert _framemd5(dec) == _framemd5(plain)
diff --git a/OF-Scraper-3.14.7/test/unit/test_ffmpeg_version.py b/OF-Scraper-3.14.7/test/unit/test_ffmpeg_version.py
new file mode 100644
index 0000000..0d5e45a
--- /dev/null
+++ b/OF-Scraper-3.14.7/test/unit/test_ffmpeg_version.py
@@ -0,0 +1,40 @@
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
+import pytest
+
+pytestmark = pytest.mark.unit
+
+import ofscraper.utils.system.ffmpeg as ffmpeg
+
+
+def _fake_version(monkeypatch, line):
+    monkeypatch.setattr(ffmpeg.shutil, "which", lambda p: p)
+    monkeypatch.setattr(
+        ffmpeg, "run", lambda *a, **k: SimpleNamespace(stdout=line, stderr="")
+    )
+
+
+@pytest.mark.parametrize(
+    "line,ok",
+    [
+        ("ffmpeg version 5.1.6 Copyright", False),
+        ("ffmpeg version 6.1.1 Copyright", True),
+        ("ffmpeg version 7.1.1-essentials_build Copyright", True),
+        # 8+ decrypts the same; it used to be rejected
+        ("ffmpeg version 8.1.2-essentials_build Copyright", True),
+        ("ffmpeg version 9.0.2-full_build Copyright", True),
+        ("ffmpeg version N-118000-gabcdef Copyright", True),
+        ("not ffmpeg", False),
+    ],
+)
+def test_ffmpeg_version_gate(monkeypatch, line, ok):
+    _fake_version(monkeypatch, line)
+    assert ffmpeg._is_valid_ffmpeg("ffmpeg") is ok
```
