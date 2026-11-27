"""A small MCP server (Model Context Protocol, Streamable HTTP with JSON
replies) that lets an MCP client such as Claude Code see and use this GUI
window, for testing.

Only the standard library: http.server answers on its own threads, and every
tool runs on the Qt main thread through bridge.py. It listens on 127.0.0.1
only, needs the token from the Developer panel (Authorization: Bearer ...),
and refuses requests a web page could make (an Origin header that isn't
localhost), so a site open in a browser can't drive it.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, pyqtSignal

from ofscraper.gui.devtools import settings as dev_settings
from ofscraper.gui.devtools.bridge import CallTimeout, MainThreadBridge
from ofscraper.gui.devtools.tools import TOOL_SPECS, GuiTools, ToolError

log = logging.getLogger("shared")

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
# a client counts as connected while it has asked something this recently
CONNECTED_SECONDS = 120
MAX_BODY = 1_000_000

INSTRUCTIONS = (
    "This server controls one OF-Scraper GUI window (one site) for testing. "
    "Start with gui_status and list_controls. Actions (click, set_text, select, "
    "navigate, ...) are queued in the GUI: confirm what they did with list_controls, "
    "read or wait_for. Like/Unlike and screenshots are refused unless the person "
    "allowed them in the Developer panel."
)


def _text(data) -> dict:
    if not isinstance(data, str):
        data = json.dumps(data, indent=1, ensure_ascii=False, default=str)
    return {"type": "text", "text": data}


class TestControl(QObject):
    """The server for one GUI window. Create it on the main thread."""

    status_changed = pyqtSignal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.bridge = MainThreadBridge(self)
        self.values = dev_settings.load()
        self.tools = GuiTools(window, lambda: self.values)
        self._server = None
        self._thread = None
        self.last_request = 0.0
        self.error = ""

    # --- running -------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._server is not None

    def connected(self) -> bool:
        return self.running and time.monotonic() - self.last_request < CONNECTED_SECONDS

    def state_text(self) -> str:
        if self.error:
            return f"Test control: error ({self.error})"
        if not self.running:
            return "Test control: off"
        return "Test control: connected" if self.connected() else "Test control: on"

    def start(self) -> bool:
        if self.running:
            return True
        self.error = ""
        port = int(self.values["port"])
        try:
            server = ThreadingHTTPServer((dev_settings.HOST, port), self._handler_class())
        except OSError as e:
            self.error = f"port {port} is in use" if e.errno in (48, 98, 10048) else str(e)
            log.warning(f"[Developer] test control server didn't start on port {port}: {e}")
            self.status_changed.emit(self.state_text())
            return False
        server.daemon_threads = True
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="gui-test-control", daemon=True)
        self._thread.start()
        log.warning(
            f"[Developer] test control (MCP) is on: http://{dev_settings.HOST}:{port}/mcp. "
            "A connected client can use this window."
        )
        self.status_changed.emit(self.state_text())
        return True

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception:
                pass
            log.info("[Developer] test control (MCP) is off")
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None
        self.status_changed.emit(self.state_text())

    def apply_settings(self, values: dict) -> None:
        """Save the panel's values; restart the server when the port or
        token changed, start or stop it when enabled changed."""
        restart = self.running and (
            values["port"] != self.values["port"] or values["token"] != self.values["token"]
        )
        self.values = dict(values)
        dev_settings.save(self.values)
        if restart or not values["enabled"]:
            self.stop()
        if values["enabled"]:
            self.start()
        self.status_changed.emit(self.state_text())

    # --- HTTP --------------------------------------------------------------------

    def _handler_class(self):
        control = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ofscraper-gui-test-control"
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # no stderr lines per request
                return

            def _reply(self, status, body=None, extra=None):
                data = b"" if body is None else json.dumps(body).encode("utf-8")
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in (extra or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if data:
                    self.wfile.write(data)

            def _allowed(self) -> bool:
                origin = self.headers.get("Origin")
                if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost", "::1"):
                    self._reply(403, {"error": "requests from web pages aren't accepted"})
                    return False
                if urlparse(self.path).path.rstrip("/") != "/mcp":
                    self._reply(404, {"error": "the MCP endpoint is /mcp"})
                    return False
                given = self.headers.get("Authorization", "")
                expected = f"Bearer {control.values.get('token', '')}"
                if not control.values.get("token") or not hmac.compare_digest(given, expected):
                    self._reply(401, {"error": "a valid token is needed (Developer panel)"},
                                {"WWW-Authenticate": "Bearer"})
                    return False
                return True

            def do_GET(self):
                # no server-initiated stream
                if self._allowed():
                    self._reply(405, None, {"Allow": "POST, DELETE"})

            def do_DELETE(self):
                if self._allowed():
                    self._reply(200)

            def do_POST(self):
                if not self._allowed():
                    return
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                if length <= 0 or length > MAX_BODY:
                    self._reply(400, {"error": "a JSON-RPC body is needed"})
                    return
                try:
                    message = json.loads(self.rfile.read(length))
                except ValueError:
                    self._reply(400, {"jsonrpc": "2.0", "id": None,
                                      "error": {"code": -32700, "message": "Parse error"}})
                    return
                control.last_request = time.monotonic()
                batch = isinstance(message, list)
                replies = [r for r in (control.handle(m) for m in (message if batch else [message])) if r]
                if not replies:
                    self._reply(202)
                    return
                extra = {"Mcp-Session-Id": "ofscraper-gui"}
                self._reply(200, replies if batch else replies[0], extra)

        return Handler

    # --- JSON-RPC ---------------------------------------------------------------

    def handle(self, message):
        """The reply to one JSON-RPC message, or None for a notification."""
        if not isinstance(message, dict):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        method = message.get("method")
        msg_id = message.get("id")
        if msg_id is None:
            return None  # a notification (or a reply): nothing to say
        params = message.get("params") or {}
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                result = {
                    "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": f"ofscraper-gui-{dev_settings.site()}", "version": _patch_id()},
                    "instructions": INSTRUCTIONS,
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOL_SPECS}
            elif method == "tools/call":
                result = self.call_tool(params.get("name"), params.get("arguments") or {})
            else:
                return {"jsonrpc": "2.0", "id": msg_id,
                        "error": {"code": -32601, "message": f"Method not found: {method}"}}
        except Exception as e:
            log.debug(f"[Developer] MCP {method} failed: {e!r}")
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def call_tool(self, name, args):
        if not isinstance(args, dict):
            args = {}
        # the tool and which arguments, never their values (text can be a password)
        log.info(f"[Developer] MCP {name}({', '.join(sorted(args))})")
        try:
            if name == "wait_for":
                return {"content": [_text(self._wait_for(**_pick(args, "text", "gone", "idle", "timeout")))]}
            method = {
                "gui_status": self.tools.status,
                "list_controls": self.tools.list_controls,
                "read": self.tools.read,
                "read_log": self.tools.read_log,
                "click": self.tools.click,
                "set_checked": self.tools.set_checked,
                "set_text": self.tools.set_text,
                "select": self.tools.select,
                "navigate": self.tools.navigate,
                "press_key": self.tools.press_key,
                "screenshot": self.tools.screenshot,
            }.get(name)
            if method is None:
                raise ToolError(f"unknown tool {name!r}")
            spec = next(s for s in TOOL_SPECS if s["name"] == name)
            kwargs = _pick(args, *spec["inputSchema"].get("properties", {}))
            result = self.bridge.run(lambda: method(**kwargs))
            if name == "screenshot":
                return {"content": [
                    {"type": "image", "data": result["image"], "mimeType": "image/png"},
                    _text(f"{result['title']} ({result['size']})"),
                ]}
            if name in ("click", "set_checked", "set_text", "select", "navigate", "press_key"):
                time.sleep(0.15)  # let the queued action run before the next call
            return {"content": [_text(result)]}
        except (ToolError, CallTimeout, TypeError, ValueError) as e:
            return {"content": [_text(str(e))], "isError": True}

    def _wait_for(self, text=None, gone=None, idle=False, timeout=30):
        try:
            timeout = max(0.5, min(float(timeout or 30), 1800.0))
        except (TypeError, ValueError):
            timeout = 30.0
        if not (text or gone or idle):
            raise ToolError("give text, gone or idle")
        end = time.monotonic() + timeout
        while True:
            def check():
                status = self.tools.status() if idle else {}
                ok = True
                if text and not self.tools.page_text(text):
                    ok = False
                if gone and self.tools.page_text(gone):
                    ok = False
                if idle and (status.get("scraping") or status.get("loading_models")):
                    ok = False
                return ok
            if self.bridge.run(check):
                return {"done": True, "waited": round(timeout - (end - time.monotonic()), 1)}
            if time.monotonic() >= end:
                return {"done": False, "timed_out_after": timeout}
            time.sleep(0.4)


def _pick(args: dict, *names) -> dict:
    return {k: args[k] for k in names if k in args and args[k] is not None}


def _patch_id() -> str:
    try:
        from ofscraper.gui.patch_version import PATCH_ID

        return PATCH_ID
    except Exception:
        return "unknown"
