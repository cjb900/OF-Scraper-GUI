"""How runs are posted to the Discord webhook.

Lines are batched (one message per creator, not per line), the avatar link of
each creator is left out unless discord_avatars is on in config.json (and then
no link previews are made), summaries go in a code block, the run totals are
an embed card (green, or red when something failed), messages post as
"OF-Scraper · <site>", and long text is cut at line breaks under Discord's
2,000-character limit. A fake session records each post; nothing is sent.
"""

import contextlib
import logging

import pytest

import ofscraper.managers.stats as stats
import ofscraper.sites as sites
import ofscraper.utils.config.data as data
import ofscraper.utils.logs.classes.handlers.discord as discord
from ofscraper.utils.logs.classes.classes import DiscordFormatter


class FakeResponse:
    status_code = 204


class FakeSession:
    def __init__(self, posts):
        self.posts = posts

    def _set_session(self, **kwargs):
        pass

    @contextlib.contextmanager
    def requests(self, url, method=None, headers=None, json=None):
        self.posts.append(json)
        yield FakeResponse()


@pytest.fixture
def posts(monkeypatch):
    sent = []
    monkeypatch.setattr(discord.sessionManager, "sessionManager", lambda **k: FakeSession(sent))
    monkeypatch.setattr(discord.data, "get_discord", lambda **k: "https://discord.invalid/hook")
    monkeypatch.setattr(sites, "current_site", lambda: "onlyfans")
    monkeypatch.setattr(discord, "show_avatars", lambda: False)
    return sent


def run(lines, **embeds):
    """Log ``lines`` through a fresh handler and flush it."""
    handler = discord.DiscordHandler()
    handler.setFormatter(DiscordFormatter("%(message)s"))
    logger = logging.getLogger("test_discord_messages")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    for line in lines:
        extra = {"discord_embed": embeds[line]} if line in embeds else None
        logger.warning(line, extra=extra)
    handler.close()
    logger.handlers = []


CREATOR = [
    "Progress 1/2",
    "Data Retrival on creator_one",
    "Avatar : https://public.onlyfans.com/files/a/avatar.jpg",
    "Subscription: Active",
    "Expiration Date: 2033-04-03",
]


def test_lines_are_batched_and_avatars_left_out(posts):
    run(CREATOR)
    assert len(posts) == 1
    content = posts[0]["content"]
    assert "Data Retrival on creator_one" in content and "Expiration Date" in content
    assert "Avatar" not in content
    assert posts[0]["flags"] == discord.SUPPRESS_EMBEDS
    assert posts[0]["username"] == "OF-Scraper · OnlyFans"


def test_avatars_kept_with_previews_when_turned_on(posts, monkeypatch):
    monkeypatch.setattr(discord, "show_avatars", lambda: True)
    run(CREATOR)
    assert "Avatar : https://public.onlyfans.com/files/a/avatar.jpg" in posts[0]["content"]
    assert "flags" not in posts[0]


SIGNED = (
    "https://cdn3.fansly.com/1000/2000.jpeg?ngsw-bypass=true&Expires=1796010609"
    "&Key-Pair-Id=KEYPAIRID123&Signature=SIGNATUREVALUE123"
)


def log_avatar(url):
    """Log an avatar line the way the scraper does, the real link as extra."""
    handler = discord.DiscordHandler()
    handler.setFormatter(DiscordFormatter("%(message)s"))
    logger = logging.getLogger("test_discord_messages")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.warning("Progress 1/1")
    logger.warning("Data Retrival on creator_one")
    logger.warning(f"Avatar : {url}", extra={"discord_avatar": url})
    logger.warning("Subscription: Active")
    handler.close()
    logger.handlers = []


@pytest.fixture
def uploads(monkeypatch):
    sent, fetched = [], []

    def fetch(url):
        fetched.append(url)
        return b"\xff\xd8jpeg", "image/jpeg", "jpeg"

    def post(url, payload, files):
        sent.append((payload, files))
        return 200

    monkeypatch.setattr(discord, "fetch_image", fetch)
    monkeypatch.setattr(discord, "post_with_files", post)
    return sent, fetched


