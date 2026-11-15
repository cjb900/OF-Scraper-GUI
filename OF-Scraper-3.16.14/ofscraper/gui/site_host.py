"""The tab window: OnlyFans and Fansly, each in its own GUI process.

ofscraper keeps config, auth, sessions and settings in process-wide state, so
one process can only work on one site. This window starts one GUI process per
site (see site_context.site_command) and shows each in a tab, embedding the
child's main window with QWindow.fromWinId + QWidget.createWindowContainer.
Both sites can scrape at the same time; their files never mix.

Embedding another process's window needs X11 (Linux, including XWayland and
Docker) or Windows. Elsewhere (macOS, Wayland-only) the same window works as a
launcher and each site opens in its own window.

The children report over their stdout (site_context.send) and are asked to
quit over their stdin; see site_context.
"""

from __future__ import annotations

import logging
import os
import platform
import signal
import sys

log = logging.getLogger("shared")

# how long the children get to stop their scrapes before they are killed
QUIT_TIMEOUT_MS = 30_000


def prefer_x11() -> None:
    """On Linux, run on X11 (XWayland under Wayland): embedding needs it."""
    if platform.system() != "Linux":
        return
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("DISPLAY"):
        os.environ["QT_QPA_PLATFORM"] = "xcb"


def embedding_supported(app) -> bool:
    return app.platformName() in ("xcb", "windows")


def _last_site() -> str | None:
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        site = load_gui_settings().get("last_site")
        from ofscraper.gui import site_context

        return site if site in site_context.SITES else None
    except Exception:
        return None


def _remember_site(site: str) -> None:
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

        settings = load_gui_settings()
        if settings.get("last_site") != site:
            settings["last_site"] = site
            save_gui_settings(settings, quiet=True)
    except Exception:
        pass


def run_site_host(manager=None) -> None:
    """Entry point for ``ofscraper --gui`` (outside a child process)."""
    prefer_x11()

    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QApplication

    import ofscraper.utils.args.accessors.read as read_args
    from ofscraper.gui import site_context

    args = read_args.retriveArgs()
    requested = site_context.FANSLY if getattr(args, "site", None) == "fansly" else (
        site_context.ONLYFANS if getattr(args, "site", None) == "onlyfans" else None
    )
    initial = requested or _last_site() or site_context.ONLYFANS
    forwarded = site_context.strip_site_args(sys.argv[1:])
    onlyfans_config = getattr(args, "config", None)

    app = QApplication(sys.argv[:1])
    app.setApplicationName("OF-Scraper")
    app.setStyle("Fusion")
    try:
        import pathlib

        icon = pathlib.Path(__file__).parent / "assets" / "icon.png"
        if icon.exists():
            app.setWindowIcon(QIcon(str(icon)))
    except Exception:
        pass
    try:
        from ofscraper.gui.styles import get_dark_theme_qss, get_light_theme_qss
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        light = load_gui_settings().get("theme", "dark") == "light"
        app.setStyleSheet(get_light_theme_qss() if light else get_dark_theme_qss())
    except Exception:
        pass

    _, host_window_class = _define_classes()
    window = host_window_class(
        initial=initial,
        forwarded=forwarded,
        onlyfans_config=onlyfans_config,
        embed=embedding_supported(app),
    )
    window.show()
    window.start_site(initial)

    # docker stop / SIGTERM: stop the children the clean way, then exit
    def _on_sigterm(signum, frame):
        QTimer.singleShot(0, window.close)

    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
        # let Python run the handler while Qt's loop is waiting
        pump = QTimer()
        pump.start(250)
        pump.timeout.connect(lambda: None)
        app._ofs_signal_pump = pump
    except Exception:
        pass

    app.exec()


