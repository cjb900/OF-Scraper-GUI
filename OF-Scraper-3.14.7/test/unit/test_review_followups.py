"""Follow-ups from reviewing PRs #29-#35."""

import logging
import os
import pathlib
import subprocess
import sys
from types import SimpleNamespace

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first.
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

import ofscraper.commands.scraper.actions.download.utils.leaky as leaky
import ofscraper.data.api.init as init
import ofscraper.utils.checkers as checkers
import ofscraper.utils.logs.utils.sensitive as sensitive
from ofscraper.gui.utils.auth_errors import (
    CRED_TEST_UNAVAILABLE,
    cred_test_timeout,
)
from ofscraper.utils.logs.classes.classes import SensitiveFormatter

pytestmark = pytest.mark.unit


# --- low download limit warning ---
@pytest.fixture
def limit(monkeypatch):
    def setup(value, cli=None):
        monkeypatch.setattr(leaky, "_warned_low_limit", False)
        monkeypatch.setattr(
            leaky.settings,
            "get_settings",
            lambda: SimpleNamespace(download_limit=value),
        )
        monkeypatch.setattr(
            leaky.settings, "get_args", lambda: SimpleNamespace(download_limit=cli)
        )
        records = []
        handler = logging.Handler(level=logging.WARNING)
        handler.emit = records.append
        logger = logging.getLogger("shared")
        logger.addHandler(handler)
        try:
            leaky.warn_if_limit_looks_too_low()
            leaky.warn_if_limit_looks_too_low()
        finally:
            logger.removeHandler(handler)
        return [r.getMessage() for r in records]

    return setup


def test_low_limit_from_the_config_warns_once(limit):
    # 500 typed into the old "KB/s" box is 500 bytes, raised to the 1024 minimum
    warnings = limit(1024)
    assert len(warnings) == 1
    assert "1 KB/s" in warnings[0]
    assert "Older GUI versions" in warnings[0]


@pytest.mark.parametrize(
    "value,cli",
    [(0, None), (100_000, None), (500_000, None), (1024, 1024)],
    ids=["unlimited", "at-threshold", "high", "from-command-line"],
)
def test_other_limits_do_not_warn(limit, value, cli):
    assert limit(value, cli) == []


# --- home folder masking ---
def _masked(monkeypatch, home, text):
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: home)
    record = logging.LogRecord("x", logging.INFO, "", 1, text, None, None)
    return SensitiveFormatter("%(message)s").format(record)


@pytest.mark.parametrize(
    "home,text",
    [
        ("dan", "danger"),
        ("user", "username not found"),
        ("root", "rootfs mounted"),
        ("a", "data path"),
    ],
)
def test_home_name_inside_a_longer_word_is_left_alone(monkeypatch, home, text):
    assert _masked(monkeypatch, home, text) == text


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/home/dan/file.txt", "/home/{home_directory}/file.txt"),
        (r"C:\Users\dan\file.txt", r"C:\Users\{home_directory}\file.txt"),
        ("owner dan here", "owner {home_directory} here"),
        ("dan_log.txt", "{home_directory}_log.txt"),
    ],
)
def test_home_name_is_still_hidden(monkeypatch, text, expected):
    assert _masked(monkeypatch, "dan", text) == expected


def test_home_name_with_regex_characters(monkeypatch):
    assert _masked(monkeypatch, "a.b", "/home/a.b/x axb") == "/home/{home_directory}/x axb"


# --- status line ---
@pytest.mark.parametrize(
    "status,shown,hidden",
    [
        ("UP", "UP", "DOWN"),
        ("DOWN", "DOWN", "Couldn't check"),
        ("UNAVAILABLE", "Couldn't check", "DOWN"),
    ],
)
def test_sign_status_line(monkeypatch, status, shown, hidden):
    printed = []
    monkeypatch.setattr(init, "getstatus", lambda: status)
    monkeypatch.setattr(
        init.console,
        "get_shared_console",
        lambda: SimpleNamespace(print=printed.append),
    )
    init.print_sign_status()
    assert len(printed) == 1
    assert shown in printed[0]
    assert hidden not in printed[0]


# --- Test Credentials timeout ---
def test_model_list_timeout_is_not_reported_as_bad_credentials():
    result, text = cred_test_timeout()
    assert result == CRED_TEST_UNAVAILABLE
    assert "not a problem with your auth" in text
    assert "45 s" in text


# --- the message is shown once ---
def test_auth_check_failure_is_marked_as_already_logged():
    assert checkers.AuthCheckUnavailable.already_logged is True


# --- usage errors from the real program ---
@pytest.mark.parametrize(
    "args,message",
    [
        (["-a", "download", "--username", "x", "--after", "garbage"], "isn't a date"),
        (["-a", "download", "--username", "x", "--after", "25/12/2024"], "isn't a date"),
        (["--no-such-option"], "No such option"),
    ],
    ids=["garbage-date", "day-first-date", "unknown-option"],
)
def test_usage_errors_show_a_message_not_a_traceback(tmp_path, args, message):
    # a real run: the parser reads sys.argv while the modules are imported
    root = pathlib.Path(__file__).resolve().parents[2]
    env = {
        **os.environ,
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / ".config"),
        "PYTHONPATH": str(root),
        "PYTHONWARNINGS": "ignore",
    }
    out = subprocess.run(
        [sys.executable, "-m", "ofscraper", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    assert out.returncode == 2
    assert message in out.stderr
    assert "Traceback" not in out.stderr + out.stdout
