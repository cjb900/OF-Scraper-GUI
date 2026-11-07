# GUI tree tests from the 3.14.7 tree's test/unit/test_messages_pagination.py that the fork's test/test_messages_pagination.py does not have
import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = pytest.mark.unit

import ofscraper.data.api.messages as messages


class FakeResponse:
    def __init__(self, data):
        self.status = 200
        self._data = data

    async def json_(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeClient:
    """Paginates newest-first like the chats API: ?id=X returns messages older than X."""

    def __init__(self, ids, page_size=3):
        # createdAt equals the id, so ordering by id and by time agree
        self.messages = [{"id": i, "createdAt": i} for i in sorted(ids, reverse=True)]
        self.page_size = page_size
        self.cursors = []

    def requests_async(self, url, **kwargs):
        cursor = parse_qs(urlsplit(url).query).get("id", [None])[0]
        self.cursors.append(cursor)
        older = [
            m for m in self.messages if cursor is None or m["id"] < int(cursor)
        ]
        page = older[: self.page_size]
        has_more = len(older) > self.page_size
        return FakeResponse({"list": page, "hasMore": has_more})


def collect(client, **kwargs):
    async def run():
        out = []
        async for batch in messages.scrape_messages(client, 1, "user", **kwargs):
            out.extend(m["id"] for m in batch)
        return out

    return asyncio.run(run())


@pytest.fixture
def recorded_tasks(monkeypatch):
    calls = []

    def fake_scrape_messages(c, model_id, username, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(messages, "scrape_messages", fake_scrape_messages)
    return calls


def chunks():
    # Newest-first chunks, as get_split_array produces them
    return [
        [{"post_id": 9, "created_at": 900}, {"post_id": 8, "created_at": 800}],
        [{"post_id": 7, "created_at": 700}, {"post_id": 6, "created_at": 600}],
        [{"post_id": 5, "created_at": 500}],
    ]


def set_before(monkeypatch, before):
    monkeypatch.setattr(
        messages.settings, "get_settings", lambda: SimpleNamespace(before=before)
    )


def test_anchor_is_strictly_newer_than_before(monkeypatch):
    # chunk 0 starts at the anchor and the API returns only older messages, so
    # a message exactly at 'before' must not be the anchor or it is skipped
    # (and then flagged as deleted by the ghost check)
    async def cache(model_id, username):
        return [{"post_id": i, "created_at": i} for i in (68, 69, 70, 71, 72)]

    monkeypatch.setattr(messages, "get_old_messages", cache)
    set_before(monkeypatch, 70)
    split, anchor = asyncio.run(messages.get_split_array(1, "user", 0))
    assert anchor == 71
    assert [x["post_id"] for chunk in split for x in chunk] == [70, 69, 68]
