import os
import random

# Pre-allocate debugging port and set environment variables before importing PyQt6.
# This is critical because importing PyQt6 modules or submodules can trigger
# early initialization of the WebEngine library, ignoring later environment changes.
if "QTWEBENGINE_CHROMIUM_FLAGS" not in os.environ:
    port = random.randint(9200, 9299)
    os.environ["OFSCRAPER_WEBENGINE_DEBUG_PORT"] = str(port)
    os.environ["QTWEBENGINE_REMOTE_DEBUGGING"] = str(port)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        f"--remote-debugging-port={port} "
        "--remote-allow-origins=* "
        "--disable-blink-features=AutomationControlled "
        "--disable-web-security "
        "--allow-running-insecure-content "
        "--disable-features=StorageAccessAPI"
    )

import logging
import subprocess
import sys

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtGui import QIcon

from ofscraper.gui.styles import get_dark_theme_qss, get_light_theme_qss
from ofscraper.gui.utils.progress_bridge import GUILogHandler

log = logging.getLogger("shared")


class GUIEventLogger(QObject):
    """Global event filter: always writes crash-diag breadcrumbs; Verbose Log also gets debug lines."""

    def eventFilter(self, obj, event):
        try:
            verbose = log.level <= logging.DEBUG
            if event.type() == QEvent.Type.MouseButtonRelease:
                from PyQt6.QtWidgets import QAbstractButton, QTabBar, QComboBox
                from ofscraper.gui.utils.crash_diagnostics import gui_action

                if isinstance(obj, QAbstractButton):
                    name = str(obj.objectName() or "")
                    text = str(obj.text() or "").strip()
                    widget_type = type(obj).__name__
                    # Cap text so breadcrumbs stay small / readable.
                    short = (text[:48] + "…") if len(text) > 48 else text

                    from PyQt6.QtWidgets import QCheckBox, QRadioButton
                    if isinstance(obj, (QCheckBox, QRadioButton)):
                        from PyQt6.QtCore import QTimer

                        def _after_toggle(
                            o=obj, t=short, n=name, wt=widget_type, v=verbose
                        ):
                            try:
                                checked = bool(o.isChecked())
                                gui_action(
                                    "toggle",
                                    f"text={t!r} name={n!r} type={wt} checked={checked}",
                                )
                                if v:
                                    log.debug(
                                        f"[GUI Event] CheckBox/RadioButton Toggled: "
                                        f"text='{t}', name='{n}', type='{wt}', checked={checked}"
                                    )
                            except Exception:
                                pass

                        QTimer.singleShot(0, _after_toggle)
                    else:
                        gui_action(
                            "click",
                            f"text={short!r} name={name!r} type={widget_type}",
                        )
                        if verbose:
                            log.debug(
                                f"[GUI Event] Button Clicked: text='{text}', "
                                f"name='{name}', type='{widget_type}'"
                            )
                elif isinstance(obj, QComboBox):
                    name = str(obj.objectName() or "")
                    current = str(obj.currentText() or "")
                    gui_action(
                        "click",
                        f"combo name={name!r} current={current[:48]!r}",
                    )
                    if verbose:
                        log.debug(
                            f"[GUI Event] ComboBox Clicked: current='{current}', name='{name}'"
                        )
                elif isinstance(obj, QTabBar):
                    idx = obj.tabAt(event.pos())
                    if idx != -1:
                        title = str(obj.tabText(idx) or "")
                        gui_action("click", f"tab index={idx} title={title!r}")
                        if verbose:
                            log.debug(
                                f"[GUI Event] Tab Clicked: index={idx}, title='{title}'"
                            )

            elif event.type() == QEvent.Type.FocusOut and verbose:
                from PyQt6.QtWidgets import QLineEdit
                if isinstance(obj, QLineEdit):
                    name = str(obj.objectName() or "")
                    placeholder = str(obj.placeholderText() or "")
                    is_sensitive = (
                        obj.echoMode() == QLineEdit.EchoMode.Password or
                        any(x in name.lower() for x in ("auth", "token", "password", "key", "secret"))
                    )
                    if is_sensitive:
                        log.debug(f"[GUI Event] Sensitive Input Field FocusOut: name='{name}'")
                    else:
                        val = obj.text()
                        if len(val) > 40:
                            val = val[:40] + "..."
                        log.debug(f"[GUI Event] Input Field FocusOut: name='{name}', placeholder='{placeholder}', current_value='{val}'")
        except Exception:
            pass
        return False


