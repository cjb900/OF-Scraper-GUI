"""The Fansly timeline check: what a scan found and what it couldn't use,
next to the media counts Fansly shows on the profile.

A creator showed 5.5K photos and 3.5K videos on Fansly, and a full scrape
downloaded fewer videos with nothing failed. Attachments the parser can't
match used to be skipped without a word; the report counts them by reason.
"""

import asyncio
import copy
import json
import logging
import pathlib

import pytest

from ofscraper.sites.fansly import api, normalize, scrape

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures" / "fansly"
CREATOR_ID = 100000000000000002


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def envelope(response):
    return {"success": True, "response": response}


class Resp:
    def __init__(self, data):
        self._data = data

    async def json_(self):
        return copy.deepcopy(self._data)


class Session:
    def __init__(self, route):
        self.route = route

    def requests_async(self, url=None, **kwargs):
        from contextlib import asynccontextmanager
        from urllib.parse import parse_qs, urlparse

        from ofscraper.sites.fansly import constants

        parsed = urlparse(url)
        path = parsed.path[len(urlparse(constants.API_BASE).path):]
        query = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}

        @asynccontextmanager
        async def cm():
            yield Resp(self.route(path, query))

        return cm()


def route(timeline=None, backfill=None, account=None):
    timeline = timeline or load("timeline.json")
    backfill = load("timeline_missing_media.json")["response"] if backfill is None else backfill

    def answer(path, query):
        if path == f"timelinenew/{CREATOR_ID}":
            if query["before"] == "0":
                return timeline
            return envelope({"posts": [], "accountMedia": [], "accountMediaBundles": []})
        if path == "account/media":
            wanted = query["ids"].split(",")
            return envelope([m for m in backfill if m["id"] in wanted])
        if path == "account":
            if account is None:
                raise RuntimeError("no account")
            return account
        raise AssertionError(f"unexpected Fansly call {path}")

    return answer


def scan(**kw):
    report = normalize.ScanReport()
    posts = asyncio.run(api.timeline(Session(route(**kw)), CREATOR_ID, report=report))
    return posts, report


def test_a_clean_scan_counts_every_media_and_drops_nothing():
    posts, report = scan()
    media = [m for p in posts for m in p["media"] if not m["fansly"]["isPreview"]]
    assert report.posts == len(posts)
    assert sum(report.uses.values()) == len(media)
    assert len(report.account_media) == len({m["fansly"]["accountMediaId"] for m in media})
    assert report.backfill_asked == report.backfill_returned > 0
    assert not report.dropped


def test_bundle_members_fansly_didnt_send_are_counted():
    posts, report = scan(backfill=[])
    assert report.backfill_returned == 0
    assert report.dropped["bundle member Fansly didn't send"] == report.backfill_asked
    assert "bundle media fetched separately: 0 of" in report.summary("x")


def test_other_attachment_types_are_counted_not_dropped_silently():
    timeline = load("timeline.json")
    post = timeline["response"]["posts"][0]
    post.setdefault("attachments", []).append({"contentType": 7100, "contentId": "1", "pos": 99})
    post["attachments"].append({"contentType": 2, "contentId": "424242", "pos": 100})
    post["attachments"].append({"contentType": 1, "contentId": "434343", "pos": 101})
    _, report = scan(timeline=timeline)
    assert report.dropped["attachment type 7100 (not media)"] == 1
    assert report.dropped["bundle Fansly didn't send"] == 1
    # the backfill is asked for it, and Fansly doesn't return it
    assert report.dropped["media Fansly didn't send"] == 1


def test_the_report_changes_nothing_in_the_posts():
    with_report, _ = scan()
    without = asyncio.run(api.timeline(Session(route()), CREATOR_ID))
    assert with_report == without


def test_summary_puts_fansly_counts_next_to_the_scan():
    _, report = scan()
    stats = load("account.json")["response"][0]["timelineStats"]
    text = report.summary("samplecreator1", stats)
    assert "Fansly counts: 37 images + 36 in bundles, 383 videos + 46 in bundles, 7 bundles" in text
    assert f"scan found {report.posts} posts" in text
    assert "videos:" in text and "counting repeats" in text
    assert "not used: nothing" in text


@pytest.fixture
def after_none(monkeypatch):
    monkeypatch.setattr(scrape, "_after", lambda: None)


def test_the_scrape_logs_the_check(after_none, caplog):
    session = Session(route(account=load("account.json")))
    with caplog.at_level(logging.INFO, logger="shared"):
        posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=session))
    assert posts
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Fansly timeline check for samplecreator1:" in text
    assert "Fansly counts: 37 images" in text


def test_the_scrape_still_returns_posts_when_the_counts_cant_be_read(after_none, caplog):
    session = Session(route(account=None))
    with caplog.at_level(logging.INFO, logger="shared"):
        posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=session))
    assert posts
    assert "Fansly counts: not available" in "\n".join(r.getMessage() for r in caplog.records)
