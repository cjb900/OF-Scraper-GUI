# GUI tree tests from the 3.14.7 tree's test/unit/test_paid_scan_warnings.py that the fork's test/test_paid_scan_warnings.py does not have
import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import asyncio
import logging
from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.unit

import ofscraper.data.api.paid as paid


class _Response:
    def __init__(self, status, data):
        self.status = status
        self._data = data

    async def json_(self):
        return self._data


class _Client:
    def __init__(self, status=200, data=None, exc=None):
        self.status, self.data, self.exc = status, data, exc

    @asynccontextmanager
    async def requests_async(self, url):
        if self.exc:
            raise self.exc
        yield _Response(self.status, self.data)


@pytest.fixture
def warnings_seen(monkeypatch):
    monkeypatch.setattr(paid.progress_utils.api, "add_job_task", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(paid.log, "traceback_", lambda *a, **k: None, raising=False)
    seen = []

    class Capture(logging.Handler):
        def emit(self, record):
            if record.levelno == logging.WARNING:
                seen.append(record.getMessage())

    handler = Capture()
    paid.log.addHandler(handler)
    yield seen
    paid.log.removeHandler(handler)


def _scans(client):
    async def per_model():
        return [b async for b in paid.scrape_paid(client, "model")]

    async def all_models():
        return [b async for b in paid.scrape_all_paid(client)]

    return {"per-model": per_model, "all-models": all_models}


@pytest.mark.parametrize("scan", ["per-model", "all-models"])
def test_http_error_warning_does_not_leak_request_headers(warnings_seen, scan):
    # repr() of an aiohttp ClientResponseError includes the request headers,
    # i.e. the session cookie and signing headers; the warning must not
    from aiohttp import ClientResponseError, RequestInfo
    from multidict import CIMultiDict, CIMultiDictProxy
    from yarl import URL

    url = URL("https://onlyfans.com/api2/v2/posts/paid/all?offset=0")
    headers = CIMultiDictProxy(CIMultiDict({"Cookie": "sess=SECRET", "x-bc": "SECRET"}))
    exc = ClientResponseError(RequestInfo(url, "GET", headers, url), (), status=403)
    assert asyncio.run(_scans(_Client(exc=exc))[scan]()) == []
    assert len(warnings_seen) == 1
    assert "SECRET" not in warnings_seen[0]
    assert "ClientResponseError" in warnings_seen[0] and "403" in warnings_seen[0]
