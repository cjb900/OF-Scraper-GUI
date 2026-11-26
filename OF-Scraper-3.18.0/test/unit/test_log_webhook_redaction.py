"""A Discord webhook link never appears whole in a log.

The token in the path is the webhook's password. A retry line
("attempt: 2 for https://discord.com/api/webhooks/<id>/<token>") wrote it to
the log file: hide_link only hides a link's query. Every log output (file,
console, the GUI's log panel, Discord, privacy mode) goes through
SensitiveFormatter, which now keeps the host and the ID's first digits.
"""
import logging
import re
import sys

import pytest

from ofscraper.utils.logs.classes import classes
from ofscraper.utils.logs.utils import sensitive

pytestmark = pytest.mark.unit

ID = "1243469541804081193"
TOKEN = "6VKi67Z2mQSbPnFOQagx-IGEkrgxDjSJ_pN9Jn5sXomyW3"


@pytest.fixture(autouse=True)
def no_home_name(monkeypatch):
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
    # values other tests registered (a user id of 1 turns every 1 into userid)
    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})


def _record(msg):
    return logging.LogRecord("shared", logging.DEBUG, __file__, 1, msg, None, None)


def _formatted(fmt_class, msg):
    return fmt_class("%(message)s").format(_record(msg))


@pytest.mark.parametrize(
    "url",
    [
        f"https://discord.com/api/webhooks/{ID}/{TOKEN}",
        f"https://discord.com/api/webhooks/{ID}/{TOKEN}?wait=true",
        f"https://discordapp.com/api/webhooks/{ID}/{TOKEN}",
        f"https://ptb.discord.com/api/v10/webhooks/{ID}/{TOKEN}",
        f"https://CANARY.DISCORD.COM/api/webhooks/{ID}/{TOKEN}/slack",
    ],
)
@pytest.mark.parametrize(
    "fmt_class",
    [classes.SensitiveFormatter, classes.LogFileFormatter, classes.DiscordFormatter],
)
def test_the_token_and_full_id_never_reach_the_log(fmt_class, url):
    out = _formatted(fmt_class, f"[bold]attempt: 2[bold] for {url}")
    assert TOKEN not in out
    assert ID not in out
    # still says which webhook was used
    assert re.search(r"(?i)discord(app)?\.com/api/(v10/)?webhooks/1243\.\.\./\{hidden\}", out)


def test_a_traceback_with_the_link_is_cleaned_too():
    msg = (
        "Traceback (most recent call last):\n"
        f"httpx.HTTPStatusError: Client error '404' for url "
        f"'https://discord.com/api/webhooks/{ID}/{TOKEN}'"
    )
    out = _formatted(classes.LogFileFormatter, msg)
    assert TOKEN not in out and ID not in out
    assert "for url 'https://discord.com/api/webhooks/1243.../{hidden}'" in out


def test_the_retry_line_as_sessionmanager_writes_it():
    url = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"
    msg = f"[bold]attempt: 2[bold] for {sensitive.hide_link(url)}"
    out = _formatted(classes.LogFileFormatter, msg)
    assert out == "attempt: 2 for https://discord.com/api/webhooks/1243.../{hidden}"


def test_other_discord_links_are_left_alone():
    for text in (
        "https://discord.com/channels/123456789/987654321",
        "https://discord.gg/abcdef",
        "webhooks/123/abc without the host",
    ):
        assert _formatted(classes.SensitiveFormatter, text) == text


def test_privacy_mode_uses_the_same_rules():
    patterns = sensitive.getSenstiveDict()
    text = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"
    for pattern, replacement in patterns.items():
        text = re.sub(pattern, replacement, text)
    assert TOKEN not in text


def test_discord_send_errors_printed_to_the_console_are_cleaned(monkeypatch, capsys):
    # httpx names the link it failed on; print() skips the log formatters
    from ofscraper.utils.logs.classes.handlers import discord as discord_handler

    url = f"https://discord.com/api/webhooks/{ID}/{TOKEN}"

    def fail(*a, **k):
        raise RuntimeError(f"Client error '404 Not Found' for url '{url}'")

    monkeypatch.setattr(discord_handler.httpx, "post", fail)
    assert discord_handler.post_with_files(url, {"content": "x"}, []) is None
    out = capsys.readouterr().out
    assert TOKEN not in out and ID not in out
    assert "webhooks/1243.../{hidden}" in out
