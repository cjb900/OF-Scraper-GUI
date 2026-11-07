"""About dialog — app / patch / FFmpeg / OS info (single-instance via registry)."""
from __future__ import annotations

import platform
import re
import shutil

from PyQt6.QtCore import Qt, QThreadPool, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import (
    DESIGN_BASE,
    allowed_sizes,
    apply_font,
    get_gui_font_size,
    scale_px,
)
from ofscraper.gui.styles import c
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.widgets.styled_button import StyledButton

DISCORD_URL = "https://discord.gg/wN7uxEVHRK"
PYPI_URL = "https://pypi.org/project/ofscraper/"


def _tool_version_line(binary_name: str, path: str | None) -> str:
    if not path or not shutil.which(path):
        return "Not detected"
    try:
        from ofscraper.utils.system.subprocess import run
        import ofscraper.utils.of_env.of_env as env

        result = run(
            [path, "-version"],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
            level=env.getattr("FFMPEG_SUBPROCESS_LEVEL"),
            name=binary_name,
        )
        output = (result.stdout or "") + (result.stderr or "")
        m = re.search(
            rf"(?i){re.escape(binary_name)}\s+version\s+([^\s]+)",
            output,
        )
        if m:
            return m.group(1)
        first = (output.splitlines() or [""])[0].strip()
        return first[:80] if first else "Detected (version unknown)"
    except Exception:
        return "Detected (version unknown)"


def _windows_pretty() -> str:
    """Best-effort friendly Windows string, e.g. ``Windows 11 Pro 25H2``."""
    product = ""
    display = ""
    build = ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
        ) as key:

            def _q(name: str) -> str:
                try:
                    return str(winreg.QueryValueEx(key, name)[0] or "").strip()
                except OSError:
                    return ""

            product = _q("ProductName")
            display = _q("DisplayVersion") or _q("ReleaseId")
            build = _q("CurrentBuild") or _q("CurrentBuildNumber")
    except Exception:
        pass

    try:
        build_n = int(build) if build else 0
    except ValueError:
        build_n = 0

    # Registry still says "Windows 10" on many Win11 installs.
    if build_n >= 22000 and product:
        product = product.replace("Windows 10", "Windows 11")

    if not product:
        release = platform.release() or ""
        product = f"Windows {release}".strip() or "Windows"

    parts = [product]
    if display:
        parts.append(display)
    elif build:
        parts.append(f"build {build}")
    return " ".join(parts)


def _linux_pretty() -> str:
    """Read ``PRETTY_NAME`` from os-release (Kubuntu, PikaOS, etc.)."""
    for path in ("/etc/os-release", "/usr/lib/os-release"):
        try:
            data: dict[str, str] = {}
            with open(path, encoding="utf-8") as fh:
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    data[key] = val.strip().strip('"').strip("'")
            pretty = (data.get("PRETTY_NAME") or data.get("NAME") or "").strip()
            if pretty:
                return pretty
        except OSError:
            continue
    return platform.platform()


def _detect_os() -> str:
    """Human-readable OS label for the About dialog."""
    system = platform.system()
    try:
        if system == "Windows":
            return _windows_pretty()
        if system == "Darwin":
            ver = (platform.mac_ver() or ("", "", ""))[0] or ""
            return f"macOS {ver}".strip() if ver else "macOS"
        if system == "Linux":
            return _linux_pretty()
    except Exception:
        pass
    try:
        return platform.platform() or system or "Unknown"
    except Exception:
        return "Unknown"


def _resolve_versions() -> dict[str, str]:
    app_ver = "unknown"
    try:
        from ofscraper.__version__ import __version__

        app_ver = str(__version__)
    except Exception:
        pass

    patch_id = ""
    try:
        from ofscraper.gui.patch_version import PATCH_ID

        patch_id = str(PATCH_ID or "")
    except Exception:
        pass

    ffmpeg_path = None
    ffprobe_path = None
    try:
        import ofscraper.utils.system.ffmpeg as ffmpeg_mod

        try:
            ffmpeg_path = ffmpeg_mod.get_ffmpeg()
        except Exception:
            ffmpeg_path = None
        try:
            ffprobe_path = ffmpeg_mod.get_ffprobe()
        except Exception:
            ffprobe_path = None
    except Exception:
        pass

    if not ffmpeg_path:
        try:
            import ofscraper.utils.config.data as config_data

            ffmpeg_path = config_data.get_ffmpeg() or None
        except Exception:
            pass

    return {
        "app": app_ver,
        "patch": patch_id or "(not set)",
        "os": _detect_os(),
        "ffmpeg": _tool_version_line("ffmpeg", ffmpeg_path),
        "ffprobe": _tool_version_line("ffprobe", ffprobe_path or ffmpeg_path),
    }


