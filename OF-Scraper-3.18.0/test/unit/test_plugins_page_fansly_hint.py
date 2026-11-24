"""On the Fansly tab the Plugins page says, at the top, that plugins are
OnlyFans only; the OnlyFans tab doesn't show that notice."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui import site_context  # noqa: E402
from ofscraper.gui.pages import plugins_page  # noqa: E402


def test_notice_says_onlyfans_only():
    text = plugins_page.FANSLY_NOTICE
    assert "OnlyFans only" in text
    assert "aren't supported on Fansly" in text


def test_fansly_empty_hint_is_short(monkeypatch):
    monkeypatch.setattr(site_context, "is_fansly", lambda: True)
    assert plugins_page._empty_hint() == "No Fansly plugins found."


def test_onlyfans_tab(monkeypatch):
    monkeypatch.setattr(site_context, "is_fansly", lambda: False)
    assert plugins_page._empty_hint().startswith("No plugins installed yet")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    # keep a reference: an unreferenced QApplication is freed at once
    return QApplication.instance() or QApplication([])


def _page(monkeypatch, fansly):
    monkeypatch.setattr(site_context, "is_fansly", lambda: fansly)
    monkeypatch.setattr(plugins_page.PluginsPage, "refresh", lambda self: None)
    return plugins_page.PluginsPage()


def test_notice_sits_under_the_title_on_fansly(qapp, monkeypatch):
    page = _page(monkeypatch, True)
    layout = page.layout()
    assert layout.itemAt(1).widget() is page.fansly_notice
    assert not page.fansly_notice.isHidden()


def test_notice_hidden_on_onlyfans(qapp, monkeypatch):
    page = _page(monkeypatch, False)
    assert page.fansly_notice.isHidden()
