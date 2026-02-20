import logging
import os
import subprocess
import sys

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import QObject, QEvent
from PyQt6.QtGui import QIcon

from ofscraper.gui.styles import get_dark_theme_qss, get_light_theme_qss
from ofscraper.gui.utils.progress_bridge import GUILogHandler

log = logging.getLogger("shared")


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


def launch_gui(manager=None):
    """Launch the PyQt6 GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("OF-Scraper")
    app.setStyle("Fusion")
    # Apply saved theme preference (falls back to dark if not set)
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

    log.info("OF-Scraper GUI started")
    app.exec()
