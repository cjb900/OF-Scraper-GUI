"""Fansly authentication page: the token and user agent in fansly_auth.json.

Fansly signs requests with an authorization token (the web app keeps it in
localStorage under ``session_active_session``) and needs the user agent of the
browser the token came from. The token can be pasted, read from the built-in
browser after signing in to fansly.com, or imported from a browser on this
computer that is signed in to Fansly (gui/utils/fansly_browser_import.py).
"""

from __future__ import annotations

import logging
import os
import platform
import shutil

from PyQt6.QtCore import Qt, QThreadPool, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.group_layout import compact_group
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.utils.ui_scale import style_page_title
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

FANSLY_URL = "https://fansly.com/"
# the web app's localStorage entry that holds the session token
TOKEN_JS = (
    "(function(){try{var s=localStorage.getItem('session_active_session');"
    "if(!s)return '';var o=JSON.parse(s);return (o&&o.token)||'';}"
    "catch(e){return ''}})()"
)


def browser_user_agent() -> str:
    """A current, stable Chrome user agent for this OS (as the OnlyFans login uses)."""
    system = platform.system()
    if system == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif system == "Darwin":
        os_ua = "Macintosh; Intel Mac OS X 10_15_7"
    else:
        os_ua = "X11; Linux x86_64"
    return (
        f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    )


def _browser_profile_dir() -> str:
    from ofscraper.gui import site_context

    return str(site_context.fansly_config_home() / "browser_profile")


