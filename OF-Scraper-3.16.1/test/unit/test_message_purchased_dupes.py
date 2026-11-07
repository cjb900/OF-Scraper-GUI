"""Unit tests for Messages ↔ Purchased duplicate collapse."""

from types import SimpleNamespace

from ofscraper.filters.media.message_purchased_dupes import (
    collapse_message_purchased_dupes,
    media_response_bucket,
)


def test_media_response_bucket():
    assert media_response_bucket("Messages") == "messages"
    assert media_response_bucket("Paid") == "purchased"
    assert media_response_bucket("Purchased") == "purchased"
    assert media_response_bucket("Timeline") == "other"


def test_collapse_prefers_messages_over_purchased():
    media = [
        SimpleNamespace(id=1, responsetype="Messages"),
        SimpleNamespace(id=1, responsetype="Paid"),
        SimpleNamespace(id=2, responsetype="Timeline"),
        SimpleNamespace(id=2, responsetype="Pinned"),  # other dupe kept
        SimpleNamespace(id=3, responsetype="Purchased"),  # alone — kept
    ]
    out = collapse_message_purchased_dupes(media)
    assert len(out) == 4
    assert {m.id for m in out if m.responsetype == "Paid"} == set()
    assert any(m.id == 1 and m.responsetype == "Messages" for m in out)
    assert any(m.id == 2 and m.responsetype == "Pinned" for m in out)
    assert any(m.id == 3 and m.responsetype == "Purchased" for m in out)


def test_collapse_noop_without_overlap():
    media = [
        SimpleNamespace(id=1, responsetype="Messages"),
        SimpleNamespace(id=2, responsetype="Paid"),
    ]
    out = collapse_message_purchased_dupes(media)
    assert len(out) == 2
