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


# --- the Media tab -------------------------------------------------------------------------
#
# A creator's Media tab can list media no timeline post returns. A page lists
# media offers (mediaOfferId = accountMedia id, correlationId = its post) and
# embeds the accountMedia, bundles and posts in aggregationData.

WALL = "100000000000000900"


def fake_account_media(new_id, media_id, access=True):
    template = load("timeline_missing_media.json")["response"][0]
    item = copy.deepcopy(template)
    item["id"] = new_id
    item["mediaId"] = media_id
    item["access"] = access
    item["media"]["id"] = media_id
    return item


def offer(offer_id, account_media_id, post_id=""):
    return {"id": offer_id, "mediaOfferId": account_media_id, "mediaId": "1",
            "mediaType": 2, "correlationId": post_id, "locationId": WALL, "locationType": 1002}


def media_tab_page(known_id):
    """Four offers: one the timeline gave, one in an embedded post, one with no
    post, and one Fansly left out of aggregationData."""
    post = {"id": "100000000000000950", "accountId": str(CREATOR_ID), "content": "[s:lg]hi[/s]",
            "createdAt": 1700000000, "attachments": [
                {"contentType": 1, "contentId": "100000000000000901", "pos": 0}]}
    return envelope({
        "data": [
            offer("9004", known_id),
            offer("9003", "100000000000000901", post["id"]),
            offer("9002", "100000000000000902"),
            offer("9001", "100000000000000903"),
        ],
        "aggregationData": {
            "accountMedia": [
                fake_account_media("100000000000000901", "100000000000000801"),
                fake_account_media("100000000000000902", "100000000000000802", access=False),
            ],
            "accountMediaBundles": [],
            "posts": [post],
        },
    })


def account_with_main_wall():
    account = load("account.json")
    account["response"][0]["walls"] = [{"id": WALL, "pos": 0, "name": "Posts ", "defaultWall": True}]
    return account


def media_tab_route(known_id, pages=None):
    timeline_answer = route(account=account_with_main_wall())
    late = fake_account_media("100000000000000903", "100000000000000803")
    calls = []

    def answer(path, query):
        if path == "mediaoffers/location":
            calls.append(query)
            assert query["locationId"] == WALL and query["accountId"] == str(CREATOR_ID)
            if query["before"] == "" and query["mediaType"] == "2":
                return pages[0] if pages else media_tab_page(known_id)
            return envelope({"data": [], "aggregationData": {}})
        if path == "account/media" and "100000000000000903" in query["ids"]:
            return envelope([late])
        return timeline_answer(path, query)

    answer.calls = calls
    return answer


def known_timeline_id():
    _, report = scan()
    return sorted(report.account_media)[0]


def test_the_main_wall_is_the_media_tab_location():
    walls = [{"id": "2", "pos": 1, "name": "Extra"}, {"id": "1", "pos": 0, "name": "Posts"}]
    assert normalize.main_wall_id(walls, True) == "1"
    assert normalize.main_wall_id([{"id": "5", "defaultWall": True, "pos": 3}], True) == "5"
    assert normalize.main_wall_id([{"id": "2", "pos": 2}], False) is None


def test_media_tab_items_the_timeline_gave_are_left_alone():
    known = known_timeline_id()
    page = media_tab_page(known)["response"]
    report = normalize.ScanReport()
    extra = [fake_account_media("100000000000000903", "100000000000000803")]
    found = normalize.media_tab_posts(page, {known}, extra, report=report)
    ids = {m["fansly"]["accountMediaId"] for p in found for m in p["media"]}
    assert known not in ids
    assert {"100000000000000901", "100000000000000902", "100000000000000903"} <= ids


def test_an_item_in_an_embedded_post_keeps_that_post():
    page = media_tab_page("x")["response"]
    found = normalize.media_tab_posts(page, set(), ())
    post = next(p for p in found if p["id"] == 100000000000000950)
    assert post["text"] == "hi"
    assert [m["fansly"]["accountMediaId"] for m in post["media"]] == ["100000000000000901"]


def test_an_item_without_a_post_becomes_its_own_post():
    page = media_tab_page("x")["response"]
    report = normalize.ScanReport()
    found = normalize.media_tab_posts(page, {"x"}, (), report=report)
    alone = next(p for p in found if p["id"] == 100000000000000902)
    assert alone["responseType"] == "post"
    assert alone["media"] and alone["isOpened"] is False
    # not sent and not fetched: counted, not lost silently
    assert report.dropped["Media tab item Fansly didn't send"] == 1