def test_signed_avatar_uploaded_with_the_message(posts, uploads, monkeypatch):
    # the text's signature is hidden, and Fansly's CDN won't serve Discord
    # itself, so the picture is downloaded and uploaded
    monkeypatch.setattr(discord, "show_avatars", lambda: True)
    sent, fetched = uploads
    log_avatar(SIGNED)
    assert fetched == [SIGNED]
    assert posts == []
    ((payload, files),) = sent
    assert "Avatar" not in payload["content"] and "Signature" not in payload["content"]
    assert "creator_one" in payload["content"] and "Subscription" in payload["content"]
    assert files == [("avatar0.jpeg", b"\xff\xd8jpeg", "image/jpeg")]
    # a plain attachment: an image embed of it showed as an empty box in the
    # Discord desktop/web client (tested in Zen); the attachment shows everywhere
    assert "embeds" not in payload
    assert payload["attachments"] == [{"id": 0, "filename": "avatar0.jpeg"}]
    assert payload["username"] == "OF-Scraper · OnlyFans"


def test_avatar_that_cannot_be_downloaded_is_left_out(posts, uploads, monkeypatch):
    monkeypatch.setattr(discord, "show_avatars", lambda: True)
    monkeypatch.setattr(discord, "fetch_image", lambda url: None)
    sent, _ = uploads
    log_avatar(SIGNED)
    assert sent == []
    assert "Avatar" not in posts[0]["content"] and "embeds" not in posts[0]


def test_text_still_sent_when_the_upload_is_refused(posts, uploads, monkeypatch):
    monkeypatch.setattr(discord, "show_avatars", lambda: True)
    monkeypatch.setattr(discord, "post_with_files", lambda url, payload, files: 400)
    log_avatar(SIGNED)
    assert "creator_one" in posts[0]["content"]


def test_signed_avatar_left_out_when_avatars_are_off(posts, uploads):
    sent, fetched = uploads
    log_avatar(SIGNED)
    assert sent == [] and fetched == []
    assert "embeds" not in posts[0]
    assert "Avatar" not in posts[0]["content"]


JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def test_fetch_image_goes_by_the_bytes_not_the_label(monkeypatch):
    # Fansly labels avatars as a generic binary file; Firefox then won't show
    # them, and a check on the label would throw them away
    class R:
        def __init__(self, status, ctype, content):
            self.status_code, self.headers, self.content = status, {"content-type": ctype}, content

    monkeypatch.setattr(discord, "image_headers", lambda url: {})
    monkeypatch.setattr(discord.httpx, "get", lambda *a, **k: R(200, "binary/octet-stream", JPEG))
    assert discord.fetch_image(SIGNED) == (JPEG, "image/jpeg", "jpg")
    monkeypatch.setattr(discord.httpx, "get", lambda *a, **k: R(403, "image/jpeg", JPEG))
    assert discord.fetch_image(SIGNED) is None
    monkeypatch.setattr(discord.httpx, "get", lambda *a, **k: R(200, "image/jpeg", b"<html>denied"))
    assert discord.fetch_image(SIGNED) is None


@pytest.mark.parametrize(
    "content, expected",
    [
        (JPEG, ("image/jpeg", "jpg")),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, ("image/png", "png")),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ("image/webp", "webp")),
        (b"GIF89a" + b"\x00" * 8, ("image/gif", "gif")),
        (b"<?xml", None),
        (b"", None),
    ],
)
def test_image_type(content, expected):
    assert discord.image_type(content) == expected


def test_plain_avatar_link_stays_a_link(posts, uploads, monkeypatch):
    monkeypatch.setattr(discord, "show_avatars", lambda: True)
    url = "https://public.onlyfans.com/files/a/avatar.jpg"
    log_avatar(url)
    assert f"Avatar : {url}" in posts[0]["content"]
    assert uploads == ([], [])
    assert "embeds" not in posts[0]


def test_each_creator_gets_its_own_message(posts):
    second = ["Progress 2/2", "Data Retrival on creator_two"]
    run(CREATOR + second)
    assert len(posts) == 2
    assert "creator_one" in posts[0]["content"] and "creator_two" not in posts[0]["content"]
    assert "creator_two" in posts[1]["content"]


