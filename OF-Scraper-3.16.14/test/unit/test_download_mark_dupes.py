"""Marking a download in the database with duplicate downloads allowed.

The allow-dupes UPDATE (keyed on post_id too) must set the same columns as
upstream's mediaUpdateDownload, skip_permanent included: a missing column
failed every download's database write ("8 bindings, 9 supplied").
"""

import sqlite3
from types import SimpleNamespace

import pytest

import ofscraper.db.operations_.media as media_ops
import ofscraper.utils.settings as settings


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE medias (media_id INT, model_id INT, post_id INT, directory TEXT,"
        " filename TEXT, size INT, downloaded INT, hash TEXT, skip_permanent INT)"
    )
    conn.execute("INSERT INTO medias (media_id, model_id, post_id) VALUES (1, 9, 100)")
    conn.execute("INSERT INTO medias (media_id, model_id, post_id) VALUES (1, 9, 200)")
    yield conn
    conn.close()


@pytest.mark.parametrize("allow_dupes", [True, False])
def test_download_is_marked(db, monkeypatch, allow_dupes):
    monkeypatch.setattr(
        settings, "get_settings", lambda: SimpleNamespace(allow_dupe_downloads=allow_dupes)
    )
    media = SimpleNamespace(id=1, post_id=100)
    media_ops.update_media_table_download_helper(
        media, 9, filename="a.jpg", directory="/d", hashdata="h", conn=db,
        downloaded=1, curr=db.cursor(), size=5, skip_permanent=True,
    )
    rows = db.execute("SELECT post_id, downloaded, skip_permanent FROM medias ORDER BY post_id").fetchall()
    if allow_dupes:
        assert rows == [(100, 1, 1), (200, None, None)]  # only this post's row
    else:
        assert rows == [(100, 1, 1), (200, 1, 1)]