class FanslyBrowserLogin(QDialog):
    """fansly.com in the built-in browser; closes with the token once signed in."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        self.setWindowTitle("Log in to Fansly")
        self.resize(1100, 820)
        self.token = ""
        self.user_agent = browser_user_agent()

        layout = QVBoxLayout(self)
        self._status = QLabel(
            "Sign in to Fansly below. The token is read automatically once you're signed in."
        )
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # persistent, Fansly-only browser storage: stays signed in, and never
        # shares cookies with the OnlyFans login
        profile_dir = _browser_profile_dir()
        os.makedirs(profile_dir, exist_ok=True)
        self._view = QWebEngineView(self)
        self._profile = QWebEngineProfile("ofscraper_fansly_auth", self._view)
        self._profile.setPersistentStoragePath(profile_dir)
        self._profile.setCachePath(os.path.join(profile_dir, "cache"))
        self._profile.setHttpUserAgent(self.user_agent)
        self._page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(self._page)
        layout.addWidget(self._view, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = StyledButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self._view.setUrl(QUrl(FANSLY_URL))

    def _poll(self):
        try:
            self._page.runJavaScript(TOKEN_JS, self._on_token)
        except Exception as e:
            log.debug(f"[GUI] Fansly token poll failed: {e}")

    def _on_token(self, value):
        token = str(value or "").strip()
        if len(token) < 50:
            return
        self._timer.stop()
        self.token = token
        self.accept()

    def done(self, result):
        self._timer.stop()
        # the page must go before its profile
        try:
            self._view.setPage(None)
            self._page.deleteLater()
        except Exception:
            pass
        super().done(result)


class FanslyAuthPage(QWidget):
    """Authentication page used when this GUI process runs Fansly."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._worker = None
        self._import_worker = None
        self._build()
        self.load_auth()

    # --- layout ---------------------------------------------------------------

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        title = QLabel("Fansly Authentication")
        style_page_title(title)
        layout.addWidget(title)

        intro = QLabel(
            "Fansly needs the authorization token of a signed-in session and the user agent "
            "of the browser it came from. Log in with the built-in browser, import them from a "
            "browser on this computer that is signed in to Fansly, or paste them: "
            "in your browser's developer tools on fansly.com, Application → Local Storage → "
            "session_active_session → token."
        )
        intro.setWordWrap(True)
        intro.setProperty("subheading", True)
        layout.addWidget(intro)

        group = compact_group(QGroupBox("Credentials"))
        form = QFormLayout(group)

        token_row = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("authorization token")
        token_row.addWidget(self.token_input, 1)
        self.show_token = QCheckBox("Show")
        self.show_token.toggled.connect(
            lambda on: self.token_input.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        token_row.addWidget(self.show_token)
        form.addRow("Authorization token", token_row)

        ua_row = QHBoxLayout()
        self.ua_input = QLineEdit()
        self.ua_input.setPlaceholderText("user agent of the browser the token came from")
        ua_row.addWidget(self.ua_input, 1)
        form.addRow("User agent", ua_row)

        self.check_key_input = QLineEdit()
        self.check_key_input.setPlaceholderText("optional: leave empty for the built-in default")
        self.check_key_input.setToolTip(
            "The web app's current check key (fansly-client-check header). Fansly changes it\n"
            "when it updates its site; set it only if requests start failing."
        )
        form.addRow("Check key", self.check_key_input)
        layout.addWidget(group)

        buttons = QHBoxLayout()
        self.browser_btn = StyledButton("Log in with browser", primary=True)
        self.browser_btn.clicked.connect(self._browser_login)
        buttons.addWidget(self.browser_btn)
        self.save_btn = StyledButton("Save && Test")
        self.save_btn.clicked.connect(self._save_and_test)
        buttons.addWidget(self.save_btn)
        self.save_only_btn = StyledButton("Save")
        self.save_only_btn.setToolTip("Save what's in the fields without checking them with Fansly.")
        self.save_only_btn.clicked.connect(self._save_only)
        buttons.addWidget(self.save_only_btn)
        reload_btn = StyledButton("Reload")
        reload_btn.setToolTip("Discard unsaved edits and show what's saved.")
        reload_btn.clicked.connect(self.load_auth)
        buttons.addWidget(reload_btn)
        self.clear_btn = StyledButton("Clear")
        self.clear_btn.setToolTip("Remove the saved Fansly token and user agent.")
        self.clear_btn.clicked.connect(self._clear)
        buttons.addWidget(self.clear_btn)
        file_btn = StyledButton("Open fansly_auth.json")
        file_btn.clicked.connect(self._open_file)
        buttons.addWidget(file_btn)
        folder_btn = StyledButton("Open folder")
        folder_btn.clicked.connect(self._open_folder)
        buttons.addWidget(folder_btn)
        buttons.addStretch()
        layout.addLayout(buttons)

        import_group = compact_group(QGroupBox("Import from a browser on this computer"))
        import_row = QHBoxLayout(import_group)
        self.import_combo = QComboBox()
        from ofscraper.gui.utils.fansly_browser_import import BROWSERS

        self.import_combo.addItems(BROWSERS)
        self.import_combo.setToolTip(
            "A browser where you're signed in to fansly.com. The token is read from its\n"
            "saved site data on this computer; nothing is sent anywhere."
        )
        import_row.addWidget(self.import_combo)
        self.import_btn = StyledButton("Import from browser")
        self.import_btn.clicked.connect(self._import_from_browser)
        import_row.addWidget(self.import_btn)
        import_row.addStretch()
        layout.addWidget(import_group)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        self.path_label = QLabel("")
        self.path_label.setProperty("muted", True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.path_label)
        layout.addStretch()

    # --- file ---------------------------------------------------------------------

    def _auth_module(self):
        import ofscraper.sites.fansly.auth as fansly_auth

        return fansly_auth

    def load_auth(self):
        fansly_auth = self._auth_module()
        try:
            auth = fansly_auth.read_auth()
        except Exception as e:
            self._set_status(f"Could not read the Fansly auth file: {e}", error=True)
            return
        self.token_input.setText(auth.get("authorization_token") or "")
        self.ua_input.setText(auth.get("user_agent") or "")
        self.check_key_input.setText(auth.get("check_key") or "")
        self.path_label.setText(f"Saved in {fansly_auth.auth_path()}")
        issues = fansly_auth.problems(auth)
        self._set_status("; ".join(issues).capitalize() + "." if issues else "Credentials saved.",
                         error=bool(issues))

    def _form_auth(self) -> dict:
        fansly_auth = self._auth_module()
        current = fansly_auth.read_auth()
        current.update(
            authorization_token=self.token_input.text(),
            user_agent=self.ua_input.text(),
            check_key=self.check_key_input.text(),
        )
        return fansly_auth.normalize(current)

    def _save(self, allow_incomplete=False) -> bool:
        fansly_auth = self._auth_module()
        auth = self._form_auth()
        issues = fansly_auth.problems(auth)
        if issues and not allow_incomplete:
            self._set_status("Not saved: " + "; ".join(issues) + ".", error=True)
            return False
        try:
            fansly_auth.write_auth(auth)
            fansly_auth.hide_token(auth.get("authorization_token"))
        except Exception as e:
            self._set_status(f"Could not save: {e}", error=True)
            return False
        app_signals.auth_updated.emit()
        return True

    # --- actions ---------------------------------------------------------------------

    def _save_and_test(self):
        if not self._save():
            return
        self._set_status("Saved. Checking the token with Fansly…")
        self.save_btn.setEnabled(False)

        def _check():
            import ofscraper.sites.fansly.me as fansly_me

            return fansly_me.scrape_user()

        worker = Worker(_check)
        worker.signals.finished.connect(self._on_test_ok)
        worker.signals.error.connect(self._on_test_failed)
        self._worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_test_ok(self, me):
        self.save_btn.setEnabled(True)
        name = (me or {}).get("username") if isinstance(me, dict) else None
        self._set_status(f"Signed in to Fansly as {name}." if name else "Fansly accepted the token.")
        self._worker = None

    def _on_test_failed(self, message):
        self.save_btn.setEnabled(True)
        self._set_status(
            f"Saved, but Fansly didn't accept it: {message}. Log in again with the browser, "
            "or copy a fresh token.",
            error=True,
        )
        self._worker = None

    def _browser_login(self):
        try:
            dialog = FanslyBrowserLogin(self)
        except ImportError:
            QMessageBox.warning(
                self, "Browser not available",
                "The built-in browser needs PyQt6-WebEngine. Paste the token instead.",
            )
            return
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.token:
            return
        self.token_input.setText(dialog.token)
        self.ua_input.setText(dialog.user_agent)
        self._save_and_test()

    def _import_from_browser(self):
        browser = self.import_combo.currentText()
        self.import_btn.setEnabled(False)
        self._set_status(f"Reading the Fansly sign-in from {browser}…")

        def _find():
            from ofscraper.gui.utils import fansly_browser_import as fbi

            found = fbi.find_token(browser)
            return found, fbi.user_agent_for(browser, found.profile_dir)

        worker = Worker(_find)
        worker.signals.finished.connect(self._on_import_found)
        worker.signals.error.connect(self._on_import_failed)
        self._import_worker = worker
        QThreadPool.globalInstance().start(worker)

    def _on_import_found(self, result):
        self.import_btn.setEnabled(True)
        self._import_worker = None
        found, user_agent = result
        self.token_input.setText(found.token)
        if user_agent:
            self.ua_input.setText(user_agent)
        elif not self.ua_input.text().strip():
            self._set_status(
                f"Imported the token from {found.browser}, but its user agent couldn't be "
                "found: paste it (in that browser, search \"my user agent\"), then Save & Test.",
                error=True,
            )
            return
        self._save_and_test()

    def _on_import_failed(self, message):
        self.import_btn.setEnabled(True)
        self._import_worker = None
        self._set_status(f"Couldn't import from {self.import_combo.currentText()}: {message}",
                         error=True)

    def _save_only(self):
        fansly_auth = self._auth_module()
        issues = fansly_auth.problems(self._form_auth())
        if issues:
            answer = QMessageBox.question(
                self, "Save incomplete credentials?",
                "These credentials look incomplete: " + "; ".join(issues)
                + ".\n\nFansly scrapes won't work with them. Save anyway?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self._save(allow_incomplete=True):
            self._set_status(
                "Saved (not checked with Fansly)." if not issues
                else "Saved, but incomplete: " + "; ".join(issues) + ".",
                error=bool(issues),
            )

    def _clear(self):
        box = QMessageBox(self)
        box.setWindowTitle("Clear Fansly credentials")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            "Remove the saved Fansly token and user agent?\n\n"
            "Fansly scrapes won't work until you sign in again."
        )
        sign_out = QCheckBox("Also sign out of Fansly in the built-in browser")
        sign_out.setChecked(True)
        sign_out.setToolTip(
            "Otherwise \"Log in with browser\" signs straight back in with the same session."
        )
        box.setCheckBox(sign_out)
        clear_btn = box.addButton("Clear", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is not clear_btn:
            return
        fansly_auth = self._auth_module()
        try:
            fansly_auth.write_auth(fansly_auth.empty())
        except Exception as e:
            self._set_status(f"Could not clear the credentials: {e}", error=True)
            return
        browser_note = ""
        if sign_out.isChecked():
            shutil.rmtree(_browser_profile_dir(), ignore_errors=True)
            browser_note = " The built-in browser is signed out."
        self.token_input.clear()
        self.ua_input.clear()
        self.check_key_input.clear()
        app_signals.auth_updated.emit()
        self._set_status("Fansly credentials cleared." + browser_note)

    def _open_file(self):
        path = self._auth_module().auth_path()
        if not path.exists():
            self._set_status("Nothing saved yet: fansly_auth.json doesn't exist.", error=True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_folder(self):
        path = self._auth_module().auth_path().parent
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _set_status(self, text, error=False):
        self.status_label.setText(text)
        self.status_label.setProperty("error", bool(error))
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
