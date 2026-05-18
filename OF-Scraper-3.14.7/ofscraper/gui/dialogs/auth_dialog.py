import json
import logging
import os
import platform
import struct
import traceback

from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
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


_DYNAMIC_RULE_URLS = [
    "https://raw.githubusercontent.com/datawhores/onlyfans-dynamic-rules/main/dynamicRules.json",
    "https://raw.githubusercontent.com/xagler/dynamic-rules/main/onlyfans.json",
    "https://raw.githubusercontent.com/DATAHOARDERS/dynamic-rules/main/onlyfans.json",
]


def _validate_of_credentials(creds: dict) -> "tuple[bool | None, str]":
    """Test credentials by temporarily writing them to auth.json, then calling
    the exact same model-loading function the Scraper tab uses.  If models come
    back the credentials (and dynamic rules) are confirmed working."""
    import json as _json
    import asyncio as _aio

    try:
        import ofscraper.utils.paths.common as _paths
        import ofscraper.utils.auth.request as _auth_req
        import ofscraper.data.models.utils.retriver as _retriver
    except ImportError as e:
        return False, f"Missing ofscraper module: {e}"

    auth_path = _paths.get_auth_file()

    # Back up current auth.json so we always restore it afterwards
    _old_auth = None
    try:
        if auth_path.exists():
            _old_auth = auth_path.read_text(encoding="utf-8")
    except Exception:
        pass

    try:
        # Write test credentials — ofscraper reads auth from disk
        auth_path.parent.mkdir(parents=True, exist_ok=True)
        auth_path.write_text(
            _json.dumps({
                "sess": creds.get("sess", ""),
                "auth_id": creds.get("auth_id", ""),
                "auth_uid": creds.get("auth_uid", ""),
                "user_agent": creds.get("user_agent", ""),
                "x-bc": creds.get("x-bc", ""),
            }, indent=4),
            encoding="utf-8",
        )

        # Clear ofscraper's in-memory signing-rules cache so it re-fetches
        try:
            _auth_req.curr_auth = None
            _auth_req.last_check = None
        except Exception:
            pass

        # Run get_models() — the exact coroutine all_subs_retriver() calls —
        # with a 45-second timeout so it never hangs forever.
        loop = _aio.new_event_loop()
        try:
            models = loop.run_until_complete(
                _aio.wait_for(_retriver.get_models(), timeout=45)
            )
        finally:
            loop.close()

        if models:
            return True, (
                f"Credentials valid — loaded {len(models)} model(s) successfully.\n\n"
                "Your auth is working correctly."
            )
        else:
            return False, (
                "No models returned — credentials may be invalid, or the account "
                "has no active subscriptions.\n\n"
                "If you have subscriptions, check your Dynamic Rules setting in "
                "Configuration → Advanced and try again."
            )

    except _aio.TimeoutError:
        return False, (
            "Timed out waiting for model list — OnlyFans did not respond in 45 s.\n"
            "Check your internet connection or try again."
        )
    except Exception as e:
        msg = str(e)
        if "401" in msg or "sess" in msg.lower() or "auth" in msg.lower():
            return False, f"Auth error — session may be expired. Re-import credentials.\n\nDetail: {msg}"
        return False, f"Model load failed: {msg}"

    finally:
        # Always restore original auth.json
        try:
            if _old_auth is not None:
                auth_path.write_text(_old_auth, encoding="utf-8")
        except Exception:
            pass


class _CredTestWorker(QThread):
    # success: True=valid, False=invalid, None=inconclusive
    result_ready = pyqtSignal(object, str)

    def __init__(self, creds: dict, parent=None):
        super().__init__(parent)
        self._creds = creds

    def run(self):
        result = _validate_of_credentials(self._creds)
        # result is (success_or_None, message)
        self.result_ready.emit(result[0], result[1])


# Module-level remote debugging port — set once before the first QWebEngineView
# is created so Chromium picks it up.  Reused for every subsequent open of the
# dialog (Chromium keeps the same browser process alive).
_WEBENGINE_DEBUG_PORT: "int | None" = None


def _get_or_create_debug_port() -> int:
    """Return (and lazily allocate) the Chromium remote-debugging port.

    Must be called before the first QWebEngineView is instantiated so the
    QTWEBENGINE_CHROMIUM_FLAGS env-var is read by the Chromium process.
    """
    global _WEBENGINE_DEBUG_PORT
    if _WEBENGINE_DEBUG_PORT is None:
        import random
        _WEBENGINE_DEBUG_PORT = random.randint(9200, 9299)
        existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        if "--remote-debugging-port" not in existing:
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
                f"{existing} --remote-debugging-port={_WEBENGINE_DEBUG_PORT}".strip()
            )
    return _WEBENGINE_DEBUG_PORT


