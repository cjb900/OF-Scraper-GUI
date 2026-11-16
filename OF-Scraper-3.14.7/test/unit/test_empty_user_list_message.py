"""A creator's username typed into the User Lists box matches no OnlyFans
list, so the model list comes back empty. The Unable to Load Models dialog
then said to check the auth, change Dynamic Mode or turn SSL Verify off."""
from types import SimpleNamespace

import pytest

import ofscraper.utils.settings as settings
from ofscraper.gui.utils import auth_errors

pytestmark = pytest.mark.unit


def _user_lists(monkeypatch, lists):
    monkeypatch.setattr(
        settings, "get_settings", lambda *a, **k: SimpleNamespace(userlist=lists)
    )


def test_empty_list_with_a_user_lists_filter_names_the_filter(monkeypatch):
    _user_lists(monkeypatch, ["some_creator"])
    main, detail = auth_errors.model_load_failure_dialog_text()

    assert "User Lists" in main and "some_creator" in main
    assert "not creator usernames" in main
    assert "check your auth information" not in main
    assert "SSL Verify" not in main
    assert detail is None


def test_built_in_list_names_are_not_a_filter(monkeypatch):
    _user_lists(monkeypatch, ["main", "ofscraper.active"])
    assert auth_errors.active_user_lists() == []
    main, _ = auth_errors.model_load_failure_dialog_text()
    assert "Please check your auth information" in main


def test_empty_list_without_a_filter_is_unchanged(monkeypatch):
    _user_lists(monkeypatch, [])
    main, detail = auth_errors.model_load_failure_dialog_text()
    assert "Please check your auth information" in main
    assert detail is None


def test_a_failed_fetch_keeps_its_message_with_a_filter_set(monkeypatch):
    _user_lists(monkeypatch, ["some_creator"])
    main, detail = auth_errors.model_load_failure_dialog_text(
        "Model list fetch failed: Client error '401 Unauthorized'"
    )
    assert "Please check your auth information" in main
    assert "User Lists filter" not in main
    assert detail
