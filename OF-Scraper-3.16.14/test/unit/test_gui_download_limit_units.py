"""The Config page's "Download Speed Limit (KB/s)" must mean KB/s.

The page saved the number as typed, but OF-Scraper reads a bare number as
bytes per second (and raises anything under 1024 to 1024). So typing 500,
meaning 500 KB/s, set a limit of about 1 KB/s.
"""

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.utils.config_validation as config_validation  # noqa: E402
import ofscraper.utils.config.data as config_data  # noqa: E402
import ofscraper.utils.config.file as config_file  # noqa: E402
from ofscraper.gui.dialogs import config_dialog  # noqa: E402


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


@pytest.fixture
def page(qapp, monkeypatch):
    saved = []
    monkeypatch.setattr(config_file, "write_config", lambda config: saved.append(config))
    monkeypatch.setattr(
        config_validation, "show_config_validation_dialog", lambda *a, **k: True
    )
    # the page reports with modal message boxes; record them instead
    messages = []

    class Boxes:
        StandardButton = QtWidgets.QMessageBox.StandardButton

        @staticmethod
        def _record(kind):
            def box(parent, title, text, *a, **k):
                messages.append((kind, title, text))
                return QtWidgets.QMessageBox.StandardButton.Ok

            return box

    for kind in ("information", "warning", "critical", "question"):
        setattr(Boxes, kind, staticmethod(Boxes._record(kind)))
    monkeypatch.setattr(config_dialog, "QMessageBox", Boxes)
    p = config_dialog.ConfigPage()
    p.saved = saved
    p.messages = messages
    yield p
    p.deleteLater()


def effective_limit(config):
    """Bytes per second, the way OF-Scraper reads the saved config."""
    limit = config_data.get_download_limit(config=config)
    # settings.merged_settings raises a set limit to at least 1024
    return max(limit, 1024) if limit else limit


def show(page, stored):
    page._config = {"performance_options": {"download_limit": stored}}
    monkey_config = page._config

    import ofscraper.utils.config.config as config_mod

    real_read = config_mod.read_config
    config_mod.read_config = lambda update=False: monkey_config
    try:
        page._load_config()
    finally:
        config_mod.read_config = real_read
    return page._widgets["download_limit"].value()


def test_typing_500_saves_about_500_kb_per_second(page):
    page._widgets["download_limit"].setValue(500)
    page._save_config()
    assert page.saved, f"the page didn't save: {page.messages}"
    limit = effective_limit(page.saved[-1])
    assert 450_000 <= limit <= 550_000, limit


def test_zero_still_means_unlimited(page):
    page._widgets["download_limit"].setValue(0)
    page._save_config()
    assert effective_limit(page.saved[-1]) == 0


def test_a_saved_limit_is_shown_back_in_kb_per_second(page):
    # what the page saves for 500, and what OF-Scraper writes back for --download-limit 500K
    assert show(page, 500_000) == 500
    assert show(page, "500K") == 500
    assert show(page, 0) == 0


def test_a_huge_stored_limit_is_shown_at_the_page_maximum(page):
    # 10 TB/s is past what the page's spin box (and Qt's int) can hold
    assert show(page, "10TB") == page._widgets["download_limit"].maximum()


def test_an_old_bare_number_is_shown_as_the_limit_it_really_sets(page):
    # The old page saved 500 for "500 KB/s"; OF-Scraper reads that as
    # 500 bytes/s and raises it to 1024, about 1 KB/s. Show that, not 0
    # (unlimited), so saving the page again doesn't silently remove the limit.
    assert show(page, 500) == 1
