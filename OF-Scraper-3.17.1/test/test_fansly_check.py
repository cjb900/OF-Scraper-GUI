"""Check posts, messages and purchased on a Fansly profile.

The check commands build the same table as for OnlyFans: every media item
Fansly lists for the creator, with whether it is downloaded (and, with the
disk option, whether its file is still on disk). The creator is looked up
through Fansly's account API and the areas through the Fansly fetchers the
normal scrape uses. The tests run the real runners and retrievers into a real
SQLite database in a temporary folder; a fake session answers each Fansly
request from the anonymised fixtures, and any OnlyFans call fails.
"""

import asyncio
import contextlib
import logging
from types import SimpleNamespace

import pytest

import ofscraper.classes.placeholder as placeholder
import ofscraper.commands.check as check
import ofscraper.db.operations as operations
import ofscraper.gui.site_context as site_context
import ofscraper.utils.settings as settings

from test_fansly_api import (
    CREATOR,
    CREATOR_ID,
    DM_CREATOR,
    DM_CREATOR_ID,
    FakeSession,
    both_routes,
    envelope,
    load,
    timeline_route,
)


def account_route(path, query):
    """``account?usernames=`` / ``account?ids=`` for the two fixture creators."""
    accounts = []
    base = load("account.json")["response"][0]
    for username, account_id in ((CREATOR, CREATOR_ID), (DM_CREATOR, DM_CREATOR_ID)):
        wanted = query.get("usernames", "").split(",") + query.get("ids", "").split(",")
        if username in wanted or str(account_id) in wanted:
            accounts.append(dict(base, id=str(account_id), username=username))
    return envelope(accounts)


def purchases_route(path, query):
    messages_ = load("messages.json")["response"]
    return envelope({
        "accountMediaOrders": [{"accountMediaId": "100000000000000149", "createdAt": 1777913614}],
        "accountMedia": messages_["accountMedia"],
    })


def route(path, query):
    if path == "account":
        return account_route(path, query)
    if path == "account/media/orders/":
        return purchases_route(path, query)
    if path.startswith("timelinenew/"):
        return timeline_route(f"timelinenew/{CREATOR_ID}", query)
    return both_routes(path, query)


@pytest.fixture
def env(monkeypatch, tmp_path):
    db = tmp_path / "user_data.db"
    monkeypatch.setattr(
        placeholder.databasePlaceholder, "databasePathHelper", lambda self, mid, name: db
    )
    monkeypatch.setattr(operations, "create_backup", lambda *a, **k: None)
    real = settings.get_settings()

    class Stub(SimpleNamespace):
        def __getattr__(self, name):
            return getattr(real, name)

    stub = Stub(
        site="fansly", force=True, metadata=None, after=None, post_id=None,
        url=[CREATOR], file=None, check_usernames=[CREATOR], file_usernames=None,
        check_area=["Timeline"], timeline_strict=False, usernames=None, label=None,
        allow_dupe_downloads=False, command="post_check",
    )
    monkeypatch.setattr(settings, "get_settings", lambda: stub)
    c = FakeSession(route)

    @contextlib.asynccontextmanager
    async def session(*args, **kwargs):
        yield c

    monkeypatch.setattr(
        check.manager, "Manager", SimpleNamespace(session=SimpleNamespace(aget_ofsession=session))
    )

    def no_onlyfans(*args, **kwargs):
        raise AssertionError("the Fansly check called OnlyFans")

    for module, name in [
        (check.timeline, "get_timeline_posts"),
        (check.messages_, "get_messages"),
        (check.paid_, "get_paid_posts"),
        (check.profile, "get_id"),
        (check.profile, "scrape_profile"),
        (check.auth_requests, "make_headers"),
    ]:
        monkeypatch.setattr(module, name, no_onlyfans)
    monkeypatch.setattr(check, "read_check", lambda *a, **k: None)
    monkeypatch.setattr(check, "set_check", lambda *a, **k: None)
    monkeypatch.setattr(check.progress_utils, "setup_live", lambda *a, **k: contextlib.nullcontext())
    monkeypatch.setattr(
        check.progress_updater, "activity",
        SimpleNamespace(update_task=lambda *a, **k: None, desc=None, get_desc_id=lambda: None),
    )
    monkeypatch.setattr(check, "check_user_dict", check.defaultdict(dict))
    monkeypatch.setattr(check, "ROWS", [])
    monkeypatch.setattr(check, "_disk_check", False)
    return SimpleNamespace(settings=stub, session=c, db=db)


