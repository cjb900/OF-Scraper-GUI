"""With duplicates allowed, a download is recorded even when its post had no row."""

import sqlite3
from types import SimpleNamespace

import pytest

import ofscraper.db.operations_.media as media_ops

MEDIA, OLD_POST, PAID_POST, MODEL = 2250633137, 258049161208, 11691187163537, 442464


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(
        "ofscraper.utils.settings.get_settings",
        lambda: SimpleNamespace(allow_dupe_downloads=True),
    )
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(media_ops.mediaCreate)
    # as 3.14.7 left it: one row per media id, here the unbought older message
    conn.execute(
        "INSERT INTO medias (id, media_id, post_id, api_type, media_type, unlocked, model_id)"
        " VALUES (1, ?, ?, 'Messages', 'Images', 0, ?)", (MEDIA, OLD_POST, MODEL))
    return conn


def _media(post_id):
    return SimpleNamespace(id=MEDIA, post_id=post_id, link="u", responsetype="paid",
                           mediatype="images", preview=0, linked=None, date="2026-10-18",
                           postdate="2026-10-18", duration_string=None, canview=True)


def _mark(conn, post_id):
    cur = conn.cursor()
    media_ops.update_media_table_download_helper(
        _media(post_id), MODEL, filename="a.jpeg", directory="/d", downloaded=1,
        hashdata=None, size=5, conn=conn, curr=cur)


def _rows(conn):
    return {r["post_id"]: (r["downloaded"], r["filename"]) for r in
            conn.execute("SELECT post_id, downloaded, filename FROM medias WHERE media_id=?", (MEDIA,))}


def test_download_from_a_post_without_a_row_is_recorded(db):
    _mark(db, PAID_POST)
    rows = _rows(db)
    assert rows[PAID_POST] == (1, "a.jpeg")
    assert rows[OLD_POST] == (None, None)  # the unbought message is left alone


def test_an_existing_row_is_updated_not_duplicated(db):
    _mark(db, OLD_POST)
    assert _rows(db) == {OLD_POST: (1, "a.jpeg")}
