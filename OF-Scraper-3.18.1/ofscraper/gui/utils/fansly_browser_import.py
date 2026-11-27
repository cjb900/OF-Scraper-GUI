"""Read a Fansly session token from a browser installed on this computer.

Fansly keeps its token in the web app's localStorage, under
``session_active_session`` (a JSON object with a ``token``), not in a cookie,
so cookie readers can't get it. This reads the browser's localStorage files
directly; nothing is sent anywhere.

- Firefox family (Firefox, Zen, LibreWolf, Floorp, Waterfox): each profile
  keeps fansly.com's localStorage in
  ``storage/default/https+++fansly.com/ls/data.sqlite``. Values may be
  snappy-compressed (``compression_type`` 1) and stored as UTF-8
  (``conversion_type`` 1) or UTF-16.
- Chromium family (Chrome, Edge, Brave, Opera, Vivaldi, Chromium): each
  profile keeps localStorage in a LevelDB folder, ``Local Storage/leveldb``.
  Its ``.log`` files hold recent writes, its ``.ldb`` tables hold older ones
  in (usually snappy-compressed) blocks. The entry with the highest sequence
  number is the current value. These files aren't encrypted, unlike
  Chromium's cookies on Windows.

The token never appears in logs.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import platform
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass

log = logging.getLogger("shared")

LS_KEY = "session_active_session"
FIREFOX_ORIGIN = "https+++fansly.com"
CHROMIUM_ORIGIN = b"_https://fansly.com\x00"

FIREFOX_FAMILY = ("Firefox", "Zen Browser", "LibreWolf", "Floorp", "Waterfox")
CHROMIUM_FAMILY = ("Chrome", "Edge", "Brave", "Opera", "Opera GX", "Vivaldi", "Chromium")
BROWSERS = FIREFOX_FAMILY + CHROMIUM_FAMILY

MIN_TOKEN = 50


class ImportFailed(Exception):
    """No usable Fansly token in that browser; the message says why."""


@dataclass(frozen=True)
class FoundToken:
    token: str
    browser: str
    profile_dir: str
    freshness: float  # newest write to the storage it came from


# --- snappy -------------------------------------------------------------------


def _varint(buf, pos):
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def snappy_decompress(buf: bytes) -> bytes:
    """Decompress raw (unframed) snappy data, as Firefox and LevelDB store it."""
    size, pos = _varint(buf, 0)
    out = bytearray()
    n = len(buf)
    while pos < n:
        tag = buf[pos]
        pos += 1
        kind = tag & 3
        if kind == 0:  # literal
            length = tag >> 2
            if length >= 60:
                extra = length - 59
                length = int.from_bytes(buf[pos:pos + extra], "little")
                pos += extra
            length += 1
            if pos + length > n:
                raise ValueError("truncated literal")
            out += buf[pos:pos + length]
            pos += length
            continue
        if kind == 1:
            length = ((tag >> 2) & 7) + 4
            offset = ((tag >> 5) << 8) | buf[pos]
            pos += 1
        elif kind == 2:
            length = (tag >> 2) + 1
            offset = int.from_bytes(buf[pos:pos + 2], "little")
            pos += 2
        else:
            length = (tag >> 2) + 1
            offset = int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
        if offset <= 0 or offset > len(out):
            raise ValueError("bad copy offset")
        start = len(out) - offset
        if offset >= length:
            out += out[start:start + length]
        else:  # overlapping copy repeats the last `offset` bytes
            for i in range(length):
                out.append(out[start + i])
    if len(out) != size:
        raise ValueError("wrong decompressed size")
    return bytes(out)


# --- the token in a localStorage value ------------------------------------------


_TOKEN_RE = re.compile(r'"token"\s*:\s*"([^"\\]{%d,})"' % MIN_TOKEN)


def token_from_value(text: str) -> str | None:
    """The token in a ``session_active_session`` value, or None."""
    text = (text or "").replace("\x00", "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        if isinstance(data, str):  # stored as a JSON string of JSON
            data = json.loads(data)
        token = data.get("token") if isinstance(data, dict) else None
        if isinstance(token, str) and len(token.strip()) >= MIN_TOKEN:
            return token.strip()
    except (ValueError, TypeError):
        pass
    m = _TOKEN_RE.search(text)
    return m.group(1) if m else None


# --- Firefox family ---------------------------------------------------------------


def _firefox_roots(browser: str) -> list[str]:
    home = os.path.expanduser("~")
    system = platform.system()
    appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    mac = os.path.join(home, "Library", "Application Support")
    table = {
        "Firefox": {
            "Windows": [os.path.join(appdata, "Mozilla", "Firefox")],
            "Darwin": [os.path.join(mac, "Firefox")],
            "Linux": [
                os.path.join(home, ".mozilla", "firefox"),
                os.path.join(home, ".var/app/org.mozilla.firefox/.mozilla/firefox"),
                os.path.join(home, "snap/firefox/common/.mozilla/firefox"),
            ],
        },
        "Zen Browser": {
            "Windows": [os.path.join(appdata, "zen")],
            "Darwin": [os.path.join(mac, "zen")],
            "Linux": [
                os.path.join(home, ".zen"),
                os.path.join(home, ".mozilla", "zen"),
                os.path.join(home, ".var/app/app.zen_browser.zen/.zen"),
            ],
        },
        "LibreWolf": {
            "Windows": [os.path.join(appdata, "librewolf")],
            "Darwin": [os.path.join(mac, "librewolf")],
            "Linux": [
                os.path.join(home, ".librewolf"),
                os.path.join(home, ".var/app/io.gitlab.librewolf-community/.librewolf"),
            ],
        },
        "Floorp": {
            "Windows": [os.path.join(appdata, "Floorp")],
            "Darwin": [os.path.join(mac, "Floorp")],
            "Linux": [
                os.path.join(home, ".floorp"),
                os.path.join(home, ".var/app/one.ablaze.floorp/.floorp"),
            ],
        },
        "Waterfox": {
            "Windows": [os.path.join(appdata, "Waterfox")],
            "Darwin": [os.path.join(mac, "Waterfox")],
            "Linux": [os.path.join(home, ".waterfox")],
        },
    }
    return table.get(browser, {}).get(system, table.get(browser, {}).get("Linux", []))


def firefox_profiles(browser: str, roots: list[str] | None = None) -> list[str]:
    """Profile folders that have fansly.com localStorage."""
    found = []
    for root in roots if roots is not None else _firefox_roots(browser):
        if not os.path.isdir(root):
            continue
        # <root>/<profile> and <root>/Profiles/<profile>
        for pattern in ("*", os.path.join("Profiles", "*")):
            for profile in glob.glob(os.path.join(root, pattern)):
                db = os.path.join(profile, "storage", "default", FIREFOX_ORIGIN, "ls", "data.sqlite")
                if os.path.isfile(db) and profile not in found:
                    found.append(profile)
    return found


def _freshness(*paths) -> float:
    best = 0.0
    for p in paths:
        try:
            best = max(best, os.path.getmtime(p))
        except OSError:
            pass
    return best


def _decode_firefox_value(value, conversion, compression) -> str:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, str):
        return value
    data = bytes(value or b"")
    if compression == 1:
        data = snappy_decompress(data)
    if conversion == 1:
        return data.decode("utf-8", errors="replace")
    return data.decode("utf-16-le", errors="replace")


def read_firefox_profile(profile_dir: str) -> FoundToken | None:
    db = os.path.join(profile_dir, "storage", "default", FIREFOX_ORIGIN, "ls", "data.sqlite")
    if not os.path.isfile(db):
        return None
    tmp = tempfile.mkdtemp(prefix="ofsc-fansly-")
    try:
        copy = os.path.join(tmp, "data.sqlite")
        shutil.copy2(db, copy)
        for ext in ("-wal", "-shm"):  # the live session is often only in the WAL
            if os.path.exists(db + ext):
                shutil.copy2(db + ext, copy + ext)
        conn = sqlite3.connect(copy)
        try:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(data)")}
            conv = "conversion_type" if "conversion_type" in cols else "1"
            comp = "compression_type" if "compression_type" in cols else "0"
            rows = conn.execute(
                f"SELECT value, {conv}, {comp} FROM data WHERE key = ?", (LS_KEY,)
            ).fetchall()
        finally:
            conn.close()
        for value, conversion, compression in rows:
            try:
                token = token_from_value(_decode_firefox_value(value, conversion, compression))
            except ValueError as e:
                log.debug(f"[GUI] Fansly import: unreadable value in {profile_dir}: {e}")
                continue
            if token:
                return FoundToken(token, "", profile_dir, _freshness(db, db + "-wal"))
    except (OSError, sqlite3.Error) as e:
        log.debug(f"[GUI] Fansly import: could not read {db}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return None


# --- Chromium family (LevelDB) ------------------------------------------------------


def _chromium_user_data_dirs(browser: str) -> list[str]:
    home = os.path.expanduser("~")
    system = platform.system()
    local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
    roaming = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    mac = os.path.join(home, "Library", "Application Support")
    cfg = os.path.join(home, ".config")
    flat = os.path.join(home, ".var", "app")
    table = {
        "Chrome": {
            "Windows": [os.path.join(local, "Google", "Chrome", "User Data")],
            "Darwin": [os.path.join(mac, "Google", "Chrome")],
            "Linux": [os.path.join(cfg, "google-chrome"),
                      os.path.join(flat, "com.google.Chrome/config/google-chrome")],
        },
        "Chromium": {
            "Windows": [os.path.join(local, "Chromium", "User Data")],
            "Darwin": [os.path.join(mac, "Chromium")],
            "Linux": [os.path.join(cfg, "chromium"),
                      os.path.join(flat, "org.chromium.Chromium/config/chromium"),
                      os.path.join(home, "snap/chromium/common/chromium")],
        },
        "Edge": {
            "Windows": [os.path.join(local, "Microsoft", "Edge", "User Data")],
            "Darwin": [os.path.join(mac, "Microsoft Edge")],
            "Linux": [os.path.join(cfg, "microsoft-edge"),
                      os.path.join(cfg, "microsoft-edge-stable"),
                      os.path.join(flat, "com.microsoft.Edge/config/microsoft-edge")],
        },
        "Brave": {
            "Windows": [os.path.join(local, "BraveSoftware", "Brave-Browser", "User Data")],
            "Darwin": [os.path.join(mac, "BraveSoftware", "Brave-Browser")],
            "Linux": [os.path.join(cfg, "BraveSoftware", "Brave-Browser"),
                      os.path.join(flat, "com.brave.Browser/config/BraveSoftware/Brave-Browser"),
                      os.path.join(home, "snap/brave/current/.config/BraveSoftware/Brave-Browser")],
        },
        "Opera": {
            "Windows": [os.path.join(roaming, "Opera Software", "Opera Stable")],
            "Darwin": [os.path.join(mac, "com.operasoftware.Opera")],
            "Linux": [os.path.join(cfg, "opera"),
                      os.path.join(flat, "com.opera.Opera/config/opera")],
        },
        "Opera GX": {
            "Windows": [os.path.join(roaming, "Opera Software", "Opera GX Stable")],
            "Darwin": [os.path.join(mac, "com.operasoftware.OperaGX")],
            "Linux": [],
        },
        "Vivaldi": {
            "Windows": [os.path.join(local, "Vivaldi", "User Data")],
            "Darwin": [os.path.join(mac, "Vivaldi")],
            "Linux": [os.path.join(cfg, "vivaldi"),
                      os.path.join(flat, "com.vivaldi.Vivaldi/config/vivaldi")],
        },
    }
    return table.get(browser, {}).get(system, table.get(browser, {}).get("Linux", []))


def chromium_profiles(browser: str, roots: list[str] | None = None) -> list[str]:
    """Profile folders (Default, Profile 1, ...) that have a localStorage LevelDB."""
    found = []
    for root in roots if roots is not None else _chromium_user_data_dirs(browser):
        if not os.path.isdir(root):
            continue
        # Opera keeps its profile in the user-data folder itself
        candidates = [root] + sorted(glob.glob(os.path.join(root, "*")))
        for profile in candidates:
            if os.path.isdir(os.path.join(profile, "Local Storage", "leveldb")) and profile not in found:
                found.append(profile)
    return found


def _read_shared(path: str) -> bytes:
    """Read a file the browser may hold open."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        pass
    if platform.system() == "Windows":
        try:
            from ofscraper.gui.dialogs.auth_dialog import _read_file_bytes_shared

            return _read_file_bytes_shared(path) or b""
        except Exception:
            return b""
    return b""


