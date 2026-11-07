"""Every #link in the GUI help points at an anchor that exists."""
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

HELP = pathlib.Path(__file__).resolve().parents[2] / "ofscraper" / "gui" / "help" / "GUI_HELP.md"


def test_help_links_have_targets():
    text = HELP.read_text(encoding="utf-8")
    anchors = set(re.findall(r'<a id="([^"]+)"', text))
    links = set(re.findall(r"\]\(#([^)\s]+)\)", text))
    assert links, "no links found: has the help format changed?"
    assert sorted(links - anchors) == []


def test_new_actions_are_in_the_help():
    text = HELP.read_text(encoding="utf-8")
    for anchor in ("action-metadata", "action-paid-all"):
        assert f'<a id="{anchor}"></a>' in text
        assert f"](#{anchor})" in text  # reachable from the contents list
