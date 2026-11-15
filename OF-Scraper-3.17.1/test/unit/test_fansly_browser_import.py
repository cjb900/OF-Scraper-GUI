"""Importing the Fansly session token from a browser's own localStorage files."""

import json
import os
import sqlite3

import pytest

from ofscraper.gui.utils import fansly_browser_import as fbi

TOKEN = "MTIzNDU2Nzg5MDEyMzQ1Njc4OjE6MjphYmNkZWZnaGlqa2xtbm9wcXJzdHV2d3h5ejAxMjM0NTY3ODk"
OLD_TOKEN = TOKEN[::-1]
SESSION = json.dumps({"id": "1", "accountId": "2", "token": TOKEN, "metadata": None})


# --- builders ---------------------------------------------------------------------


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def snappy_literals(data: bytes) -> bytes:
    """Valid snappy made only of literals (what any reader must accept)."""
    out = bytearray(_varint(len(data)))
    for i in range(0, len(data), 60):
        chunk = data[i:i + 60]
        out.append((len(chunk) - 1) << 2)
        out += chunk
    return bytes(out)


def firefox_profile(root, name="abc.default-release", value=SESSION, compress=True, utf8=True):
    profile = root / name
    ls = profile / "storage" / "default" / fbi.FIREFOX_ORIGIN / "ls"
    ls.mkdir(parents=True)
    raw = value.encode("utf-8" if utf8 else "utf-16-le")
    conn = sqlite3.connect(ls / "data.sqlite")
    conn.execute(
        "CREATE TABLE data (key TEXT PRIMARY KEY, utf16_length INTEGER, conversion_type INTEGER,"
        " compression_type INTEGER, last_access_time INTEGER, value BLOB)"
    )
    conn.execute(
        "INSERT INTO data VALUES (?, ?, ?, ?, 0, ?)",
        (fbi.LS_KEY, len(value), 1 if utf8 else 0, 1 if compress else 0,
         snappy_literals(raw) if compress else raw),
    )
    conn.commit()
    conn.close()
    return profile


def ls_key(name=fbi.LS_KEY):
    return fbi.CHROMIUM_ORIGIN + b"\x01" + name.encode()


def ls_value(text):
    return b"\x01" + text.encode("latin-1")


def write_batch(seq, entries):
    out = bytearray(seq.to_bytes(8, "little") + len(entries).to_bytes(4, "little"))
    for kind, key, value in entries:
        out.append(kind)
        out += _varint(len(key)) + key
        if kind == 1:
            out += _varint(len(value)) + value
    return bytes(out)