def _batch_entries(batch: bytes):
    """(sequence, kind, key, value) for each record of a LevelDB WriteBatch."""
    if len(batch) < 12:
        return
    seq = int.from_bytes(batch[0:8], "little")
    count = int.from_bytes(batch[8:12], "little")
    pos = 12
    for i in range(count):
        if pos >= len(batch):
            return
        kind = batch[pos]
        pos += 1
        klen, pos = _varint(batch, pos)
        key = batch[pos:pos + klen]
        pos += klen
        value = b""
        if kind == 1:
            vlen, pos = _varint(batch, pos)
            value = batch[pos:pos + vlen]
            pos += vlen
        elif kind != 0:
            return
        yield seq + i, kind, key, value


def leveldb_log_entries(data: bytes):
    """Records of a LevelDB .log file: 32 KiB blocks of fragments, each with a
    7-byte header (checksum, length, type); FULL=1, FIRST=2, MIDDLE=3, LAST=4."""
    block = 32768
    pos = 0
    pending = None
    while pos + 7 <= len(data):
        room = block - pos % block
        if room < 7:  # trailer padding
            pos += room
            continue
        length = int.from_bytes(data[pos + 4:pos + 6], "little")
        kind = data[pos + 6]
        payload = data[pos + 7:pos + 7 + length]
        pos += 7 + length
        if kind == 0 and length == 0:  # preallocated zeros
            pos += block - pos % block if pos % block else 0
            continue
        if kind == 1:
            pending = None
            batch = payload
        elif kind == 2:
            pending = bytearray(payload)
            continue
        elif kind == 3:
            if pending is not None:
                pending += payload
            continue
        elif kind == 4:
            if pending is None:
                continue
            batch = bytes(pending + payload)
            pending = None
        else:
            continue
        try:
            yield from _batch_entries(batch)
        except ValueError:
            continue


