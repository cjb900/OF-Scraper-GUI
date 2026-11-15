"""A log line with broken Rich markup is still logged, not dropped.

Rich raises MarkupError on a stray closing tag such as "[/bold]"; the log
file and Discord formatters and the terminal handler used to lose the line.
"""

import io
import logging

import pytest
from rich.console import Console

import ofscraper.utils.console as console_mod
import ofscraper.utils.logs.classes.classes as log_class
import ofscraper.utils.logs.stdout as stdout_mod
import ofscraper.utils.logs.utils.sensitive as sensitive

pytestmark = pytest.mark.unit

STRAY = "done [/bold] here"
# the terminal and log file line format, from utils/logs/stdout.py
LINE_FMT = r" \[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"


@pytest.fixture(autouse=True)
def no_run_masks(monkeypatch):
    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)


def _record(msg):
    return logging.LogRecord(
        "t", logging.INFO, "mod.py", 7, msg, None, None, func="fn"
    )


# -- log file and Discord formatters -----------------------------------------


@pytest.mark.parametrize(
    "formatter", [log_class.LogFileFormatter, log_class.DiscordFormatter]
)
def test_formatters_keep_line_with_stray_closing_tag(formatter):
    out = formatter("%(message)s").format(_record(STRAY))
    assert out == STRAY


def test_log_file_fallback_removes_escapes_like_rich_does():
    out = log_class.LogFileFormatter(LINE_FMT).format(_record(STRAY))
    assert "\\[" not in out
    assert out == " [mod.fn:7]  " + STRAY


def test_strip_markup_removes_only_bracket_escapes_on_fallback():
    assert log_class.strip_markup(r"\[a] b [/bold] c\d") == r"[a] b [/bold] c\d"


def test_formatters_still_strip_valid_markup():
    out = log_class.LogFileFormatter("%(message)s").format(
        _record("[bold]ok[/bold] fine")
    )
    assert out == "ok fine"


# -- terminal handlers, as utils/logs/stdout.py builds them -------------------


def _terminal_output(monkeypatch, msg):
    buf = io.StringIO()
    test_console = Console(file=buf, width=200, color_system=None)
    monkeypatch.setattr(console_mod, "get_console", lambda: test_console)
    logger = logging.getLogger(f"stray-markup-test-{id(buf)}")
    logger.propagate = False
    stdout_mod.add_stdout_handler(logger)
    raised = []
    try:
        for h in logger.handlers:
            h.handleError = lambda record: raised.append(record)
        logger.info(msg)
    finally:
        for h in list(logger.handlers):
            logger.removeHandler(h)
    return buf.getvalue(), raised


def test_terminal_handler_keeps_line_with_stray_closing_tag(monkeypatch):
    out, raised = _terminal_output(monkeypatch, STRAY)
    assert not raised
    assert STRAY in out


def test_terminal_fallback_removes_escapes(monkeypatch):
    out, raised = _terminal_output(monkeypatch, STRAY)
    assert not raised
    assert "\\[" not in out
    assert "[test_log_stray_markup._terminal_output:" in out


def test_terminal_handler_still_renders_valid_markup(monkeypatch):
    out, raised = _terminal_output(monkeypatch, "[bold]ok[/bold] fine")
    assert not raised
    assert "ok fine" in out
    assert "[bold]" not in out
