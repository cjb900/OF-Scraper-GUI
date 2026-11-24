"""Reset in the filter panel restores the start-up dates (1/1/2000 and today),
not Qt's minimum date 9/14/1752; a 1752 saved by an older Reset is ignored."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QDate  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_reset_restores_the_default_dates(qapp):
    from ofscraper.gui.widgets.sidebar import FilterSidebar

    fs = FilterSidebar()
    fs.min_date.setDate(QDate(2026, 9, 1))
    fs.max_date.setDate(QDate(2026, 9, 30))
    fs.reset_all()
    assert fs.min_date.date() == QDate(2000, 1, 1)
    assert fs.max_date.date() == QDate.currentDate()


def test_a_saved_1752_is_ignored(qapp, monkeypatch):
    import ofscraper.gui.pages.area_selector_page as area_mod

    saved = {"after_date": "1752-09-14", "before_date": "1752-09-14"}
    monkeypatch.setattr(area_mod, "load_gui_settings", lambda: dict(saved))
    monkeypatch.setattr(area_mod, "save_gui_settings", lambda *a, **k: True)
    page = area_mod.AreaSelectorPage(manager=None)
    page._load_area_settings()
    fs = page.filter_sidebar
    assert fs.min_date.date() == QDate(2000, 1, 1)
    assert fs.max_date.date() == QDate.currentDate()


def test_a_real_saved_date_still_loads(qapp, monkeypatch):
    import ofscraper.gui.pages.area_selector_page as area_mod

    saved = {"after_date": "2026-09-01", "before_date": "2026-09-30"}
    monkeypatch.setattr(area_mod, "load_gui_settings", lambda: dict(saved))
    monkeypatch.setattr(area_mod, "save_gui_settings", lambda *a, **k: True)
    page = area_mod.AreaSelectorPage(manager=None)
    page._load_area_settings()
    assert page.filter_sidebar.min_date.date() == QDate(2026, 9, 1)
    assert page.filter_sidebar.max_date.date() == QDate(2026, 9, 30)
