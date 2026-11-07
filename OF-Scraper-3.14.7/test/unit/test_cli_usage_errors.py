"""A mistake on the command line prints click's usage message, not a traceback."""

import sys

import click
import pytest

pytestmark = pytest.mark.unit

import ofscraper.main.open.load as load  # noqa: E402
import ofscraper.utils.args.globals as global_args  # noqa: E402
import ofscraper.utils.args.main as args_main  # noqa: E402
import ofscraper.utils.settings as settings  # noqa: E402


@pytest.fixture
def argv(monkeypatch):
    def set_argv(*args):
        monkeypatch.setattr(sys, "argv", ["OF-Scraper", *args])
        # parsed again from sys.argv, not reused from another test
        monkeypatch.setattr(global_args, "args", None)
        monkeypatch.setattr(settings, "settings", {})

    # parse_args registers the subcommands on each call, and cloup refuses a
    # second registration; the options tested here are on the main program
    monkeypatch.setattr(args_main.main.program, "add_command", lambda *a, **k: None)
    monkeypatch.setattr(load, "systemSet", lambda: None)
    return set_argv


@pytest.mark.parametrize(
    "args, message",
    [
        (["--action", "download", "--bogus-flag"], "No such option"),
        (["--action", "download", "--dynamic-rules", "nope"], "Invalid value"),
    ],
)
def test_usage_error_prints_a_message_and_exits_2(argv, capsys, args, message):
    argv(*args)
    with pytest.raises(SystemExit) as exit_info:
        load.main()
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert "Usage:" in captured.err
    assert message in captured.err
    assert "Traceback" not in captured.out + captured.err


def test_parse_args_still_raises_an_ordinary_exception(argv):
    # GUI code reads settings inside try/except Exception; a usage error
    # there must not turn into SystemExit
    argv("--bogus-flag")
    with pytest.raises(click.exceptions.UsageError):
        args_main.parse_args()
