"""v507: developer tools and test control (an MCP server) for testing installs.

The patch writes ofscraper/gui/devtools only with --testing. Test control
listens on 127.0.0.1, needs the panel's token, refuses requests from web
pages, runs every tool on the Qt main thread, never logs typed text, and
refuses screenshots and Like/Unlike unless allowed.
"""
from __future__ import annotations

import base64
import importlib.util
import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui.devtools import settings as dev_settings  # noqa: E402
from ofscraper.gui.utils import devtools_loader  # noqa: E402


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def gui_settings(monkeypatch):
    import ofscraper.gui.utils.gui_settings as gs

    store = {}
    monkeypatch.setattr(gs, "load_gui_settings", lambda: json.loads(json.dumps(store)))

    def save(data, quiet=False):
        store.clear()
        store.update(data)
        return True

    monkeypatch.setattr(gs, "save_gui_settings", save)
    return store


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeWindow(QtWidgets.QMainWindow):
    """Enough of MainWindow: pages in a stack, a status bar, _navigate."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OF-Scraper test")
        self.stack = QtWidgets.QStackedWidget()
        self.setCentralWidget(self.stack)
        self._pages = {}
        for pid in ("scraper", "config"):
            page = QtWidgets.QWidget()
            self._pages[pid] = page
            self.stack.addWidget(page)
        lay = QtWidgets.QVBoxLayout(self._pages["scraper"])
        self.clicked = []
        self.start = QtWidgets.QPushButton("Start Scraping")
        self.start.clicked.connect(lambda: self.clicked.append("start"))
        self.like = QtWidgets.QPushButton("Like")
        self.like.clicked.connect(lambda: self.clicked.append("like"))
        self.name = QtWidgets.QLineEdit()
        self.box = QtWidgets.QCheckBox("Allow duplicates")
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["manual", "cdrm"])
        self.table = QtWidgets.QTableWidget(3, 2)
        self.table.setHorizontalHeaderLabels(["UserName", "Downloaded"])
        for r, (user, done) in enumerate([("alice", "True"), ("bob", "False"), ("carol", "True")]):
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(user))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(done))
        self.table.setRowHidden(1, True)  # left out by a filter
        for w in (self.start, self.like, self.name, self.box, self.combo, self.table):
            lay.addWidget(w)
        self.status_bar = QtWidgets.QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _navigate(self, page_id):
        self.stack.setCurrentWidget(self._pages[page_id])


@pytest.fixture
def running(qapp, gui_settings):
    from ofscraper.gui.devtools.server import TestControl

    window = FakeWindow()
    window.show()
    control = TestControl(window)
    control.values.update(enabled=True, port=_free_port(), token="secret-token")
    assert control.start()
    yield window, control
    control.stop()
    window.close()


def _post(control, body, token="secret-token", origin=None, path="/mcp"):
    """POST from another thread while this (main) thread runs Qt events,
    as the GUI's event loop would."""
    out = {}

    def go():
        req = urllib.request.Request(
            f"http://127.0.0.1:{control.values['port']}{path}",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
        )
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = r.read()
                out["status"], out["body"] = r.status, json.loads(text) if text else None
        except urllib.error.HTTPError as e:
            out["status"], out["body"] = e.code, None

    t = threading.Thread(target=go)
    t.start()
    app = QtWidgets.QApplication.instance()
    end = time.monotonic() + 30
    while t.is_alive() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    t.join(1)
    for _ in range(20):  # let queued actions run
        app.processEvents()
    return out


def _tool(server, name, **args):
    reply = _post(server, {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                            "params": {"name": name, "arguments": args}})
    assert reply["status"] == 200, reply
    return reply["body"]["result"]


def _text(result):
    return result["content"][0]["text"]


# --- protocol and access ---------------------------------------------------------------


