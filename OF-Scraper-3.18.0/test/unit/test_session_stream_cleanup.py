"""requests_async must close a streamed response when the caller's code fails.

requests_async yielded the response from inside tenacity's retry attempt. An
error raised while the caller was reading it (e.g. a read timeout on a
stalled CDN download) was thrown back into that attempt, which swallows every
exception: the response was never closed, the semaphore was released a
second time, and a new request was sent and yielded again. The caller got a
RuntimeError instead of the timeout, and each failed download left
connections open with unread data (datawhores/OF-Scraper#655).
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
import asyncio
import gc
from types import SimpleNamespace

from aiohttp import web

import ofscraper.utils.settings as settings
from ofscraper.managers.sessionmanager.sessionmanager import sessionManager

QUIET = SimpleNamespace(
    traceback_=lambda *a, **k: None,
    debug=lambda *a, **k: None,
    warning=lambda *a, **k: None,
)


@pytest.fixture(autouse=True)
def plain_settings(monkeypatch):
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
    )


async def serve(handler):
    app = web.Application()
    app.router.add_get("/f", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/f"


def session():
    return sessionManager(
        sem_count=2, retries=3, wait_min=0, wait_max=0, read_timeout=0.5, log=QUIET
    )


def connected(transports):
    return sum(1 for t in transports if t is not None and not t.is_closing())


def test_stalled_stream_is_closed_and_not_requested_again():
    transports = []
    stop = asyncio.Event()

    async def stalled(request):
        transports.append(request.transport)
        resp = web.StreamResponse(headers={"Content-Length": str(10 * 1024 * 1024)})
        await resp.prepare(request)
        await resp.write(b"x" * 65536)
        await stop.wait()
        return resp

    async def run():
        runner, url = await serve(stalled)
        errors = []
        try:
            async with session() as c:
                for _ in range(3):
                    try:
                        async with c.requests_async(url=url, total_timeout=None) as r:
                            async for _ in r.iter_chunked(65536):
                                pass
                    except Exception as E:
                        errors.append(E)
                    gc.collect()
                    await asyncio.sleep(0.2)
                in_use = len(c._session.connector._acquired)
                still_connected = connected(transports)
                free = c._sem._value
        finally:
            stop.set()
            await runner.cleanup()
        return errors, in_use, still_connected, free

    errors, in_use, still_connected, free = asyncio.run(run())
    # the caller sees the real timeout, once per download, and no retry inside
    assert len(errors) == 3
    assert all(isinstance(E, asyncio.TimeoutError) for E in errors), errors
    assert len(transports) == 3, f"{len(transports)} requests for 3 downloads"
    # and nothing is left open
    assert in_use == 0
    assert still_connected == 0
    assert free == 2


def test_completed_stream_is_released():
    async def ok(request):
        return web.Response(body=b"y" * 200000)

    async def run():
        runner, url = await serve(ok)
        try:
            async with session() as c:
                async with c.requests_async(url=url) as r:
                    body = b"".join([x async for x in r.iter_chunked(65536)])
                in_use = len(c._session.connector._acquired)
                free = c._sem._value
        finally:
            await runner.cleanup()
        return body, in_use, free

    body, in_use, free = asyncio.run(run())
    assert body == b"y" * 200000
    assert in_use == 0
    assert free == 2


def test_failed_status_is_still_retried():
    calls = []

    async def flaky(request):
        calls.append(1)
        if len(calls) < 3:
            return web.Response(status=500, text="try again")
        return web.Response(text="done")

    async def run():
        runner, url = await serve(flaky)
        try:
            async with session() as c:
                async with c.requests_async(url=url) as r:
                    text = await r.text_()
                in_use = len(c._session.connector._acquired)
                free = c._sem._value
        finally:
            await runner.cleanup()
        return text, in_use, free

    text, in_use, free = asyncio.run(run())
    assert text == "done"
    assert len(calls) == 3
    assert in_use == 0
    assert free == 2
