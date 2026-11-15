"""Requests without their own read timeout must still time out.

The session took its default read timeout from OF_READ_TIMEOUT, which was
never defined, so it was None: a server that accepted the connection and
then sent nothing hung the run forever, on both the async (aiohttp) and the
sync (httpx) path.
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
import socket
import threading
import time
from types import SimpleNamespace

import aiohttp
import httpx

import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings
from ofscraper.managers.sessionmanager.sessionmanager import sessionManager
from ofscraper.utils.of_env.values.req.req import load_network_config


@pytest.fixture(autouse=True)
def plain_settings(monkeypatch):
    monkeypatch.setattr(
        settings,
        "get_settings",
        lambda: SimpleNamespace(ssl_verify="false", cached_disabled=True),
    )


def set_default(monkeypatch, value):
    """Set the default through its environment variable, as a user would."""
    monkeypatch.setenv("OFSC_READ_TIMEOUT", value)
    network = load_network_config()
    real = of_env.getattr

    def getattr_(key, default=None):
        if key in network:
            return network[key]
        return real(key, default)

    monkeypatch.setattr(of_env, "getattr", getattr_)


@pytest.fixture
def one_second_default(monkeypatch):
    set_default(monkeypatch, "1")


@pytest.fixture
def no_limit_default(monkeypatch):
    set_default(monkeypatch, "0")


class SilentServer:
    """Accepts connections, reads the request and never answers."""

    reply_after = None

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.url = f"http://127.0.0.1:{self.sock.getsockname()[1]}/api"
        self.held = []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._accept, daemon=True)
        self.thread.start()

    def _accept(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
                self.held.append(conn)
                if self.reply_after is not None:
                    threading.Thread(
                        target=self._reply, args=(conn,), daemon=True
                    ).start()
            except OSError:
                pass

    def _reply(self, conn):
        try:
            conn.settimeout(5)
            conn.recv(65536)
            time.sleep(self.reply_after)
            conn.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
            )
        except OSError:
            pass

    def close(self):
        self.stop.set()
        self.thread.join(2)
        for conn in self.held:
            conn.close()
        self.sock.close()


class SlowServer(SilentServer):
    """Answers each request after 1.5 s."""

    reply_after = 1.5


QUIET = SimpleNamespace(
    traceback_=lambda *a, **k: None,
    debug=lambda *a, **k: None,
    warning=lambda *a, **k: None,
)


def run_with_cap(fetch, cap=10, server_class=SilentServer):
    """Run fetch in a thread; report a hang instead of hanging the test."""
    server = server_class()
    result = {}

    def worker():
        start = time.monotonic()
        try:
            fetch(server.url)
            result["error"] = None
        except Exception as E:
            result["error"] = E
        result["seconds"] = time.monotonic() - start

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(cap)
    hung = thread.is_alive()
    attempts = len(server.held)
    server.close()
    thread.join(5)
    return hung, result, attempts


def test_default_read_timeout_is_set():
    assert load_network_config().get("OF_READ_TIMEOUT", 0) > 0
    assert (sessionManager()._read_timeout or 0) > 0


def test_async_request_to_a_silent_server_times_out_and_retries(one_second_default):
    def fetch(url):
        async def go():
            async with sessionManager(
                retries=2, wait_min=0, wait_max=0, log=QUIET
            ) as c:
                async with c.requests_async(url=url):
                    pass

        asyncio.run(go())

    hung, result, attempts = run_with_cap(fetch)
    assert not hung, "the request was still waiting for a response after 10 s"
    assert isinstance(result["error"], aiohttp.ServerTimeoutError), result
    assert attempts == 2
    assert result["seconds"] < 6


def test_sync_request_to_a_silent_server_times_out_and_retries(one_second_default):
    def fetch(url):
        with sessionManager(retries=2, wait_min=0, wait_max=0, log=QUIET) as c:
            with c.requests(url):
                pass

    hung, result, attempts = run_with_cap(fetch)
    assert not hung, "the request was still waiting for a response after 10 s"
    assert isinstance(result["error"], httpx.ReadTimeout), result
    assert attempts == 2
    assert result["seconds"] < 6


# A read timeout of 0 means "no limit". aiohttp already reads 0 that way, but
# httpx reads 0 as "fail at once", so the session turns any 0 into None.


def test_zero_from_any_source_means_no_limit(monkeypatch):
    # a 0 that reaches the session from of_env without the OFSC_ loader
    real = of_env.getattr
    monkeypatch.setattr(
        of_env,
        "getattr",
        lambda k, d=None: 0 if k == "OF_READ_TIMEOUT" else real(k, d),
    )
    assert sessionManager()._read_timeout is None
    # and a 0 passed to the session
    monkeypatch.setattr(of_env, "getattr", real)
    assert sessionManager(read_timeout=0)._read_timeout is None


def test_zero_passed_to_the_session_means_no_limit_on_the_sync_path():
    body = {}

    def fetch(url):
        with sessionManager(retries=1, read_timeout=0, log=QUIET) as c:
            with c.requests(url) as r:
                body["text"] = r.text_()

    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
    assert not hung
    assert result["error"] is None, result
    assert body["text"] == "ok"


def test_zero_means_no_limit_on_the_async_path(no_limit_default):
    body = {}

    def fetch(url):
        async def go():
            async with sessionManager(retries=1, log=QUIET) as c:
                async with c.requests_async(url=url) as r:
                    body["text"] = await r.text_()

        asyncio.run(go())

    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
    assert not hung
    assert result["error"] is None, result
    assert body["text"] == "ok"


def test_zero_means_no_limit_on_the_sync_path(no_limit_default):
    body = {}

    def fetch(url):
        with sessionManager(retries=1, log=QUIET) as c:
            with c.requests(url) as r:
                body["text"] = r.text_()

    hung, result, attempts = run_with_cap(fetch, server_class=SlowServer)
    assert not hung
    assert result["error"] is None, result
    assert body["text"] == "ok"
