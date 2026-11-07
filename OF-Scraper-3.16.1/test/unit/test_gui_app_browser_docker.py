"""Login in App Browser must open inside Docker (it is the only browser login there)."""
import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.dialogs.auth_dialog as auth_dialog  # noqa: E402

pytestmark = pytest.mark.unit


class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)


class _FakeLoginDialog:
    created = []

    def __init__(self, parent):
        self.parent = parent
        self.credentials_ready = _Signal()
        self.executed = False
        _FakeLoginDialog.created.append(self)

    def exec(self):
        self.executed = True


class _FakePage:
    def __init__(self):
        self.busy_calls = []

    def _set_browser_login_busy(self, busy, status=""):
        self.busy_calls.append(busy)

    def _apply_browser_credentials(self, creds):
        pass


@pytest.fixture
def in_docker(monkeypatch):
    real_exists = os.path.exists
    monkeypatch.setattr(
        auth_dialog.os.path,
        "exists",
        lambda p: True if p == "/.dockerenv" else real_exists(p),
    )
    real_open = open

    def fake_open(path, *a, **kw):
        if path == "/proc/1/cgroup":
            import io

            return io.StringIO("0::/docker/abc123\n")
        return real_open(path, *a, **kw)

    monkeypatch.setattr("builtins.open", fake_open)


def test_app_browser_login_opens_in_docker(monkeypatch, in_docker):
    _FakeLoginDialog.created.clear()
    monkeypatch.setattr(auth_dialog, "BrowserLoginDialog", _FakeLoginDialog)
    shown = []
    monkeypatch.setattr(
        auth_dialog.QMessageBox, "information", lambda *a, **k: shown.append(a)
    )
    page = _FakePage()

    auth_dialog.AuthPage._open_browser_login(page)

    assert not shown, "no 'not supported in Docker' message"
    assert len(_FakeLoginDialog.created) == 1
    dlg = _FakeLoginDialog.created[0]
    assert dlg.executed
    assert dlg.credentials_ready.slots == [page._apply_browser_credentials]
    assert page.busy_calls == [True, False]


def test_auth_page_has_no_docker_gate():
    assert not hasattr(auth_dialog.AuthPage, "_is_docker")
