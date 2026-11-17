"""A system notification when a scrape, like or unlike run ends (option on the
Scraper page, on by default)."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui.pages.table_page import TablePage, run_end_notice  # noqa: E402


@pytest.mark.parametrize("actions, status, dl, failed, title, message", [
    ({"download"}, "ok", 644, 0, "Scrape finished", "644 downloaded"),
    ({"download"}, "ok", 644, 2, "Scrape finished", "644 downloaded, 2 failed"),
    ({"download"}, "ok", 0, 0, "Scrape finished", "Nothing new to download."),
    ({"download"}, "cancelled", 302, 0, "Scrape cancelled", "302 downloaded"),
    ({"download"}, "cancelled", 0, 0, "Scrape cancelled", "Nothing was downloaded."),
    ({"download"}, "error", 5, 1, "Scrape stopped with an error",
     "5 downloaded, 1 failed Check the log for details."),
    ({"download", "like"}, "ok", 3, 0, "Scrape finished", "3 downloaded"),
    ({"like"}, "ok", 0, 0, "Liking finished", "See the Liked column for the result."),
    ({"unlike"}, "cancelled", 0, 0, "Unliking cancelled", "See the Liked column for the result."),
    (set(), "ok", 1, 0, "Scrape finished", "1 downloaded"),
])
def test_notice_text(actions, status, dl, failed, title, message):
    assert run_end_notice(actions, status, dl, failed) == (title, message)


class Area:
    def __init__(self, on):
        self.on = on

    def is_notify_finished_enabled(self):
        return self.on


class Main:
    def __init__(self, on):
        self.area_page = Area(on)


class Page:  # stands in for the TablePage widget
    def __init__(self, on, actions=("download",)):
        self._main, self._actions = Main(on), set(actions)

    def window(self):
        return self._main

    def _current_actions(self):
        return self._actions


@pytest.fixture
def sent(monkeypatch):
    from ofscraper.gui.signals import app_signals

    out = []

    class Sig:
        def emit(self, title, message):
            out.append((title, message))

    monkeypatch.setattr(app_signals, "show_notification", Sig(), raising=False)
    return out


def test_sends_one_notice(sent):
    TablePage._notify_run_end(Page(True), "ok", 10, 0)
    assert sent == [("Scrape finished", "10 downloaded")]


def test_option_off_sends_nothing(sent):
    TablePage._notify_run_end(Page(False), "ok", 10, 0)
    assert sent == []


def test_history_record_notifies(sent, monkeypatch):
    import ofscraper.gui.utils.scrape_history as history

    monkeypatch.setattr(history, "record_run", lambda *a, **k: None)
    page = Page(True)
    page._notify_run_end = lambda *a: TablePage._notify_run_end(page, *a)
    page.data_table = type("T", (), {"_display_data": []})()
    TablePage._record_scrape_history(page, status="ok", run_dl=7, failed=1, model_names=["m"])
    assert sent == [("Scrape finished", "7 downloaded, 1 failed")]


def test_an_aborted_start_sends_nothing(sent):
    # confirm declined: no snapshot, no models, nothing downloaded
    page = Page(True)
    page._notify_run_end = lambda *a: TablePage._notify_run_end(page, *a)
    TablePage._record_scrape_history(page, status="ok")
    assert sent == []


def test_tab_window_names_the_site():
    from ofscraper.gui import site_host

    import pathlib

    src = pathlib.Path(site_host.__file__).read_text(encoding="utf-8")
    assert 'f"{self.label}: {payload.get(\'title\', \'\')}"' in src


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_option_is_on_by_default_and_saved(qapp, monkeypatch):
    import ofscraper.gui.pages.area_selector_page as area_mod

    stored = {}
    monkeypatch.setattr(area_mod, "load_gui_settings", lambda: dict(stored), raising=False)
    monkeypatch.setattr(area_mod, "save_gui_settings",
                        lambda gs, **k: stored.update(gs) or True, raising=False)
    page = area_mod.AreaSelectorPage(manager=None)
    assert page.is_notify_finished_enabled()
    page.notify_finished_check.setChecked(False)
    page._save_area_settings()
    assert stored.get("notify_finished") is False
    assert "notify_finished" in area_mod.AreaSelectorPage._AREA_SETTINGS_KEYS
