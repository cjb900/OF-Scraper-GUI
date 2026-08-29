"""Crash / hang diagnostics for the GUI.

Hard Qt/native crashes often leave no Python traceback. This module:

1. Enables ``faulthandler`` dumping to a dedicated file
2. Installs ``sys.excepthook`` / ``threading.excepthook`` and a Qt message handler
3. ``breadcrumb()`` / ``gui_action()`` — always-on flushed markers (independent of
   Verbose Log) so the last UI action + whether a model-fetch/scrape was in flight
   is visible after a hard crash
"""
from __future__ import annotations

import faulthandler
import logging
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("shared")

_breadcrumb_path: Optional[Path] = None
_fault_path: Optional[Path] = None
_fault_fp = None
_installed = False
_lock = threading.Lock()

# Concurrent activity flags — included on every gui_action / breadcrumb line.
_activity_lock = threading.Lock()
_model_fetch_active = False
_scrape_active = False
_last_page = ""


def _config_parent() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths

        return Path(common_paths.get_config_path()).parent
    except Exception:
        return Path.home() / ".config" / "ofscraper"


def diagnostics_dir() -> Path:
    d = _config_parent() / "gui_crash_logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def breadcrumb_log_path() -> Path:
    global _breadcrumb_path
    if _breadcrumb_path is None:
        # Same file as before so existing copies still work.
        _breadcrumb_path = diagnostics_dir() / "model_fetch_breadcrumbs.log"
    return _breadcrumb_path


def fault_log_path() -> Path:
    global _fault_path
    if _fault_path is None:
        _fault_path = diagnostics_dir() / "faulthandler.log"
    return _fault_path


def set_model_fetch_active(active: bool) -> None:
    global _model_fetch_active
    with _activity_lock:
        _model_fetch_active = bool(active)
    breadcrumb(
        "activity_model_fetch",
        f"active={bool(active)}",
    )


def set_scrape_active(active: bool) -> None:
    global _scrape_active
    with _activity_lock:
        _scrape_active = bool(active)
    breadcrumb(
        "activity_scrape",
        f"active={bool(active)}",
    )


def is_model_fetch_active() -> bool:
    with _activity_lock:
        return bool(_model_fetch_active)


def is_scrape_active() -> bool:
    with _activity_lock:
        return bool(_scrape_active)


def is_heavy_background_active() -> bool:
    """True while model-list fetch or scrape should avoid heavy UI work (theme, etc.)."""
    with _activity_lock:
        return bool(_model_fetch_active or _scrape_active)


def set_last_page(page: str) -> None:
    global _last_page
    with _activity_lock:
        _last_page = str(page or "")


def activity_snapshot() -> str:
    with _activity_lock:
        return (
            f"model_fetch={int(_model_fetch_active)} "
            f"scrape={int(_scrape_active)} "
            f"page={_last_page or '?'}"
        )


def _write_line(stage: str, detail: str = "") -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + "Z"
    tid = threading.current_thread().name
    snap = activity_snapshot()
    line = f"{ts} [{tid}] [{snap}] {stage}"
    if detail:
        line = f"{line} | {detail}"
    line += "\n"
    try:
        with _lock:
            path = breadcrumb_log_path()
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
    except Exception:
        pass


def breadcrumb(stage: str, detail: str = "") -> None:
    """Append a flushed marker line (always writes, independent of log level).

    Mirrors to ``log.info`` only on the Qt main thread (and only for non-spammy
    stages). Worker-thread log.info was flooding the GUI console and coincided
    with Windows access violations.
    """
    _write_line(stage, detail)
    if threading.current_thread() is not threading.main_thread():
        return
    # Skip mirroring high-frequency UI click noise to the console.
    if stage.startswith("ui_click") or stage.startswith("ui_toggle"):
        return
    try:
        msg = f"[GUI crash diag][{stage}]"
        if detail:
            msg = f"{msg} {detail}"
        log.info(msg)
    except Exception:
        pass


def gui_action(kind: str, detail: str = "") -> None:
    """Record a user/GUI action to the crash breadcrumb file (always on)."""
    _write_line(f"ui_{kind}", detail)