def test_initialize_and_tool_list(running):
    _window, control = running
    init = _post(control, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "t", "version": "1"}}})
    assert init["status"] == 200
    assert init["body"]["result"]["protocolVersion"] == "2025-06-18"
    assert "tools" in init["body"]["result"]["capabilities"]
    # a notification gets no reply
    assert _post(control, {"jsonrpc": "2.0", "method": "notifications/initialized"})["status"] == 202
    tools = _post(control, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["body"]["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"gui_status", "list_controls", "click", "set_text", "screenshot", "wait_for"} <= names


@pytest.mark.parametrize("token", [None, "wrong"])
def test_a_missing_or_wrong_token_is_refused(running, token):
    _window, control = running
    assert _post(control, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, token=token)["status"] == 401


def test_a_web_page_cant_use_it(running):
    _window, control = running
    reply = _post(control, {"jsonrpc": "2.0", "id": 1, "method": "ping"}, origin="https://evil.example")
    assert reply["status"] == 403
    assert _post(control, {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                 origin="http://localhost:1234")["status"] == 200


def test_it_listens_on_this_computer_only(running):
    _window, control = running
    assert control._server.server_address[0] == "127.0.0.1"


# --- tools ---------------------------------------------------------------------------------


def test_status_and_controls(running):
    window, control = running
    status = json.loads(_text(_tool(control, "gui_status")))
    assert status["page"] == "scraper" and status["status_bar"] == "Ready"
    controls = json.loads(_text(_tool(control, "list_controls", kinds=["button"])))["controls"]
    assert {c["text"] for c in controls} >= {"Start Scraping", "Like"}


def test_click_by_text_runs_the_button(running):
    window, control = running
    assert not _tool(control, "click", control="Start Scraping").get("isError")
    assert window.clicked == ["start"]


def test_like_is_refused_unless_allowed(running):
    window, control = running
    result = _tool(control, "click", control="Like")
    assert result["isError"] and "account" in _text(result)
    assert window.clicked == []
    control.values["account_actions"] = True
    _tool(control, "click", control="Like")
    assert window.clicked == ["like"]


def test_typing_ticking_and_choosing(running, caplog):
    window, control = running
    handle = next(
        c["handle"] for c in json.loads(_text(_tool(control, "list_controls", kinds=["input"])))["controls"]
        if c["type"] == "QLineEdit"
    )
    with caplog.at_level(logging.INFO, logger="shared"):
        _tool(control, "set_text", control=handle, text="hunter2-password")
    assert window.name.text() == "hunter2-password"
    assert "hunter2" not in caplog.text  # typed text isn't logged
    _tool(control, "set_checked", control="Allow duplicates", checked=True)
    assert window.box.isChecked()
    _tool(control, "select", control=window.combo.currentText(), option="cdrm")
    assert window.combo.currentText() == "cdrm"


def test_reading_a_table_skips_filtered_rows(running):
    _window, control = running
    table = json.loads(_text(_tool(control, "list_controls", kinds=["table"])))["controls"][0]["handle"]
    data = json.loads(_text(_tool(control, "read", control=table)))
    assert data["total_rows"] == 3 and data["visible_rows"] == 2
    assert [r["UserName"] for r in data["rows"]] == ["alice", "carol"]


def test_navigate_and_wait_for(running):
    window, control = running
    _tool(control, "navigate", page="config")
    assert window.stack.currentWidget() is window._pages["config"]
    _tool(control, "navigate", page="scraper")
    result = json.loads(_text(_tool(control, "wait_for", text="Start Scraping", timeout=2)))
    assert result["done"] is True
    result = json.loads(_text(_tool(control, "wait_for", text="never shown", timeout=1)))
    assert result["done"] is False


def test_screenshots_only_when_allowed(running):
    _window, control = running
    refused = _tool(control, "screenshot")
    assert refused["isError"] and "turned off" in _text(refused)
    control.values["screenshots"] = True
    shot = _tool(control, "screenshot")
    image = shot["content"][0]
    assert image["type"] == "image" and image["mimeType"] == "image/png"
    assert base64.b64decode(image["data"])[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_server_stops(running):
    _window, control = running
    port = control.values["port"]
    control.stop()
    with pytest.raises(OSError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/mcp", timeout=2)


# --- settings and loading ---------------------------------------------------------------------


def test_settings_make_a_token_and_a_site_port(gui_settings, monkeypatch):
    monkeypatch.setattr(dev_settings, "site", lambda: "fansly")
    values = dev_settings.load()
    assert values["port"] == 8766 and len(values["token"]) >= 24
    assert values["enabled"] is False and values["screenshots"] is False
    assert dev_settings.load()["token"] == values["token"]  # kept
    command = dev_settings.connect_command(values)
    assert "127.0.0.1:8766/mcp" in command and values["token"] in command


def test_a_normal_install_has_no_developer_tools(monkeypatch):
    monkeypatch.setattr(devtools_loader.importlib.util, "find_spec", lambda name: None)
    assert devtools_loader.available() is False
    assert devtools_loader.patch_args() == []
    devtools_loader.install(None, None, None)  # does nothing


def test_update_now_keeps_a_testing_install(monkeypatch, tmp_path):
    import ofscraper.gui.utils.self_update as su

    monkeypatch.setattr(su, "patch_python", lambda: ["python"])
    monkeypatch.setattr(devtools_loader, "available", lambda: True)
    assert su.manual_command(tmp_path / "patch.py").endswith("patch.py --testing")
    assert 'script = next((c for c in reversed(cmd) if c.lower().endswith(".py"))' in su.HELPER


# --- the patch script ----------------------------------------------------------------------------

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.18.1_gui.py"


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_script_devtools", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_testing_installs_and_a_normal_run_removes(patch_mod, tmp_path):
    target = tmp_path / "ofscraper"
    target.mkdir()
    assert patch_mod.apply(target=str(target), backup_dir=str(tmp_path / "b1"), testing=True) == 0
    assert sorted(str(p.relative_to(target)).replace("\\", "/") for p in (target / "gui/devtools").glob("*.py")) \
        == sorted(patch_mod.DEV_FILES)
    assert (target / "gui/utils/devtools_loader.py").is_file()

    # a normal run takes them out, keeping a copy in its backup
    assert patch_mod.apply(target=str(target), backup_dir=str(tmp_path / "b2")) == 0
    assert not (target / "gui/devtools").exists()
    assert (tmp_path / "b2/gui/devtools/server.py").is_file()
    assert (target / "gui/utils/devtools_loader.py").is_file()  # the hook stays, harmless


def test_the_payload_matches_the_source(patch_mod):
    import io
    import zipfile

    src = Path(__file__).resolve().parents[2] / "ofscraper"
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(patch_mod.DEV_ZIP_B64)))
    assert sorted(zf.namelist()) == sorted(patch_mod.DEV_FILES)
    for name in zf.namelist():
        assert zf.read(name) == (src / name).read_bytes(), name


# --- secrets never leave the GUI (v508) -------------------------------------------------------

COOKIE = "sess-cookie-value-0123456789abcdef"
WEBHOOK = "https://discord.com/api/webhooks/1243/abcdefTOKEN"


class AuthPage(QtWidgets.QWidget):
    """Named like the real Authentication page (auth_dialog.AuthPage)."""

    def __init__(self):
        super().__init__()
        lay = QtWidgets.QFormLayout(self)
        self.sess = QtWidgets.QLineEdit(COOKIE)
        self.agent = QtWidgets.QLineEdit("Mozilla/5.0")
        lay.addRow("sess", self.sess)
        lay.addRow("user agent", self.agent)


@pytest.fixture
def with_secrets(running):
    window, control = running
    auth = AuthPage()
    window._pages["auth"] = auth
    window.stack.addWidget(auth)
    config = window._pages["config"]
    form = QtWidgets.QFormLayout(config)
    window.webhook = QtWidgets.QLineEdit(WEBHOOK)
    window.webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
    window.password = QtWidgets.QLineEdit("hunter2")
    form.addRow("Discord Webhook URL", window.webhook)
    form.addRow("Password", window.password)
    window.plain = QtWidgets.QLineEdit("ordinary value")
    form.addRow("Download limit", window.plain)
    return window, control


def _controls_text(control):
    return _text(_tool(control, "list_controls", limit=500))


def test_login_fields_are_masked(with_secrets):
    window, control = with_secrets
    _tool(control, "navigate", page="auth")
    listed = _controls_text(control)
    assert COOKIE not in listed and "Mozilla" not in listed
    assert f"set ({len(COOKIE)} characters)" in listed
    assert '"secret": true' in listed


def test_webhook_and_password_fields_are_masked_elsewhere(with_secrets):
    window, control = with_secrets
    _tool(control, "navigate", page="config")
    listed = _controls_text(control)
    assert WEBHOOK not in listed and "hunter2" not in listed
    assert "ordinary value" in listed  # other fields still read
    handle = next(
        c["handle"] for c in json.loads(listed)["controls"] if c.get("text") == f"set ({len(WEBHOOK)} characters)"
    )
    assert WEBHOOK not in _text(_tool(control, "read", control=handle))


def test_wait_for_cant_probe_a_secret(with_secrets):
    window, control = with_secrets
    _tool(control, "navigate", page="config")
    found = json.loads(_text(_tool(control, "wait_for", text="abcdefTOKEN", timeout=0.5)))
    assert found["done"] is False


def test_no_screenshot_of_secrets(with_secrets):
    window, control = with_secrets
    control.values["screenshots"] = True
    _tool(control, "navigate", page="auth")
    refused = _tool(control, "screenshot")
    assert refused["isError"] and "Authentication page" in _text(refused)
    _tool(control, "navigate", page="config")
    refused = _tool(control, "screenshot")
    assert refused["isError"] and "plain text" in _text(refused)
    window.webhook.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    window.password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
    assert _tool(control, "screenshot")["content"][0]["type"] == "image"


def test_the_developer_panels_token_is_masked(running):
    from ofscraper.gui.devtools.dialog import DeveloperDialog

    window, control = running
    dialog = DeveloperDialog(control, window)
    dialog.token.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal)  # "Show"
    dialog.show()
    try:
        listed = _controls_text(control)
        assert control.values["token"] not in listed
    finally:
        dialog.close()


def test_lists_skip_hidden_rows_and_tick_checkbox_items(running):
    from PyQt6.QtCore import Qt

    window, control = running
    models = QtWidgets.QListWidget()
    for name in ("alice", "melodymarksx", "carol"):
        item = QtWidgets.QListWidgetItem(name)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        models.addItem(item)
    models.item(0).setHidden(True)  # a search left it out
    window._pages["scraper"].layout().addWidget(models)
    handle = json.loads(_text(_tool(control, "list_controls", kinds=["list"])))["controls"][0]["handle"]
    items = json.loads(_text(_tool(control, "read", control=handle)))["items"]
    assert [i["text"] for i in items] == ["melodymarksx", "carol"]
    assert items[0]["checked"] is False
    assert "ticked" in _text(_tool(control, "select", control=handle, option="melodymarksx"))
    assert models.item(1).checkState() == Qt.CheckState.Checked


def test_a_dialog_owned_by_the_window_is_listed_once(running):
    window, control = running
    dialog = QtWidgets.QDialog(window)
    dialog.setWindowTitle("Download failures")
    QtWidgets.QVBoxLayout(dialog).addWidget(QtWidgets.QPushButton("Add failures to cart"))
    dialog.show()
    try:
        listed = json.loads(_text(_tool(control, "list_controls", text="Add failures to cart")))
        assert listed["count"] == 1
        assert listed["controls"][0]["window"] == "Download failures"
    finally:
        dialog.close()
