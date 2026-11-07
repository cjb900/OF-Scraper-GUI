"""The download-limit help must say the limit is shared by all downloads.

The CLI config prompt said "for each thread", and the Config page and its
help page didn't say either way. One limit is shared by every download in
the download session.
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import inspect
import pathlib
import re

import ofscraper.prompts.prompt_groups.config as config_prompts

HELP = (
    pathlib.Path(__file__).resolve().parents[2]
    / "ofscraper"
    / "gui"
    / "help"
    / "GUI_HELP.md"
)


def test_cli_prompt_says_shared():
    source = inspect.getsource(config_prompts)
    lines = [line for line in source.splitlines() if "download speed" in line]
    assert len(lines) == 2, lines  # the config overview and the prompt
    for line in lines:
        assert not re.search(r"each\s+thread", line), line
        assert "shared by all downloads" in line, line


def test_gui_help_says_shared():
    lines = [
        line
        for line in HELP.read_text(encoding="utf-8").splitlines()
        if "performance_options.download_limit" in line
    ]
    assert len(lines) == 1, lines
    assert "shared by all downloads, not set per thread" in lines[0]


def test_config_page_tooltip_says_shared():
    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
    from ofscraper.gui.dialogs import config_dialog

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    page = config_dialog.ConfigPage()
    try:
        tooltip = page._widgets["download_limit"].toolTip()
    finally:
        page.deleteLater()
    assert "shared by all downloads, not set per thread" in tooltip