# Qt classes are defined lazily so importing this module never needs PyQt6
def _define_classes():
    from PyQt6.QtCore import QProcess, Qt, QTimer
    from PyQt6.QtGui import QWindow
    from PyQt6.QtWidgets import (
        QLabel,
        QMainWindow,
        QMessageBox,
        QStackedWidget,
        QSystemTrayIcon,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    from ofscraper.gui import site_context
    from ofscraper.gui.widgets.styled_button import StyledButton

    class SiteTab(QWidget):
        """One site: a Start screen, or the site's embedded window."""

        def __init__(self, host, site, embed):
            super().__init__()
            self.host = host
            self.site = site
            self.embed = embed
            self.label = site_context.site_label(site)
            self.process = None
            self.busy = False
            self.container = None
            self._buffer = b""

            self.stack = QStackedWidget(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.stack)

            self.start_page = QWidget()
            start_layout = QVBoxLayout(self.start_page)
            start_layout.addStretch()
            self.message = QLabel(f"{self.label} isn't running.")
            self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.message.setWordWrap(True)
            start_layout.addWidget(self.message)
            self.start_btn = StyledButton(f"Start {self.label}", primary=True)
            self.start_btn.clicked.connect(self.start)
            start_layout.addWidget(self.start_btn, 0, Qt.AlignmentFlag.AlignCenter)
            self.show_btn = StyledButton(f"Show {self.label} window")
            self.show_btn.clicked.connect(self.raise_window)
            self.show_btn.hide()
            start_layout.addWidget(self.show_btn, 0, Qt.AlignmentFlag.AlignCenter)
            start_layout.addStretch()
            self.stack.addWidget(self.start_page)

        # --- process ----------------------------------------------------------------

        def running(self) -> bool:
            return self.process is not None and self.process.state() != QProcess.ProcessState.NotRunning

        def start(self, extra=None):
            if self.running():
                return
            command = site_context.site_command(
                self.site,
                extra=extra if extra is not None else [],
                config=self.host.onlyfans_config,
            )
            proc = QProcess(self)
            env = site_context.child_environment(self.embed)
            from PyQt6.QtCore import QProcessEnvironment

            penv = QProcessEnvironment()
            for k, v in env.items():
                penv.insert(k, v)
            proc.setProcessEnvironment(penv)
            proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            proc.readyReadStandardOutput.connect(self._read)
            proc.finished.connect(self._finished)
            self.process = proc
            self._buffer = b""
            self.message.setText(f"Starting {self.label}…")
            self.start_btn.hide()
            self.show_btn.hide()
            log.info(f"[GUI] starting {self.label}: {' '.join(command[:4])} …")
            proc.start(command[0], command[1:])

        def request_quit(self):
            if self.running():
                try:
                    self.process.write(b"quit\n")
                except Exception:
                    pass

        def kill(self):
            if self.running():
                self.process.kill()

        def raise_window(self):
            # separate-window mode: nothing to raise from here; the child is its
            # own window. Starting again brings up a new one if it was closed.
            if not self.running():
                self.start()

        # --- messages from the child -------------------------------------------------

        def _read(self):
            self._buffer += bytes(self.process.readAllStandardOutput())
            while b"\n" in self._buffer:
                raw, self._buffer = self._buffer.split(b"\n", 1)
                line = raw.decode("utf-8", "replace").rstrip("\r")
                parsed = site_context.parse_channel_line(line)
                if parsed is None:
                    # the child's console output, labelled
                    try:
                        sys.stdout.write(f"[{self.label}] {line}\n")
                        sys.stdout.flush()
                    except Exception:
                        pass
                    continue
                self._on_message(*parsed)

        def _on_message(self, kind, payload):
            if kind == "window" and self.embed and isinstance(payload, dict):
                self._embed(int(payload.get("id") or 0))
            elif kind == "ready" and not self.embed:
                self.message.setText(f"{self.label} is open in its own window.")
                self.show_btn.hide()
            elif kind == "busy":
                self.busy = True
                self.host.update_tab(self)
            elif kind == "idle":
                self.busy = False
                self.host.update_tab(self)
            elif kind == "notify" and isinstance(payload, dict):
                self.host.notify(
                    f"{self.label}: {payload.get('title', '')}", payload.get("message", "")
                )

        def _embed(self, win_id):
            if not win_id or self.container is not None:
                return
            foreign = QWindow.fromWinId(win_id)
            if foreign is None:
                self.message.setText(
                    f"Couldn't embed the {self.label} window; it stays open on its own."
                )
                return
            self.container = QWidget.createWindowContainer(foreign, self)
            self.container.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.stack.addWidget(self.container)
            self.stack.setCurrentWidget(self.container)

        def _finished(self, code, status):
            self.busy = False
            if self.container is not None:
                self.stack.removeWidget(self.container)
                self.container.deleteLater()
                self.container = None
            self.stack.setCurrentWidget(self.start_page)
            crashed = status == QProcess.ExitStatus.CrashExit or code not in (0, 130)
            self.message.setText(
                f"{self.label} stopped unexpectedly (exit code {code}). See the console for details."
                if crashed and not self.host.closing
                else f"{self.label} isn't running."
            )
            self.start_btn.show()
            self.host.update_tab(self)
            self.host.child_finished()

    class SiteHostWindow(QMainWindow):
        def __init__(self, initial, forwarded, onlyfans_config, embed):
            super().__init__()
            self.setWindowTitle("OF-Scraper")
            self.resize(1500, 950)
            self.embed = embed
            self.onlyfans_config = onlyfans_config
            self.forwarded = forwarded
            self.initial = initial
            self.closing = False
            self._close_deadline = None

            self.tabs = QTabWidget(self)
            self.tabs.setDocumentMode(True)
            self.site_tabs = {}
            for site in site_context.SITES:
                tab = SiteTab(self, site, embed)
                self.site_tabs[site] = tab
                self.tabs.addTab(tab, tab.label)
            self.tabs.currentChanged.connect(self._on_tab_changed)
            self.setCentralWidget(self.tabs)
            if not embed:
                self.resize(520, 300)
                self.statusBar().showMessage(
                    "Each site opens in its own window on this system."
                )

            self.tray = None
            try:
                if QSystemTrayIcon.isSystemTrayAvailable():
                    from PyQt6.QtWidgets import QApplication

                    self.tray = QSystemTrayIcon(QApplication.windowIcon(), self)
                    self.tray.setToolTip("OF-Scraper")
                    self.tray.show()
            except Exception:
                self.tray = None

        def start_site(self, site):
            tab = self.site_tabs[site]
            self.tabs.setCurrentWidget(tab)
            # command-line options (e.g. Docker's GUI_ARGS) go to the first site
            tab.start(extra=self.forwarded if site == self.initial else [])

        def _on_tab_changed(self, index):
            tab = self.tabs.widget(index)
            if tab is not None:
                _remember_site(tab.site)

        def update_tab(self, tab):
            index = self.tabs.indexOf(tab)
            text = ("● " if tab.busy else "") + tab.label
            self.tabs.setTabText(index, text)
            self.tabs.setTabToolTip(
                index, f"{tab.label}: downloading" if tab.busy else tab.label
            )

        def notify(self, title, message):
            if self.tray is not None:
                try:
                    self.tray.showMessage(
                        title, message, QSystemTrayIcon.MessageIcon.Information, 5000
                    )
                except Exception:
                    pass

        # --- closing ----------------------------------------------------------------------

        def closeEvent(self, event):
            running = [t for t in self.site_tabs.values() if t.running()]
            if not running:
                event.accept()
                return
            if not self.closing:
                busy = [t.label for t in running if t.busy]
                if busy:
                    answer = QMessageBox.question(
                        self,
                        "Stop downloads?",
                        f"{' and '.join(busy)} {'is' if len(busy) == 1 else 'are'} still "
                        "downloading. Stop and close?",
                    )
                    if answer != QMessageBox.StandardButton.Yes:
                        event.ignore()
                        return
                self.closing = True
                self.statusBar().showMessage("Stopping… waiting for the sites to close")
                for tab in running:
                    tab.request_quit()
                QTimer.singleShot(QUIT_TIMEOUT_MS, self._kill_children)
            event.ignore()

        def child_finished(self):
            if self.closing and not any(t.running() for t in self.site_tabs.values()):
                self.close()

        def _kill_children(self):
            for tab in self.site_tabs.values():
                tab.kill()

    return SiteTab, SiteHostWindow


def __getattr__(name):
    if name in ("SiteTab", "SiteHostWindow"):
        site_tab, host_window = _define_classes()
        globals().update(SiteTab=site_tab, SiteHostWindow=host_window)
        return globals()[name]
    raise AttributeError(name)
