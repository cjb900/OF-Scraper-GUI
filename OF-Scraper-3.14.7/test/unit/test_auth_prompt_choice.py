"""The CLI auth prompt must act on "Quit" and "Go to Main Menu".

check_auth() ignored what make_auth() returned, so picking either one
brought the auth prompt straight back. (GUI mode never shows this prompt.)
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
from types import SimpleNamespace

import ofscraper.data.api.init as init
import ofscraper.utils.checkers as checkers
import ofscraper.utils.menu as menu
import ofscraper.utils.settings as settings


class PromptAgain(Exception):
    """The auth prompt came back after the user left it."""


@pytest.fixture
def failed_auth(monkeypatch):
    """The auth check fails as bad auth; the auth prompt answers with `choice`."""
    monkeypatch.setattr(init, "auth_status", lambda: ("DOWN", None))
    monkeypatch.setattr(checkers.auth_file, "read_auth", lambda: {})
    monkeypatch.setattr(settings, "get_args", lambda: SimpleNamespace(gui=False))
    monkeypatch.setattr(
        settings, "get_settings", lambda: SimpleNamespace(daemon=False)
    )
    calls = []

    def answer(choice):
        def make_auth(auth=None, include_main_menu=False):
            calls.append(include_main_menu)
            if len(calls) > 1:
                raise PromptAgain
            return None, choice

        monkeypatch.setattr(checkers.make, "make_auth", make_auth)
        return calls

    return answer


def test_quit_in_the_auth_prompt_quits(failed_auth):
    calls = failed_auth("quit")
    with pytest.raises(SystemExit):
        checkers.check_auth()
    assert len(calls) == 1


def test_main_in_the_auth_prompt_returns_to_the_main_menu(failed_auth, monkeypatch):
    calls = failed_auth("main")
    # main menu: pick an action and run it, then quit at the next main menu
    main_answers = iter(["action", "quit"])
    monkeypatch.setattr(menu.prompts, "main_prompt", lambda: next(main_answers))
    monkeypatch.setattr(menu.prompts, "action_prompt", lambda: "download")
    monkeypatch.setattr(
        menu.console,
        "get_shared_console",
        lambda: SimpleNamespace(clear_live=lambda: None),
    )

    assert menu.main_menu_action() is True
    # the auth prompt offered "Go to Main Menu" and wasn't shown again
    assert calls == [True]
    assert next(main_answers, None) is None


def test_other_runs_are_not_offered_the_main_menu(failed_auth):
    # one-off runs, the daemon and check/manual/metadata call check_auth()
    calls = failed_auth("quit")
    with pytest.raises(SystemExit):
        checkers.check_auth()
    assert calls == [False]
