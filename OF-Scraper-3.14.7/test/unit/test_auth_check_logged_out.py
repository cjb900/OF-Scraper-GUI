"""The auth check must report a logged-out session as bad auth.

If /me answered {"isAuth": false}, getstatus() said UP: scrape_user() only
reads isAuth to decide whether to record the user's details. The check is
in getstatus() only. Anonymous runs ask /me for the user id too (the
self-media filter), get isAuth false, and get_id() falls back to
'id_unknown' for that reply, so scrape_user() must keep accepting it.
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import logging
from contextlib import contextmanager
from types import SimpleNamespace

import ofscraper.data.api.init as init
import ofscraper.data.api.me as me
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.request as auth_requests
import ofscraper.utils.checkers as checkers
import ofscraper.utils.me as me_util
import ofscraper.utils.profiles.data as profile_data
import ofscraper.utils.settings as settings


class AuthPrompted(Exception):
    pass


@pytest.fixture
def me_replies(monkeypatch):
    """/me answers with the given JSON through the real me.scrape_user."""
    run_settings = SimpleNamespace(anon=False, auth_fail=False)
    run_args = SimpleNamespace(gui=False)
    monkeypatch.setattr(settings, "get_settings", lambda: run_settings)
    monkeypatch.setattr(settings, "get_args", lambda: run_args)
    monkeypatch.setattr(
        logging.getLogger("shared"), "traceback_", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(auth_file, "read_auth", lambda: {})
    # signing isn't part of this test
    monkeypatch.setattr(auth_requests, "read_request_auth", lambda: {})
    # scrape_user registers the user's id and names for log redaction, for
    # the rest of the process; keep the test user out of other tests
    monkeypatch.setattr(me.sensitive, "add_sensitive_pattern", lambda *a, **k: None)
    prompts = []

    def make_auth(*args, **kwargs):
        prompts.append(1)
        raise AuthPrompted

    monkeypatch.setattr(checkers.make, "make_auth", make_auth)

    def set_reply(data):
        @contextmanager
        def requests(url, *args, **kwargs):
            yield SimpleNamespace(json_=lambda: data)

        @contextmanager
        def get_ofsession(*args, **kwargs):
            yield SimpleNamespace(requests=requests)

        monkeypatch.setattr(
            me.manager,
            "Manager",
            SimpleNamespace(session=SimpleNamespace(get_ofsession=get_ofsession)),
        )

    set_reply.settings = run_settings
    set_reply.args = run_args
    set_reply.prompts = prompts
    return set_reply


def test_logged_out_session_is_reported_as_bad_auth(me_replies):
    me_replies({"isAuth": False})
    assert init.getstatus() == "DOWN"


def test_logged_out_session_asks_for_auth_in_the_cli(me_replies, caplog):
    me_replies({"isAuth": False})
    with caplog.at_level(logging.INFO, logger="shared"):
        with pytest.raises(AuthPrompted):
            checkers.check_auth()
    assert "isn't logged in" in caplog.text
    assert "Auth Failed" in caplog.text


def test_logged_out_session_is_auth_failed_in_the_gui(me_replies, caplog):
    # GUI scrapes log "Auth Failed" and carry on, as for a 401
    me_replies.args.gui = True
    me_replies({"isAuth": False})
    with caplog.at_level(logging.INFO, logger="shared"):
        assert checkers.check_auth() is None
    assert "Auth Failed" in caplog.text
    assert me_replies.prompts == []


def test_logged_in_session_passes(me_replies):
    me_replies({"isAuth": True, "id": 1, "username": "u1", "name": "n1"})
    assert init.getstatus() == "UP"


def test_anon_run_still_gets_unknown_id(me_replies, monkeypatch):
    # --anon metadata runs ask /me for the user id (self-media filter), and
    # /me answers isAuth false because no one is logged in
    me_replies.settings.anon = True
    monkeypatch.setattr(profile_data, "get_active_profile", lambda: "a_profile")
    monkeypatch.setattr(profile_data, "currentProfile", None)
    monkeypatch.setattr(profile_data, "currentData", None)
    me_replies({"isAuth": False})

    assert me_util.get_id() == "id_unknown"
    assert me_util.get_id() == "id_unknown"

    # the same reply still fails the auth check of a logged-in run
    me_replies.settings.anon = False
    assert init.getstatus() == "DOWN"