def install_crash_diagnostics() -> None:
    """Install once at GUI startup. Safe to call repeatedly."""
    global _installed, _fault_fp
    if _installed:
        return
    _installed = True

    try:
        fault_path = fault_log_path()
        _fault_fp = open(fault_path, "a", encoding="utf-8", buffering=1)
        _fault_fp.write(
            f"\n===== faulthandler enabled {datetime.now(timezone.utc).isoformat()} =====\n"
        )
        _fault_fp.flush()
        faulthandler.enable(file=_fault_fp, all_threads=True)
        try:
            faulthandler.dump_traceback_later(300, repeat=True, file=_fault_fp)
        except Exception:
            pass
        log.info(f"[GUI crash diag] faulthandler → {fault_path}")
    except Exception as e:
        log.warning(f"[GUI crash diag] Could not enable faulthandler: {e}")

    try:
        breadcrumb("startup", f"breadcrumb_file={breadcrumb_log_path()}")
    except Exception:
        pass

    _prev_hook = sys.excepthook

    def _excepthook(exc_type, exc, tb):
        try:
            breadcrumb(
                "sys.excepthook",
                f"{exc_type.__name__}: {exc}",
            )
            with open(breadcrumb_log_path(), "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
                f.flush()
        except Exception:
            pass
        try:
            log.error(
                f"[GUI crash diag] Uncaught: {exc_type.__name__}: {exc}",
                exc_info=(exc_type, exc, tb),
            )
        except Exception:
            pass
        _prev_hook(exc_type, exc, tb)

    sys.excepthook = _excepthook

    if hasattr(threading, "excepthook"):
        _prev_thread_hook = threading.excepthook

        def _thread_excepthook(args):
            try:
                breadcrumb(
                    "threading.excepthook",
                    f"thread={getattr(args.thread, 'name', '?')} "
                    f"{getattr(args.exc_type, '__name__', '?')}: {args.exc_value}",
                )
                with open(breadcrumb_log_path(), "a", encoding="utf-8") as f:
                    f.write(
                        "".join(
                            traceback.format_exception(
                                args.exc_type, args.exc_value, args.exc_traceback
                            )
                        )
                    )
                    f.flush()
            except Exception:
                pass
            try:
                _prev_thread_hook(args)
            except Exception:
                pass

        threading.excepthook = _thread_excepthook

    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler

        def _qt_msg_handler(mode, context, message):
            try:
                kind = {
                    QtMsgType.QtDebugMsg: "QtDebug",
                    QtMsgType.QtInfoMsg: "QtInfo",
                    QtMsgType.QtWarningMsg: "QtWarning",
                    QtMsgType.QtCriticalMsg: "QtCritical",
                    QtMsgType.QtFatalMsg: "QtFatal",
                }.get(mode, str(mode))
                if mode in (
                    QtMsgType.QtWarningMsg,
                    QtMsgType.QtCriticalMsg,
                    QtMsgType.QtFatalMsg,
                ):
                    loc = ""
                    try:
                        if context is not None:
                            loc = (
                                f" {getattr(context, 'file', '')}:"
                                f"{getattr(context, 'line', '')}"
                            )
                    except Exception:
                        pass
                    breadcrumb(kind, f"{message}{loc}")
            except Exception:
                pass

        qInstallMessageHandler(_qt_msg_handler)
        log.info("[GUI crash diag] Qt message handler installed")
    except Exception as e:
        log.debug(f"[GUI crash diag] Qt message handler skipped: {e}")


def install_gui_action_hooks() -> None:
    """Connect app_signals so navigation / scrape / workflow actions are logged.

    Call after ``ensure_app_signals()`` / QApplication exists.
    """
    try:
        from ofscraper.gui.signals import app_signals
    except Exception as e:
        log.debug(f"[GUI crash diag] action hooks skipped: {e}")
        return

    def _nav(page):
        try:
            set_last_page(str(page))
            gui_action("navigate", f"page={page}")
        except Exception:
            pass

    def _actions(actions):
        try:
            gui_action("action_selected", f"actions={sorted(actions or [])}")
        except Exception:
            pass

    def _models(models):
        try:
            gui_action("models_selected", f"count={len(models or [])}")
        except Exception:
            pass

    def _areas(areas):
        try:
            gui_action("areas_selected", f"areas={areas!r}")
        except Exception:
            pass

    def _scrape_start(*_a):
        try:
            set_scrape_active(True)
            gui_action("scrape_started")
        except Exception:
            pass

    def _scrape_end(*_a):
        try:
            set_scrape_active(False)
            gui_action("scrape_finished")
        except Exception:
            pass

    def _data_loaded(*_a):
        try:
            gui_action("data_loading_finished")
        except Exception:
            pass

    def _err(title, msg=""):
        # error_occurred is pyqtSignal(str, str) — accept both args.
        try:
            detail = f"{title}: {msg}" if msg else str(title)
            gui_action("error_signal", detail[:200])
        except Exception:
            pass

    try:
        app_signals.navigate_to_page.connect(_nav)
        app_signals.action_selected.connect(_actions)
        app_signals.models_selected.connect(_models)
        app_signals.areas_selected.connect(_areas)
        app_signals.error_occurred.connect(_err)
        app_signals.data_loading_finished.connect(_data_loaded)
    except Exception as e:
        log.debug(f"[GUI crash diag] core signal hooks failed: {e}")

    for name, slot in (
        ("scrape_started", _scrape_start),
        ("scraping_finished", _scrape_end),
    ):
        try:
            sig = getattr(app_signals, name, None)
            if sig is not None:
                sig.connect(slot)
        except Exception:
            pass

    breadcrumb("action_hooks_installed")
