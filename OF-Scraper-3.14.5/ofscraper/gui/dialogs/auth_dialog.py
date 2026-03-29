import json
import logging
import platform
import traceback

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QColor, QFont, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton
import ofscraper.utils.paths.common as common_paths

log = logging.getLogger("shared")

AUTH_FIELDS = [
    ("sess", "Session Cookie (sess)"),
    ("auth_id", "Auth ID Cookie"),
    ("auth_uid", "Auth UID Cookie (optional, for 2FA)"),
    ("user_agent", "User Agent"),
    ("x-bc", "X-BC Header"),
]

BROWSERS = [
    "Chrome",
    "Chromium",
    "Firefox",
    "Opera",
    "Opera GX",
    "Edge",
    "Brave",
    "Vivaldi",
]


def _detect_user_agent(browser_name: str) -> str:
    """Try to detect the user agent string for the given browser.

    Checks the installed browser version and constructs a standard UA string.
    Returns empty string if detection fails.
    """
    import subprocess
    import shutil

    browser_name = browser_name.lower().replace(" ", "")
    os_name = platform.system()

    # Map browser names to executable names and version detection commands
    if os_name == "Windows":
        # On Windows, check registry or run the executable with --version
        version_commands = {
            "chrome": [
                r'reg query "HKLM\SOFTWARE\Google\Chrome\BLBeacon" /v version',
                r'reg query "HKLM\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon" /v version',
            ],
            "chromium": [
                r'reg query "HKLM\SOFTWARE\Chromium\BLBeacon" /v version',
            ],
            "edge": [
                r'reg query "HKLM\SOFTWARE\Microsoft\Edge\BLBeacon" /v version',
                r'reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Edge\BLBeacon" /v version',
            ],
            "brave": [
                r'reg query "HKLM\SOFTWARE\BraveSoftware\Brave-Browser\BLBeacon" /v version',
                r'reg query "HKLM\SOFTWARE\WOW6432Node\BraveSoftware\Brave-Browser\BLBeacon" /v version',
            ],
            "vivaldi": [
                r'reg query "HKLM\SOFTWARE\Vivaldi\BLBeacon" /v version',
            ],
            "firefox": [
                r'reg query "HKLM\SOFTWARE\Mozilla\Mozilla Firefox" /v CurrentVersion',
                r'reg query "HKLM\SOFTWARE\WOW6432Node\Mozilla\Mozilla Firefox" /v CurrentVersion',
            ],
        }
    else:
        # Linux / macOS — use command-line --version
        version_commands = {
            "chrome": ["google-chrome --version", "google-chrome-stable --version"],
            "chromium": ["chromium --version", "chromium-browser --version"],
            "edge": ["microsoft-edge --version", "microsoft-edge-stable --version"],
            "brave": ["brave-browser --version", "brave --version"],
            "vivaldi": ["vivaldi --version", "vivaldi-stable --version"],
            "firefox": ["firefox --version"],
            "opera": ["opera --version"],
            "operagx": ["opera --version"],
        }

    # Try to get the version
    version = ""
    for cmd in version_commands.get(browser_name, []):
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=5
            )
            output = result.stdout.strip()
            if output:
                # Extract version number (e.g., "120.0.6099.130")
                import re
                match = re.search(r"(\d+\.\d+[\.\d]*)", output)
                if match:
                    version = match.group(1)
                    break
        except Exception:
            continue

    if not version:
        return ""

    # Build the OS part of the UA
    if os_name == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif os_name == "Darwin":
        mac_ver = platform.mac_ver()[0] or "10_15_7"
        mac_ver = mac_ver.replace(".", "_")
        os_ua = f"Macintosh; Intel Mac OS X {mac_ver}"
    else:
        os_ua = "X11; Linux x86_64"

    # Build browser-specific UA string
    if browser_name == "firefox":
        major = version.split(".")[0]
        return f"Mozilla/5.0 ({os_ua}; rv:{major}.0) Gecko/20100101 Firefox/{major}.0"
    else:
        # Chrome-based browsers all use the Chrome UA format
        return (
            f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )


