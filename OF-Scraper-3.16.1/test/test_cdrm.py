import asyncio
import contextlib
import logging
from types import SimpleNamespace

import pytest

import ofscraper.commands.scraper.actions.download.utils.keyhelpers as keyhelpers
import ofscraper.utils.system.network as network


class _Response:
    ok = True
    status = 200
    headers = {}

    def text_(self):
        return ""

    async def json_(self):
        return {"message": "kid:key"}


class _Session:
    def __init__(self):
        self.calls = []

    @contextlib.asynccontextmanager
    async def requests_async(self, **kw):
        self.calls.append(kw)
        yield _Response()

    @contextlib.contextmanager
    def requests(self, **kw):
        self.calls.append(kw)
        yield _Response()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_cdrm_sends_only_pssh_and_license_url(monkeypatch):
    # GUI tree: unlike the fork (which sends the session headers, #43), the
    # remote key helper never gets the OnlyFans cookies, sign or x-bc
    monkeypatch.setattr(keyhelpers, "get_cmd_download_req_retries", lambda: 1)
    monkeypatch.setattr(keyhelpers, "log", logging.getLogger("test"))
    session = _Session()

    key = asyncio.run(keyhelpers.key_helper_cdrm(session, "pssh", "https://lic", 1))

    assert key == "kid:key"
    assert session.calls[0]["json"] == {"licurl": "https://lic", "pssh": "pssh"}


@pytest.mark.parametrize("status,ok", [(200, True), (405, True), (404, False), (500, False)])
def test_cdrm_health_check(monkeypatch, status, ok):
    session = _Session()
    _Response.status = status
    _Response.ok = 200 <= status < 300
    monkeypatch.setattr(
        network.settings, "get_settings", lambda: SimpleNamespace(key_mode="cdrm")
    )
    monkeypatch.setattr(network.sessionManager, "sessionManager", lambda **kw: session)
    monkeypatch.setattr(network.time, "sleep", lambda *a: None)
    try:
        assert network.check_cdm() is ok
    finally:
        _Response.status, _Response.ok = 200, True