class AboutDialog(QDialog):
    """Non-modal About window; open via ``show_about_dialog`` for single-instance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About OF-Scraper")
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(460)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._project_url = PYPI_URL
        self._check_worker = None
        self._setup_ui()

    def _setup_ui(self):
        info = _resolve_versions()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel("OF-Scraper")
        apply_font(title, "Segoe UI", 18, QFont.Weight.Bold)
        title.setProperty("heading", True)
        layout.addWidget(title)

        rows = [
            ("App version", info["app"]),
            ("GUI patch", info["patch"]),
            ("Operating system", info["os"]),
            ("FFmpeg", info["ffmpeg"]),
            ("FFprobe", info["ffprobe"]),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            key = QLabel(f"{label}:")
            key.setMinimumWidth(120)
            key.setProperty("muted", True)
            val = QLabel(value)
            val.setWordWrap(True)
            val.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            row.addWidget(key)
            row.addWidget(val, stretch=1)
            layout.addLayout(row)

        update_row = QHBoxLayout()
        update_key = QLabel("Updates:")
        update_key.setMinimumWidth(120)
        update_key.setProperty("muted", True)
        self._update_status = QLabel("Not checked yet.")
        self._update_status.setWordWrap(True)
        self._update_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        update_row.addWidget(update_key)
        update_row.addWidget(self._update_status, stretch=1)
        layout.addLayout(update_row)

        # Global GUI text size (moved here from the sidebar)
        text_row = QHBoxLayout()
        text_key = QLabel("Text size:")
        text_key.setMinimumWidth(120)
        text_key.setProperty("muted", True)
        text_row.addWidget(text_key)
        self._font_smaller_btn = QPushButton("A−")
        self._font_smaller_btn.setFixedWidth(36)
        self._font_smaller_btn.setToolTip("Decrease GUI text size")
        self._font_smaller_btn.clicked.connect(lambda: self._nudge_font_size(-1))
        text_row.addWidget(self._font_smaller_btn)
        self._font_size_combo = QComboBox()
        self._font_size_combo.setMinimumWidth(130)
        self._font_size_combo.setToolTip(
            "GUI text size for the whole app (saved to gui_settings.json)"
        )
        for px in allowed_sizes():
            label = f"{px} px"
            if px == DESIGN_BASE:
                label = f"{px} px (default)"
            self._font_size_combo.addItem(label, px)
        _fs = get_gui_font_size()
        _idx = self._font_size_combo.findData(_fs)
        self._font_size_combo.setCurrentIndex(_idx if _idx >= 0 else 1)
        self._font_size_combo.currentIndexChanged.connect(self._on_font_size_combo)
        text_row.addWidget(self._font_size_combo)
        self._font_larger_btn = QPushButton("A+")
        self._font_larger_btn.setFixedWidth(36)
        self._font_larger_btn.setToolTip("Increase GUI text size")
        self._font_larger_btn.clicked.connect(lambda: self._nudge_font_size(1))
        text_row.addWidget(self._font_larger_btn)
        self._font_reset_btn = StyledButton("Reset")
        self._font_reset_btn.setToolTip(
            f"Restore default GUI text size ({DESIGN_BASE} px)"
        )
        self._font_reset_btn.clicked.connect(self._reset_font_size)
        text_row.addWidget(self._font_reset_btn)
        text_row.addStretch()
        layout.addLayout(text_row)
        self._sync_font_buttons()
        try:
            app_signals.font_size_changed.connect(self._on_global_font_size_changed)
        except Exception:
            pass

        update_btns = QHBoxLayout()
        update_btns.addStretch()
        self._check_btn = StyledButton("Check for updates")
        self._check_btn.clicked.connect(self._check_for_updates)
        update_btns.addWidget(self._check_btn)
        self._open_pypi_btn = StyledButton("Open PyPI")
        self._open_pypi_btn.setEnabled(False)
        self._open_pypi_btn.clicked.connect(self._open_project_url)
        update_btns.addWidget(self._open_pypi_btn)
        layout.addLayout(update_btns)

        hint = QLabel(
            "Tip: clicking the version label in the sidebar opens this window. "
            "Opening it again raises this same window instead of creating another. "
            "Update checks use PyPI (same source as the CLI). "
            "Text size scales the whole GUI; Reset restores the default."
        )
        hint.setWordWrap(True)
        hint.setProperty("muted", True)
        hint.setStyleSheet(f"color: {c('muted')}; font-size: {scale_px(11)}px;")
        self._hint = hint
        layout.addWidget(hint)

        btns = QHBoxLayout()
        btns.addStretch()
        help_btn = StyledButton("Open Help")
        help_btn.clicked.connect(self._open_help)
        btns.addWidget(help_btn)
        discord_btn = StyledButton("Discord")
        discord_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(DISCORD_URL))
        )
        btns.addWidget(discord_btn)
        close_btn = StyledButton("Close")
        close_btn.clicked.connect(self.close)
        btns.addWidget(close_btn)
        layout.addLayout(btns)

    def _main_window(self):
        w = self.parent()
        while w is not None:
            if hasattr(w, "_set_gui_font_size"):
                return w
            w = w.parent()
        return None

    def _sync_font_buttons(self):
        sizes = allowed_sizes()
        try:
            i = sizes.index(get_gui_font_size())
        except ValueError:
            i = 1
        self._font_smaller_btn.setEnabled(i > 0)
        self._font_larger_btn.setEnabled(i < len(sizes) - 1)
        self._font_reset_btn.setEnabled(get_gui_font_size() != DESIGN_BASE)

    def _on_global_font_size_changed(self, size: int):
        try:
            self._font_size_combo.blockSignals(True)
            idx = self._font_size_combo.findData(int(size))
            if idx >= 0:
                self._font_size_combo.setCurrentIndex(idx)
            self._font_size_combo.blockSignals(False)
        except Exception:
            pass
        self._sync_font_buttons()
        try:
            self._hint.setStyleSheet(
                f"color: {c('muted')}; font-size: {scale_px(11)}px;"
            )
        except Exception:
            pass

    def _nudge_font_size(self, delta: int):
        sizes = allowed_sizes()
        try:
            i = sizes.index(get_gui_font_size())
        except ValueError:
            i = 1
        ni = max(0, min(len(sizes) - 1, i + int(delta)))
        self._font_size_combo.setCurrentIndex(ni)

    def _reset_font_size(self):
        win = self._main_window()
        if win is not None and hasattr(win, "_reset_gui_font_size"):
            win._reset_gui_font_size()
        elif win is not None:
            win._set_gui_font_size(DESIGN_BASE)
        else:
            from ofscraper.gui.utils.ui_scale import set_gui_font_size

            set_gui_font_size(DESIGN_BASE, persist=True)
            app_signals.font_size_changed.emit(DESIGN_BASE)

    def _on_font_size_combo(self, _idx: int = 0):
        try:
            size = self._font_size_combo.currentData()
            if size is None:
                return
            size = int(size)
            if size == get_gui_font_size():
                self._sync_font_buttons()
                return
            win = self._main_window()
            if win is not None:
                win._set_gui_font_size(size)
            else:
                from ofscraper.gui.utils.ui_scale import set_gui_font_size

                set_gui_font_size(size, persist=True)
                app_signals.font_size_changed.emit(size)
        except Exception:
            pass

    def _check_for_updates(self):
        if self._check_worker is not None:
            return
        self._check_btn.setEnabled(False)
        self._update_status.setText("Checking PyPI…")
        from ofscraper.gui.utils.version_check import check_for_updates

        worker = Worker(check_for_updates)
        self._check_worker = worker
        worker.signals.finished.connect(self._on_update_check_finished)
        worker.signals.error.connect(self._on_update_check_error)
        QThreadPool.globalInstance().start(worker)

    def _on_update_check_finished(self, result):
        self._check_worker = None
        self._check_btn.setEnabled(True)
        try:
            self._update_status.setText(getattr(result, "message", str(result)))
            url = getattr(result, "project_url", None) or PYPI_URL
            self._project_url = url
            status = getattr(result, "status", "")
            self._open_pypi_btn.setEnabled(status in ("update_available", "error", "up_to_date", "dev"))
            if status == "update_available":
                self._update_status.setStyleSheet(f"color: {c('peach')};")
            elif status == "up_to_date":
                self._update_status.setStyleSheet(f"color: {c('green')};")
            else:
                self._update_status.setStyleSheet("")
        except Exception:
            self._update_status.setText("Update check finished with an unexpected result.")
            self._open_pypi_btn.setEnabled(True)

    def _on_update_check_error(self, message: str):
        self._check_worker = None
        self._check_btn.setEnabled(True)
        self._update_status.setText(f"Update check failed: {message}")
        self._update_status.setStyleSheet("")
        self._open_pypi_btn.setEnabled(True)

    def _open_project_url(self):
        QDesktopServices.openUrl(QUrl(self._project_url or PYPI_URL))

    def _open_help(self):
        try:
            from ofscraper.gui.signals import app_signals

            app_signals.navigate_to_page.emit("help")
        except Exception:
            pass
        self.raise_()


def show_about_dialog(parent=None) -> AboutDialog:
    """Show the About dialog, or raise the existing one."""
    from ofscraper.gui.utils.window_registry import show_or_raise

    def _factory():
        return AboutDialog(parent)

    return show_or_raise("about", _factory)  # type: ignore[return-value]