def _find_firefox_cookie_file() -> str | None:
    """Search all known Firefox profile locations for cookies.sqlite.

    Checks XDG, standard, Snap, and Flatpak install paths on Linux.
    Uses glob to find cookies.sqlite directly (more robust than parsing profiles.ini).
    Returns the path to cookies.sqlite if found, else None.
    """
    from pathlib import Path

    home = Path.home()
    candidates = [
        home / ".config" / "mozilla" / "firefox",           # XDG (KDE Neon, etc.)
        home / "snap" / "firefox" / "common" / ".mozilla" / "firefox",  # Snap
        home / ".mozilla" / "firefox",                       # Standard
        home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",  # Flatpak
        home / ".mozilla" / "firefox-esr",                   # ESR
    ]

    for profile_dir in candidates:
        if not profile_dir.is_dir():
            continue
        # Glob for cookies.sqlite in any profile subdirectory
        cookie_files = sorted(
            profile_dir.glob("*/cookies.sqlite"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,  # most recently modified first
        )
        if cookie_files:
            log.debug(f"Found Firefox cookies: {cookie_files[0]}")
            return str(cookie_files[0])

    return None


class AuthPage(QWidget):
    """Authentication credential editor page — replaces the InquirerPy auth prompt.
    Displayed inline as a page in the main window stack."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._inputs = {}
        self._setup_ui()
        self._load_auth()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Header
        header = QLabel("Authentication")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Enter your OnlyFans authentication credentials. "
            "These are stored in auth.json in your profile directory."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        # Credential fields
        form_group = QGroupBox("Credentials")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(12)

        _auth_tips = {
            "sess": "Your 'sess' session cookie from OnlyFans.\nFound in browser DevTools > Application > Cookies.",
            "auth_id": "Your 'auth_id' cookie from OnlyFans.\nFound in browser DevTools > Application > Cookies.",
            "auth_uid": "Your 'auth_uid_XXXX' cookie (only needed for 2FA accounts).\nLeave empty if you don't use two-factor authentication.",
            "user_agent": "Your browser's User-Agent string.\nFound in browser DevTools > Console: navigator.userAgent",
            "x-bc": "The 'x-bc' header from OnlyFans API requests.\nFound in browser DevTools > Network tab > any OF API request > Request Headers.",
        }
        for field_key, label_text in AUTH_FIELDS:
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"Enter {label_text}...")
            line_edit.setClearButtonEnabled(True)
            line_edit.setToolTip(_auth_tips.get(field_key, ""))
            if field_key == "sess":
                # Add eye toggle action for showing/hiding the session cookie
                self._sess_toggle = QAction(self)
                self._sess_toggle.setIcon(self._make_eye_icon(visible=True))
                self._sess_toggle.setToolTip("Show/hide session cookie")
                self._sess_toggle.triggered.connect(self._toggle_sess_visibility)
                line_edit.addAction(self._sess_toggle, QLineEdit.ActionPosition.TrailingPosition)
            form_layout.addRow(label_text + ":", line_edit)
            self._inputs[field_key] = line_edit

        layout.addWidget(form_group)

        # Browser import
        import_group = QGroupBox("Import from Browser *")
        import_inner = QVBoxLayout(import_group)

        # Info label
        info_label = QLabel(
            "* This feature is a work in progress and may not work on all systems.\n"
            "Imports cookies (sess, auth_id) and detects User Agent automatically.\n"
            "X-BC Header must still be entered manually from browser DevTools (F12 > Network tab).\n"
            "Only works with the browser's default profile. The browser must be closed before importing."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("muted", True)
        import_inner.addWidget(info_label)

        import_row = QHBoxLayout()
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(BROWSERS)
        self.browser_combo.setToolTip(
            "Select which browser to import cookies from.\n"
            "The browser must be closed before importing."
        )
        import_row.addWidget(QLabel("Browser:"))
        import_row.addWidget(self.browser_combo)

        import_btn = StyledButton("Import Cookies")
        import_btn.clicked.connect(self._import_from_browser)
        import_row.addWidget(import_btn)
        import_row.addStretch()

        import_inner.addLayout(import_row)
        layout.addWidget(import_group)

        # Troubleshooting help
        help_group = QGroupBox("Still having issues?")
        help_layout = QVBoxLayout(help_group)
        help_label = QLabel(
            "If authentication keeps failing, try the following:\n"
            "\n"
            "1. Make sure you are logged into OnlyFans in your browser\n"
            "2. Try changing the Dynamic Rules setting in Configuration > General\n"
            "    (try 'digitalcriminals', 'datawhores', or 'xagler')\n"
            "3. Clear your browser cookies for OnlyFans, log in again, and re-import\n"
            "4. Manually copy all values from browser DevTools (F12 > Network tab > any API request headers)\n"
            "5. Check the OF-Scraper docs: "
        )
        help_label.setWordWrap(True)
        help_label.setProperty("muted", True)
        help_layout.addWidget(help_label)

        docs_btn = StyledButton("Open Auth Help Docs")
        docs_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://of-scraper.gitbook.io/of-scraper/auth")
            )
        )
        help_layout.addWidget(docs_btn)
        layout.addWidget(help_group)

        layout.addStretch()

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        open_auth_btn = StyledButton("Open auth.json")
        open_auth_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(common_paths.get_auth_file()))
            )
        )
        btn_layout.addWidget(open_auth_btn)

        reload_btn = StyledButton("Reload")
        reload_btn.clicked.connect(self._load_auth)
        btn_layout.addWidget(reload_btn)

        save_btn = StyledButton("Save", primary=True)
        save_btn.setFixedWidth(120)
        save_btn.clicked.connect(self._save_auth)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    @staticmethod
    def _make_eye_icon(visible: bool = True) -> QIcon:
        """Create a simple eye icon. visible=True means 'click to show', False means 'click to hide'."""
        size = 16
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))  # transparent
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor("#a6adc8") if visible else QColor("#cdd6f4")
        p.setPen(color)
        p.setBrush(QColor(0, 0, 0, 0))
        # Draw eye outline
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(1, 8)
        path.cubicTo(4, 3, 12, 3, 15, 8)
        path.cubicTo(12, 13, 4, 13, 1, 8)
        p.drawPath(path)
        # Draw pupil
        p.setBrush(color)
        p.drawEllipse(QPointF(8, 8), 2.5, 2.5)
        # Draw strike-through line when hidden
        if visible:
            p.setPen(QColor("#f38ba8"))
            p.drawLine(3, 13, 13, 3)
        p.end()
        return QIcon(pm)

    def _toggle_sess_visibility(self):
        """Toggle session cookie field between visible text and dots."""
        sess = self._inputs.get("sess")
        if not sess:
            return
        if sess.echoMode() == QLineEdit.EchoMode.Password:
            sess.setEchoMode(QLineEdit.EchoMode.Normal)
            self._sess_toggle.setIcon(self._make_eye_icon(visible=False))
            self._sess_toggle.setToolTip("Hide session cookie")
        else:
            sess.setEchoMode(QLineEdit.EchoMode.Password)
            self._sess_toggle.setIcon(self._make_eye_icon(visible=True))
            self._sess_toggle.setToolTip("Show session cookie")

    def _load_auth(self):
        """Load current auth.json values into the form."""
        try:
            from ofscraper.utils.auth.utils.dict import get_auth_dict, get_empty
            try:
                auth = get_auth_dict()
            except Exception:
                auth = get_empty()

            for field_key, _ in AUTH_FIELDS:
                value = auth.get(field_key, "")
                self._inputs[field_key].setText(str(value) if value else "")

            # Mask session cookie after loading
            sess = self._inputs.get("sess")
            if sess and sess.text():
                sess.setEchoMode(QLineEdit.EchoMode.Password)

            app_signals.status_message.emit("Auth credentials loaded")
        except Exception as e:
            log.error(f"Failed to load auth: {e}")
            app_signals.status_message.emit(f"Failed to load auth: {e}")

    def _save_auth(self):
        """Save form values to auth.json."""
        try:
            auth = {}
            for field_key, _ in AUTH_FIELDS:
                auth[field_key] = self._inputs[field_key].text().strip()

            # Warn about missing required fields but still allow save
            required = ["sess", "auth_id", "user_agent", "x-bc"]
            missing = [k for k in required if not auth.get(k)]
            if missing:
                reply = QMessageBox.warning(
                    self,
                    "Missing Fields",
                    f"The following required fields are empty: {', '.join(missing)}\n\n"
                    "Save anyway? (Auth may not work until all fields are filled.)",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            from ofscraper.utils.auth.file import write_auth
            import ofscraper.utils.paths.common as common_paths
            auth_path = common_paths.get_auth_file()
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"Saving auth to: {auth_path}")
            write_auth(json.dumps(auth))
            log.info(f"Auth saved successfully. Keys with values: {[k for k in required if auth.get(k)]}")

            # Mask session cookie after saving
            sess = self._inputs.get("sess")
            if sess and sess.text():
                sess.setEchoMode(QLineEdit.EchoMode.Password)

            app_signals.status_message.emit("Auth credentials saved")
            QMessageBox.information(self, "Saved", "Authentication credentials saved successfully.")
        except Exception as e:
            log.error(f"Failed to save auth: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

    def _import_from_browser(self):
        """Attempt to import cookies and detect user agent from the selected browser."""
        browser_display = self.browser_combo.currentText()
        browser_name = browser_display.lower().replace(" ", "")
        try:
            import browser_cookie3

            browser_func_map = {
                "chrome": browser_cookie3.chrome,
                "chromium": browser_cookie3.chromium,
                "firefox": browser_cookie3.firefox,
                "opera": browser_cookie3.opera,
                "operagx": browser_cookie3.opera_gx,
                "edge": browser_cookie3.edge,
                "brave": browser_cookie3.brave,
                "vivaldi": browser_cookie3.vivaldi,
            }

            func = browser_func_map.get(browser_name)
            if not func:
                QMessageBox.warning(
                    self, "Error", f"Unsupported browser: {browser_name}"
                )
                return

            # For Firefox on Linux, try to find the cookie file manually
            # since browser_cookie3 may miss Snap/Flatpak profile paths
            kwargs = {"domain_name": "onlyfans"}
            if browser_name == "firefox" and platform.system() == "Linux":
                cookie_path = _find_firefox_cookie_file()
                if cookie_path:
                    kwargs["cookie_file"] = cookie_path
                    log.debug(f"Using Firefox cookie file: {cookie_path}")

            cj = func(**kwargs)
            cookies = {c.name: c.value for c in cj}

            imported = []
            if "sess" in cookies:
                self._inputs["sess"].setText(cookies["sess"])
                imported.append("sess")
            if "auth_id" in cookies:
                self._inputs["auth_id"].setText(cookies["auth_id"])
                imported.append("auth_id")
            if "auth_uid_" in cookies:
                self._inputs["auth_uid"].setText(cookies["auth_uid_"])
                imported.append("auth_uid")

            # Try to auto-detect user agent from installed browser version
            ua_detected = False
            if not self._inputs["user_agent"].text().strip():
                try:
                    ua = _detect_user_agent(browser_name)
                    if ua:
                        self._inputs["user_agent"].setText(ua)
                        imported.append("user_agent")
                        ua_detected = True
                except Exception as e:
                    log.debug(f"User agent detection failed: {e}")

            if imported:
                app_signals.status_message.emit(
                    f"Imported {', '.join(imported)} from {browser_display}"
                )

                # Build result message
                msg_parts = [f"Imported: {', '.join(imported)}"]
                if ua_detected:
                    msg_parts.append(
                        "User Agent was auto-detected from your browser version. "
                        "Verify it matches what you see in browser DevTools."
                    )
                else:
                    msg_parts.append(
                        "User Agent could not be detected automatically. "
                        "Please enter it manually from browser DevTools (F12 > Network tab)."
                    )
                msg_parts.append(
                    "\nX-BC Header must be entered manually.\n"
                    "Open OnlyFans in your browser, press F12, go to Network tab,\n"
                    "click any API request, and copy the 'x-bc' value from Request Headers."
                )
                QMessageBox.information(
                    self, "Import Results", "\n\n".join(msg_parts)
                )
            else:
                QMessageBox.warning(
                    self,
                    "No Cookies Found",
                    f"No OnlyFans cookies found in {browser_display}.\n\n"
                    "Make sure you are logged into OnlyFans in that browser\n"
                    "and that the browser is closed before importing.\n\n"
                    "Note: Only the browser's default profile is supported.",
                )
        except Exception as e:
            log.error(f"Browser import failed: {e}")
            log.debug(traceback.format_exc())
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Could not import cookies from {browser_display}:\n{e}\n\n"
                "Make sure the browser is fully closed and try again.",
            )
