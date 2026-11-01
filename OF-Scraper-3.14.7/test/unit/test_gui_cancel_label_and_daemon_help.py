"""Only Cancel says "Cancelling..."; the daemon @here option has a ? button."""
import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def test_only_cancel_says_cancelling(qapp):
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    page.start_scraping_btn.setText("Scraping...")
    page._enter_cancelling_ui()
    assert page.cancel_scrape_btn.text() == "Cancelling..."
    assert not page.cancel_scrape_btn.isEnabled()
    assert page.start_scraping_btn.text() == "Start Scraping >>"
    assert not page.start_scraping_btn.isEnabled()
    # a late scrape_started while cancelling must not relabel Start
    page._on_scrape_started()
    assert page.start_scraping_btn.text() == "Start Scraping >>"
    page.close()


def test_daemon_discord_ping_has_a_help_button(qapp):
    from PyQt6.QtWidgets import QToolButton

    from ofscraper.gui.pages.area_selector_page import AreaSelectorPage

    page = AreaSelectorPage(manager=None)
    row = page.daemon_discord_ping_check.parentWidget().layout()
    # find the layout row holding the checkbox, then its ? button
    found = None
    stack = [row]
    while stack and found is None:
        lay = stack.pop()
        items = [lay.itemAt(i) for i in range(lay.count())]
        widgets = [it.widget() for it in items if it.widget() is not None]
        if page.daemon_discord_ping_check in widgets:
            found = widgets
        stack.extend(it.layout() for it in items if it.layout() is not None)
    assert found is not None
    helps = [w for w in found if isinstance(w, QToolButton) and w.text() == "?"]
    assert len(helps) == 1
    page.close()


def test_help_anchor_exists():
    from pathlib import Path

    help_md = Path(__file__).resolve().parents[2] / "ofscraper" / "gui" / "help" / "GUI_HELP.md"
    text = help_md.read_text(encoding="utf-8")
    assert '<a id="sca-daemon-discord-ping"></a>' in text
