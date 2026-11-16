"""The Plugins page says no Fansly plugins exist yet on the Fansly tab."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui import site_context  # noqa: E402
from ofscraper.gui.pages import plugins_page  # noqa: E402


def test_fansly_tab(monkeypatch):
    monkeypatch.setattr(site_context, "is_fansly", lambda: True)
    assert "No plugins exist for Fansly yet" in plugins_page._empty_hint()


def test_onlyfans_tab(monkeypatch):
    monkeypatch.setattr(site_context, "is_fansly", lambda: False)
    assert plugins_page._empty_hint().startswith("No plugins installed yet")