def _read_block(data: bytes, offset: int, size: int) -> bytes:
    raw = data[offset:offset + size]
    kind = data[offset + size] if offset + size < len(data) else 0
    if kind == 1:
        return snappy_decompress(raw)
    if kind == 0:
        return raw
    raise ValueError(f"unsupported block compression {kind}")


def _block_entries(block: bytes):
    """(key, value) pairs of a LevelDB table block (prefix-compressed keys)."""
    if len(block) < 4:
        return
    restarts = int.from_bytes(block[-4:], "little")
    end = len(block) - 4 - 4 * restarts
    pos = 0
    key = b""
    while pos < end:
        shared, pos = _varint(block, pos)
        unshared, pos = _varint(block, pos)
        vlen, pos = _varint(block, pos)
        key = key[:shared] + block[pos:pos + unshared]
        pos += unshared
        value = block[pos:pos + vlen]
        pos += vlen
        yield key, value


def leveldb_table_entries(data: bytes):
    """(sequence, kind, user_key, value) for each entry of a LevelDB .ldb table."""
    if len(data) < 48 or data[-8:] != bytes.fromhex("57fb808b247547db"):
        return
    footer = data[-48:]
    pos = 0
    _meta_off, pos = _varint(footer, pos)
    _meta_size, pos = _varint(footer, pos)
    index_off, pos = _varint(footer, pos)
    index_size, pos = _varint(footer, pos)
    index = _read_block(data, index_off, index_size)
    for _last_key, handle in _block_entries(index):
        off, p = _varint(handle, 0)
        size, _ = _varint(handle, p)
        try:
            block = _read_block(data, off, size)
        except ValueError:
            continue
        for ikey, value in _block_entries(block):
            if len(ikey) < 8:
                continue
            tag = int.from_bytes(ikey[-8:], "little")
            yield tag >> 8, tag & 0xFF, ikey[:-8], value


