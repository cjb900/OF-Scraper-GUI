"""Pick… sees subscriptions loaded by the Areas page; Test Credentials hides
the account name in Privacy mode.
"""
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.managers.manager as manager_mod  # noqa: E402
from ofscraper.gui.utils import gui_settings, privacy_mode  # noqa: E402


@pytest.fixture
def no_saved_creators(monkeypatch):
    monkeypatch.setattr(gui_settings, "load_gui_settings", lambda: {})


def _mm(*names):
    return SimpleNamespace(all_subs=[SimpleNamespace(name=n) for n in names])


def test_pick_uses_models_loaded_by_the_areas_page(monkeypatch, no_saved_creators):
    from ofscraper.gui.pages.action_page import ActionPage

    # Areas page fills model_manager; the profile's manager is still empty.
    fake = SimpleNamespace(model_manager=_mm("Bob", "alice"), current_model_manager=_mm())
    monkeypatch.setattr(manager_mod, "Manager", fake)
    assert ActionPage.known_creator_names() == ["alice", "Bob"]


def test_pick_also_uses_the_profile_manager(monkeypatch, no_saved_creators):
    from ofscraper.gui.pages.action_page import ActionPage

    fake = SimpleNamespace(model_manager=_mm("alice"), current_model_manager=_mm("carol", "alice"))
    monkeypatch.setattr(manager_mod, "Manager", fake)
    assert ActionPage.known_creator_names() == ["alice", "carol"]


def test_pick_survives_no_manager(monkeypatch, no_saved_creators):
    from ofscraper.gui.pages.action_page import ActionPage

    monkeypatch.setattr(manager_mod, "Manager", None)
    assert ActionPage.known_creator_names() == []


# -- Test Credentials message ------------------------------------------------


@pytest.fixture
def cred_env(tmp_path, monkeypatch):
    import ofscraper.data.api.me as me
    import ofscraper.data.models.utils.retriver as retriver
    import ofscraper.utils.auth.request as auth_request
    import ofscraper.utils.paths.common as paths

    monkeypatch.setattr(paths, "get_auth_file", lambda *a, **k: tmp_path / "auth.json")
    # Test Credentials fetches the dynamic rule before /me
    monkeypatch.setattr(auth_request, "read_request_auth", lambda: {})
    monkeypatch.setattr(
        me, "scrape_user",
        lambda *a, **k: {"isAuth": True, "name": "Real Name", "username": "realhandle"},
    )

    async def models(*a, **k):
        return [object(), object()]

    monkeypatch.setattr(retriver, "get_models", models)
    before = privacy_mode.is_privacy_mode()
    yield
    privacy_mode.set_privacy_mode(before, persist=False, emit=False)


@pytest.mark.parametrize("private", [True, False])
def test_credentials_message_respects_privacy(cred_env, private):
    from ofscraper.gui.dialogs.auth_dialog import _validate_of_credentials

    privacy_mode.set_privacy_mode(private, persist=False, emit=False)
    ok, msg = _validate_of_credentials(
        {"sess": "s", "auth_id": "1", "user_agent": "ua", "x-bc": "x"}
    )
    assert ok is True and "loaded 2 model(s)" in msg
    if private:
        assert "Real Name" not in msg and "realhandle" not in msg
        assert privacy_mode.PRIVACY_PLACEHOLDER in msg
    else:
        assert "Logged in as: Real Name (@realhandle)" in msg
