"""Select Action on the Fansly tab: no User Lists box (Fansly has no user
lists) and the posts check is labelled with Fansly's timeline and walls."""
import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui import site_context  # noqa: E402
from ofscraper.gui.pages import action_page  # noqa: E402

POSTS = "Check posts: build table of timeline/pinned/archived media"


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


def _page(monkeypatch, site):
    monkeypatch.setattr(site_context, "current_site", lambda: site)
    return action_page.ActionPage()


def _radio_texts(page):
    return [b.text() for b in page._button_group.buttons()]


def test_userlists_supported_per_site():
    assert site_context.userlists_supported(site_context.ONLYFANS)
    assert not site_context.userlists_supported(site_context.FANSLY)


def test_check_choice_text():
    assert action_page._check_choice_text(POSTS, False) == (POSTS, action_page._CHECK_TIPS[POSTS])
    shown, tip = action_page._check_choice_text(POSTS, True)
    assert shown == "Check posts: build table of timeline/walls media"
    assert "wall" in tip and "pinned" not in tip
    other = "Check messages: build table of message & paid media"
    assert action_page._check_choice_text(other, True)[0] == other


def test_fansly_hides_user_lists(qapp, monkeypatch):
    page = _page(monkeypatch, site_context.FANSLY)
    assert page._userlist_widget.isHidden()
    page._on_action_changed(0)  # Download
    assert page._userlist_widget.isHidden()
    page.reset_to_defaults()
    assert page._userlist_widget.isHidden()
    # a value set from --ul is never used on Fansly
    page._userlist_input.setText("vip")
    assert page.get_userlist() == []
    texts = _radio_texts(page)
    assert "Check posts: build table of timeline/walls media" in texts
    assert POSTS not in texts


def test_onlyfans_keeps_user_lists(qapp, monkeypatch):
    page = _page(monkeypatch, site_context.ONLYFANS)
    assert not page._userlist_widget.isHidden()
    page._userlist_input.setText("VIP, testing")
    assert page.get_userlist() == ["vip", "testing"]
    page._on_action_changed(0)
    assert not page._userlist_widget.isHidden()
    assert POSTS in _radio_texts(page)