def log_file(batches, split=False):
    out = bytearray()
    for batch in batches:
        parts = [batch[: len(batch) // 2], batch[len(batch) // 2:]] if split else [batch]
        kinds = [2, 4] if split else [1]
        for kind, part in zip(kinds, parts):
            out += b"\x00\x00\x00\x00" + len(part).to_bytes(2, "little") + bytes([kind]) + part
    return bytes(out)


def table_block(entries):
    out = bytearray()
    for key, value in entries:  # no shared prefixes: one restart per entry is fine
        out += _varint(0) + _varint(len(key)) + _varint(len(value)) + key + value
    out += (0).to_bytes(4, "little") + (1).to_bytes(4, "little")
    return bytes(out)


def ldb_file(entries, compress=True):
    """A LevelDB table: one data block, an index block and the footer."""
    internal = [(k + ((seq << 8) | kind).to_bytes(8, "little"), v) for seq, kind, k, v in entries]
    data = bytearray()
    block = table_block(internal)
    stored = snappy_literals(block) if compress else block
    data += stored + bytes([1 if compress else 0]) + b"\x00" * 4
    handle = _varint(0) + _varint(len(stored))
    index = table_block([(internal[-1][0], handle)])
    index_off = len(data)
    data += index + b"\x00" * 5
    footer = _varint(0) + _varint(0) + _varint(index_off) + _varint(len(index))
    footer = footer.ljust(40, b"\x00") + bytes.fromhex("57fb808b247547db")
    return bytes(data + footer)


def chromium_profile(root, name="Default"):
    ldb = root / name / "Local Storage" / "leveldb"
    ldb.mkdir(parents=True)
    return ldb


# --- snappy ------------------------------------------------------------------------


def test_snappy_literals_and_copies():
    assert fbi.snappy_decompress(snappy_literals(b"hello world" * 20)) == b"hello world" * 20
    # "abcd" then copy-1 (length 8, offset 4): overlapping repeat
    data = _varint(12) + bytes([3 << 2]) + b"abcd" + bytes([((8 - 4) << 2) | 1, 4])
    assert fbi.snappy_decompress(data) == b"abcdabcdabcd"


def test_snappy_rejects_bad_data():
    with pytest.raises(ValueError):
        fbi.snappy_decompress(_varint(5) + bytes([1, 9]))  # copy before any output


# --- the value -------------------------------------------------------------------------


def test_token_is_read_from_the_session_json():
    assert fbi.token_from_value(SESSION) == TOKEN
    assert fbi.token_from_value(json.dumps(SESSION)) == TOKEN
    assert fbi.token_from_value('{"token": "short"}') is None
    assert fbi.token_from_value("") is None


# --- Firefox family -------------------------------------------------------------------


@pytest.mark.parametrize("compress", [True, False])
@pytest.mark.parametrize("utf8", [True, False])
def test_firefox_profile(tmp_path, compress, utf8):
    profile = firefox_profile(tmp_path, compress=compress, utf8=utf8)
    found = fbi.read_firefox_profile(str(profile))
    assert found.token == TOKEN


def test_firefox_profiles_under_profiles_folder(tmp_path):
    (tmp_path / "Profiles").mkdir()
    firefox_profile(tmp_path / "Profiles", "x.default")
    (tmp_path / "other").mkdir()  # no fansly storage
    assert [os.path.basename(p) for p in fbi.firefox_profiles("Zen Browser", [str(tmp_path)])] == ["x.default"]


def test_find_token_picks_the_freshest_profile(tmp_path, monkeypatch):
    old = firefox_profile(tmp_path, "old", value=SESSION.replace(TOKEN, OLD_TOKEN))
    new = firefox_profile(tmp_path, "new")
    db = lambda p: p / "storage" / "default" / fbi.FIREFOX_ORIGIN / "ls" / "data.sqlite"
    os.utime(db(old), (1000, 1000))
    os.utime(db(new), (2000, 2000))
    monkeypatch.setattr(fbi, "_firefox_roots", lambda browser: [str(tmp_path)])
    found = fbi.find_token("Zen Browser")
    assert (found.token, found.browser, found.profile_dir) == (TOKEN, "Zen Browser", str(new))


def test_signed_out_browser_says_so(tmp_path, monkeypatch):
    firefox_profile(tmp_path, value='{"id": "1"}')
    monkeypatch.setattr(fbi, "_firefox_roots", lambda browser: [str(tmp_path)])
    with pytest.raises(fbi.ImportFailed, match="isn't signed in"):
        fbi.find_token("Firefox")


def test_browser_that_never_visited_fansly(tmp_path, monkeypatch):
    monkeypatch.setattr(fbi, "_firefox_roots", lambda browser: [str(tmp_path)])
    with pytest.raises(fbi.ImportFailed, match="has visited fansly.com"):
        fbi.find_token("Firefox")


# --- Chromium family -------------------------------------------------------------------


def test_leveldb_log_newest_write_wins(tmp_path):
    ldb = chromium_profile(tmp_path)
    old = write_batch(5, [(1, ls_key(), ls_value(SESSION.replace(TOKEN, OLD_TOKEN)))])
    new = write_batch(9, [(1, ls_key("other"), ls_value("x")), (1, ls_key(), ls_value(SESSION))])
    (ldb / "000003.log").write_bytes(log_file([old, new]))
    assert fbi.read_leveldb_dir(str(ldb))[0] == TOKEN


def test_leveldb_log_record_split_in_fragments(tmp_path):
    ldb = chromium_profile(tmp_path)
    batch = write_batch(3, [(1, ls_key(), ls_value(SESSION))])
    (ldb / "000003.log").write_bytes(log_file([batch], split=True))
    assert fbi.read_leveldb_dir(str(ldb))[0] == TOKEN


@pytest.mark.parametrize("compress", [True, False])
def test_leveldb_table(tmp_path, compress):
    ldb = chromium_profile(tmp_path)
    (ldb / "000005.ldb").write_bytes(ldb_file([(4, 1, ls_key(), ls_value(SESSION))], compress))
    assert fbi.read_leveldb_dir(str(ldb))[0] == TOKEN


def test_log_overrides_an_older_table_value(tmp_path):
    ldb = chromium_profile(tmp_path)
    (ldb / "000005.ldb").write_bytes(
        ldb_file([(4, 1, ls_key(), ls_value(SESSION.replace(TOKEN, OLD_TOKEN)))]))
    (ldb / "000006.log").write_bytes(log_file([write_batch(7, [(1, ls_key(), ls_value(SESSION))])]))
    assert fbi.read_leveldb_dir(str(ldb))[0] == TOKEN


def test_signing_out_deletes_the_entry(tmp_path):
    ldb = chromium_profile(tmp_path)
    (ldb / "000005.ldb").write_bytes(ldb_file([(4, 1, ls_key(), ls_value(SESSION))]))
    (ldb / "000006.log").write_bytes(log_file([write_batch(7, [(0, ls_key(), b"")])]))
    assert fbi.read_leveldb_dir(str(ldb))[0] is None


def test_other_sites_are_ignored(tmp_path):
    ldb = chromium_profile(tmp_path)
    other = b"_https://onlyfans.com\x00\x01" + fbi.LS_KEY.encode()
    (ldb / "000003.log").write_bytes(log_file([write_batch(3, [(1, other, ls_value(SESSION))])]))
    assert fbi.read_leveldb_dir(str(ldb))[0] is None


def test_find_token_in_chromium_profiles(tmp_path, monkeypatch):
    chromium_profile(tmp_path, "Default")
    ldb = chromium_profile(tmp_path, "Profile 1")
    (ldb / "000003.log").write_bytes(log_file([write_batch(3, [(1, ls_key(), ls_value(SESSION))])]))
    monkeypatch.setattr(fbi, "_chromium_user_data_dirs", lambda browser: [str(tmp_path)])
    found = fbi.find_token("Brave")
    assert found.token == TOKEN and found.profile_dir.endswith("Profile 1")


def test_token_never_logged(tmp_path, monkeypatch, caplog):
    firefox_profile(tmp_path)
    monkeypatch.setattr(fbi, "_firefox_roots", lambda browser: [str(tmp_path)])
    with caplog.at_level("DEBUG", logger="shared"):
        fbi.find_token("Firefox")
    assert TOKEN not in caplog.text
