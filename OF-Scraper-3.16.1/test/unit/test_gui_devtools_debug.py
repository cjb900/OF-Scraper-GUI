import os

import pytest

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.app as gui_app  # noqa: E402
import ofscraper.gui.dialogs.auth_dialog as auth_dialog  # noqa: E402
from ofscraper.gui.dialogs.model_selector_dialog import ModelSelectorDialog  # noqa: E402

pytestmark = pytest.mark.unit


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    elif not isinstance(app, QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


@pytest.fixture
def env(monkeypatch):
    for name in (gui_app.WEBENGINE_DEBUG_ENV, "OFSCRAPER_WEBENGINE_DEBUG_PORT", "QTWEBENGINE_REMOTE_DEBUGGING"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(auth_dialog, "_WEBENGINE_DEBUG_PORT", None)
    return monkeypatch


def test_debugging_is_off_by_default(env):
    flags = gui_app.webengine_flags()
    assert "--remote-debugging-port" not in flags
    assert "--disable-web-security" not in flags and "--remote-allow-origins=*" not in flags
    assert "OFSCRAPER_WEBENGINE_DEBUG_PORT" not in os.environ
    assert auth_dialog._get_or_create_debug_port() is None


def test_debugging_can_be_turned_on(env):
    env.setenv(gui_app.WEBENGINE_DEBUG_ENV, "1")
    flags = gui_app.webengine_flags()
    port = os.environ["OFSCRAPER_WEBENGINE_DEBUG_PORT"]
    assert f"--remote-debugging-port={port}" in flags
    assert f"--remote-allow-origins=http://localhost:{port}," in flags
    assert auth_dialog._get_or_create_debug_port() == int(port)


def test_devtools_button_explains_when_off(env, qapp):
    shown, opened = [], []
    env.setattr(auth_dialog.QMessageBox, "information", lambda *a, **k: shown.append(a[1]))
    env.setattr("PyQt6.QtGui.QDesktopServices.openUrl", lambda url: opened.append(url))
    fake = type("Dialog", (), {"_debug_port": None})()
    auth_dialog.BrowserLoginDialog._open_devtools(fake)
    assert shown == ["DevTools is off"] and opened == []
    fake._debug_port = 9234
    auth_dialog.BrowserLoginDialog._open_devtools(fake)
    assert opened and opened[0].toString() == "http://localhost:9234"


def test_model_selector_dialog_builds(qapp):
    # it used QWidget without importing it
    ModelSelectorDialog({}).deleteLater()


@pytest.mark.parametrize(
    "platform, docker, preset, expected",
    [
        ("win32", False, None, "1"),
        ("linux", False, None, "1"),
        ("win32", False, "0", "0"),
        ("linux", False, "0", "0"),
        ("linux", True, None, None),
        ("darwin", False, None, None),
    ],
)
def test_gui_draws_with_gpu_from_the_start(monkeypatch, platform, docker, preset, expected):
    # Without QT_WIDGETS_RHI, opening the login browser makes the whole GUI flash.
    monkeypatch.delenv("QT_WIDGETS_RHI", raising=False)
    if preset is not None:
        monkeypatch.setenv("QT_WIDGETS_RHI", preset)
    gui_app.enable_rhi_widgets(platform, docker=docker)
    assert os.environ.get("QT_WIDGETS_RHI") == expected


def test_rhi_is_set_before_the_app_is_created():
    import inspect

    src = inspect.getsource(gui_app.launch_gui)
    assert src.index("enable_rhi_widgets(docker=_is_docker())") < src.index("QApplication(")