def timeline_media_ids():
    from ofscraper.sites.fansly import scrape

    posts = asyncio.run(scrape.get_timeline_posts(CREATOR_ID, CREATOR, c=FakeSession(route)))
    return {int(m["id"]) for p in posts for m in p["media"]}


def go(runner):
    # the runners are wrapped by @run; inside a running loop they return the coroutine
    async def run():
        await runner()

    asyncio.run(run())


def rows():
    return list(check.ROWS or [])


# ------------------------------------------------------------------ GUI


@pytest.mark.parametrize("action", ["post_check", "msg_check", "paid_check"])
def test_check_tables_are_offered_on_fansly(action):
    assert site_context.action_supported(action, site=site_context.FANSLY)


def test_stories_check_stays_onlyfans_only():
    assert not site_context.action_supported("story_check", site=site_context.FANSLY)


# ------------------------------------------------------------------ Check posts


def test_post_check_lists_every_timeline_media_item(env, caplog):
    with caplog.at_level(logging.INFO, logger="shared"):
        go(check.post_check_runner)
    found = rows()
    assert {r["media_id"] for r in found} == timeline_media_ids()
    assert {r["username"] for r in found} == {CREATOR}
    assert not any(r["downloaded"] for r in found)
    # the creator came from Fansly's account lookup, by name
    assert env.session.calls("account")[0]["usernames"] == CREATOR
    assert all("onlyfans.com" not in url for url in env.session.urls)
    assert f"[{CREATOR}] Check: {len(found)} items, 0 downloaded" in caplog.text


def test_post_check_marks_what_was_downloaded(env, caplog, monkeypatch):
    go(check.post_check_runner)
    first = check.ROWS[0]
    key = (first["media_id"], first["post_id"])
    # what the database records as downloaded
    monkeypatch.setattr(
        check, "get_media_post_files_downloaded", lambda **k: {key: ("folder", "file.mp4")}
    )
    check.ROWS = []
    with caplog.at_level(logging.INFO, logger="shared"):
        asyncio.run(check.row_gather(CREATOR, CREATOR_ID))
    again = {(r["media_id"], r["post_id"]): r for r in rows()}
    assert again[key]["downloaded"]
    assert again[key]["download_cart"] == "[downloaded]"
    assert sum(r["downloaded"] for r in again.values()) == 1
    assert f"[{CREATOR}] Check: {len(again)} items, 1 downloaded" in caplog.text


def test_post_check_skips_areas_fansly_does_not_have(env, caplog):
    env.settings.check_area = ["Timeline", "Pinned", "Archived", "Streams"]
    with caplog.at_level(logging.INFO, logger="shared"):
        go(check.post_check_runner)
    assert {r["media_id"] for r in rows()} == timeline_media_ids()
    assert "Fansly has no Pinned, Archived, Streams area; skipped" in caplog.text


def test_post_check_skips_an_unknown_creator(env, caplog):
    env.settings.url = ["nobody_here", CREATOR]
    with caplog.at_level(logging.WARNING, logger="shared"):
        go(check.post_check_runner)
    assert "Skipping nobody_here: Fansly has no account by that name" in caplog.text
    assert {r["username"] for r in rows()} == {CREATOR}


def test_post_check_finds_a_creator_by_account_id(env):
    env.settings.url = [str(CREATOR_ID)]
    go(check.post_check_runner)
    assert {r["username"] for r in rows()} == {CREATOR}