def test_the_scrape_adds_media_tab_items_and_reports_them(after_none, caplog):
    known = known_timeline_id()
    answer = media_tab_route(known)
    session = Session(answer)
    with caplog.at_level(logging.INFO, logger="shared"):
        posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=session))
    ids = {m["fansly"]["accountMediaId"] for p in posts for m in p["media"]}
    assert {"100000000000000901", "100000000000000902", "100000000000000903"} <= ids
    # the media the timeline gave isn't added again
    def uses(found):
        return sum(1 for p in found for m in p["media"] if m["fansly"]["accountMediaId"] == known)

    plain, _ = scan()
    assert uses(posts) == uses(plain)
    # photos, then videos, each paged with the last item's id until an empty page
    assert [(q["mediaType"], q["before"]) for q in answer.calls] == [
        ("1", ""), ("2", ""), ("2", "9001")]
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Media tab: 4 items" in text
    assert "Media tab only: 1 videos (locked)" in text
    assert "Media tab only: 2 videos (viewable)" in text


def test_a_media_tab_failure_keeps_the_timeline(after_none, caplog):
    def answer(path, query):
        if path == "mediaoffers/location":
            raise RuntimeError("boom")
        return route(account=account_with_main_wall())(path, query)

    with caplog.at_level(logging.INFO, logger="shared"):
        posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=Session(answer)))
    plain, _ = scan()
    assert posts == plain
    assert "Media tab: not read (RuntimeError)" in "\n".join(r.getMessage() for r in caplog.records)


def test_no_main_wall_skips_the_media_tab(after_none, caplog):
    # the fixture account's walls are all named tabs
    with caplog.at_level(logging.INFO, logger="shared"):
        asyncio.run(scrape.get_timeline_posts(
            CREATOR_ID, "samplecreator1", c=Session(route(account=load("account.json")))))
    assert "Media tab: skipped, the creator has no main wall" in "\n".join(
        r.getMessage() for r in caplog.records)


def test_paging_stops_at_the_after_date():
    old = fake_account_media("100000000000000904", "100000000000000804")
    old["createdAt"] = 1600000000
    page = envelope({"data": [offer("9010", "100000000000000904")],
                     "aggregationData": {"accountMedia": [old]}})
    calls = []

    def answer(path, query):
        calls.append(query["before"])
        return page

    pages = asyncio.run(_collect(api.media_tab_pages(Session(answer), CREATOR_ID, WALL, after=1700000000)))
    assert len(pages) == 1 and calls == [""]


async def _collect(agen):
    return [x async for x in agen]


def test_photos_and_videos_are_paged_separately(after_none, caplog):
    # Fansly pages the all-types list only once (its second page is empty), so
    # the Media tab is read per type, like its Photos and Videos views
    known = known_timeline_id()
    calls = []
    base = route(account=account_with_main_wall())

    def answer(path, query):
        if path == "mediaoffers/location":
            calls.append((query["mediaType"], query["before"]))
            if query["mediaType"] == "2" and query["before"] == "":
                return media_tab_page(known)
            return envelope({"data": [], "aggregationData": {}})
        if path == "account/media" and "100000000000000903" in query["ids"]:
            return envelope([fake_account_media("100000000000000903", "100000000000000803")])
        return base(path, query)

    with caplog.at_level(logging.INFO, logger="shared"):
        posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=Session(answer)))
    assert calls == [("1", ""), ("2", ""), ("2", "9001")]
    ids = {m["fansly"]["accountMediaId"] for p in posts for m in p["media"]}
    assert "100000000000000901" in ids
    text = "\n".join(r.getMessage() for r in caplog.records)
    # the first page of each try is logged, without any login data
    assert "Fansly Media tab: mediaoffers/location?locationId=" in text
    assert "0 items" in text and "4 items" in text
    assert "type 1: 0 items in 0 pages" in text and "type 2: 4 items in 1 pages" in text


def test_an_item_on_both_lists_is_added_once(after_none):
    known = known_timeline_id()
    base = route(account=account_with_main_wall())

    def answer(path, query):
        if path == "mediaoffers/location":
            if query["before"] == "":
                return media_tab_page(known)
            return envelope({"data": [], "aggregationData": {}})
        if path == "account/media" and "100000000000000903" in query["ids"]:
            return envelope([fake_account_media("100000000000000903", "100000000000000803")])
        return base(path, query)

    posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, "samplecreator1", c=Session(answer)))
    added = [m["fansly"]["accountMediaId"] for p in posts for m in p["media"]
             if m["fansly"]["accountMediaId"].startswith("1000000000000009")]
    assert sorted(added) == sorted(set(added))
