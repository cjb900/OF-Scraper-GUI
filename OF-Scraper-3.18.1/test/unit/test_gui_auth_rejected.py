"""h15: in the GUI a refused or incomplete login ends the run with a message
for the Authentication page; it neither prompts in the terminal behind the
window nor carries on until a raw 401."""

from types import SimpleNamespace

import pytest

import ofscraper.utils.checkers as checkers


@pytest.fixture
def gui_mode(monkeypatch):
    import ofscraper.main.close.alerts as alerts
    import ofscraper.main.close.status_file as status_file

    monkeypatch.setattr(checkers.settings, "get_args", lambda: SimpleNamespace(gui=True))
    monkeypatch.setattr(alerts, "failing", lambda *a, **k: None)
    monkeypatch.setattr(status_file, "set_auth", lambda *a, **k: None)

    def no_prompt(*a, **k):
        raise AssertionError("prompted in the terminal")

    monkeypatch.setattr(checkers.make, "make_auth", no_prompt)


def test_refused_login_ends_the_gui_run(gui_mode, monkeypatch):
    monkeypatch.setattr(checkers.sites, "is_fansly", lambda: False)
    monkeypatch.setattr(checkers.init, "auth_status", lambda: ("DOWN", "401"))
    with pytest.raises(checkers.LoginRejected, match="Authentication page"):
        checkers.check_auth()


def test_incomplete_fansly_auth_is_not_asked_for_in_the_terminal(gui_mode, monkeypatch):
    import ofscraper.sites.fansly.auth as fansly_auth

    monkeypatch.setattr(checkers.sites, "is_fansly", lambda: True)
    monkeypatch.setattr(fansly_auth, "read_auth", lambda *a, **k: {"authorization_token": "short"})

    def no_load():
        raise AssertionError("load() prompts for missing auth")

    monkeypatch.setattr(fansly_auth, "load", no_load)
    with pytest.raises(checkers.LoginRejected, match="missing or incomplete"):
        checkers.check_auth()


def test_terminal_runs_still_load_the_fansly_auth(monkeypatch):
    import ofscraper.sites.fansly.auth as fansly_auth

    monkeypatch.setattr(checkers.settings, "get_args", lambda: SimpleNamespace(gui=False))
    monkeypatch.setattr(checkers.sites, "is_fansly", lambda: True)
    loaded = []
    monkeypatch.setattr(fansly_auth, "load", lambda: loaded.append(1) or {})
    monkeypatch.setattr(checkers.init, "auth_status", lambda: ("UP", ""))
    checkers.check_auth()
    assert loaded == [1]