def test_fansly_runs_post_as_fansly(posts, monkeypatch):
    monkeypatch.setattr(sites, "current_site", lambda: "fansly")
    run(["Progress 1/1"])
    assert posts[0]["username"] == "OF-Scraper · Fansly"


SUMMARY = (
    "\n--- Final Stats Summary  ---\n"
    "\\[creator_one]\\[Action Download] (1.73 MB) (1 downloads total)\n"
    "\n" + "=" * 50 + "\n"
    "📊 GLOBAL RUN TOTALS (ALL MODELS) · OnlyFans\n"
    + "=" * 50 + "\n"
    " ➜ TOTAL ITEMS: 1"
)


def test_summary_in_a_code_block_and_totals_as_a_card(posts):
    card = stats.totals_embed(downloaded=1, videos=1, models=["creator_one"])
    run([SUMMARY], **{SUMMARY: card})
    assert len(posts) == 2
    block = posts[0]["content"]
    assert block.startswith("```\n") and block.endswith("\n```")
    assert "Final Stats Summary" in block and "creator_one" in block
    assert "GLOBAL RUN TOTALS" not in block and "TOTAL ITEMS" not in block
    assert posts[1]["embeds"] == [card]
    assert "flags" not in posts[1]


def test_card_colour_follows_failures(monkeypatch):
    monkeypatch.setattr(sites, "current_site", lambda: "fansly")
    ok = stats.totals_embed(downloaded=3, photos=3, models=["a"])
    bad = stats.totals_embed(downloaded=3, photos=3, failed=2, models=["a", "b"])
    assert ok["color"] == stats.DISCORD_GREEN and ok["title"] == "✅ Run finished · Fansly"
    assert bad["color"] == stats.DISCORD_RED and bad["title"].startswith("⚠️")
    assert bad["description"] == "2 models: a, b"
    assert {f["name"]: f["value"] for f in bad["fields"]}["Failed"] == "2"
    text_only = stats.totals_embed(text=(1016, 12, 0), models=["a"])
    assert [f["name"] for f in text_only["fields"]] == ["Text files"]


def test_mention_stays_outside_the_code_block(posts):
    results = "@here\n\n\n--- Scrape Results ---\n\\[creator_one] 3 new this run"
    run([results])
    assert posts[0]["content"].startswith("@here\n```\n")
    assert "creator_one" in posts[0]["content"]


def test_long_text_is_cut_at_line_breaks():
    lines = [f"line {i:04d} " + "x" * 80 for i in range(60)]
    pieces = discord.split_lines("\n".join(lines))
    assert len(pieces) > 1
    assert all(len(p) <= discord.MAX_MESSAGE for p in pieces)
    assert "\n".join(pieces).split("\n") == lines
    long_line = "word " * 600
    assert all(len(p) <= discord.MAX_MESSAGE for p in discord.split_lines(long_line))


def test_global_summary_carries_the_card(monkeypatch):
    monkeypatch.setattr(sites, "current_site", lambda: "onlyfans")
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record)

    catcher = Catch()
    logging.getLogger("shared").addHandler(catcher)
    try:
        manager = stats.StatsManager()
        manager._stats = {"creator_one": {}}
        manager.print_global_summary()
    finally:
        logging.getLogger("shared").removeHandler(catcher)
    card = [r for r in records if getattr(r, "discord_embed", None)]
    assert card and card[0].discord_embed["description"] == "1 model: creator_one"


@pytest.mark.parametrize("value, expected", [
    (None, False), (True, True), (False, False), ("true", True), ("off", False),
])
def test_avatar_setting_in_config(value, expected):
    config = {} if value is None else {"discord_avatars": value}
    assert data.get_discord_avatars(config=config) is expected


def test_avatar_setting_is_kept_in_the_saved_config():
    import ofscraper.utils.config.schema as schema

    assert schema.get_current_config_schema({"discord_avatars": True})["discord_avatars"] is True
    assert schema.get_current_config_schema({})["discord_avatars"] is False


def test_code_blocks_drop_bold_marks():
    from ofscraper.utils.logs.classes.handlers.discord import code_blocks

    (block,) = code_blocks("**[a][Action Download]** (**1 downloads total**)")
    assert "**" not in block.strip("`")
    assert "[a][Action Download] (1 downloads total)" in block
