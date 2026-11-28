"""h12: Back to the first page and Next again left the Areas page on
"Waiting to load models" with Next off, because the models were loaded."""

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui.pages.area_selector_page import AreaSelectorPage  # noqa: E402


class _Label:
    def __init__(self):
        self.text = "Waiting to load models..."

    def setText(self, text):
        self.text = text


class _Button:
    def __init__(self):
        self.enabled = False

    def setEnabled(self, on):
        self.enabled = on


class _Page:
    start_pending_model_load = AreaSelectorPage.start_pending_model_load

    def __init__(self, loaded_for, now):
        self._current_actions = {"download"}
        self._pending_model_load = True
        self._models_loading = False
        self._models_loaded = True
        self._models_loaded_for = loaded_for
        self._loaded_model_count = 3
        self._now = now
        self.model_loading_label = _Label()
        self.next_btn = _Button()
        self.loads = 0

    def _get_active_userlist(self):
        return list(self._now)

    def _start_model_load(self):
        self.loads += 1


def test_same_list_keeps_the_models_and_turns_next_back_on():
    page = _Page(["test"], ["test"])
    page.start_pending_model_load()
    assert page.loads == 0
    assert page.next_btn.enabled
    assert page.model_loading_label.text == "Models loaded: 3"


@pytest.mark.parametrize("now", [[], ["other"]])
def test_another_list_loads_its_creators(now):
    page = _Page(["test"], now)
    page.start_pending_model_load()
    assert page.loads == 1
    assert page._models_loaded is False


def test_a_load_already_running_is_left_alone():
    page = _Page(["test"], [])
    page._models_loading = True
    page.start_pending_model_load()
    assert page.loads == 0
