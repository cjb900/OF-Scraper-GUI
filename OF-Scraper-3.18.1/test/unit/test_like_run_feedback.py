"""Like / unlike runs: the date range applies, results show at once, the button says what runs."""

import arrow
import pytest

import ofscraper.commands.scraper.actions.like.like as like_mod
import ofscraper.filters.media.filters as helpers


class P:
    def __init__(self, pid, date):
        self.id, self.date, self.expires = pid, date, None


def test_date_range_limits_likes(monkeypatch):
    class S:
        after = arrow.get("2026-09-01")
        before = arrow.get("2026-09-30T23:59:59")

    monkeypatch.setattr(helpers.settings, "get_settings", lambda: S)
    posts = [P(1, "2026-09-05T10:00:00"), P(2, "2025-01-01T00:00:00"), P(3, "2026-10-02T00:00:00")]
    assert [p.id for p in helpers.posts_date_filter(posts)] == [1]


def test_get_posts_to_like_uses_the_date_filter():
    import inspect

    from ofscraper.managers.postcollection import PostCollection

    assert "posts_date_filter" in inspect.getsource(PostCollection.get_posts_to_like)


def test_each_result_is_sent_as_it_happens(monkeypatch):
    pytest.importorskip("PyQt6")
    from ofscraper.gui.signals import app_signals

    got = []
    app_signals.posts_liked_updated.connect(got.append)
    try:
        monkeypatch.setattr(like_mod, "_GUI_LIKE_TRACKER", {})
        like_mod._gui_result(42, "Liked")
        assert got == [{42: "Liked"}] and like_mod._GUI_LIKE_TRACKER == {42: "Liked"}
        monkeypatch.setattr(like_mod, "_GUI_LIKE_TRACKER", None)
        like_mod._gui_result(43, "Liked")  # not a GUI run: nothing sent
        assert got == [{42: "Liked"}]
    finally:
        app_signals.posts_liked_updated.disconnect(got.append)


@pytest.mark.parametrize("actions, text", [
    ({"like"}, "Liking..."),
    ({"unlike"}, "Unliking..."),
    ({"download"}, "Scraping..."),
    ({"download", "like"}, "Scraping & liking..."),
])
def test_button_says_what_runs(actions, text):
    pytest.importorskip("PyQt6")
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage.__new__(TablePage)
    page._current_actions = lambda: actions
    assert TablePage._running_text(page) == text
    assert TablePage._running_text(page, 3) == text.replace("...", " (run #3)...")
