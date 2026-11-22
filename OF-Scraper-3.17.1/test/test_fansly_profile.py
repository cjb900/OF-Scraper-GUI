"""Fansly's Profile area: the creator's avatar and banner.

The account object has both as Media (``avatar``, ``banner``). They are
downloaded as "Profile" items, like OnlyFans' avatar and header. Fansly's
links are signed and change on every request, so the items are named after
the Fansly media id, not a hash of the link (as OnlyFans does). The fixtures
are anonymised and a fake session answers each request.
"""

import asyncio
import copy

import pytest

import ofscraper.classes.of.posts as posts_
import ofscraper.data.posts.post as post
from ofscraper.sites.fansly import normalize, scrape

from test_fansly_api import CREATOR, CREATOR_ID, FakeSession, envelope, load
from test_fansly_labels import fansly, run_areas, tmp_db  # noqa: F401 (fixtures)

AVATAR_ID = 100000000000000071
BANNER_ID = 100000000000000076


def account():
    return copy.deepcopy(load("account.json")["response"][0])


def account_route(acc=None):
    def route(path, query):
        assert path == "account", path
        assert query["ids"] == str(CREATOR_ID)
        return envelope([acc if acc is not None else account()])

    return route


def sign(media, query):
    for loc in media["locations"]:
        loc["location"] = loc["location"].split("?")[0] + "?" + query


# ------------------------------------------------------------------ normalize


def test_avatar_and_banner_become_profile_items():
    items = normalize.profile_items(account())
    assert [i["id"] for i in items] == [AVATAR_ID, BANNER_ID]
    for item in items:
        assert item["responseType"] == "Profile"
        assert item["text"] == "Sample about"
        assert item["createdAt"] and item["postedAt"] == item["createdAt"]
        (media,) = item["media"]
        assert media["id"] == item["id"]
        assert media["type"] == "photo"
        assert media["canView"] is True
        assert media["files"]["full"]["url"].startswith("https://cdn3.fansly.com/")
        assert media["fansly"]["mediaId"] == str(item["id"])


def test_missing_or_linkless_pictures_are_skipped():
    acc = account()
    acc["banner"] = None
    assert [i["id"] for i in normalize.profile_items(acc)] == [AVATAR_ID]
    acc = account()
    acc["avatar"]["locations"] = []
    assert [i["id"] for i in normalize.profile_items(acc)] == [BANNER_ID]
    acc = account()
    acc.pop("avatar")
    acc.pop("banner")
    assert normalize.profile_items(acc) == []


def test_same_picture_as_avatar_and_banner_is_listed_once():
    acc = account()
    acc["banner"] = copy.deepcopy(acc["avatar"])
    assert [i["id"] for i in normalize.profile_items(acc)] == [AVATAR_ID]


def test_a_new_signed_link_keeps_the_same_file():
    # the link's query changes on every request; the id and file name must not
    first, second = account(), account()
    sign(first["avatar"], "Policy=a&Signature=b")
    sign(second["avatar"], "Policy=c&Signature=d")
    a = posts_.Post(normalize.profile_items(first)[0], CREATOR_ID, CREATOR, "Profile")
    b = posts_.Post(normalize.profile_items(second)[0], CREATOR_ID, CREATOR, "Profile")
    assert a.id == b.id == AVATAR_ID
    assert a.all_media[0].filename == b.all_media[0].filename == str(AVATAR_ID)
    assert a.all_media[0].url != b.all_media[0].url


# ------------------------------------------------------------------ scrape + area dispatch


def test_get_profile_reads_the_account_fresh(fansly):
    c = FakeSession(account_route())
    items = asyncio.run(scrape.get_profile(CREATOR_ID, CREATOR, c=c))
    assert [i["id"] for i in items] == [AVATAR_ID, BANNER_ID]
    assert [q["ids"] for q in c.calls("account")] == [str(CREATOR_ID)]


def test_get_profile_without_an_account_is_empty(fansly):
    c = FakeSession(lambda path, query: envelope([]))
    assert asyncio.run(scrape.get_profile(CREATOR_ID, CREATOR, c=c)) == []


def test_process_profile_gives_profile_posts_on_fansly(fansly):
    c = FakeSession(account_route())
    found, api = asyncio.run(post.process_profile(CREATOR, CREATOR_ID, c))
    assert api == "Profile"
    assert [p.id for p in found] == [AVATAR_ID, BANNER_ID]
    assert {p.responsetype for p in found} == {"Profile"}
    media = [m for p in found for m in p.all_media]
    assert [m.filename for m in media] == [str(AVATAR_ID), str(BANNER_ID)]
    assert all(m.url for m in media)


def test_profile_is_a_fansly_area():
    assert "Profile" in scrape.AREAS


def test_profile_area_is_scraped_not_skipped(fansly, tmp_db, monkeypatch):
    fansly.command = "download"
    fansly.text = False
    c = FakeSession(account_route())
    collection = run_areas(monkeypatch, ["Profile"], c)
    assert sorted(p.id for p in collection.posts) == [AVATAR_ID, BANNER_ID]
    assert sorted(m.id for m in collection.all_unique_media) == [AVATAR_ID, BANNER_ID]
