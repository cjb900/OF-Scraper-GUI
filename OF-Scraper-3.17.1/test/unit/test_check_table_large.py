"""The check table builds in one pass, even for a creator with thousands of items."""

import asyncio
import time
from types import SimpleNamespace

import ofscraper.commands.check as check


class _Post:
    price = 0
    db_sanitized_text = ""

    def __init__(self, n):
        self.post_media = [None] * n


def _media(mid, post_id, post):
    return SimpleNamespace(
        id=mid, post_id=post_id, date="2026-01-01", postdate="2026-01-01",
        canview=True, mpd=None, url="u", _post=post, post=post,
        mediatype="images", formatted_postdate="2026-01-01", numeric_duration=0,
        responsetype="timeline",
    )


class _Collection:
    def __init__(self, media):
        self._media = media
        self.all_media_reads = 0

    @property
    def all_media(self):
        # like the real one: rebuilt on every read
        self.all_media_reads += 1
        return list(self._media)

    def posts_with_media_id(self, mid):  # the old per-row lookup
        raise AssertionError("must not search the collection once per row")


def _run(monkeypatch, media):
    collection = _Collection(media)
    monkeypatch.setattr(check, "ROWS", [])
    monkeypatch.setattr(check, "_disk_check", False)
    monkeypatch.setattr(check, "get_media_post_files_downloaded", lambda **k: {})
    monkeypatch.setattr(check.settings, "get_settings", lambda: SimpleNamespace(allow_dupe_downloads=False))
    monkeypatch.setitem(check.check_user_dict, "7", {"collection": collection})
    asyncio.run(check.row_gather("model", 7))
    return collection, check.ROWS


def test_other_posts_with_the_same_media(monkeypatch):
    shared = _Post(2)
    media = [_media(1, 10, shared), _media(1, 11, shared), _media(2, 10, shared)]
    collection, rows = _run(monkeypatch, media)
    by_key = {(r["media_id"], r["post_id"]): r for r in rows}
    assert by_key[(1, 10)]["other_posts_with_media"] == [11]
    assert by_key[(1, 11)]["other_posts_with_media"] == [10]
    assert by_key[(2, 10)]["other_posts_with_media"] == []


def test_thousands_of_items_in_one_pass(monkeypatch):
    post = _Post(1)
    media = [_media(i, i, post) for i in range(14000)]
    start = time.monotonic()
    collection, rows = _run(monkeypatch, media)
    assert len(rows) == 14000
    assert collection.all_media_reads == 1
    assert time.monotonic() - start < 10
