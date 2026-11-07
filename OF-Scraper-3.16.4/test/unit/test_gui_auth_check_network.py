"""In the GUI, a network, server or dynamic-rule problem must not be reported
as bad auth.

Test Credentials said "Credentials Invalid" and the model list said "Please
check your auth information" for a timeout, a 5xx, a 429, a reply that isn't
JSON, or a rule host that couldn't give a usable rule.

The scraper's own auth check (check_auth -> getstatus) already tells these
apart: test/test_auth_check_network.py covers it. These tests cover the GUI
side, which uses the scraper's unavailable_message and adds the aiohttp
errors of the model list's async requests.

They go through the real Test Credentials check, the real rule fetch and the
real session manager. Only httpx.Client.send is replaced, so nothing leaves
the machine, and time.sleep, so the retry waits don't slow the tests down.
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

import ofscraper.data.api.me as me
import ofscraper.managers.manager as manager
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.request as auth_requests
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
        self.rule_url = of_env.getattr("DATAWHORES_URL")
        self.rule_requests = 0
        self.me_requests = 0
        # what the rule host and /me answer: a dict/list/None for JSON, an
        # int for a status code, an exception, or a str for a text body
        self.rule = RULE
        self.me = USER

    def send(self, client, request, **kwargs):
        url = str(request.url)
        if url == self.rule_url:
            self.rule_requests += 1
            return self._answer(request, self.rule)
        if url.split("?")[0] == of_env.getattr("meEP"):
            self.me_requests += 1
            return self._answer(request, self.me)
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


def timeout():
    return httpx.ConnectTimeout("timed out")


@pytest.fixture
def gui_auth(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6.QtWidgets")
    from ofscraper.gui.dialogs import auth_dialog
    from ofscraper.gui.utils import auth_errors
    import ofscraper.utils.auth.utils.dict as auth_dict
    import ofscraper.utils.paths.common as common_paths

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
    monkeypatch.setattr(settings, "get_settings", lambda: run_settings)
    monkeypatch.setattr(settings, "get_args", lambda: Settings(gui=True))
    monkeypatch.setattr(auth_file, "read_auth", lambda: dict(AUTH))
    monkeypatch.setattr(manager, "Manager", _Manager())
    # no rule cached from an earlier check, and nothing written to the cache
    monkeypatch.setattr(auth_requests, "curr_auth", None)
    monkeypatch.setattr(auth_requests, "last_check", None)
    monkeypatch.setattr(auth_requests.cache, "set", lambda *a, **k: None)
    # scrape_user registers the user's id and names for log redaction, for
    # the rest of the process; keep the test user out of other tests
    monkeypatch.setattr(me.sensitive, "add_sensitive_pattern", lambda *a, **k: None)
    # traceback_ is added to loggers by the app's log setup
    monkeypatch.setattr(
        logging.getLogger("shared"), "traceback_", lambda *a, **k: None, raising=False
    )
    # Test Credentials writes the auth it tests to auth.json, then restores it
    monkeypatch.setattr(common_paths, "get_auth_file", lambda *a, **k: tmp_path / "auth.json")
    monkeypatch.setattr(auth_dict, "get_auth_dict", lambda *a, **k: dict(AUTH))

    net.auth_dialog = auth_dialog
    net.auth_errors = auth_errors
    return net


# --- Test Credentials -------------------------------------------------------


def test_credentials_with_the_rule_host_down_are_not_reported_invalid(gui_auth):
    gui_auth.rule = timeout()

    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))

    assert result == "unavailable", text  # CRED_TEST_UNAVAILABLE
    assert "network or server problem, not a problem with your auth" in text
    assert "Couldn't reach raw.githubusercontent.com (timed out)" in text
    # the rule is fetched once for the test (with its own retries,
    # GIT_NUM_TRIES), not once per /me try
    assert gui_auth.rule_requests == of_env.getattr("GIT_NUM_TRIES")
    assert gui_auth.me_requests == 0


def test_credentials_with_an_unusable_rule_are_not_reported_invalid(gui_auth):
    gui_auth.rule = {}

    result, text = gui_auth.auth_dialog._validate_of_credentials(dict(AUTH))

    assert result == "unavailable", text
    assert "The dynamic rule (datawhores) is unusable" in text
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


# --- the model list -----------------------------------------------------------


def test_model_list_with_the_rule_host_down_is_not_an_auth_problem(gui_auth):
    from ofscraper.gui.utils import model_fetch

    gui_auth.rule = timeout()

    with pytest.raises(Exception) as e:
        model_fetch.fetch_subscription_models(timeout_sec=30)
    main, detail = gui_auth.auth_errors.model_load_failure_dialog_text(str(e.value))

    assert "network or server problem, not a problem with your auth" in main
    assert "Couldn't reach raw.githubusercontent.com" in main
    assert "check your auth information" not in main
    assert detail == str(e.value)


def test_model_list_with_onlyfans_down_is_not_an_auth_problem(gui_auth, monkeypatch):
    from ofscraper.gui.utils import model_fetch

    monkeypatch.setattr(
        httpx.Client,
        "send",
        lambda self, request, **kw: (
            gui_auth.send(self, request, **kw)
            if str(request.url) == gui_auth.rule_url
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
        (
            aiohttp.ClientResponseError(
                aiohttp.RequestInfo(
                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
                    "GET",
                    {},
                    yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
                ),
                (),
                status=429,
            ),
            "onlyfans.com is rate limiting requests",
        ),
    ],
    ids=["aiohttp-connect", "aiohttp-503", "aiohttp-429"],
)
def test_async_errors_are_network_problems(error, message):
    # the model list's async requests raise aiohttp errors
    from ofscraper.gui.utils import auth_errors

    assert message in auth_errors.network_problem_message(error)


def test_async_auth_errors_are_not_network_problems():
    from ofscraper.gui.utils import auth_errors

    error = aiohttp.ClientResponseError(
        aiohttp.RequestInfo(
            yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
            "GET",
            {},
            yarl.URL("https://onlyfans.com/api2/v2/subscriptions"),
        ),
        (),
        status=401,
    )
    assert auth_errors.network_problem_message(error) is None