def _chromium_value_text(value: bytes) -> str:
    """localStorage values start with 0 (UTF-16) or 1 (Latin-1)."""
    if not value:
        return ""
    if value[0] == 1:
        return value[1:].decode("latin-1")
    if value[0] == 0:
        return value[1:].decode("utf-16-le", errors="replace")
    return value.decode("utf-8", errors="replace")


def _is_session_key(key: bytes) -> bool:
    return key.startswith(CHROMIUM_ORIGIN) and key.endswith(LS_KEY.encode())


def read_leveldb_dir(ldb_dir: str) -> tuple[str | None, float]:
    """(token, freshness) from the newest session_active_session entry."""
    newest = None  # (sequence, kind, value)
    fresh = 0.0
    try:
        names = os.listdir(ldb_dir)
    except OSError:
        return None, 0.0
    for name in names:
        path = os.path.join(ldb_dir, name)
        if name.endswith(".log"):
            reader = leveldb_log_entries
        elif name.endswith(".ldb") or name.endswith(".sst"):
            reader = leveldb_table_entries
        else:
            continue
        data = _read_shared(path)
        if CHROMIUM_ORIGIN not in data and not name.endswith((".ldb", ".sst")):
            continue
        try:
            for seq, kind, key, value in reader(data):
                if _is_session_key(key) and (newest is None or seq > newest[0]):
                    newest = (seq, kind, value)
                    fresh = _freshness(path)
        except (ValueError, IndexError) as e:
            log.debug(f"[GUI] Fansly import: skipped {path}: {e}")
    if newest is None or newest[1] != 1:  # missing, or deleted (signed out)
        return None, fresh
    return token_from_value(_chromium_value_text(newest[2])), fresh