class _CDPListener(QThread):
    """Connects to Chromium's remote-debugging WebSocket and listens for
    Network events to auto-capture the x-bc request header.

    Uses only Python stdlib (socket + struct) — no extra dependencies.
    Captures x-bc from *all* requests including those made by service workers,
    which is why JS injection in the main world misses it.
    """

    xbc_captured = pyqtSignal(str)

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self._port = port
        self._running = True
        self._sock = None

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass

    def run(self):
        import base64 as _b64
        import socket as _sock_mod
        import time
        import urllib.request as _ureq
        from urllib.parse import urlparse

        # Wait up to 20 s for the CDP endpoint to come up
        targets = None
        for _ in range(20):
            if not self._running:
                return
            try:
                raw = _ureq.urlopen(
                    f"http://localhost:{self._port}/json/list", timeout=2
                ).read()
                targets = json.loads(raw)
                break
            except Exception:
                time.sleep(1)
        if not targets:
            return

        ws_url = next(
            (t.get("webSocketDebuggerUrl", "") for t in targets if t.get("type") == "page"),
            "",
        )
        if not ws_url:
            return

        try:
            u = urlparse(ws_url)
            host = u.hostname or "localhost"
            port = u.port or 80
            path = u.path + (f"?{u.query}" if u.query else "")

            self._sock = _sock_mod.create_connection((host, port), timeout=5)

            # --- WebSocket opening handshake ---
            nonce = _b64.b64encode(os.urandom(16)).decode()
            hs = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {nonce}\r\n"
                "Sec-WebSocket-Version: 13\r\n\r\n"
            )
            self._sock.sendall(hs.encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = self._sock.recv(4096)
                if not chunk:
                    return
                buf += chunk

            # Enable Network domain (captures requestWillBeSent +
            # requestWillBeSentExtraInfo which includes service-worker headers)
            self._ws_send(json.dumps({"id": 1, "method": "Network.enable", "params": {}}))
            self._sock.settimeout(2.0)

            while self._running:
                try:
                    msg = self._ws_recv()
                except _sock_mod.timeout:
                    continue
                if msg is None:
                    break
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue

                method = evt.get("method", "")
                if method not in (
                    "Network.requestWillBeSent",
                    "Network.requestWillBeSentExtraInfo",
                ):
                    continue

                params = evt.get("params", {})
                # requestWillBeSent → params["request"]["headers"]
                # requestWillBeSentExtraInfo → params["headers"]
                hdrs = params.get("headers") or params.get("request", {}).get("headers", {})
                if not isinstance(hdrs, dict):
                    continue
                for k, v in hdrs.items():
                    if k.lower() == "x-bc" and v:
                        if self._running:
                            self.xbc_captured.emit(str(v))
                        return

        except Exception:
            pass
        finally:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
            self._sock = None

    def _ws_send(self, msg: str):
        data = msg.encode("utf-8")
        length = len(data)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if length < 126:
            header = bytes([0x81, 0x80 | length]) + mask
        elif length < 65536:
            header = bytes([0x81, 0xFE]) + struct.pack(">H", length) + mask
        else:
            header = bytes([0x81, 0xFF]) + struct.pack(">Q", length) + mask
        self._sock.sendall(header + masked)

    def _ws_recv(self) -> "str | None":
        def _read(n: int) -> bytes:
            buf = b""
            while len(buf) < n:
                chunk = self._sock.recv(n - len(buf))
                if not chunk:
                    return b""
                buf += chunk
            return buf

        header = _read(2)
        if len(header) < 2:
            return None
        b1, b2 = header[0], header[1]
        opcode = b1 & 0x0F
        if opcode == 8:
            return None  # close frame
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", _read(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", _read(8))[0]
        payload = _read(length)
        if len(payload) < length:
            return None
        if opcode == 1:
            return payload.decode("utf-8", errors="replace")
        return None  # binary / ping / pong — ignore


