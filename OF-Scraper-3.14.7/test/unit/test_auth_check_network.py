"""A network, server or dynamic-rule problem must not be reported as bad auth.

The auth check (check_auth -> getstatus), Test Credentials and the model
list all reported a timeout, a 5xx, a 429, a reply that isn't JSON, or rule
hosts that couldn't give a usable rule as "Auth Failed", "Could not verify
credentials" or "Please check your auth information".

When no rule host gave a rule, get_request_auth returned None and
read_request_auth raised a TypeError (json.JSONDecodeError needs three
arguments). None was never cached, so every /me retry fetched the rule again
from all three rule hosts, each with its own retries.

These tests go through the real check, the real rule fetch (with its
fallback chain) and the real session manager. Only httpx.Client.send is
replaced, so nothing leaves the machine, and time.sleep, so the retry waits
don't slow the tests down.
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import json
import logging
import socket
import time
from types import SimpleNamespace

import aiohttp
import httpx
import yarl

import ofscraper.data.api.init as init
import ofscraper.managers.manager as manager
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.request as auth_requests
import ofscraper.utils.checkers as checkers
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings
from ofscraper.managers.sessionHandler import SessionHandler

RULE = {
    "static_param": "a",
    "format": "1:{}:{:x}:2",
    "checksum_indexes": [1, 2],
    "checksum_constant": 3,
}
AUTH = {
    "sess": "s",
    "auth_id": "1",
    "auth_uid": "",
    "user_agent": "Mozilla/5.0 Chrome/120.0",
    "x-bc": "x",
}
USER = {"isAuth": True, "id": 1, "username": "u1", "name": "n1"}


class AuthPrompted(Exception):
    pass


class Settings(SimpleNamespace):
    # any other setting is unset, as with no args and no config
    def __getattr__(self, name):
        return None


class _Manager:
    # like the app's Manager: `session` is a read-only property, so the
    # GUI's `Manager.session = None` fails and is ignored
    @property
    def session(self):
        return SessionHandler()


class Offline:
    """Answers every request in place of the network, and counts them."""

    def __init__(self):
        self.rule_urls = {
            of_env.getattr(key): name
            for key, name in [
                ("DATAWHORES_URL", "datawhores"),
                ("DIGITALCRIMINALS", "digitalcriminals"),
                ("RILEY_URL", "riley"),
            ]
        }
        self.rule_requests = []
        self.me_requests = 0
        self.other_requests = []
        # what each rule host and /me answer: a dict/list/None for JSON, an
        # int for a status code, an exception, or a str for a text body
        self.rules = {name: RULE for name in self.rule_urls.values()}
        self.me = USER

    def send(self, client, request, **kwargs):
        url = str(request.url)
        if url in self.rule_urls:
            name = self.rule_urls[url]
            self.rule_requests.append(name)
            return self._answer(request, self.rules[name])
        if url.split("?")[0] == of_env.getattr("meEP"):
            self.me_requests += 1
            return self._answer(request, self.me)
        self.other_requests.append(url)
        return httpx.Response(404, request=request)

    @staticmethod
    def _answer(request, what):
        if isinstance(what, Exception):
            raise type(what)(str(what), request=request)
        if isinstance(what, int):
            return httpx.Response(what, request=request, text="error")
        if isinstance(what, str):
            return httpx.Response(200, request=request, text=what)
        return httpx.Response(
            200,
            request=request,
            content=json.dumps(what).encode(),
            headers={"content-type": "application/json"},
        )


@pytest.fixture
def offline(monkeypatch):
    net = Offline()
    monkeypatch.setattr(
        httpx.Client, "send", lambda self, request, **kw: net.send(self, request, **kw)
    )

    def no_lookups(*args, **kwargs):
        raise AssertionError("a test tried to resolve a host name")

    monkeypatch.setattr(socket, "getaddrinfo", no_lookups)
    monkeypatch.setattr(time, "sleep", lambda *a, **k: None)
    run_settings = Settings(
        anon=False,
        dynamic_rules="datawhores",
        ssl_verify="false",
        cached_disabled=True,
        auth_fail=False,
    )
    run_args = SimpleNamespace(gui=False)
    monkeypatch.setattr(settings, "get_settings", lambda: run_settings)
    monkeypatch.setattr(settings, "get_args", lambda: run_args)
    monkeypatch.setattr(auth_file, "read_auth", lambda: dict(AUTH))
    monkeypatch.setattr(manager, "Manager", _Manager())
    # no rule cached from an earlier check, and nothing written to the cache
    monkeypatch.setattr(auth_requests, "curr_auth", None)
    monkeypatch.setattr(auth_requests, "last_check", None)
    monkeypatch.setattr(auth_requests.cache, "set", lambda *a, **k: None)
    # traceback_ is added to loggers by the app's log setup
    monkeypatch.setattr(
        logging.getLogger("shared"), "traceback_", lambda *a, **k: None, raising=False
    )
    prompts = []

    def make_auth(*args, **kwargs):
        prompts.append(1)
        raise AuthPrompted

    monkeypatch.setattr(checkers.make, "make_auth", make_auth)
    net.prompts = prompts
    net.settings = run_settings
    net.args = run_args
    return net


def timeout():
    return httpx.ConnectTimeout("timed out")


def run_check(caplog):
    """Run the auth check; it must end with AuthCheckUnavailable."""
    error = None
    with caplog.at_level(logging.INFO, logger="shared"):
        try:
            checkers.check_auth()
        except Exception as e:
            error = e
    assert "Auth Failed" not in caplog.text
    assert type(error).__name__ == "AuthCheckUnavailable", repr(error)
    return str(error)


# --- the auth check (scrapes) ---------------------------------------------


@pytest.mark.parametrize("gui", [False, True], ids=["cli", "gui"])
def test_rule_hosts_down_is_not_bad_auth(offline, caplog, gui):
    offline.args.gui = gui
    offline.rules = {name: timeout() for name in offline.rules}

    message = run_check(caplog)

    assert "Couldn't get a usable dynamic rule" in message
    assert (
        "datawhores: couldn't reach raw.githubusercontent.com (timed out)" in message
    )
    assert "digitalcriminals:" in message and "riley:" in message
    assert offline.prompts == []


def test_failed_rule_fetch_is_not_repeated_by_me_retries(offline, caplog):
    offline.rules = {name: timeout() for name in offline.rules}

    run_check(caplog)

    # the selected rule host and the two fallbacks, 3 tries each (GIT_NUM_TRIES),
    # once for the whole check rather than once per /me try
    assert sorted(set(offline.rule_requests)) == [
        "datawhores",
        "digitalcriminals",
        "riley",
    ]
    assert len(offline.rule_requests) == 9
    assert offline.me_requests == 0


@pytest.mark.parametrize(
    "rule,detail",
    [
        ({}, "unusable rule: missing static_param, format, checksum_indexes, checksum_constant"),
        (None, "unusable rule: expected a JSON object, got null"),
        ([], "unusable rule: expected a JSON object, got list"),
        (
            {"static_param": "a", "suffix": "s", "checksum_indexes": [1]},
            "unusable rule: missing prefix, checksum_constant",
        ),
        (500, "raw.githubusercontent.com returned 500"),
        ("<html>blocked</html>", "the reply isn't JSON"),
    ],
    ids=["empty-object", "null", "list", "missing-keys", "server-error", "not-json"],
)
def test_unusable_rule_is_reported_as_unusable(offline, caplog, rule, detail):
    offline.rules = {name: rule for name in offline.rules}

    message = run_check(caplog)

    assert f"datawhores: {detail}" in message
    assert offline.prompts == []


def test_a_broken_selected_rule_still_falls_back(offline, caplog):
    # cjb's fallback chain: the selected source fails, digitalcriminals works
    offline.rules["datawhores"] = {}
    checkers.check_auth()
    assert offline.rule_requests == ["datawhores", "digitalcriminals"]
    assert offline.me_requests == 1


@pytest.mark.parametrize(
    "reply,message",
    [
        (httpx.ConnectTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
        (httpx.ConnectError("refused"), "Couldn't reach onlyfans.com (connection failed)"),
        (httpx.ReadTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
        (429, "onlyfans.com is rate limiting requests"),
        (500, "onlyfans.com returned 500: the server had an error"),
        (502, "onlyfans.com returned 502: the server had an error"),
        ("<html>Sign in to the wifi</html>", "Got a reply that isn't JSON from OnlyFans"),
    ],
    ids=["connect-timeout", "connect-error", "read-timeout", "429", "500", "502", "not-json"],
)
@pytest.mark.parametrize("gui", [False, True], ids=["cli", "gui"])
def test_me_network_and_server_errors_are_not_bad_auth(
    offline, caplog, reply, message, gui
):
    offline.args.gui = gui
    offline.me = reply

    assert message in run_check(caplog)
    assert offline.prompts == []


@pytest.mark.parametrize("status", [400, 401, 403])
def test_rejected_auth_still_asks_for_auth(offline, caplog, status):
    offline.me = status
    with caplog.at_level(logging.INFO, logger="shared"):
        with pytest.raises(AuthPrompted):
            checkers.check_auth()
    assert "Auth Failed" in caplog.text


@pytest.mark.parametrize("status", [400, 401, 403])
def test_rejected_auth_in_the_gui_is_still_auth_failed(offline, caplog, status):
    offline.args.gui = True
    offline.me = status
    with caplog.at_level(logging.INFO, logger="shared"):
        assert checkers.check_auth() is None
    assert "Auth Failed" in caplog.text
    assert offline.prompts == []


def test_good_auth_passes(offline):
    checkers.check_auth()
    assert offline.me_requests == 1


@pytest.mark.parametrize(
    "error,message",
    [
        (
            aiohttp.ClientConnectorError(
                SimpleNamespace(host="onlyfans.com", port=443, ssl=True),
                OSError("refused"),
            ),
            "Couldn't reach onlyfans.com (connection failed)",
        ),
        (
            aiohttp.ClientResponseError(
                aiohttp.RequestInfo(
                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
                    "GET",
                    {},
                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
                ),
                (),
                status=503,
            ),
            "onlyfans.com returned 503: the server had an error",
        ),
    ],
    ids=["aiohttp-connect", "aiohttp-503"],
)
def test_async_errors_are_network_problems(error, message):
    # the model list's async requests raise aiohttp errors
    assert message in init.unavailable_message(error)


# --- Test Credentials and the model list (GUI) ----------------------------


@pytest.fixture
def gui_auth(offline, tmp_path, monkeypatch):
    pytest.importorskip("PyQt6.QtWidgets")
    from ofscraper.gui.dialogs import auth_dialog
    from ofscraper.gui.utils import auth_errors
    import ofscraper.utils.auth.utils.dict as auth_dict
    import ofscraper.utils.paths.common as common_paths

    # Test Credentials writes the auth it tests to auth.json, then restores it
    monkeypatch.setattr(common_paths, "get_auth_file", lambda *a, **k: tmp_path / "auth.json")
    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))

    offline.auth_dialog = auth_dialog
    offline.auth_errors = auth_errors
    offline.args.gui = True
    return offline


def test_credentials_with_rule_hosts_down_are_not_reported_invalid(gui_auth):
    gui_auth.rules = {name: timeout() for name in gui_auth.rules}

    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))

    assert result == "unavailable", text  # CRED_TEST_UNAVAILABLE
    assert "network or server problem, not a problem with your auth" in text
    assert "Couldn't get a usable dynamic rule" in text
    # the rule is fetched once for the test, not once per /me try
    assert len(gui_auth.rule_requests) == 9
    assert gui_auth.me_requests == 0


@pytest.mark.parametrize(
    "reply,message",
    [
        (httpx.ConnectTimeout("timed out"), "Couldn't reach onlyfans.com (timed out)"),
        (502, "onlyfans.com returned 502"),
        (429, "onlyfans.com is rate limiting requests"),
        ("<html>blocked</html>", "Got a reply that isn't JSON"),
    ],
    ids=["timeout", "502", "429", "not-json"],
)
def test_credentials_with_onlyfans_unreachable_are_not_reported_invalid(
    gui_auth, reply, message
):
    gui_auth.me = reply

    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))

    assert result == "unavailable", text  # CRED_TEST_UNAVAILABLE
    assert message in text
    assert "not a problem with your auth" in text


def test_rejected_credentials_are_still_invalid(gui_auth):
    gui_auth.me = 401

    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))

    assert result is False, text
    assert "Auth error" in text


def test_model_list_with_rule_hosts_down_is_not_an_auth_problem(gui_auth, tmp_path, monkeypatch):
    from ofscraper.gui.utils import model_fetch

    gui_auth.rules = {name: timeout() for name in gui_auth.rules}
    import ofscraper.utils.auth.utils.dict as auth_dict

    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))

    with pytest.raises(Exception) as e:
        model_fetch.fetch_subscription_models(timeout_sec=30)
    main, detail = gui_auth.auth_errors.model_load_failure_dialog_text(str(e.value))

    assert "network or server problem, not a problem with your auth" in main
    assert "Couldn't get a usable dynamic rule" in main
    assert "check your auth information" not in main
    assert detail == str(e.value)


def test_model_list_with_onlyfans_down_is_not_an_auth_problem(gui_auth, monkeypatch):
    from ofscraper.gui.utils import model_fetch
    import ofscraper.utils.auth.utils.dict as auth_dict

    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))
    monkeypatch.setattr(
        httpx.Client,
        "send",
        lambda self, request, **kw: (
            gui_auth.send(self, request, **kw)
            if str(request.url) in gui_auth.rule_urls
            else Offline._answer(request, 502)
        ),
    )

    with pytest.raises(Exception) as e:
        model_fetch.fetch_subscription_models(timeout_sec=30)
    main, _ = gui_auth.auth_errors.model_load_failure_dialog_text(str(e.value))

    assert "returned 502: the server had an error" in main
    assert "check your auth information" not in main


def test_model_list_auth_errors_are_unchanged():
    from ofscraper.gui.utils import auth_errors

    main, _ = auth_errors.model_load_failure_dialog_text(
        "Model list fetch failed: Client error '401 Unauthorized'"
    )
    assert "Please check your auth information" in main
