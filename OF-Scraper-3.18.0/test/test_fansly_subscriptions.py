"""Fansly's creator list has the creators you're subscribed to as well as the
ones you follow: subscribing doesn't follow on Fansly, so a new subscription
was missing from Select Models (maybemolly, 2026-11-23)."""

import asyncio

from ofscraper.sites.fansly import api, scrape

from test_fansly_api import FakeSession, envelope
from test_fansly_lists import A, ACCOUNTS, B, C, _ctx
from test_fansly_labels import fansly  # noqa: F401 (fixture)


def _route(following=(), subscriptions=None, fail=False):
    def route(path, query):
        if path.endswith("/following"):
            return envelope([{"accountId": i} for i in following] if query["offset"] == "0" else [])
        if path == "subscriptions":
            if fail:
                raise RuntimeError("Fansly answered 500")
            return envelope(subscriptions)
        if path == "account":
            wanted = query["ids"].split(",")
            return envelope([{"id": i, "username": ACCOUNTS[i]} for i in wanted if i in ACCOUNTS])
        raise AssertionError(path)

    return route


def _names(monkeypatch, route):
    c = FakeSession(route)
    monkeypatch.setattr(scrape, "_session", lambda _c: _ctx(c))
    import ofscraper.utils.me as me_util

    monkeypatch.setattr(me_util, "get_id", lambda: "1")
    models = asyncio.run(scrape.get_models(userlists=[], blacklists=[]))
    return c, [m["username"] for m in models]


def _subs(*ids):
    return {"stats": {}, "subscriptions": [{"id": "9" + i, "accountId": i, "status": 3} for i in ids]}


def test_a_subscription_that_isnt_followed_is_listed(fansly, monkeypatch):
    _, names = _names(monkeypatch, _route(following=[A], subscriptions=_subs(B)))
    assert sorted(names) == sorted([ACCOUNTS[A], ACCOUNTS[B]])


def test_followed_and_subscribed_creators_are_listed_once(fansly, monkeypatch):
    c, names = _names(monkeypatch, _route(following=[A, B], subscriptions=_subs(B, C)))
    assert sorted(names) == sorted([ACCOUNTS[A], ACCOUNTS[B], ACCOUNTS[C]])
    asked = [i for q in c.calls("account") for i in q["ids"].split(",")]
    assert sorted(asked) == sorted([A, B, C])


def test_a_bare_list_reply_is_read_too(fansly, monkeypatch):
    _, names = _names(monkeypatch, _route(following=[], subscriptions=[{"accountId": C}]))
    assert names == [ACCOUNTS[C]]


def test_an_unreadable_subscriptions_reply_keeps_the_followed_creators(fansly, monkeypatch):
    _, names = _names(monkeypatch, _route(following=[A], fail=True))
    assert names == [ACCOUNTS[A]]
    _, names = _names(monkeypatch, _route(following=[A], subscriptions={"unexpected": True}))
    assert names == [ACCOUNTS[A]]


def test_subscribed_ids_skips_items_without_an_account(fansly):
    c = FakeSession(_route(subscriptions={"subscriptions": [{"accountId": A}, {"id": "x"}, "junk", {"accountId": A}]}))
    assert asyncio.run(api.subscribed_ids(c)) == [A]
