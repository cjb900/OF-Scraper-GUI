"""Model selection safety: no stale chips, no silently scraped hidden models.

1. The per-model chip bar above the table kept the previous run's chips until
   the next scrape was past its confirm dialogs, so a dialog could appear next
   to the wrong model names.
2. Select Models scrapes every ticked model, including ones the search box
   hides; that now shows in the count and asks before Next.
"""
from types import SimpleNamespace

import pytest

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt  # noqa: E402

import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def badge_resets():
    seen = []
    slot = lambda names: seen.append(list(names))  # noqa: E731
    app_signals.model_badges_reset.connect(slot)
    yield seen
    app_signals.model_badges_reset.disconnect(slot)


# -- 1. stale chips ---------------------------------------------------------


def test_start_clears_chips_before_the_first_confirm(monkeypatch, badge_resets):
    import ofscraper.gui.utils.key_mode_warning as kmw

    order = []
    on_reset = lambda n: order.append(("reset", list(n)))  # noqa: E731
    app_signals.model_badges_reset.connect(on_reset)
    monkeypatch.setattr(
        kmw,
        "confirm_remote_key_mode",
        lambda *a, **k: order.append(("confirm", None)) or False,
    )
    wf = workflow_mod.GUIWorkflow(None)
    wf._selected_models = [SimpleNamespace(name="newmodel")]
    try:
        wf._start_scraping()  # declined at the first dialog
    finally:
        app_signals.model_badges_reset.disconnect(on_reset)

    assert order[0] == ("reset", [])
    assert ("confirm", None) in order
    assert [] in badge_resets


def test_duplicate_start_leaves_running_chips_alone(badge_resets):
    wf = workflow_mod.GUIWorkflow(None)
    wf._scraper_thread = SimpleNamespace(is_alive=lambda: True)
    wf._start_scraping()
    assert badge_resets == []


def test_new_selection_clears_chips_when_idle(badge_resets):
    wf = workflow_mod.GUIWorkflow(None)
    wf._selected_actions = set()
    wf._on_models_selected([SimpleNamespace(name="a")])
    assert badge_resets == [[]]


def test_new_selection_keeps_chips_while_scraping(badge_resets):
    wf = workflow_mod.GUIWorkflow(None)
    wf._selected_actions = set()
    wf._scraper_thread = SimpleNamespace(is_alive=lambda: True)
    wf._on_models_selected([SimpleNamespace(name="a")])
    assert badge_resets == []


def test_badge_bar_hides_on_empty_reset(qapp):
    from ofscraper.gui.widgets.model_badge_bar import ModelBadgeBar

    bar = ModelBadgeBar()
    bar.reset_models(["oldmodel"])
    assert bar._chips
    bar.reset_models([])
    assert not bar._chips and bar._order == []
    assert bar.isHidden()


# -- 2. ticked models hidden by search --------------------------------------


@pytest.fixture
def page(qapp):
    from ofscraper.gui.pages.model_selector_page import ModelSelectorPage

    p = ModelSelectorPage()
    names = ["alpha", "bravo", "charlie"]
    p._all_models = {n: SimpleNamespace(name=n) for n in names}
    p._populate_list(names)
    return p


def _tick(page, *names):
    for i in range(page.model_list.count()):
        item = page.model_list.item(i)
        if item.data(Qt.ItemDataRole.UserRole) in names:
            item.setCheckState(Qt.CheckState.Checked)


@pytest.fixture
def emitted():
    seen = []
    slot = lambda models: seen.append([m.name for m in models])  # noqa: E731
    app_signals.models_selected.connect(slot)
    yield seen
    app_signals.models_selected.disconnect(slot)


def test_count_says_when_a_ticked_model_is_hidden(page):
    _tick(page, "alpha", "bravo")
    page.search_input.setText("bravo")
    assert page._get_hidden_selected_names() == ["alpha"]
    assert "1 hidden by search" in page.count_label.text()

    page.search_input.clear()
    assert page._get_hidden_selected_names() == []
    assert "hidden" not in page.count_label.text()


def test_next_without_hidden_ticks_does_not_ask(page, emitted, monkeypatch):
    monkeypatch.setattr(
        type(page), "_confirm_hidden_selection", lambda *a: pytest.fail("asked")
    )
    _tick(page, "bravo")
    page.search_input.setText("bravo")
    page._on_next()
    assert emitted == [["bravo"]]


@pytest.mark.parametrize(
    "answer, expected",
    [("all", [["alpha", "bravo"]]), ("visible", [["bravo"]]), ("back", [])],
)
def test_next_with_hidden_ticks_asks_first(page, emitted, monkeypatch, answer, expected):
    asked = []

    def fake_confirm(self, selected, hidden):
        asked.append((list(selected), list(hidden)))
        if answer == "all":
            return list(selected)
        if answer == "visible":
            return [n for n in selected if n not in hidden]
        return None

    monkeypatch.setattr(type(page), "_confirm_hidden_selection", fake_confirm)
    _tick(page, "alpha", "bravo")
    page.search_input.setText("bravo")
    page._on_next()
    assert asked == [(["alpha", "bravo"], ["alpha"])]
    assert emitted == expected


def test_dialog_buttons_map_to_choices(page, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    def run(pick):
        def fake_exec(box):
            for b in box.buttons():
                if b.text().startswith(pick):
                    box._picked = b
            assert box.defaultButton().text() == "Go back"

        monkeypatch.setattr(QMessageBox, "exec", fake_exec)
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box._picked)
        return page._confirm_hidden_selection(["alpha", "bravo"], ["alpha"])

    assert run("Scrape all") == ["alpha", "bravo"]
    assert run("Only the 1") == ["bravo"]
    assert run("Go back") is None
