"""Closing the GUI: nothing Python runs inside PyQt's QApplication teardown.

Windows crash logs (2026-10-29) showed an access violation in
sip.cp311-win_amd64.pyd at the same offset twice: sip_api_visit_wrappers, which
PyQt only calls from QApplication's destructor. Python running during that walk
(app-wide event filters, worker threads) changes sip's wrapper table under it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui import app as gui_app  # noqa: E402

PROBE = textwrap.dedent(
    """
    import sys
    from PyQt6.QtCore import QObject
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
    from ofscraper.gui.app import shutdown_gui

    calls = 0
    tearing_down = False

    class Logger(QObject):  # like GUIEventLogger: sees every widget event
        def eventFilter(self, obj, ev):
            global calls
            if tearing_down:
                calls += 1
            return False

    app = QApplication(sys.argv)
    app._gui_event_logger = Logger(app)
    app.installEventFilter(app._gui_event_logger)
    window = QWidget()  # parentless: owned by Python, like MainWindow
    lay = QVBoxLayout(window)
    for i in range(200):
        lay.addWidget(QLabel(str(i)))
        lay.addWidget(QPushButton("b"))
    window.show()
    app.processEvents()
    keep = [window]

    if sys.argv[-1] == "with-shutdown":
        shutdown_gui(app, window, worker_wait_ms=100)
    tearing_down = True
    del app  # QApplication dtor -> PyQt cleanup walk over sip's wrapper table
    print("CALLS", calls)
    """
)


def _python_calls_during_app_teardown(mode: str) -> int:
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run(
        [sys.executable, "-c", PROBE, mode],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    line = [ln for ln in out.stdout.splitlines() if ln.startswith("CALLS")][-1]
    return int(line.split()[1])


def test_python_runs_inside_qapplication_teardown_without_the_fix():
    # The hazard is real: the filter runs for every widget the walk destroys.
    assert _python_calls_during_app_teardown("plain") > 100


def test_shutdown_leaves_the_teardown_walk_nothing_to_run_python_for():
    assert _python_calls_during_app_teardown("with-shutdown") == 0


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


def test_shutdown_order(qapp, monkeypatch):
    """Plugins first (UI teardown, then unload), filters off, workers waited, window deleted."""
    import ofscraper.plugins.manager as pm
    from PyQt6 import sip

    steps = []
    monkeypatch.setattr(
        pm.plugin_manager, "dispatch_event",
        lambda name, *a, **k: steps.append(name),
    )
    removed = []
    fake_app = SimpleNamespace(
        _gui_event_logger="logger",
        _legacy_model_loading_popup_filter="popup",
        removeEventFilter=lambda f: (removed.append(f), steps.append("filters")),
        sendPostedEvents=lambda *a: steps.append("posted"),
    )
    window = QtWidgets.QWidget()
    gui_app.shutdown_gui(fake_app, window, worker_wait_ms=100)

    assert steps[:2] == ["on_ui_teardown", "on_unload"]
    assert removed == ["logger", "popup"]
    assert sip.isdeleted(window)
    assert steps[-1] == "posted"


def test_launch_gui_shuts_down_after_the_event_loop():
    import inspect

    src = inspect.getsource(gui_app.launch_gui)
    assert src.rstrip().endswith("shutdown_gui(app, window)")


# The user hadn't closed the GUI: Python exited while the app was still running.
EXIT_PROBE = textwrap.dedent(
    """
    import atexit, sys
    from pathlib import Path
    from PyQt6.QtCore import QObject, QTimer
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
    import ofscraper.gui.utils.crash_diagnostics as cd
    from ofscraper.gui.app import shutdown_gui

    cd._breadcrumb_path = Path(sys.argv[1])

    class Logger(QObject):  # like GUIEventLogger
        def eventFilter(self, obj, ev):
            return False

    app = QApplication(sys.argv[:1])
    app._gui_event_logger = Logger(app)
    app.installEventFilter(app._gui_event_logger)
    window = QWidget()
    lay = QVBoxLayout(window)
    for i in range(200):
        lay.addWidget(QLabel(str(i)))
    window.show()

    if sys.argv[2] == "with-fix":  # what launch_gui does
        atexit.register(shutdown_gui, app, window, 100)
        cd.install_exit_tracing(app)

    QTimer.singleShot(100, lambda: sys.exit(3))  # SystemExit inside a Qt callback
    app.exec()
    """
)


def _exit_from_callback(tmp_path, mode):
    crumbs = tmp_path / f"crumbs-{mode}.log"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run(
        [sys.executable, "-c", EXIT_PROBE, str(crumbs), mode],
        capture_output=True, text=True, timeout=120, env=env,
    )
    return out, (crumbs.read_text() if crumbs.exists() else "")


def test_exit_from_a_qt_callback_is_recorded_and_torn_down(tmp_path):
    out, crumbs = _exit_from_callback(tmp_path, "with-fix")
    assert out.returncode == 3, out.stderr[-2000:]
    # who called exit, that Python exited, and that the safe teardown ran
    assert "exit_call | sys.exit(3)" in crumbs and "<lambda>" in crumbs
    assert "python_exit" in crumbs
    assert "ui_shutdown_start" in crumbs and "ui_shutdown_done" in crumbs
    assert crumbs.index("python_exit") < crumbs.index("ui_shutdown_start")


def test_without_the_fix_nothing_is_recorded(tmp_path):
    out, crumbs = _exit_from_callback(tmp_path, "plain")
    assert out.returncode == 3
    assert "exit_call" not in crumbs and "ui_shutdown_start" not in crumbs


def test_worker_system_exit_does_not_end_the_gui(qapp):
    from ofscraper.gui.utils.thread_worker import Worker

    def boom():
        raise SystemExit("OnlyFans Maintenance detected.")

    w = Worker(boom)
    errors = []
    w.signals.error.connect(errors.append)
    w.run()  # in this thread; a re-raised SystemExit would fail the test
    assert w.done and "Maintenance" in (w.error_msg or "")


def test_launch_gui_registers_the_exit_safety_net_before_running():
    import inspect

    src = inspect.getsource(gui_app.launch_gui)
    reg = src.index("atexit.register(shutdown_gui, app, window")
    # before the tracing hook (atexit runs newest first) and before the loop
    assert reg < src.index("install_exit_tracing(app)") < src.index("\n    app.exec()\n")
