"""faulthandler.log is trimmed instead of growing forever on long GUI sessions."""
import faulthandler

import pytest

import ofscraper.gui.utils.crash_diagnostics as diag

pytestmark = pytest.mark.unit


@pytest.fixture
def fault_log(tmp_path, monkeypatch):
    path = tmp_path / "faulthandler.log"
    monkeypatch.setattr(diag, "_fault_path", path)
    monkeypatch.setattr(diag, "FAULT_LOG_MAX_BYTES", 1000)
    monkeypatch.setattr(diag, "_fault_fp", None)
    return path


def test_small_log_is_left_alone(fault_log):
    fault_log.write_text("x" * 1000)
    assert diag.trim_fault_log() is False
    assert fault_log.read_text() == "x" * 1000
    assert not fault_log.with_name("faulthandler.log.1").exists()


def test_big_log_is_moved_aside_at_startup(fault_log):
    fault_log.write_text("old" * 500)
    assert diag.trim_fault_log() is True
    assert fault_log.with_name("faulthandler.log.1").read_text() == "old" * 500
    assert not fault_log.exists()


def test_open_log_is_trimmed_in_place(fault_log, monkeypatch):
    # faulthandler keeps the same file open, so later dumps must land in the
    # fresh file, not after a hole where the old content was.
    fp = open(fault_log, "a", encoding="utf-8", buffering=1)
    monkeypatch.setattr(diag, "_fault_fp", fp)
    try:
        fp.write("dump\n" * 400)
        assert diag.trim_fault_log() is True
        faulthandler.dump_traceback(file=fp, all_threads=False)
        fp.flush()
        text = fault_log.read_text()
    finally:
        fp.close()
    assert text.lstrip("\n").startswith("===== trimmed (older part in faulthandler.log.1)")
    assert "\x00" not in text
    assert "test_open_log_is_trimmed_in_place" in text
    assert fault_log.with_name("faulthandler.log.1").read_text() == "dump\n" * 400


@pytest.fixture
def install(tmp_path, monkeypatch):
    """Run install_crash_diagnostics() against temp files; returns the dump calls."""
    import sys
    import threading

    calls = []
    monkeypatch.setattr(diag, "_installed", False)
    monkeypatch.setattr(diag, "_fault_path", tmp_path / "faulthandler.log")
    monkeypatch.setattr(diag, "_breadcrumb_path", tmp_path / "breadcrumbs.log")
    monkeypatch.setattr(diag, "_fault_fp", None)
    monkeypatch.setattr(faulthandler, "enable", lambda **kw: None)
    monkeypatch.setattr(faulthandler, "dump_traceback_later", lambda *a, **kw: calls.append((a, kw)))
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    try:
        import PyQt6.QtCore as qtcore

        monkeypatch.setattr(qtcore, "qInstallMessageHandler", lambda h: None)
    except ImportError:
        pass

    def run():
        before = {t.name for t in threading.enumerate()}
        diag.install_crash_diagnostics()
        diag._fault_fp.close()
        return [t.name for t in threading.enumerate() if t.name not in before]

    return calls, run


def test_no_periodic_hang_dumps_by_default(install, monkeypatch):
    # Dumping every thread's stack while they run crashed the GUI on Windows.
    monkeypatch.delenv(diag.HANG_DUMP_ENV, raising=False)
    calls, run = install
    new_threads = run()
    assert calls == []
    assert "fault-log-trim" not in new_threads


def test_hang_dumps_can_be_turned_on(install, monkeypatch):
    monkeypatch.setenv(diag.HANG_DUMP_ENV, "120")
    calls, run = install
    run()
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (120.0,) and kwargs["repeat"] is True


@pytest.mark.parametrize("value, expected", [("", None), ("0", None), ("-5", None), ("abc", None), ("90", 90.0)])
def test_hang_dump_seconds(monkeypatch, value, expected):
    monkeypatch.setenv(diag.HANG_DUMP_ENV, value)
    assert diag.hang_dump_seconds() == expected
