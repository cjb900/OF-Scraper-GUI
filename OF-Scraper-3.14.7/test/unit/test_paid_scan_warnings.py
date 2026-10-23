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
@pytest.mark.parametrize(
    "client,reason",
    [
        (_Client(status=403), "HTTP 403"),
        (_Client(data=["not", "a", "dict"]), "unexpected response format"),
        (_Client(exc=OSError("connection reset")), "connection reset"),
    ],
    ids=["http-error", "bad-format", "exception"],
)
def test_early_stop_warns(warnings_seen, scan, client, reason):
    assert asyncio.run(_scans(client)[scan]()) == []
    assert len(warnings_seen) == 1
    assert reason in warnings_seen[0] and "Purchases may be incomplete" in warnings_seen[0]


@pytest.mark.parametrize("scan", ["per-model", "all-models"])
def test_normal_page_is_yielded_without_warning(warnings_seen, scan):
    client = _Client(data={"list": [{"id": 1}], "hasMore": False})
    assert asyncio.run(_scans(client)[scan]()) == [[{"id": 1}]]
    assert warnings_seen == []