class _CDPCookieFetcher(QThread):
    """One-shot CDP thread: calls Network.getCookies and returns current
    OnlyFans cookie values.  Used at import time to get definitive values
    rather than relying on the cookieAdded event stream."""

    result_ready = pyqtSignal(dict)

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self._port = port

    def run(self):
        import base64 as _b64
        import socket as _sock_mod
        import urllib.request as _ureq
        from urllib.parse import urlparse

        result = {}
        try:
            raw = _ureq.urlopen(
                f"http://localhost:{self._port}/json/list", timeout=3
            ).read()
            targets = json.loads(raw)
            ws_url = next(
                (t.get("webSocketDebuggerUrl", "") for t in targets if t.get("type") == "page"),
                "",
            )
            if not ws_url:
                self.result_ready.emit(result)
                return

            u = urlparse(ws_url)
            host = u.hostname or "localhost"
            port = u.port or 80
            path = u.path + (f"?{u.query}" if u.query else "")

            sock = _sock_mod.create_connection((host, port), timeout=3)
            nonce = _b64.b64encode(os.urandom(16)).decode()
            hs = (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            )
            sock.sendall(hs.encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                buf += sock.recv(4096)

            # Request all OnlyFans cookies
            cmd = json.dumps({
                "id": 1,
                "method": "Network.getCookies",
                "params": {"urls": ["https://onlyfans.com"]},
            })
            # WS send (unmasked client→server frame — CDP accepts unmasked too)
            data = cmd.encode("utf-8")
            ln = len(data)
            mask = os.urandom(4)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            if ln < 126:
                header = bytes([0x81, 0x80 | ln]) + mask
            elif ln < 65536:
                header = bytes([0x81, 0xFE]) + struct.pack(">H", ln) + mask
            else:
                header = bytes([0x81, 0xFF]) + struct.pack(">Q", ln) + mask
            sock.sendall(header + masked)

            sock.settimeout(3.0)
            # Read frames until we get the getCookies response
            while True:
                hdr = b""
                while len(hdr) < 2:
                    chunk = sock.recv(2 - len(hdr))
                    if not chunk:
                        raise ConnectionError("socket closed")
                    hdr += chunk
                b1, b2 = hdr[0], hdr[1]
                length = b2 & 0x7F
                if length == 126:
                    ext = sock.recv(2)
                    length = struct.unpack(">H", ext)[0]
                elif length == 127:
                    ext = sock.recv(8)
                    length = struct.unpack(">Q", ext)[0]
                payload = b""
                while len(payload) < length:
                    payload += sock.recv(length - len(payload))
                if (b1 & 0x0F) == 1:
                    msg = payload.decode("utf-8", errors="replace")
                    evt = json.loads(msg)
                    if evt.get("id") == 1:
                        for c in evt.get("result", {}).get("cookies", []):
                            n = c.get("name", "")
                            v = c.get("value", "")
                            if n == "sess" and v:
                                result["sess"] = v
                            elif n == "auth_id" and v:
                                result["auth_id"] = v
                            elif n.startswith("auth_uid") and v and "auth_uid" not in result:
                                result["auth_uid"] = v
                        break
            sock.close()
        except Exception as e:
            log.debug(f"CDPCookieFetcher error: {e}")
        self.result_ready.emit(result)


class BrowserLoginDialog(QDialog):
    """Popup browser dialog that navigates to onlyfans.com and captures
    auth credentials (sess, auth_id, x-bc, user-agent) automatically."""

    credentials_ready = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Login to OnlyFans — Capture Credentials")
        self.resize(1200, 820)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint
        )

        self._found = {
            "sess": "",
            "auth_id": "",
            "auth_uid": "",
            "user_agent": "",
            "x-bc": "",
        }
        self._import_btn = None
        self._status_labels = {}
        self._login_status_lbl = None  # "Not logged in" / "Logged in" indicator
        self._logged_in = False        # True only after auth_id is received
        self._view = None
        self._cookie_store = None
        self._poll_timer = None
        self._cdp_listener = None
        # Allocate debug port BEFORE any QWebEngineView is created so Chromium
        # picks up the QTWEBENGINE_CHROMIUM_FLAGS env-var.
        self._debug_port = _get_or_create_debug_port()

        self._setup_webengine()  # raises ImportError if PyQt6-WebEngine missing
        self._setup_ui()

    # ------------------------------------------------------------------
    # WebEngine setup
    # ------------------------------------------------------------------

    # JS injected at DocumentCreation — patches XHR, Headers, and fetch so we
    # catch x-bc however OnlyFans adds it (Axios defaults, Headers object, raw XHR).
    _CAPTURE_JS = r"""
(function() {
    if (window.__ofscraper_xbc_installed) return;
    window.__ofscraper_xbc_installed = true;
    window.__ofscraper_xbc = '';

    function _grab(name, value) {
        if (name && String(name).toLowerCase() === 'x-bc' && value) {
            window.__ofscraper_xbc = String(value);
        }
    }

    // 1. XHR.setRequestHeader (Axios / legacy XHR)
    var _origSet = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(n, v) {
        _grab(n, v); return _origSet.apply(this, arguments);
    };

    // 2. Headers.prototype.set / append (fetch with Headers object)
    if (typeof Headers !== 'undefined') {
        var _hs = Headers.prototype.set;
        Headers.prototype.set = function(n, v) { _grab(n, v); return _hs.apply(this, arguments); };
        var _ha = Headers.prototype.append;
        Headers.prototype.append = function(n, v) { _grab(n, v); return _ha.apply(this, arguments); };
    }

    // 3. fetch with plain-object headers
    var _origFetch = window.fetch;
    if (_origFetch) {
        window.fetch = function(input, init) {
            try {
                var h = init && init.headers;
                if (h && typeof h === 'object' && !(h instanceof Headers)) {
                    Object.keys(h).forEach(function(k) { _grab(k, h[k]); });
                }
            } catch(e) {}
            return _origFetch.apply(this, arguments);
        };
    }

    // 4. Delayed self-trigger: if x-bc still missing after 3s, nudge the page
    //    to make an API call (uses the page's own authenticated fetch context).
    setTimeout(function() {
        if (!window.__ofscraper_xbc) {
            try { fetch('/api2/v2/users/me', {credentials:'include'}); } catch(e) {}
        }
    }, 3000);
})();
"""

    def _setup_webengine(self):
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import (
            QWebEngineProfile,
            QWebEnginePage,
            QWebEngineScript,
        )


        import tempfile, os
        profile_dir = os.path.join(tempfile.gettempdir(), "ofscraper_of_auth_profile")

        # Named persistent profile so the user stays logged in between opens
        self._view = QWebEngineView()
        self._profile = QWebEngineProfile("ofscraper_of_auth", self._view)
        self._profile.setPersistentStoragePath(profile_dir)
        self._profile.setCachePath(os.path.join(profile_dir, "cache"))

        # Inject the XHR/fetch interceptor script before any page JS runs
        script = QWebEngineScript()
        script.setName("ofscraper_xbc_capture")
        script.setSourceCode(self._CAPTURE_JS)
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        self._profile.scripts().insert(script)

        page = QWebEnginePage(self._profile, self._view)
        self._view.setPage(page)

        # Set a solid background colour so the view never appears transparent
        # while the page is loading — critical on Linux compositing managers
        # (KDE, GNOME with Mutter) that otherwise show the desktop through it.
        from PyQt6.QtGui import QColor as _QColor
        page.setBackgroundColor(_QColor(30, 30, 46))  # #1e1e2e — matches UI chrome

        self._cookie_store = self._profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)
        self._cookie_store.loadAllCookies()

        # Capture user-agent silently — stored but not shown until login confirmed.
        try:
            ua = self._profile.httpUserAgent()
            if ua and not self._found["user_agent"]:
                self._found["user_agent"] = ua
        except Exception:
            pass

        # Poll JS globals every second for x-bc (user-agent fallback only)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_js_captures)
        self._poll_timer.start()

        # CDP listener — connects to Chromium's remote debugging endpoint and
        # captures x-bc from the actual network-layer headers (including those
        # added by service workers, which JS injection in the main world misses).
        self._cdp_listener = _CDPListener(self._debug_port, self)
        self._cdp_listener.xbc_captured.connect(self._on_cdp_xbc)
        self._cdp_listener.start()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Instruction bar
        bar = QWidget()
        bar.setStyleSheet("background: #1e1e2e; padding: 6px 12px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 6, 12, 6)
        hint = QLabel(
            "Log in to OnlyFans below. Credentials are captured automatically "
            "once you are logged in and the page makes API calls."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        bar_layout.addWidget(hint, stretch=1)
        layout.addWidget(bar)

        # Browser
        layout.addWidget(self._view, stretch=1)

        # Status footer
        footer = QWidget()
        footer.setStyleSheet("background: #181825; border-top: 1px solid #313244;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(16)

        # Login state indicator — shows "Not logged in" until auth_id is captured.
        self._login_status_lbl = QLabel("⚠ Not logged in")
        self._login_status_lbl.setStyleSheet(
            "color: #fab387; font-size: 11px; font-weight: bold; font-family: monospace;"
        )
        self._login_status_lbl.setToolTip(
            "Credentials are only usable after you have logged in to OnlyFans.\n"
            "Some fields (user-agent, x-bc, sess) are captured from pre-login page\n"
            "requests and are not yet valid auth credentials.\n"
            "Once auth_id is detected, you are logged in and all credentials are ready."
        )
        footer_layout.addWidget(self._login_status_lbl)

        sep = QLabel("|")
        sep.setStyleSheet("color: #45475a; font-size: 11px;")
        footer_layout.addWidget(sep)

        for label_key, display in [
            ("sess", "sess"),
            ("auth_id", "auth_id"),
            ("x-bc", "x-bc"),
            ("user_agent", "user-agent"),
        ]:
            lbl = QLabel(f"{display}: —")
            lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-family: monospace;")
            self._status_labels[label_key] = lbl
            footer_layout.addWidget(lbl)

        footer_layout.addStretch()

        devtools_btn = QPushButton("DevTools ↗")
        devtools_btn.setToolTip(
            "Opens Chrome/Edge DevTools in your system browser (fully interactive).\n\n"
            "x-bc is usually captured automatically — check the status bar above.\n"
            "If it still shows '—' after browsing, use DevTools manually:\n"
            "  1. In the list, click 'OnlyFans' (NOT 'Service Worker')\n"
            "  2. Go to Network tab → browse OnlyFans in the embedded window\n"
            "  3. Click any /api2/ request → Request Headers → copy x-bc\n"
            "  4. Paste it in the field below"
        )
        devtools_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #cdd6f4; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        devtools_btn.clicked.connect(self._open_devtools)
        footer_layout.addWidget(devtools_btn)

        clear_btn = QPushButton("Clear Session")
        clear_btn.setToolTip("Wipe all cookies and cache for this browser, then reload OnlyFans.")
        clear_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #f38ba8; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        clear_btn.clicked.connect(self._clear_session)
        footer_layout.addWidget(clear_btn)

        layout.addWidget(footer)

        # x-bc manual paste row (shown below the status bar)
        xbc_bar = QWidget()
        xbc_bar.setStyleSheet("background: #11111b; border-top: 1px solid #1e1e2e;")
        xbc_layout = QHBoxLayout(xbc_bar)
        xbc_layout.setContentsMargins(12, 6, 12, 6)
        xbc_layout.setSpacing(8)

        xbc_hint = QLabel(
            "x-bc not auto-captured?  Click DevTools ↗ → click 'OnlyFans' (not Service Worker) "
            "→ Network tab → browse OF → click any /api2/ request → Request Headers → x-bc:"
        )
        xbc_hint.setStyleSheet("color: #fab387; font-size: 11px;")
        xbc_hint.setWordWrap(False)
        xbc_layout.addWidget(xbc_hint)

        from PyQt6.QtWidgets import QLineEdit as _QLE
        self._xbc_input = _QLE()
        self._xbc_input.setPlaceholderText("Paste x-bc value here…")
        self._xbc_input.setMaximumWidth(360)
        self._xbc_input.setStyleSheet(
            "QLineEdit { background: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; "
            "border-radius: 4px; padding: 4px 8px; font-family: monospace; font-size: 11px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
        )
        self._xbc_input.textChanged.connect(self._on_xbc_pasted)
        xbc_layout.addWidget(self._xbc_input)

        self._import_btn = QPushButton("Use These Credentials")
        self._import_btn.setEnabled(False)
        self._import_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e; font-weight: bold; "
            "border-radius: 4px; padding: 6px 18px; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
            "QPushButton:hover:enabled { background: #b4d0fb; }"
        )
        self._import_btn.clicked.connect(self._on_import)
        xbc_layout.addWidget(self._import_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #cdd6f4; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background: #45475a; }"
        )
        cancel_btn.clicked.connect(self.reject)
        xbc_layout.addWidget(cancel_btn)

        layout.addWidget(xbc_bar)

        self._view.page().loadFinished.connect(self._on_page_load_finished)
        self._view.load(QUrl("https://onlyfans.com"))

    # ------------------------------------------------------------------
    # Signals / slots
    # ------------------------------------------------------------------

    @staticmethod
    def _cookie_str(val) -> str:
        """Convert QByteArray or str cookie field to a plain Python str."""
        if isinstance(val, str):
            return val
        return bytes(val).decode("utf-8", errors="ignore")

    def _on_cookie_added(self, cookie):
        name = self._cookie_str(cookie.name())
        value = self._cookie_str(cookie.value())
        domain = self._cookie_str(cookie.domain())
        if "onlyfans" not in domain:
            return
        # sess is set by OnlyFans even for logged-out visitors — store silently.
        # Only auth_id is set exclusively upon a successful login, so we use its
        # arrival as the signal that the user is actually authenticated.
        if name == "sess" and value:
            self._found["sess"] = value
        elif name == "auth_id" and value:
            self._found["auth_id"] = value
            self._reveal_all_captured()  # now logged in — show all fields
        elif name.startswith("auth_uid") and value:
            self._found["auth_uid"] = value

    def _poll_js_captures(self):
        """Poll injected JS globals for x-bc and user-agent once per second."""
        if not self._view:
            return
        need_xbc = not self._found["x-bc"]
        need_ua = not self._found["user_agent"]
        if not need_xbc and not need_ua:
            if self._poll_timer:
                self._poll_timer.stop()
            return
        js = "JSON.stringify({xbc: window.__ofscraper_xbc||'', ua: navigator.userAgent||''})"
        self._view.page().runJavaScript(js, self._on_js_poll_result)

    def _on_js_poll_result(self, result):
        if not result:
            return
        try:
            import json as _json
            data = _json.loads(result)
        except Exception:
            return
        xbc = data.get("xbc", "")
        ua = data.get("ua", "")
        if xbc and not self._found["x-bc"]:
            self._found["x-bc"] = xbc
            if self._logged_in:
                self._update_status("x-bc", xbc)
        if ua and not self._found["user_agent"]:
            self._found["user_agent"] = ua
            if self._logged_in:
                self._update_status("user_agent", ua)

    def _on_page_load_finished(self, _ok):
        """Capture user-agent via JS on every page load — stored silently until login."""
        if self._found["user_agent"] or not self._view:
            return
        def _set_ua(ua):
            if ua and not self._found["user_agent"]:
                self._found["user_agent"] = ua
                if self._logged_in:
                    self._update_status("user_agent", ua)
        self._view.page().runJavaScript("navigator.userAgent", _set_ua)

    def _on_cdp_xbc(self, xbc: str):
        """Called on the GUI thread when the CDP listener captures x-bc."""
        if xbc and not self._found["x-bc"]:
            self._found["x-bc"] = xbc
            if self._logged_in:
                self._update_status("x-bc", xbc)
                if hasattr(self, "_xbc_input"):
                    self._xbc_input.blockSignals(True)
                    self._xbc_input.setText(xbc)
                    self._xbc_input.blockSignals(False)

    def _reveal_all_captured(self):
        """Called when auth_id is first received — marks the user as logged in
        and flushes all silently-captured values to the status bar at once."""
        self._logged_in = True
        for key in ("sess", "auth_id", "x-bc", "user_agent"):
            val = self._found.get(key, "")
            if val:
                self._update_status(key, val)
        # Fill the manual x-bc paste field if we already have the value
        if self._found.get("x-bc") and hasattr(self, "_xbc_input"):
            self._xbc_input.blockSignals(True)
            self._xbc_input.setText(self._found["x-bc"])
            self._xbc_input.blockSignals(False)

    def _update_status(self, key: str, value: str):
        lbl = self._status_labels.get(key)
        if lbl:
            display_key = "user-agent" if key == "user_agent" else key
            preview = value[:20] + "…" if len(value) > 20 else value
            lbl.setText(f"{display_key}: ✓ {preview}")
            lbl.setStyleSheet("color: #a6e3a1; font-size: 11px; font-family: monospace;")
        self._refresh_import_btn()

    def _refresh_import_btn(self):
        ready = bool(self._found["sess"] and self._found["auth_id"])
        if self._import_btn:
            self._import_btn.setEnabled(ready)
            if ready:
                has_xbc = bool(self._found["x-bc"])
                self._import_btn.setText(
                    "Use These Credentials" if has_xbc
                    else "Use These Credentials  ⚠ x-bc missing"
                )
        if self._login_status_lbl:
            if ready:
                self._login_status_lbl.setText("✓ Logged in")
                self._login_status_lbl.setStyleSheet(
                    "color: #a6e3a1; font-size: 11px; font-weight: bold; font-family: monospace;"
                )
            else:
                self._login_status_lbl.setText("⚠ Not logged in")
                self._login_status_lbl.setStyleSheet(
                    "color: #fab387; font-size: 11px; font-weight: bold; font-family: monospace;"
                )

    def _on_xbc_pasted(self, text: str):
        """Called when user types/pastes into the manual x-bc field."""
        val = text.strip()
        if val and val != self._found["x-bc"]:
            self._found["x-bc"] = val
            self._update_status("x-bc", val)
        elif not val:
            self._found["x-bc"] = ""
            lbl = self._status_labels.get("x-bc")
            if lbl:
                lbl.setText("x-bc: —")
                lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-family: monospace;")
            self._refresh_import_btn()

    def _open_devtools(self):
        """Open Chromium DevTools in the system browser (fully interactive).

        Qt's setInspectedPage() DevTools panel has broken keyboard/mouse input
        in most Qt6 builds.  Opening http://localhost:{port} in Chrome/Edge/Firefox
        gives a real, fully-functional DevTools that the user can interact with.
        """
        from PyQt6.QtGui import QDesktopServices as _QDS
        from PyQt6.QtCore import QUrl as _QUrl
        url = f"http://localhost:{self._debug_port}"
        _QDS.openUrl(_QUrl(url))

    def _clear_session(self):
        """Wipe all cookies and HTTP cache for this profile, then reload OnlyFans."""
        if self._cookie_store:
            self._cookie_store.deleteAllCookies()
        if self._profile:
            self._profile.clearHttpCache()
            self._profile.clearAllVisitedLinks()
        if self._view:
            self._view.page().runJavaScript(
                "try{localStorage.clear();sessionStorage.clear();}catch(e){}"
                "window.__ofscraper_xbc='';window.__ofscraper_ua='';"
            )
        for k in list(self._found.keys()):
            self._found[k] = ""
        for key, lbl in self._status_labels.items():
            disp = "user-agent" if key == "user_agent" else key
            lbl.setText(f"{disp}: —")
            lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-family: monospace;")
        if hasattr(self, "_xbc_input"):
            self._xbc_input.blockSignals(True)
            self._xbc_input.clear()
            self._xbc_input.blockSignals(False)
        self._refresh_import_btn()
        # Restart CDP listener so it can capture x-bc again after the session reset
        if self._cdp_listener:
            self._cdp_listener.stop()
            self._cdp_listener.wait(1000)
        self._cdp_listener = _CDPListener(self._debug_port, self)
        self._cdp_listener.xbc_captured.connect(self._on_cdp_xbc)
        self._cdp_listener.start()
        # deleteAllCookies / clearHttpCache are async — delay the reload so
        # they complete before the new page load picks up fresh cookies.
        if self._view:
            QTimer.singleShot(500, lambda: self._view.load(QUrl("https://onlyfans.com")))

    def _stop_timer(self):
        if self._poll_timer and self._poll_timer.isActive():
            self._poll_timer.stop()
        if self._cdp_listener and self._cdp_listener.isRunning():
            self._cdp_listener.stop()
            self._cdp_listener.wait(2000)

    def closeEvent(self, event):
        self._stop_timer()
        super().closeEvent(event)

    def _on_import(self):
        self._stop_timer()
        # Fetch definitive live cookies via CDP first — this ensures we have
        # the exact same sess/auth_id the browser is currently using, not a
        # stale value from a previous session stored on disk.
        self._cookie_fetcher = _CDPCookieFetcher(self._debug_port, self)
        self._cookie_fetcher.result_ready.connect(self._on_fresh_cookies_for_import)
        self._cookie_fetcher.start()

    def _on_fresh_cookies_for_import(self, fresh: dict):
        """Called after CDP returns the live cookie values."""
        # Overlay fresh cookies on top of event-stream captures
        for k, v in fresh.items():
            if v:
                self._found[k] = v

        def _do_emit(ua):
            if ua:
                self._found["user_agent"] = ua
            # Generate x-bc from user-agent if capture failed — same algorithm
            # ofscraper uses for its own anon-mode token generation.
            if not self._found["x-bc"] and self._found["user_agent"]:
                import base64 as _b64, hashlib as _hl, random as _rnd, time as _tm
                _parts = [
                    int(_tm.time() * 1000),
                    int(1e12 * _rnd.random()),
                    int(1e12 * _rnd.random()),
                    self._found["user_agent"],
                ]
                _msg = ".".join([_b64.b64encode(str(p).encode()).decode() for p in _parts])
                self._found["x-bc"] = _hl.sha1(_msg.encode(), usedforsecurity=False).hexdigest()
                self._found["_xbc_generated"] = True

            self.credentials_ready.emit(dict(self._found))
            self.accept()

        if self._view:
            self._view.page().runJavaScript("navigator.userAgent", _do_emit)
        else:
            _do_emit("")


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

        # Browser login
        import_group = QGroupBox("Login in Browser")
        import_inner = QVBoxLayout(import_group)

        info_label = QLabel(
            "Opens an embedded OnlyFans browser window directly inside the app.\n"
            "Log in as normal — all credentials (sess, auth_id, User Agent, and X-BC Header) "
            "are detected automatically.\n"
            "Once captured, click \"Use These Credentials\" in the browser window to populate the fields above."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("muted", True)
        import_inner.addWidget(info_label)

        login_row = QHBoxLayout()
        login_row.addStretch()
        login_btn = StyledButton("Login in Browser…")
        login_btn.setToolTip(
            "Opens an embedded OnlyFans browser window.\n"
            "Log in and all auth fields are captured automatically.\n"
            "Requires: pip install PyQt6-WebEngine"
        )
        login_btn.clicked.connect(self._open_browser_login)
        login_row.addWidget(login_btn)

        import_inner.addLayout(login_row)
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

        self._test_btn = StyledButton("Test Credentials")
        self._test_btn.setToolTip(
            "Make a live API call to OnlyFans to verify these credentials work.\n"
            "Fetches dynamic signing rules and calls /api2/v2/users/me."
        )
        self._test_btn.clicked.connect(self._test_credentials)
        btn_layout.addWidget(self._test_btn)

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

    def _test_credentials(self):
        """Validate the currently entered credentials against the live OF API."""
        creds = {fk: self._inputs[fk].text().strip() for fk, _ in AUTH_FIELDS}
        missing = [k for k in ("sess", "auth_id", "user_agent", "x-bc") if not creds.get(k)]
        if missing:
            QMessageBox.warning(
                self, "Missing Fields",
                f"Cannot test — fill in all required fields first:\n{', '.join(missing)}"
            )
            return
        self._test_btn.setEnabled(False)
        self._test_btn.setText("Testing…")
        app_signals.status_message.emit("Testing credentials against OnlyFans API…")

        # Build a progress dialog so the user knows something is happening.
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar
        from PyQt6.QtCore import Qt as _Qt2

        self._test_progress_dlg = QDialog(self)
        self._test_progress_dlg.setWindowTitle("Testing Credentials")
        self._test_progress_dlg.setWindowFlags(
            self._test_progress_dlg.windowFlags()
            & ~_Qt2.WindowType.WindowContextHelpButtonHint
        )
        self._test_progress_dlg.setMinimumWidth(380)
        self._test_progress_dlg.setModal(True)
        _vbox = QVBoxLayout(self._test_progress_dlg)
        _vbox.setSpacing(12)
        _vbox.setContentsMargins(20, 20, 20, 20)
        _lbl = QLabel("Connecting to OnlyFans and loading model list…\nThis may take up to 45 seconds.")
        _lbl.setWordWrap(True)
        _vbox.addWidget(_lbl)
        _bar = QProgressBar()
        _bar.setRange(0, 0)  # indeterminate / marquee
        _bar.setTextVisible(False)
        _vbox.addWidget(_bar)
        self._test_progress_dlg.setFixedHeight(self._test_progress_dlg.sizeHint().height() + 10)

        self._test_worker = _CredTestWorker(creds, self)
        self._test_worker.result_ready.connect(self._on_test_done)
        self._test_worker.start()
        self._test_progress_dlg.exec()

    def _on_test_done(self, success, message: str):
        # Close the progress dialog before showing the result.
        try:
            if hasattr(self, "_test_progress_dlg") and self._test_progress_dlg is not None:
                self._test_progress_dlg.accept()
                self._test_progress_dlg = None
        except Exception:
            pass

        self._test_btn.setEnabled(True)
        self._test_btn.setText("Test Credentials")
        if success is True:
            app_signals.status_message.emit(f"Credentials OK — {message}")
            QMessageBox.information(self, "Credentials Valid", message)
        elif success is None:
            # Inconclusive — credentials likely valid but session state mismatch
            app_signals.status_message.emit("Credentials test inconclusive — likely valid")
            QMessageBox.information(self, "Credentials Appear Valid", message)
        else:
            app_signals.status_message.emit(f"Credentials failed — {message}")
            QMessageBox.warning(self, "Credentials Invalid", message)

    def _open_browser_login(self):
        """Open embedded browser login dialog and populate fields from captured credentials."""
        try:
            dlg = BrowserLoginDialog(self)
        except ImportError as e:
            QMessageBox.critical(
                self,
                "PyQt6-WebEngine Not Installed",
                "The browser login feature requires PyQt6-WebEngine.\n\n"
                f"Install it with:\n    pip install PyQt6-WebEngine\n\nError: {e}",
            )
            return
        dlg.credentials_ready.connect(self._apply_browser_credentials)
        dlg.exec()

    def _apply_browser_credentials(self, creds: dict):
        """Populate auth fields from credentials captured by BrowserLoginDialog."""
        mapping = {
            "sess": "sess",
            "auth_id": "auth_id",
            "auth_uid": "auth_uid",
            "user_agent": "user_agent",
            "x-bc": "x-bc",
        }
        imported = []
        for cred_key, field_key in mapping.items():
            value = creds.get(cred_key, "").strip()
            if value and field_key in self._inputs:
                self._inputs[field_key].setText(value)
                imported.append(cred_key)

        xbc_generated = creds.get("_xbc_generated", False)
        missing = [k for k in ("sess", "auth_id", "x-bc") if not creds.get(k)]
        msg_parts = [f"Imported: {', '.join(imported) if imported else 'nothing'}"]
        if xbc_generated:
            msg_parts.append(
                "x-bc could not be captured from the browser — a synthetic token was "
                "generated instead (same method ofscraper uses).\n"
                "Use 'Test Credentials' after saving to verify it works. If it fails, "
                "click 'DevTools' in the browser popup to open the Network inspector "
                "and copy x-bc manually from any API request header."
            )
        elif not missing:
            msg_parts.append("All required fields captured. Click Save to store credentials.")

        QMessageBox.information(self, "Browser Login", "\n\n".join(msg_parts))
        app_signals.status_message.emit(
            f"Browser login: imported {', '.join(imported)}"
        )

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