def read_chromium_profile(profile_dir: str) -> FoundToken | None:
    token, fresh = read_leveldb_dir(os.path.join(profile_dir, "Local Storage", "leveldb"))
    return FoundToken(token, "", profile_dir, fresh) if token else None


# --- entry point ------------------------------------------------------------------


def find_token(browser: str) -> FoundToken:
    """The freshest Fansly token in that browser's profiles; ImportFailed if none."""
    if browser in FIREFOX_FAMILY:
        profiles, reader = firefox_profiles(browser), read_firefox_profile
    elif browser in CHROMIUM_FAMILY:
        profiles, reader = chromium_profiles(browser), read_chromium_profile
    else:
        raise ImportFailed(f"{browser} isn't supported")
    if not profiles:
        raise ImportFailed(
            f"No {browser} profile has visited fansly.com. Sign in to Fansly in {browser} first."
        )
    best = None
    for profile in profiles:
        found = reader(profile)
        if found and (best is None or found.freshness > best.freshness):
            best = found
    if best is None:
        raise ImportFailed(
            f"{browser} isn't signed in to Fansly (no session token in "
            f"{len(profiles)} profile{'s' if len(profiles) != 1 else ''}). "
            "Sign in on fansly.com in that browser, then try again."
        )
    log.info(f"[GUI] Fansly token imported from {browser} ({best.profile_dir})")
    return FoundToken(best.token, browser, best.profile_dir, best.freshness)


def user_agent_for(browser: str, profile_dir: str) -> str:
    """The user agent of the browser the token came from, best effort."""
    try:
        from ofscraper.gui.dialogs import auth_dialog
    except Exception:
        return ""
    name = {"Zen Browser": "Zen Browser"}.get(browser, browser)
    if browser in ("Firefox", "Zen Browser"):
        try:
            ua = auth_dialog._get_firefox_or_zen_profile_user_agent(profile_dir, name)
            if ua:
                return ua
        except Exception:
            pass
    try:
        # other Firefox forks report as Firefox
        return auth_dialog._detect_user_agent("Firefox" if browser in FIREFOX_FAMILY else name) or ""
    except Exception:
        return ""
