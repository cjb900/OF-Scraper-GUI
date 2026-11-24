import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import warnings

import httpx

from ofscraper.managers.sessionmanager.sessionmanager import sessionManager


def _manager(seen):
    def handler(request):
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, json={})

    m = sessionManager.__new__(sessionManager)
    m._session = httpx.Client(transport=httpx.MockTransport(handler))
    return m


def test_request_cookies_are_sent_for_that_request_only():
    seen = []
    m = _manager(seen)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        m._httpx_funct("get", url="https://onlyfans.com/api2/v2/me", cookies={"sess": "s"})
        m._httpx_funct("get", url="https://cdn.example/x")
    # _httpx_funct clears the client's jar before each request, so only the
    # cookies passed for a request are sent, and they don't carry over
    assert seen == ["sess=s", None]
    assert "sess" not in m._session.cookies
