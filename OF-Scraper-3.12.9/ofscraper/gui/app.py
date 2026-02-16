import logging
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, QEvent

from ofscraper.gui.styles import get_dark_theme_qss
from ofscraper.gui.utils.progress_bridge import GUILogHandler

log = logging.getLogger("shared")

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

    log.info("OF-Scraper GUI started")
    app.exec()
