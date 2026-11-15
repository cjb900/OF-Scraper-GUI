import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
from types import SimpleNamespace

import ofscraper.data.models.utils.retriver as retriver
import ofscraper.utils.args.accessors.read as read_args
from ofscraper.classes.of.models import Model
from ofscraper.managers import model as model_manager
from ofscraper.utils.args.mutators.user import resetUserSelect


def test_reset_user_select_clears_to_empty_list(monkeypatch):
    monkeypatch.setattr(
        read_args, "retriveArgs", lambda: SimpleNamespace(usernames=["a", "b"])
    )
    assert resetUserSelect().usernames == []


def test_selection_after_reset_opens_selector(monkeypatch):
    # "Yes Update Selection" left usernames=None, and `"ALL" in None`
    # dropped the user back to the main menu
    mm = model_manager.ModelManager()
    models = [Model({"id": i, "username": f"m{i}"}) for i in range(3)]
    mm._update_all_subs(models)
    monkeypatch.setattr(
        model_manager.settings,
        "get_settings",
        lambda: SimpleNamespace(usernames=None, daemon=None),
    )
    monkeypatch.setattr(mm, "_filter_and_prompt_for_selection", lambda: {m.name: m for m in models})
    monkeypatch.setattr(retriver, "get_selected_model", lambda found, existing: found[:1])
    assert [m.name for m in mm._select_models_scraper()] == ["m0"]