def _show_windows_toast(title: str, message: str) -> bool:
    """Show a native Windows 10/11 toast notification via PowerShell.

    Uses the Windows Runtime ToastNotificationManager API which appears in
    the Windows Notification Center.  The app AUMID is registered in the
    current-user registry on first call so Windows will accept the notification.

    Runs PowerShell in a hidden window; stderr is captured in a daemon thread
    for debug logging without blocking the GUI thread.

    Returns True if the subprocess launched without error.
    """
    if sys.platform != "win32":
        return False
    try:
        # Title and message are passed via environment variables to avoid
        # any PowerShell quoting/injection issues.
        ps_script = r"""
# Register app AUMID so Windows 10/11 will accept and display the notification.
$RegPath = "HKCU:\SOFTWARE\Classes\AppUserModelId\OF-Scraper"
if (-not (Test-Path $RegPath)) {
    New-Item -Path $RegPath -Force | Out-Null
    New-ItemProperty -Path $RegPath -Name "DisplayName" -Value "OF-Scraper" -PropertyType String -Force | Out-Null
}

$t = [System.Security.SecurityElement]::Escape($env:TOAST_TITLE)
$m = [System.Security.SecurityElement]::Escape($env:TOAST_MSG)

[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template=`"ToastText02`"><text id=`"1`">$t</text><text id=`"2`">$m</text></binding></visual></toast>")

$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("OF-Scraper").Show($toast)
"""
        env = os.environ.copy()
        env["TOAST_TITLE"] = str(title)
        env["TOAST_MSG"] = str(message)
        proc = subprocess.Popen(
            [
                "powershell",
                "-WindowStyle", "Hidden",
                "-NonInteractive",
                "-Command", ps_script,
            ],
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Collect stderr in a daemon thread so we can log errors without
        # blocking the GUI thread.
        import threading

        def _log_stderr():
            try:
                _, stderr_data = proc.communicate(timeout=10)
                if proc.returncode != 0 and stderr_data:
                    log.debug(
                        f"[Toast] PowerShell error (rc={proc.returncode}): "
                        f"{stderr_data.decode(errors='replace').strip()}"
                    )
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception as exc:
                log.debug(f"[Toast] stderr reader error: {exc}")

        threading.Thread(target=_log_stderr, daemon=True).start()
        return True
    except Exception as e:
        log.debug(f"[Toast] Failed to launch PowerShell: {e}")
        return False


class _CloseLegacyModelLoadingPopup(QObject):
    """Event filter that closes any stray legacy 'Loading models from API...' popup.

    Some older code paths (or stale Qt objects) can still create a small top-level
    window with that label. We don't want it since we show an inline loading bar.
    """

    TARGET_TEXT = "Loading models from API..."

    @staticmethod
    def _norm(s: str) -> str:
        """Normalize strings to catch unicode ellipsis / spacing variations."""
        if not s:
            return ""
        s = str(s)
        s = s.replace("\u2026", "...")  # unicode ellipsis
        return " ".join(s.strip().lower().split())

    def _looks_like_legacy_popup(self, obj) -> bool:
        """Return True if obj is a top-level legacy loading popup."""
        target = self._norm(self.TARGET_TEXT)

        # 1) Match window title
        try:
            title = self._norm(getattr(obj, "windowTitle", lambda: "")() or "")
            if title and target.startswith("loading models from api") and target in title:
                return True
            if title and title == target:
                return True
        except Exception:
            pass

        # 2) Match QProgressDialog-like labelText()
        try:
            label_text = getattr(obj, "labelText", None)
            if callable(label_text):
                txt = self._norm(label_text() or "")
                if "loading models from api" in txt:
                    return True
        except Exception:
            pass

        # 3) Match any child QLabel text
        try:
            from PyQt6.QtWidgets import QLabel

            lbls = obj.findChildren(QLabel)
            for l in lbls:
                txt = self._norm(l.text() or "")
                if "loading models from api" in txt:
                    return True
        except Exception:
            pass

        return False

    def eventFilter(self, obj, event):
        try:
            if event.type() in (
                QEvent.Type.Show,
                QEvent.Type.ShowToParent,
                QEvent.Type.WindowActivate,
                QEvent.Type.Polish,
                QEvent.Type.WindowTitleChange,
            ):
                # Only consider top-level widgets (popups/dialogs)
                if hasattr(obj, "isWindow") and obj.isWindow():
                    if self._looks_like_legacy_popup(obj):
                        obj.close()
        except Exception:
            pass
        return False


def _is_docker() -> bool:
    """Return True when running inside a Docker / OCI container."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", errors="ignore") as _f:
            _c = _f.read()
            return "docker" in _c or "containerd" in _c
    except OSError:
        pass
    return False


def launch_gui(manager=None):
    """Launch the PyQt6 GUI application."""
    # Tell Windows to use our own AppUserModelID so the taskbar shows our
    # icon instead of the generic Python icon.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "OFScraper.GUI.1"
            )
        except Exception:
            pass


    # Docker / container environment: Qt defaults to hardware OpenGL which is
    # unavailable in containers, causing transparent windows or hard crashes.
    # Force Mesa software rendering BEFORE QApplication is constructed so the
    # platform plugin picks up the correct GL backend.
    if _is_docker():
        os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
        os.environ.setdefault("QT_X11_NO_MITSHM", "1")
        # Disable GPU acceleration in QtWebEngine (Chromium) too — containers
        # have no GPU and often have a tiny /dev/shm that causes Chromium to crash.
        _existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        _docker_flags = "--disable-gpu --no-sandbox --disable-dev-shm-usage"
        if "--disable-gpu" not in _existing:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
                f"{_existing} {_docker_flags}".strip()
            )
        log.info("[GUI] Docker environment detected — software rendering enabled")

    # QtWebEngineWidgets requires AA_ShareOpenGLContexts to be set before
    # QApplication is created.  Set it unconditionally; it's a no-op when
    # WebEngine is absent.
    try:
        from PyQt6.QtCore import Qt as _Qt
        QApplication.setAttribute(_Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    except Exception:
        pass

    # Append command line flags directly to sys.argv so they are parsed by Chromium.
    # This acts as a robust backup to environment variables.
    # Note: Qt WebEngine expects all Chromium flags to be passed as a single
    # space-separated string argument following the '--webEngineArgs' parameter.
    port_str = os.environ.get("OFSCRAPER_WEBENGINE_DEBUG_PORT", "9208")
    flags_str = (
        f"--remote-debugging-port={port_str} "
        "--remote-allow-origins=* "
        "--disable-blink-features=AutomationControlled "
        "--disable-web-security "
        "--allow-running-insecure-content "
        "--disable-features=StorageAccessAPI"
    )
    sys.argv.extend([
        "--webEngineArgs",
        flags_str
    ])

    app = QApplication(sys.argv)
    app.setApplicationName("OF-Scraper")
    app.setStyle("Fusion")

    # Crash breadcrumbs + faulthandler (helps diagnose hard GUI crashes during model load).
    try:
        from ofscraper.gui.utils.crash_diagnostics import install_crash_diagnostics

        install_crash_diagnostics()
    except Exception as e:
        log.warning(f"Could not install crash diagnostics: {e}")

    # AppSignals must be created *after* QApplication (parented to it).
    try:
        from ofscraper.gui.signals import ensure_app_signals

        ensure_app_signals()
    except Exception:
        pass

    # Log navigation / scrape / selection to the same crash breadcrumb file.
    try:
        from ofscraper.gui.utils.crash_diagnostics import install_gui_action_hooks

        install_gui_action_hooks()
    except Exception as e:
        log.warning(f"Could not install GUI action hooks: {e}")

    # Load and apply the application icon (taskbar, title bar, tray).
    try:
        import pathlib as _pathlib
        _icon_path = _pathlib.Path(__file__).parent / "assets" / "icon.png"
        if _icon_path.exists():
            app.setWindowIcon(QIcon(str(_icon_path)))
    except Exception:
        pass

    # Apply saved theme + GUI font size preference (falls back to dark / 13px)
    try:
        from ofscraper.gui.utils.ui_scale import (
            apply_application_font,
            load_gui_font_size_from_settings,
        )

        load_gui_font_size_from_settings()
        apply_application_font()
    except Exception:
        pass
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings
        _saved_theme = load_gui_settings().get("theme", "dark")
    except Exception:
        _saved_theme = "dark"
    if _saved_theme == "light":
        app.setStyleSheet(get_light_theme_qss())
    else:
        app.setStyleSheet(get_dark_theme_qss())

    # Close any stray legacy "Loading models..." popup globally.
    try:
        # Keep a Python reference so the filter can't be garbage-collected.
        app._legacy_model_loading_popup_filter = _CloseLegacyModelLoadingPopup(app)  # type: ignore[attr-defined]
        app.installEventFilter(app._legacy_model_loading_popup_filter)  # type: ignore[attr-defined]
    except Exception:
        pass

    # Global GUI interaction verbose logger event filter
    try:
        app._gui_event_logger = GUIEventLogger(app)
        app.installEventFilter(app._gui_event_logger)
    except Exception as e:
        log.warning(f"Could not install GUI interaction event filter: {e}")

    # Attach GUI log handler to forward logs to the console widget
    gui_handler = GUILogHandler()
    gui_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    # Hook both loggers used by the scraper
    for logger_name in ["shared", "shared_other"]:
        target_logger = logging.getLogger(logger_name)
        target_logger.addHandler(gui_handler)

    # Ensure auth.json exists (fresh installs won't have one yet).
    # Create an empty one so the GUI auth page can load/save without errors.
    try:
        import json
        import ofscraper.utils.paths.common as common_paths
        import ofscraper.utils.auth.utils.dict as auth_dict

        auth_file = common_paths.get_auth_file()
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        if not auth_file.exists():
            with open(auth_file, "w") as f:
                f.write(json.dumps(auth_dict.get_empty(), indent=4))
            log.info(f"Created empty auth.json at {auth_file}")
    except Exception as e:
        log.warning(f"Could not create auth.json: {e}")

    from ofscraper.gui.main_window import MainWindow

    window = MainWindow(manager=manager)
    window.show()

    # Set up a persistent system tray icon for notifications.
    # Must be created on the main thread and kept alive for the app lifetime.
    try:
        if QSystemTrayIcon.isSystemTrayAvailable():
            tray = QSystemTrayIcon(app)
            icon = app.windowIcon()
            if icon.isNull():
                icon = app.style().standardIcon(
                    app.style().StandardPixmap.SP_MessageBoxInformation
                )
            tray.setIcon(icon)
            tray.setToolTip("OF-Scraper")
            tray.show()
            # Keep a reference so it isn't garbage-collected
            app._tray_icon = tray  # type: ignore[attr-defined]

            from ofscraper.gui.signals import app_signals

            def _on_show_notification(title, message):
                # Try native Windows 10/11 toast first (appears in Notification
                # Center). Falls back to legacy tray balloon on failure.
                if not _show_windows_toast(title, message):
                    try:
                        tray.showMessage(
                            title, message,
                            QSystemTrayIcon.MessageIcon.Information, 5000,
                        )
                    except Exception:
                        pass

            app_signals.show_notification.connect(_on_show_notification)
    except Exception as e:
        log.debug(f"Could not set up tray icon: {e}")

    try:
        from ofscraper.__version__ import __version__ as _of_ver
    except Exception:
        _of_ver = "unknown"
    try:
        from ofscraper.gui.patch_version import PATCH_ID as _pid
        _patch_ver = _pid.split("_")[-1]  # e.g. "20260514_gui_3_14_7_v58" → "v58"
    except Exception:
        _patch_ver = "unknown"
    log.info(f"OF-Scraper {_of_ver} GUI {_patch_ver} started")
    app.exec()
