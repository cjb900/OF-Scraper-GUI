"""Fansly user lists (--ul / the GUI's User Lists box) and black lists.

Request and reply shapes are from a fansly.com HAR (2026-11-21):
lists/account?itemId= -> [{id, accountId, type, label, itemCount}]
lists/itemsnew?listId=<id>&limit=50&sortMode=3 -> [{id: <account id>, sortId, listId, ...}]
"""
import asyncio
import contextlib
import copy
from urllib.parse import parse_qs, urlparse

import pytest

from ofscraper.sites.fansly import api, constants, scrape

LIST_TEST = "900000000000000001"
LIST_BAD = "900000000000000002"
A = "100000000000000901"
B = "100000000000000902"
C = "100000000000000903"
ACCOUNTS = {A: "creatora", B: "creatorb", C: "creatorc"}


def envelope(response):
    return {"success": True, "response": response}


class FakeResponse:
    def __init__(self, data):
        self._data = data

    async def json_(self):
        return copy.deepcopy(self._data)


class FakeSession:
    def __init__(self, route):
        self.route = route
        self.urls = []

    @contextlib.asynccontextmanager
    async def requests_async(self, url=None, **kwargs):
        self.urls.append(url)
        parsed = urlparse(url)
        path = parsed.path[len(urlparse(constants.API_BASE).path):]
        query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
        yield FakeResponse(self.route(path, query))

    def calls(self, path):
        return [
            {k: v[0] for k, v in parse_qs(urlparse(u).query, keep_blank_values=True).items()}
            for u in self.urls
            if urlparse(u).path.endswith("/" + path)
        ]


def _lists():
    return [
        {"id": LIST_TEST, "accountId": "1", "pos": None, "type": 1, "label": "Test", "itemCount": 2},
        {"id": LIST_BAD, "accountId": "1", "pos": None, "type": 1, "label": "nope", "itemCount": 1},
    ]


def _route(members, following=()):
    def route(path, query):
        if path == "lists/account":
            return envelope(_lists())
        if path == "lists/itemsnew":
            ids = members[query["listId"]]
            return envelope(
                [{"id": i, "sortId": str(int(i) + 5), "listId": query["listId"], "type": 1, "metadata": ""} for i in ids]
            )
        if path == "account":
            wanted = query["ids"].split(",")
            return envelope([{"id": i, "username": ACCOUNTS[i]} for i in wanted if i in ACCOUNTS])
        if path.endswith("/following"):
            return envelope([{"accountId": i} for i in following] if query["offset"] == "0" else [])
        raise AssertionError(path)

    return route


@contextlib.asynccontextmanager
async def _ctx(c):
    yield c


def _run(monkeypatch, route, **kw):
    c = FakeSession(route)
    monkeypatch.setattr(scrape, "_session", lambda _c: _ctx(c))
    import ofscraper.utils.me as me_util

    monkeypatch.setattr(me_util, "get_id", lambda: "1")
    models = asyncio.run(scrape.get_models(**kw))
    return c, sorted(m["username"] for m in models)


def test_user_list_loads_only_its_members(monkeypatch):
    c, names = _run(
        monkeypatch, _route({LIST_TEST: [A, B]}, following=[A, B, C]),
        userlists=["test"], blacklists=[],
    )
    assert names == ["creatora", "creatorb"]
    assert c.calls("lists/itemsnew") == [
        {"listId": LIST_TEST, "limit": "50", "sortMode": "3", "ngsw-bypass": "true"}
    ]
    assert not c.calls("account/1/following")


def test_list_names_match_case_insensitively(monkeypatch):
    _, names = _run(monkeypatch, _route({LIST_TEST: [A]}), userlists=["TEST"], blacklists=[])
    assert names == ["creatora"]


def test_reserved_names_mean_no_filter(monkeypatch):
    _, names = _run(
        monkeypatch, _route({}, following=[A, B]), userlists=["main", "ofscraper.main"], blacklists=[]
    )
    assert names == ["creatora", "creatorb"]


def test_unknown_list_loads_nobody_and_warns(monkeypatch, caplog):
    with caplog.at_level("WARNING", logger="shared"):
        _, names = _run(monkeypatch, _route({}, following=[A]), userlists=["vip accounts"], blacklists=[])
    assert names == []
    assert "not found: vip accounts" in caplog.text


def test_black_list_drops_its_members(monkeypatch):
    _, names = _run(
        monkeypatch, _route({LIST_BAD: [B]}, following=[A, B, C]), userlists=[], blacklists=["nope"]
    )
    assert names == ["creatora", "creatorc"]


def test_named_creators_ignore_lists(monkeypatch):
    def route(path, query):
        assert not path.startswith("lists/"), path
        if "usernames" in query:
            return envelope([{"id": B, "username": "creatorb"}])
        return envelope([])

    _, names = _run(monkeypatch, route, usernames=["creatorb"], userlists=["test"], blacklists=["nope"])
    assert names == ["creatorb"]


def test_list_items_page_until_item_count(monkeypatch):
    ids = [str(100000000000001000 + i) for i in range(7)]

    def route(path, query):
        assert path == "lists/itemsnew"
        start = 0
        if "before" in query:
            start = next(i for i, x in enumerate(ids) if str(int(x) + 5) == query["before"]) + 1
        page = ids[start : start + int(query["limit"])]
        return envelope([{"id": i, "sortId": str(int(i) + 5)} for i in page])

    c = FakeSession(route)
    out = asyncio.run(api.list_account_ids(c, LIST_TEST, item_count=7, limit=3))
    assert out == ids
    assert [q.get("before") for q in c.calls("lists/itemsnew")] == [None, str(int(ids[2]) + 5), str(int(ids[5]) + 5)]


def test_list_paging_stops_when_cursor_is_ignored(monkeypatch, caplog):
    # a server that ignores before= returns page 1 again: no new ids, stop
    def route(path, query):
        return envelope([{"id": i, "sortId": i} for i in (A, B)])

    c = FakeSession(route)
    with caplog.at_level("WARNING", logger="shared"):
        out = asyncio.run(api.list_account_ids(c, LIST_TEST, item_count=5, limit=2))
    assert out == [A, B]
    assert len(c.calls("lists/itemsnew")) == 2
    assert "got 2 of 5" in caplog.text