# ------------------------------------------------------------------ Check messages / purchased


def test_message_check_reads_fansly_messages_and_purchases(env):
    env.settings.command = "msg_check"
    env.settings.url = [DM_CREATOR]
    go(check.message_checker_runner)
    found = rows()
    assert found
    assert {r["username"] for r in found} == {DM_CREATOR}
    assert {r["responsetype"] for r in found} >= {"Messages"}
    assert env.session.calls("message")
    assert env.session.calls("account/media/orders/")


def test_purchased_check_reads_fansly_purchases(env):
    env.settings.command = "paid_check"
    env.settings.check_usernames = [DM_CREATOR]
    go(check.purchase_checker_runner)
    found = rows()
    assert found
    assert {r["username"] for r in found} == {DM_CREATOR}
    assert env.session.calls("account/media/orders/")
    assert all("onlyfans.com" not in url for url in env.session.urls)


def test_stories_check_on_fansly_stops_with_a_message(env, caplog, monkeypatch):
    monkeypatch.setattr(check, "check_auth", lambda: pytest.fail("ran the stories check"))
    env.settings.command = "story_check"
    with caplog.at_level(logging.ERROR, logger="shared"):
        check._checker()
    assert "stories check is OnlyFans only" in caplog.text


# ------------------------------------------------------------------ files on disk


def test_disk_option_shows_a_missing_file_as_not_downloaded(env, tmp_path, monkeypatch):
    go(check.post_check_runner)
    first, second = check.ROWS[0], check.ROWS[1]
    on_disk = tmp_path / "here.mp4"
    on_disk.write_bytes(b"x")
    recorded = {
        (first["media_id"], first["post_id"]): (str(tmp_path), "here.mp4"),
        (second["media_id"], second["post_id"]): (str(tmp_path), "gone.mp4"),
    }
    monkeypatch.setattr(
        check, "get_media_post_files_downloaded", lambda **k: dict(recorded)
    )
    monkeypatch.setattr(check, "_disk_check", True)
    check.ROWS = []
    asyncio.run(check.row_gather(CREATOR, CREATOR_ID))
    by_key = {(r["media_id"], r["post_id"]): r for r in rows()}
    assert by_key[(first["media_id"], first["post_id"])]["downloaded"]
    assert not by_key[(second["media_id"], second["post_id"])]["downloaded"]


# ------------------------------------------------------------------ totals line


def test_totals_count_locked_items_apart():
    def row(kind, downloaded, unlocked=True):
        return {"mediatype": kind, "downloaded": downloaded, "unlocked": unlocked}

    line = check.check_totals("someone", [
        row("Videos", True), row("Videos", False), row("Videos", False, unlocked=False),
        row("Images", True),
    ])
    assert line == (
        "[someone] Check: 4 items, 2 downloaded, 1 not downloaded, 1 locked; "
        "images 1/1, videos 1/3 (1 locked)"
    )
    assert check.check_totals("someone", []) == (
        "[someone] Check: 0 items, 0 downloaded, 0 not downloaded, 0 locked"
    )


# ------------------------------------------------------------------ failed cart downloads


def test_a_failed_timeline_download_refreshes_that_post_only(env):
    go(check.post_check_runner)
    post_id = check.ROWS[0]["post_id"]
    calls = []

    def answer(path, query):
        calls.append((path, query))
        if path == "post":
            return envelope({"posts": [], "accountMedia": [], "accountMediaBundles": []})
        return route(path, query)

    env.session.route = answer
    found = asyncio.run(check._fansly_refresh_post("timeline", post_id, CREATOR_ID, CREATOR))
    assert found == []
    assert [p for p, _ in calls] == ["post"]
    assert calls[0][1]["ids"] == str(post_id)
    assert asyncio.run(check._fansly_refresh_post("stories", post_id, CREATOR_ID, CREATOR)) is None
