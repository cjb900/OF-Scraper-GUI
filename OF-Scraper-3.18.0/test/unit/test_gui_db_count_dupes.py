"""The run summary's "DB: downloaded/total" counts each media once. With
allow-dupes a media has one row per post, and it counts as downloaded if any
of those rows is (it used to take the first row's flag, so 912 instead of 947)."""

import sqlite3
from types import SimpleNamespace

import ofscraper.classes.placeholder as placeholder
from ofscraper.gui.utils import workflow


def _make_db(path, rows):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE medias (media_id INTEGER, post_id INTEGER, link TEXT,"
        " directory TEXT, filename TEXT, size INTEGER, api_type TEXT,"
        " media_type TEXT, preview INTEGER, linked TEXT, downloaded INTEGER,"
        " created_at TEXT, unlocked INTEGER, model_id INTEGER, posted_at TEXT,"
        " hash TEXT, duration REAL)"
    )
    conn.executemany(
        "INSERT INTO medias (media_id, post_id, media_type, downloaded, model_id)"
        " VALUES (?, ?, ?, ?, 1)",
        rows,
    )
    conn.commit()
    conn.close()


def test_repost_counts_once_as_downloaded_if_any_copy_is(tmp_path, monkeypatch):
    db = tmp_path / "user_data.db"
    _make_db(
        db,
        [
            # a repost: the first row (older post) isn't downloaded, the second is
            (10, 100, "Images", 0),
            (10, 200, "Images", 1),
            # downloaded once
            (11, 101, "Videos", 1),
            # never downloaded
            (12, 102, "Images", 0),
        ],
    )

    class _Ph:
        def databasePathHelper(self, model_id, username):
            return str(db)

    monkeypatch.setattr(placeholder, "databasePlaceholder", _Ph)
    stats = workflow._load_models_from_db(
        [SimpleNamespace(id=1, name="someone")], stats_only=True
    )
    st = stats["someone"]
    assert (st["photos"], st["videos"]) == (2, 1)
    assert (st["dl_photos"], st["dl_videos"]) == (1, 1)
