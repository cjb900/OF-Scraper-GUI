"""Check mode: a media sold in two paid messages is downloaded once (for the
first post) when allow-dupes is off, so the second post's row counts as
downloaded too. With allow-dupes on, each post needs its own copy."""

import asyncio
from types import SimpleNamespace

import pytest

import ofscraper.commands.check as check
from ofscraper.classes.of.posts import Post

MODEL_ID = 1000
USERNAME = "a_creator"
WHEN = "2024-05-01T20:00:00+00:00"


def paid_message(post_id):
    raw = {
        "id": post_id,
        "createdAt": WHEN,
        "text": "",
        "price": 10,
        "fromUser": {"id": MODEL_ID},
        "media": [
            {
                "id": 3000,
                "type": "video",
                "canView": True,
                "createdAt": WHEN,
                "files": {"full": {"url": "https://example.invalid/a.mp4"}},
            }
        ],
    }
    return Post(raw, MODEL_ID, USERNAME, "messages")


@pytest.mark.parametrize("allow_dupes, expected", [(False, [True, True]), (True, [True, False])])
def test_media_downloaded_for_one_post(monkeypatch, allow_dupes, expected):
    media = paid_message(2000).all_media + paid_message(2001).all_media
    collection = SimpleNamespace(all_media=media, posts_with_media_id=lambda _id: [])
    monkeypatch.setattr(
        check,
        "get_media_post_files_downloaded",
        lambda **kw: {(3000, 2000): ("/dl", "a.mp4")},
    )
    monkeypatch.setattr(check.settings, "allow_dupes", lambda: allow_dupes)
    monkeypatch.setattr(check, "check_user_dict", {str(MODEL_ID): {"collection": collection}})
    monkeypatch.setattr(check, "ROWS", [])

    asyncio.run(check.row_gather(USERNAME, MODEL_ID))

    rows = sorted(check.ROWS, key=lambda r: str(r["post_id"]))
    assert [r["downloaded"] for r in rows] == expected
