"""v504: fixes from the combined crash analysis.

- The GUI closed itself during a model load: an app-wide filter meant for an
  old "Loading models from API..." popup matched the main window by its
  hidden inline loading label and closed it (six times in the crash logs).
- That close left the model-fetch worker waiting 60 s for an ack into
  interpreter shutdown.
- A malformed auth.json made read_auth() retry forever in GUI mode.
- Every scrape sent scraping_finished twice.
- Breadcrumbs: PID and role on every line, a heartbeat, rotation, and the tab
  host recording how each site's window ended.
"""
from __future__ import annotations

import inspect
import json
import re
import threading
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui import app as gui_app  # noqa: E402
from ofscraper.gui.utils import crash_diagnostics as diag  # noqa: E402


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def crumbs(tmp_path, monkeypatch):
    path = tmp_path / "breadcrumbs.log"
    monkeypatch.setattr(diag, "_breadcrumb_path", path)
    monkeypatch.setattr(diag, "_role", "gui")
    return path


# --- the window isn't closed during a model load ---------------------------


def test_no_filter_closes_windows_that_show_the_loading_text():
    assert not hasattr(gui_app, "_CloseLegacyModelLoadingPopup")
    src = inspect.getsource(gui_app.launch_gui)
    assert "legacy_model_loading_popup" not in src


def test_a_main_window_with_the_loading_label_stays_open(qapp):
    from PyQt6.QtCore import QEvent

    window = QtWidgets.QMainWindow()
    label = QtWidgets.QLabel("Loading models from API...", window)
    label.hide()
    window.show()
    qapp.sendEvent(window, QEvent(QEvent.Type.WindowActivate))
    qapp.processEvents()
    assert window.isVisible()
    window.close()


def test_shutdown_releases_a_waiting_model_fetch(monkeypatch, qapp):
    import ofscraper.gui.utils.model_fetch as model_fetch
    import ofscraper.plugins.manager as pm

    monkeypatch.setattr(pm.plugin_manager, "dispatch_event", lambda *a, **k: None)
    model_fetch.clear_ui_ack()
    fake_app = SimpleNamespace(
        _gui_event_logger=None,
        removeEventFilter=lambda f: None,
        sendPostedEvents=lambda *a: None,
    )
    gui_app.shutdown_gui(fake_app, QtWidgets.QWidget(), worker_wait_ms=50)
    # a worker reaching wait_for_ui_ack now returns at once
    assert model_fetch._ui_ack.is_set()


def test_shutdown_stops_the_heartbeat(monkeypatch, qapp):
    import ofscraper.plugins.manager as pm

    monkeypatch.setattr(pm.plugin_manager, "dispatch_event", lambda *a, **k: None)
    stopped = []
    fake_app = SimpleNamespace(
        _ofs_heartbeat=SimpleNamespace(stop=lambda: stopped.append(1)),
        removeEventFilter=lambda f: None,
        sendPostedEvents=lambda *a: None,
    )
    gui_app.shutdown_gui(fake_app, QtWidgets.QWidget(), worker_wait_ms=50)
    assert stopped == [1]


# --- a malformed auth.json ---------------------------------------------------


def test_malformed_auth_json_stops_with_the_reason_in_gui_mode(monkeypatch):
    import ofscraper.utils.auth.file as auth_file
    import ofscraper.utils.auth.utils.error as auth_error

    def broken(*a, **k):
        return json.loads('{"auth": {"sess": "x",}}')

    monkeypatch.setattr(auth_file.auth_dict, "get_auth_dict", broken)
    monkeypatch.setattr(auth_error, "_is_gui_mode", lambda: True)

    result = {}

    def run():
        try:
            auth_file.read_auth()
            result["out"] = "returned"
        except Exception as e:  # noqa: BLE001
            result["out"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(5)
    assert not t.is_alive(), "read_auth() still looping"
    assert isinstance(result["out"], auth_error.AuthFileError)
    assert "line 1" in str(result["out"])


# --- one scraping_finished per scrape -----------------------------------------


def test_a_finished_run_sends_scraping_finished_once():
    from ofscraper.gui.utils import workflow

    src = inspect.getsource(workflow)
    body = src[src.index("    def _run_scraper_thread(self):"):]
    body = body[: body.index("\n    def ", 10)]
    # set right before the normal run's break, checked by the finally
    assert re.search(r"_finished_sent = True\n\s+break", body)
    final = body[body.rindex("\n        finally:"):]
    assert "if not _finished_sent:" in final
    assert final.index("if not _finished_sent:") < final.index("scraping_finished.emit()")


# --- breadcrumbs ------------------------------------------------------------------


def test_lines_carry_the_role_and_pid(crumbs):
    import os

    diag.set_role("gui-onlyfans")
    diag.breadcrumb("probe")
    line = crumbs.read_text().strip()
    assert f"[gui-onlyfans pid={os.getpid()}]" in line
    assert line.endswith("probe")


def test_a_big_breadcrumb_file_is_rotated(crumbs, monkeypatch):
    monkeypatch.setattr(diag, "BREADCRUMB_LOG_MAX_BYTES", 10)
    crumbs.write_text("x" * 50)
    assert diag.trim_breadcrumb_log()
    assert not crumbs.exists()
    assert crumbs.with_name(crumbs.name + ".1").read_text() == "x" * 50
    assert not diag.trim_breadcrumb_log()


def test_heartbeat_writes_from_the_event_loop(crumbs, qapp):
    from PyQt6.QtCore import QEventLoop, QTimer

    timer = diag.start_heartbeat(qapp, seconds=1)
    try:
        loop = QEventLoop()
        QTimer.singleShot(1300, loop.quit)
        loop.exec()
    finally:
        timer.stop()
    assert "heartbeat" in crumbs.read_text()


def test_host_records_how_a_sites_window_ended(crumbs):
    from ofscraper.gui import site_host

    site_host._host_breadcrumb("child_exit", "site=onlyfans pid=42 code=1 status=crash")
    line = crumbs.read_text().strip()
    assert "[host pid=" in line
    assert "child_exit | site=onlyfans pid=42 code=1 status=crash" in line
    src = inspect.getsource(site_host._define_classes)
    assert '_host_breadcrumb(\n                "child_exit"' in src
