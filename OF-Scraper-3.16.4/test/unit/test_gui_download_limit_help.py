"""The GUI's download-limit help must say the limit is shared by all downloads.

The Config page and its help page didn't say either way. One limit is
shared by every download in the download session. The CLI config prompt
is covered by test/test_download_limit_help.py.
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import pathlib

HELP = (
    pathlib.Path(__file__).resolve().parents[2]
    / "ofscraper"
    / "gui"
    / "help"
    / "GUI_HELP.md"
)


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
