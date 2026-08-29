#Enabled 1 / Disabled 0 - Set this plugin as enabled - Default value 1
plugin_enabled = 1

import os
import sys
import json
import time
import base64
import shutil
import datetime
import logging
import subprocess
import threading
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ofscraper.plugins.base import BasePlugin
from ofscraper.utils.paths.common import get_save_location, get_config_path

try:
    from .live_probe import (
        classify_delivery,
        redact_json,
        redact_url,
        summarize_requests,
        url_is_interesting,
    )
except ImportError:
    from live_probe import (  # type: ignore
        classify_delivery,
        redact_json,
        redact_url,
        summarize_requests,
        url_is_interesting,
    )


# ---------------------------------------------------------------------------
# Install-method detection (mirrors the patch file logic)
# ---------------------------------------------------------------------------

def _detect_ofscraper_install_method() -> str:
    """Return 'uv', 'pipx', or 'pip' based on how ofscraper is installed."""
    import platform
    home = Path.home()
    is_win = platform.system() == "Windows"

    # UV: check for ofscraper in the uv tools directory
    uv_tool_env = os.environ.get("UV_TOOL_DIR")
    if uv_tool_env:
        uv_cands = [Path(uv_tool_env)]
    elif is_win:
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        uv_cands = [Path(appdata) / "uv" / "data" / "tools",
                    Path(appdata) / "uv" / "tools"]
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
        uv_cands = [Path(xdg) / "uv" / "tools"]
    for d in uv_cands:
        if (d / "ofscraper").is_dir():
            return "uv"

    # pipx: check for ofscraper venv in the pipx home directory
    pipx_env = os.environ.get("PIPX_HOME")
    if pipx_env:
        pipx_cands = [Path(pipx_env)]
    elif is_win:
        pipx_cands = [home / "pipx",
                      home / "AppData" / "Local" / "pipx",
                      home / ".local" / "pipx"]
    else:
        pipx_cands = [home / ".local" / "share" / "pipx",
                      home / ".local" / "pipx"]
    for d in pipx_cands:
        if (d / "venvs" / "ofscraper").is_dir():
            return "pipx"

    # Fallback: inspect the Python executable path for clues
    exe = str(sys.executable).replace("\\", "/").lower()
    if "uv" in exe and "tools" in exe:
        return "uv"
    if "pipx" in exe:
        return "pipx"

    return "pip"


def _chromium_channel_for_host() -> str | None:
    """Prefer a real installed Chrome/Edge channel over bundled Chromium.

    Bundled Playwright Chromium is often stuck in OnlyFans reCAPTCHA loops.
    ``channel`` uses the system browser binary when Playwright can find it.
    """
    import platform
    from shutil import which

    system = platform.system()
    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        pf = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
        pf86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        candidates = [
            ("chrome", local / "Google" / "Chrome" / "Application" / "chrome.exe"),
            ("chrome", pf / "Google" / "Chrome" / "Application" / "chrome.exe"),
            ("chrome", pf86 / "Google" / "Chrome" / "Application" / "chrome.exe"),
            ("msedge", local / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            ("msedge", pf / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            ("msedge", pf86 / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
        ]
        for channel, path in candidates:
            if path.is_file():
                return channel
        if which("chrome") or which("google-chrome"):
            return "chrome"
        if which("msedge"):
            return "msedge"
    elif system == "Darwin":
        if Path("/Applications/Google Chrome.app").exists():
            return "chrome"
        if Path("/Applications/Microsoft Edge.app").exists():
            return "msedge"
    else:
        for name, channel in (
            ("google-chrome", "chrome"),
            ("google-chrome-stable", "chrome"),
            ("chromium-browser", "chromium"),
            ("chromium", "chromium"),
            ("microsoft-edge", "msedge"),
        ):
            if which(name):
                return channel
    return None


def _playwright_user_agent(auth_ua: str | None) -> str | None:
    """Only pass auth UA into Chromium when it looks like a Chromium UA.

    Forcing a Firefox/Zen UA onto Chrome/Chromium fingerprints the session and
    commonly triggers OnlyFans login / captcha failures.
    """
    ua = (auth_ua or "").strip()
    if not ua:
        return None
    lower = ua.lower()
    if "chrome/" in lower or "chromium/" in lower or "edg/" in lower:
        return ua
    return None


def _apply_chromium_launch_kwargs(kwargs: dict, user_agent: str | None) -> dict:
    """Mutate launch kwargs: real Chrome channel + Chromium-compatible UA only."""
    channel = _chromium_channel_for_host()
    if channel:
        kwargs["channel"] = channel
    ua = _playwright_user_agent(user_agent)
    if ua:
        kwargs["user_agent"] = ua
    return kwargs




def _url_is_live_stream(url: str, username: str) -> bool:
    """True only for /{user}/live — not login redirects that merely mention live."""
    from urllib.parse import urlparse, parse_qs, unquote

    try:
        u = urlparse(url or "")
        if "return_to" in parse_qs(u.query or ""):
            return False
        path = unquote((u.path or "")).rstrip("/").lower()
        user = (username or "").strip().lower()
        if not user:
            return path.endswith("/live")
        return path == f"/{user}/live"
    except Exception:
        return False


def _hide_capture_window(context, page) -> bool:
    """Move the real Chrome window off-screen (true headless drops OF sessions)."""
    try:
        client = context.new_cdp_session(page)
        info = client.send("Browser.getWindowForTarget")
        window_id = info.get("windowId")
        if window_id is None:
            return False
        client.send(
            "Browser.setWindowBounds",
            {
                "windowId": window_id,
                "bounds": {
                    "left": -20000,
                    "top": -20000,
                    "width": 1280,
                    "height": 720,
                    "windowState": "normal",
                },
            },
        )
        return True
    except Exception:
        return False



def _find_uv_binary() -> str | None:
    """Return the path to the uv executable, or None if not found."""
    import platform
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    is_win = platform.system() == "Windows"
    if is_win:
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        candidates = [
            home / ".local" / "bin" / "uv.exe",
            home / ".cargo" / "bin" / "uv.exe",
            Path(appdata) / "uv" / "bin" / "uv.exe",
        ]
    else:
        candidates = [
            home / ".local" / "bin" / "uv",
            home / ".cargo" / "bin" / "uv",
        ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _playwright_driver_node(pkg_root: Path) -> Path:
    """Platform-native Playwright driver binary path under a package root."""
    if sys.platform == "win32":
        return pkg_root / "driver" / "node.exe"
    return pkg_root / "driver" / "node"


def _playwright_wrong_platform_node(pkg_root: Path) -> Path | None:
    """Return the opposite-platform driver if present (common with Docker bind mounts)."""
    if sys.platform == "win32":
        other = pkg_root / "driver" / "node"
    else:
        other = pkg_root / "driver" / "node.exe"
    return other if other.is_file() else None


def _purge_playwright_modules() -> None:
    """Drop cached playwright imports so a repaired install can be reloaded."""
    doomed = [k for k in list(sys.modules) if k == "playwright" or k.startswith("playwright.")]
    for k in doomed:
        sys.modules.pop(k, None)


def _remove_path_entry(path: Path) -> None:
    """Remove *path* from ``sys.path`` (resolved comparison)."""
    try:
        target = path.resolve()
    except OSError:
        target = path
    kept = []
    for entry in sys.path:
        try:
            if Path(entry).resolve() == target:
                continue
        except OSError:
            if entry == str(path):
                continue
        kept.append(entry)
    sys.path[:] = kept


def _inspect_playwright_install() -> tuple[bool, str, Path | None]:
    """Return ``(usable, detail, package_root)`` for the currently importable playwright."""
    try:
        import playwright  # noqa: F401
    except ImportError as e:
        return False, f"not installed ({e})", None
    root = Path(playwright.__file__).resolve().parent
    node = _playwright_driver_node(root)
    if node.is_file():
        if sys.platform != "win32":
            try:
                mode = node.stat().st_mode
                if not os.access(node, os.X_OK):
                    node.chmod(mode | 0o111)
            except OSError:
                pass
        return True, str(root), root
    wrong = _playwright_wrong_platform_node(root)
    if wrong is not None:
        return (
            False,
            f"wrong-platform driver at {wrong} (need {node.name} on {sys.platform})",
            root,
        )
    return False, f"missing driver binary {node}", root


def _wipe_deps_playwright(deps_path: Path, log_fn=None) -> None:
    """Remove a pip --target playwright tree (often Windows binaries on a Linux mount)."""
    pw = deps_path / "playwright"
    if not pw.exists():
        return
    msg = f"[Playwright] Removing incompatible/broken deps install: {pw}"
    if log_fn:
        log_fn(msg)
    shutil.rmtree(pw, ignore_errors=True)
    # Leftover dist-info confuses some importers
    for meta in deps_path.glob("playwright-*.dist-info"):
        shutil.rmtree(meta, ignore_errors=True)


def _browsers_path_for_plugin() -> Path:
    """Prefer pre-set PLAYWRIGHT_BROWSERS_PATH (Docker image), else config folder."""
    env = (os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "").strip()
    if env:
        path = Path(env)
    else:
        path = get_config_path().parent / "playwright_browsers"
    path.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(path)
    return path


# ---------------------------------------------------------------------------

def _patch_webm_duration(path: Path, duration_ms: float, log_fn=None) -> bool:
    """
    Write a Duration element into a MediaRecorder WebM file.

    Chrome's MediaRecorder omits the Duration field entirely from the Segment Info
    block, causing VLC and other players to show 00:00 as the total length.

    Strategy:
      1. If Duration (0x4489 0x88) already exists and is zero → overwrite in-place.
      2. Otherwise, insert an 11-byte Duration element at the end of the Segment
         Info block by rebuilding the affected header bytes and writing a new file.

    WebM default TimestampScale = 1,000,000 ns/tick → 1 tick = 1 ms, so the
    Duration field value is duration_ms (a float64, big-endian).
    """
    import struct

    if duration_ms <= 0:
        if log_fn:
            log_fn("[Capture] Duration unknown — skipping EBML patch.")
        return False

    def _read_vint(data, offset):
        """Parse EBML variable-length integer. Returns (value, byte_width)."""
        b = data[offset]
        for width, mask in enumerate([0x80, 0x40, 0x20, 0x10, 0x08], start=1):
            if b & mask:
                val = b & (mask - 1)
                for i in range(1, width):
                    val = (val << 8) | data[offset + i]
                return val, width
        return None, 0

    def _encode_vint(value):
        """Encode value as the smallest valid EBML VINT (avoids reserved all-ones values)."""
        if value < 0x7F:
            return bytes([value | 0x80])
        elif value < 0x3FFF:
            return bytes([(value >> 8) | 0x40, value & 0xFF])
        elif value < 0x1FFFFF:
            return bytes([(value >> 16) | 0x20, (value >> 8) & 0xFF, value & 0xFF])
        else:
            return bytes([(value >> 24) | 0x10, (value >> 16) & 0xFF,
                          (value >> 8) & 0xFF, value & 0xFF])

    # Duration EBML element: ID=0x4489 (2 bytes) + size=0x88 (8-byte payload) + float64
    DURATION_ELEM = b'\x44\x89\x88' + struct.pack('>d', duration_ms)

    try:
        file_bytes = path.read_bytes()

        # --- Pass 1: Duration present but zero → overwrite in-place (no file rewrite) ---
        inplace_pos = file_bytes.find(b'\x44\x89\x88', 0, 8192)
        if inplace_pos != -1:
            patched = bytearray(file_bytes)
            struct.pack_into('>d', patched, inplace_pos + 3, duration_ms)
            path.write_bytes(bytes(patched))
            if log_fn:
                log_fn(f"[Capture] Duration metadata written ({duration_ms/1000:.1f}s).")
            return True

        # --- Pass 2: Duration absent → insert into Segment Info block ---
        SI_ID = b'\x15\x49\xA9\x66'
        si_pos = file_bytes.find(SI_ID, 0, 8192)
        if si_pos == -1:
            if log_fn:
                log_fn("[Capture] Segment Info not found — cannot add Duration.")
            return False

        size_offset = si_pos + 4
        seg_size, size_len = _read_vint(file_bytes, size_offset)
        if size_len == 0 or seg_size is None:
            if log_fn:
                log_fn("[Capture] Cannot parse Segment Info size — skipping.")
            return False

        # Reject unknown-size (all data-bits = 1 for that width)
        unknown_vals = {w: (1 << (7 * w)) - 1 for w in range(1, 6)}
        if seg_size == unknown_vals.get(size_len):
            if log_fn:
                log_fn("[Capture] Segment Info has unknown size — cannot patch.")
            return False

        content_start = size_offset + size_len
        content_end = content_start + seg_size

        # Already has a Duration (4-byte float variant or other encoding)?
        if b'\x44\x89' in file_bytes[content_start:content_end]:
            if log_fn:
                log_fn("[Capture] Duration element already present.")
            return True

        # Build patched file: everything up to SegInfo size field, then new size,
        # then original content, then Duration element, then rest of file unchanged.
        new_seg_size = seg_size + len(DURATION_ELEM)
        new_data = (
            file_bytes[:si_pos + 4]                  # EBML header + SegInfo element ID
            + _encode_vint(new_seg_size)              # updated Segment Info size
            + file_bytes[content_start:content_end]  # original Segment Info content
            + DURATION_ELEM                           # new Duration element
            + file_bytes[content_end:]               # Tracks + Clusters unchanged
        )

        tmp_path = path.with_name(path.stem + ".tmp.webm")
        try:
            tmp_path.write_bytes(new_data)
            path.unlink()
            tmp_path.rename(path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

        if log_fn:
            log_fn(f"[Capture] Duration metadata written ({duration_ms/1000:.1f}s).")
        return True

    except Exception as e:
        if log_fn:
            log_fn(f"[Capture] EBML patch failed: {e}")
        return False


def _read_webm_last_cluster_ms(file_bytes: bytes) -> float:
    """
    Scan all WebM Cluster timestamps and return the last one in milliseconds.

    Chrome MediaRecorder writes a new Cluster every keyframe (~2-5 seconds for VP8).
    The last cluster's timestamp + 2000ms gives a close estimate of the true content
    duration — much more accurate than wall-clock time.

    Returns 0.0 if no clusters with readable timestamps are found.
    """
    CLUSTER_ID = b'\x1F\x43\xB6\x75'
    max_ts = 0
    pos = 0
    while True:
        pos = file_bytes.find(CLUSTER_ID, pos)
        if pos == -1:
            break
        # The Cluster Timestamp element (EBML ID 0xE7) is always the first element
        # inside a Cluster. Chrome uses an 8-byte unknown-size VINT for cluster size
        # (01 FF FF FF FF FF FF FF), placing E7 at pos+12. We search pos+5..pos+22
        # to also handle clusters with explicit sizes (1-4 byte VINTs).
        window_start = pos + 5
        window_end = min(pos + 22, len(file_bytes))
        e7_idx = file_bytes.find(b'\xe7', window_start, window_end)
        if e7_idx != -1:
            size_b = file_bytes[e7_idx + 1]
            if size_b & 0x80:  # 1-byte VINT
                ts_size = size_b & 0x7F
                ts_bytes = file_bytes[e7_idx + 2: e7_idx + 2 + ts_size]
                ts_val = int.from_bytes(ts_bytes, 'big')
                if 0 < ts_val < 86_400_000:  # sanity: > 0 and < 24 hours
                    max_ts = max(max_ts, ts_val)
        pos += 4
    return float(max_ts)


class LiveMonitorWorker(QThread):
    """Background worker thread that polls OnlyFans for live creators."""
    log_msg = pyqtSignal(str)
    status_updated = pyqtSignal(dict)
    auth_error = pyqtSignal()

    def __init__(self, plugin, interval, save_location):
        super().__init__()
        self.plugin = plugin
        self.interval = interval
        self.save_location = save_location
        self.running = True

    def run(self):
        self.log_msg.emit("[System] Monitoring worker thread active.")
        
        while self.running:
            try:
                # 1. Fetch subscribed models
                self.log_msg.emit("[Monitor] Polling subscriptions status...")
                models = self.fetch_models()
                
                # 2. Build current status dict
                model_statuses = {}
                for m in models:
                    if not m.active:
                        continue
                    
                    username = m.name
                    is_live = m.model.get("hasStream", False)
                    expired_date = m.expired_string or "Active"
                    
                    status = "Offline"
                    if username in self.plugin.active_recordings:
                        status = "Recording 🔴"
                    elif username in self.plugin._connecting_recordings:
                        if username in getattr(self.plugin, "_probe_sessions", set()):
                            status = "Probing 🔬"
                        else:
                            status = "Connecting 🟡"
                    elif is_live:
                        status = "Live 🟢"

                    model_statuses[username] = {
                        "username": username,
                        "subscription": expired_date,
                        "status": status,
                        "is_live": is_live
                    }

                    # 3. If live and not already recording or connecting, spawn a session
                    already_active = (
                        username in self.plugin.active_recordings
                        or username in self.plugin._connecting_recordings
                    )
                    if is_live and not already_active:
                        if self.plugin.is_ignored(username):
                            self.log_msg.emit(f"[Monitor] {username} is live but ignored — skipping.")
                        else:
                            cool_until = float(
                                getattr(self.plugin, "_capture_cooldown", {}).get(
                                    username, 0
                                )
                                or 0
                            )
                            now = time.time()
                            if cool_until > now:
                                remaining = int(cool_until - now)
                                self.log_msg.emit(
                                    f"[Monitor] {username} live but on capture cooldown "
                                    f"({remaining}s left) — skip."
                                )
                            elif getattr(self.plugin, "probe_mode", False):
                                self.log_msg.emit(
                                    f"[Live] {username} is live! Starting diagnostics probe "
                                    "(no WebM recording)..."
                                )
                                self.plugin.start_probe(username, self.save_location)
                                model_statuses[username]["status"] = "Probing 🔬"
                            else:
                                self.log_msg.emit(f"[Live] {username} is live! Starting auto-capture...")
                                self.plugin.start_recording(username, self.save_location)
                                model_statuses[username]["status"] = "Connecting 🟡"
                
                # Emit update to refresh GUI table
                self.status_updated.emit(model_statuses)
                
            except Exception as e:
                err_msg = str(e)
                if (
                    "Auth fields not configured" in err_msg
                    or "Authentication validation failed" in err_msg
                    or "400" in err_msg
                    or "401" in err_msg
                    or "403" in err_msg
                    or "bad request" in err_msg.lower()
                    or "wrong user" in err_msg.lower()
                ):
                    active = list(self.plugin.active_recordings.keys())
                    connecting = list(self.plugin._connecting_recordings.keys())
                    self.log_msg.emit(f"\n[Error] {err_msg}")
                    if active or connecting:
                        self.log_msg.emit(
                            "[Monitor] API auth failed — pausing auto-capture polls, "
                            "but leaving in-progress capture(s) running: "
                            + ", ".join(active + connecting)
                        )
                    self.auth_error.emit()
                    break
                else:
                    self.log_msg.emit(f"[Error] Error in monitor loop: {e}")
                    self.log_msg.emit(traceback.format_exc())
                
            # Wait for next poll interval
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

        self.log_msg.emit("[System] Monitoring worker thread terminated.")

    def fetch_models(self):
        """Fetch subscriptions via the same API path as Areas / Select Models.

        Uses a Windows ``SelectorEventLoop`` (avoids Proactor under Qt) and mutes
        Rich Live activity updates so the poll works from this QThread.
        """
        import asyncio
        import sys
        from ofscraper.data.models.utils.retriver import get_models
        from ofscraper.utils.auth.file import read_auth
        from ofscraper.utils.live import updater as live_updater

        def _of_error_detail(exc: Exception) -> str:
            detail = ""
            resp = getattr(exc, "response", None)
            if resp is None:
                return detail
            try:
                body = resp.json()
                err = body.get("error", {}) if isinstance(body, dict) else {}
                if isinstance(err, dict):
                    msg = err.get("message") or ""
                    code = err.get("code")
                    if msg or code is not None:
                        detail = f" OnlyFans: {msg} (code {code})".rstrip()
                if not detail:
                    text = getattr(resp, "text", "") or ""
                    if text:
                        detail = f" Body: {text[:240]}"
            except Exception:
                try:
                    text = getattr(resp, "text", "") or ""
                    if text:
                        detail = f" Body: {text[:240]}"
                except Exception:
                    pass
            return detail

        try:
            auth_data = read_auth()
            required = ["sess", "auth_id", "user_agent", "x-bc"]
            missing = [k for k in required if not auth_data.get(k)]
            if missing:
                raise Exception(
                    f"Auth fields not configured: {', '.join(missing)}. "
                    "Please fill in your OnlyFans credentials in the 'Authentication' tab."
                )
        except Exception as e:
            raise Exception(f"Authentication validation failed: {e}")

        # Same prep as Authentication → Test: drop stale signing rules / session /
        # /me cache so this QThread does not reuse a bad in-memory state.
        try:
            import ofscraper.utils.auth.request as auth_req

            if hasattr(auth_req, "invalidate_auth_cache"):
                auth_req.invalidate_auth_cache()
            else:
                auth_req.curr_auth = None
                auth_req.last_check = None
        except Exception:
            pass
        try:
            import ofscraper.utils.profiles.data as profile_data

            profile_data.currentData = None
            profile_data.currentProfile = None
        except Exception:
            pass
        try:
            import ofscraper.managers.manager as mgr

            if hasattr(mgr, "Manager") and mgr.Manager is not None:
                mgr.Manager.session = None
        except Exception:
            pass

        # Probe /users/me first so we can surface OnlyFans' real error body.
        try:
            import ofscraper.data.api.me as me_api

            user_info = me_api.scrape_user()
            if not user_info or not user_info.get("isAuth"):
                raise Exception(
                    "OnlyFans returned unauthorized for this session "
                    "(isAuth=false). Re-import cookies from a logged-in tab."
                )
        except Exception as e:
            detail = _of_error_detail(e)
            msg = str(e)
            lower = msg.lower()
            of_wrong_user = "wrong user" in lower or "code 301" in lower
            hint = ""
            if of_wrong_user or "400" in msg or "401" in msg or "403" in msg:
                hint = (
                    " Re-import cookies from a logged-in OnlyFans tab "
                    "(include auth_uid_ if 2FA is enabled)."
                )
            raise Exception(f"{msg}{detail}.{hint}".replace("..", ".").strip())

        restores = []
        try:
            for attr in ("update_task", "update_activity", "update_activity_task"):
                obj = getattr(live_updater, "activity", None)
                if obj is None or not hasattr(obj, attr):
                    continue
                old = getattr(obj, attr)
                setattr(obj, attr, lambda *a, **k: None)
                restores.append((obj, attr, old))
        except Exception:
            pass

        try:
            from ofscraper.gui.utils.workflow import _install_gui_live_stubs

            _install_gui_live_stubs()
        except Exception:
            pass

        async def _do_fetch():
            return await get_models(all_main_models=False)

        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_do_fetch())
        finally:
            try:
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                loop.close()
            except Exception:
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            for obj, attr, old in restores:
                try:
                    setattr(obj, attr, old)
                except Exception:
                    pass
            try:
                from ofscraper.gui.utils.workflow import _uninstall_gui_live_stubs

                _uninstall_gui_live_stubs()
            except Exception:
                pass



def _popen_logged(cmd, emit, env=None, timeout=None) -> int:
    """Run *cmd*, stream lines to *emit*, return exit code (Windows-safe unbuffered)."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["PYTHONUNBUFFERED"] = "1"
    run_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    emit(f"[Playwright] Running: {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=run_env,
            bufsize=1,
        )
    except Exception as e:
        emit(f"[Playwright] Failed to start process: {e}")
        return 1
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            emit(f"  {line.rstrip()}")
        return int(proc.wait(timeout=timeout) if timeout else proc.wait())
    except subprocess.TimeoutExpired:
        emit(f"[Playwright] Timed out after {timeout}s — killing process.")
        try:
            proc.kill()
        except Exception:
            pass
        return 1
    except Exception as e:
        emit(f"[Playwright] Process error: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return 1


class ChromiumInstallWorker(QThread):
    """Background worker that runs playwright install chromium."""
    log_msg = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, browsers_path, deps_path):
        super().__init__()
        self.browsers_path = browsers_path
        self.deps_path = Path(deps_path)

    def _emit(self, msg: str) -> None:
        self.log_msg.emit(msg)

    def _pip_install_venv(self) -> bool:
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "playwright>=1.40.0",
        ]
        self._emit("[Playwright] Installing playwright package into active Python (may take a few minutes)...")
        code = _popen_logged(cmd, self._emit, timeout=900)
        if code == 0:
            self._emit("[Playwright] playwright installed into the active Python environment.")
            return True
        self._emit(f"[Playwright] pip install failed (exit {code}).")
        return False

    def _pip_install_target(self) -> bool:
        self.deps_path.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "pip",
            "install",
            "--upgrade",
            "playwright>=1.40.0",
            "--target",
            str(self.deps_path),
        ]
        self._emit("[Playwright] Installing playwright via pip --target (may take a few minutes)...")
        code = _popen_logged(cmd, self._emit, timeout=900)
        if code == 0:
            self._emit("[Playwright] playwright installed via pip --target.")
            return True
        self._emit(f"[Playwright] pip --target failed (exit {code}).")
        return False

    def _ensure_playwright_package(self) -> bool:
        """Make a *native* playwright package importable (venv preferred over deps)."""
        # Never prefer a host-mounted deps tree until the venv has been checked.
        _remove_path_entry(self.deps_path)
        _purge_playwright_modules()

        ok, detail, root = _inspect_playwright_install()
        if ok:
            self._emit(f"[Playwright] Using existing package: {detail}")
            return True

        if root is not None:
            self._emit(f"[Playwright] Existing package unusable: {detail}")
            try:
                if self.deps_path.resolve() in root.resolve().parents or root.resolve().is_relative_to(
                    self.deps_path.resolve()
                ):
                    _wipe_deps_playwright(self.deps_path, self._emit)
            except Exception:
                _wipe_deps_playwright(self.deps_path, self._emit)
            _purge_playwright_modules()

        # Also wipe deps when present but not yet imported (Windows mount into Linux).
        deps_node = _playwright_driver_node(self.deps_path / "playwright")
        deps_wrong = _playwright_wrong_platform_node(self.deps_path / "playwright")
        if (self.deps_path / "playwright").exists() and (
            not deps_node.is_file() or deps_wrong is not None
        ):
            _wipe_deps_playwright(self.deps_path, self._emit)

        install_method = _detect_ofscraper_install_method()
        self._emit(f"[Playwright] Detected install method: {install_method}")
        installed = False

        if install_method == "uv":
            uv_bin = _find_uv_binary()
            if uv_bin:
                cmd = [
                    uv_bin,
                    "pip",
                    "install",
                    "playwright>=1.40.0",
                    "--python",
                    sys.executable,
                ]
                self._emit(f"[Playwright] Running: {' '.join(cmd)}")
                try:
                    proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                    )
                    for line in proc.stdout:
                        self._emit(f"  {line.rstrip()}")
                    proc.wait()
                    if proc.returncode == 0:
                        installed = True
                        self._emit("[Playwright] playwright installed via uv pip.")
                    else:
                        self._emit(
                            f"[Playwright] uv pip failed (exit {proc.returncode}), "
                            "trying pip..."
                        )
                except Exception as e:
                    self._emit(f"[Playwright] uv pip error: {e}, trying pip...")
            else:
                self._emit("[Playwright] uv binary not found, trying pip...")

        if not installed:
            # Docker / pipx / plain venv: install into the active interpreter first.
            installed = self._pip_install_venv()

        if not installed:
            # Last resort isolated target (must match container OS — never reuse host deps).
            installed = self._pip_install_target()

        if not installed:
            self._emit(
                "[Error] Could not install playwright automatically. "
                "Try: pip install playwright  (inside the container/venv), "
                "then click Install Chromium again. Also delete "
                f"{self.deps_path / 'playwright'} if it came from another OS."
            )
            return False

        _purge_playwright_modules()
        # Prefer venv; only add deps path when the package lives there.
        ok, detail, root = _inspect_playwright_install()
        if ok:
            self._emit(f"[Playwright] Package ready: {detail}")
            return True

        if str(self.deps_path) not in sys.path:
            sys.path.insert(0, str(self.deps_path))
        _purge_playwright_modules()
        ok, detail, root = _inspect_playwright_install()
        if ok:
            self._emit(f"[Playwright] Package ready from deps: {detail}")
            return True

        self._emit(f"[Error] playwright still unusable after install: {detail}")
        return False

    def run(self):
        self._emit("[Playwright] Initiating Chromium installation...")
        if not self._ensure_playwright_package():
            self.finished.emit(False)
            return

        ok, detail, root = _inspect_playwright_install()
        use_deps = False
        if root is not None:
            try:
                use_deps = self.deps_path.resolve() in root.resolve().parents or (
                    root.resolve() == (self.deps_path / "playwright").resolve()
                )
            except OSError:
                use_deps = False

        env = os.environ.copy()
        env["PLAYWRIGHT_BROWSERS_PATH"] = str(self.browsers_path)
        if use_deps:
            if "PYTHONPATH" in env:
                env["PYTHONPATH"] = str(self.deps_path) + os.pathsep + env["PYTHONPATH"]
            else:
                env["PYTHONPATH"] = str(self.deps_path)
        else:
            # Avoid a host-mounted deps tree shadowing the venv playwright module.
            pp = env.get("PYTHONPATH", "")
            if pp:
                parts = [
                    p
                    for p in pp.split(os.pathsep)
                    if p and Path(p).resolve() != self.deps_path.resolve()
                ]
                if parts:
                    env["PYTHONPATH"] = os.pathsep.join(parts)
                else:
                    env.pop("PYTHONPATH", None)

        if sys.platform.startswith("linux"):
            deps_cmd = [sys.executable, "-m", "playwright", "install-deps", "chromium"]
            self._emit(f"[Playwright] Ensuring OS libs: {' '.join(deps_cmd)}")
            try:
                proc = subprocess.Popen(
                    deps_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    env=env,
                )
                for line in proc.stdout:
                    self._emit(f"  {line.rstrip()}")
                proc.wait()
                if proc.returncode != 0:
                    self._emit(
                        f"[Playwright] install-deps exited {proc.returncode} "
                        "(continuing; image may already have the libraries)."
                    )
            except Exception as e:
                self._emit(f"[Playwright] install-deps skipped: {e}")

        # If system Chrome/Edge works, skip the large Chromium download.
        channel = _chromium_channel_for_host()
        if channel:
            self._emit(
                f"[Playwright] System browser channel={channel} detected — "
                "verifying launch (bundled Chromium download not required)..."
            )
            try:
                _purge_playwright_modules()
                from playwright.sync_api import sync_playwright

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, channel=channel)
                    browser.close()
                self._emit(f"[Playwright] System {channel} is ready for Live Monitor.")
                self.finished.emit(True)
                return
            except Exception as e:
                self._emit(
                    f"[Playwright] System {channel} launch failed ({e}); "
                    "falling back to bundled Chromium download..."
                )

        cmd = [sys.executable, "-u", "-m", "playwright", "install", "chromium"]
        self._emit(f"[Playwright] Target folder: {self.browsers_path}")
        self._emit("[Playwright] Downloading Chromium (this can take several minutes)...")
        code = _popen_logged(cmd, self._emit, env=env, timeout=1800)
        if code == 0:
            self._emit("[Playwright] Chromium browser install finished.")
            self.finished.emit(True)
        else:
            self._emit(f"[Error] playwright install chromium failed (exit {code}).")
            self.finished.emit(False)



class ChromiumCheckWorker(QThread):
    """Run Playwright Chromium probe off the GUI thread."""
    finished = pyqtSignal(bool)

    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

    def run(self):
        ok = False
        try:
            ok = bool(self._plugin.check_chromium_installed())
        except Exception:
            ok = False
        self.finished.emit(ok)


class _LogBridge(QObject):
    """Thread-safe log fan-out that outlives the monitor worker.

    Recording threads may keep logging after stop_monitor clears self.worker.
    This bridge stays connected to the GUI for the plugin lifetime.
    """
    log_msg = pyqtSignal(str)


class Plugin(BasePlugin):
    """Plugin implementing the OnlyFans Live Monitor & Capture."""

    def __init__(self, metadata: dict, plugin_dir: str):
        super().__init__(metadata, plugin_dir)
        self.plugin_dir = Path(plugin_dir)
        self.gui = None
        self.worker = None
        
        # username -> (thread, stop_event)  [browser launching / joining stream]
        self._connecting_recordings = {}
        # username -> (thread, stop_event, start_time)  [MediaRecorder actually running]
        self.active_recordings = {}
        # usernames currently in diagnostics-probe sessions (subset of connecting)
        self._probe_sessions: set = set()

        self.ignored_creators: set = set()
        self._load_ignored()
        # username -> unix cooldown-until (avoid poll spam after failed starts)
        self._capture_cooldown: dict = {}
        # Recording phase: True = no visible Chrome window (default).
        self.headless_capture = True
        # When True, auto-capture runs a network/API probe instead of WebM recording.
        self.probe_mode = False
        # When True, show probe / API-dump controls in the GUI (off by default).
        self.show_diagnostics = False
        self._load_settings()

        self.log = logging.getLogger("ofscraper_plugins")
        self._log_bridge = _LogBridge()

    def on_load(self):
        self.log.info("Live Stream Monitor loaded.")

    def _emit_log(self, msg: str) -> None:
        """Emit a console line via the durable log bridge (never requires self.worker)."""
        try:
            self._log_bridge.log_msg.emit(str(msg))
        except Exception:
            try:
                if self.gui is not None:
                    self.gui.append_log(str(msg))
            except Exception:
                pass

    # ── Ignored creators ──────────────────────────────────────────────────────

    def _ignored_file_path(self) -> Path:
        return self.plugin_dir / "live_stream_ignored.json"

    def _load_ignored(self):
        try:
            data = json.loads(self._ignored_file_path().read_text())
            self.ignored_creators = set(data.get("ignored", []))
        except Exception:
            self.ignored_creators = set()

    def _save_ignored(self):
        try:
            path = self._ignored_file_path()
            path.write_text(json.dumps({"ignored": sorted(self.ignored_creators)}, indent=2))
        except Exception as e:
            self.log.warning(f"Failed to save ignored creators: {e}")

    def is_ignored(self, username: str) -> bool:
        return username in self.ignored_creators

    def set_ignored(self, username: str, ignored: bool):
        if ignored:
            self.ignored_creators.add(username)
        else:
            self.ignored_creators.discard(username)
        self._save_ignored()

    def _settings_file_path(self) -> Path:
        return self.plugin_dir / "live_stream_settings.json"

    def _load_settings(self):
        try:
            data = json.loads(self._settings_file_path().read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if "headless_capture" in data:
                    self.headless_capture = bool(data.get("headless_capture"))
                if "probe_mode" in data:
                    self.probe_mode = bool(data.get("probe_mode"))
                if "show_diagnostics" in data:
                    self.show_diagnostics = bool(data.get("show_diagnostics"))
        except Exception:
            pass

    def _save_settings(self):
        try:
            path = self._settings_file_path()
            path.write_text(
                json.dumps(
                    {
                        "headless_capture": bool(self.headless_capture),
                        "probe_mode": bool(self.probe_mode),
                        "show_diagnostics": bool(self.show_diagnostics),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception as e:
            self.log.warning(f"Failed to save live monitor settings: {e}")

    def set_headless_capture(self, enabled: bool):
        self.headless_capture = bool(enabled)
        self._save_settings()

    def set_probe_mode(self, enabled: bool):
        self.probe_mode = bool(enabled)
        self._save_settings()

    def set_show_diagnostics(self, enabled: bool):
        self.show_diagnostics = bool(enabled)
        self._save_settings()

    def probe_reports_dir(self) -> Path:
        path = Path(self.plugin_dir) / "live_probe_reports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ─────────────────────────────────────────────────────────────────────────

    def on_ui_setup(self, main_window):
        """Builds and mounts the dashboard tab in the sidebar nav."""
        from .gui import LiveMonitorTab
        
        # Create dashboard page
        self.gui = LiveMonitorTab(main_window, self)
        self._page_id = "live_monitor"

        # Durable log bridge (recording threads survive worker teardown)
        try:
            self._log_bridge.log_msg.disconnect()
        except Exception:
            pass
        self._log_bridge.log_msg.connect(self.gui.append_log)
        
        # Build Navigation Button
        from ofscraper.gui.widgets.styled_button import NavButton
        self.btn = NavButton("📺 Live Monitor")
        
        # Add button to the main navigation group
        main_window._nav_buttons["live_monitor"] = self.btn
        main_window._nav_group.addButton(self.btn)
        
        # Insert before theme toggle (with other plugin nav entries)
        layout = main_window._nav_frame.layout()
        theme_btn = getattr(main_window, "_theme_btn", None)
        theme_idx = layout.indexOf(theme_btn) if theme_btn is not None else -1
        if theme_idx >= 0:
            layout.insertWidget(theme_idx, self.btn)
        else:
            help_btn = main_window._nav_buttons.get("help")
            if help_btn:
                layout.insertWidget(layout.indexOf(help_btn), self.btn)
            else:
                layout.addWidget(self.btn)
            
        # Wire button click to navigate to the live_monitor page
        self.btn.clicked.connect(lambda checked: main_window._navigate("live_monitor"))
        
        # Mount the tab to the stack
        main_window._add_page("live_monitor", self.gui)

    def on_ui_teardown(self, main_window):
        """Remove Live Monitor nav/page before unload."""
        try:
            self.stop_monitor()
        except Exception:
            pass
        try:
            if main_window is not None and hasattr(main_window, "_remove_page"):
                main_window._remove_page("live_monitor")
        except Exception:
            pass
        self.btn = None
        self.gui = None

    def on_unload(self):
        """Clean up background processes on shutdown."""
        self.stop_monitor()

    def check_chromium_installed(self) -> bool:
        """Helper that verifies if Playwright and Chromium are fully installed and loadable."""
        _browsers_path_for_plugin()

        deps_path = Path(self.plugin_dir) / "deps"
        # Prefer the active venv/site-packages. Only fall back to deps when native.
        _remove_path_entry(deps_path)
        _purge_playwright_modules()
        ok, detail, root = _inspect_playwright_install()
        if not ok:
            # Try deps only when it has a native driver (not a Windows mount in Linux).
            deps_pw = deps_path / "playwright"
            if deps_pw.is_dir() and _playwright_driver_node(deps_pw).is_file():
                if str(deps_path) not in sys.path:
                    sys.path.insert(0, str(deps_path))
                _purge_playwright_modules()
                ok, detail, root = _inspect_playwright_install()
            if not ok:
                return False

        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                channel = _chromium_channel_for_host()
                # Prefer system Chrome/Edge — no bundled Chromium download required.
                if channel:
                    try:
                        browser = p.chromium.launch(headless=True, channel=channel)
                        browser.close()
                        return True
                    except Exception:
                        pass
                try:
                    browser = p.chromium.launch(headless=True)
                    browser.close()
                    return True
                except Exception:
                    return False
        except Exception:
            return False

    def install_chromium(self, log_sink=None, finished_cb=None):
        """Spawns background installer worker to download Chromium binary.

        Optional *log_sink* / *finished_cb* let modal dialogs own the UX while
        still falling back to the Live Monitor tab console.
        """
        browsers_path = _browsers_path_for_plugin()
        deps_path = Path(self.plugin_dir) / "deps"

        self.install_worker = ChromiumInstallWorker(browsers_path, deps_path)
        sink = log_sink or (self.gui.append_log if self.gui else self._emit_log)
        self.install_worker.log_msg.connect(sink)

        def _done(ok: bool):
            if finished_cb:
                try:
                    finished_cb(ok)
                except Exception:
                    pass
            if self.gui is not None and finished_cb is None:
                self.gui.install_finished(ok)
            elif self.gui is not None and finished_cb is not None:
                # Keep tab status in sync when a modal ran the install
                try:
                    self.gui._check_browser_status()
                except Exception:
                    pass

        self.install_worker.finished.connect(_done)
        self.install_worker.start()

    def start_monitor(self, interval, save_location):
        """Instantiates and starts the polling monitor worker thread."""
        self.worker = LiveMonitorWorker(self, interval, save_location)
        self.worker.log_msg.connect(self.gui.append_log)
        self.worker.status_updated.connect(self.gui.update_status_table)
        self.worker.auth_error.connect(self.gui.handle_auth_error)
        self.worker.start()

    def stop_monitor(self, *, terminate_recordings: bool = True):
        """Stops the monitor poll loop.

        When *terminate_recordings* is True (manual Stop), connecting/active
        capture threads are signalled and joined. When False (API auth failure
        mid-capture), polls stop but Playwright recordings keep running until
        the stream ends or the user stops them.
        """
        # Stop polling loop first (keep worker object until recorders finish)
        if self.worker:
            self.worker.running = False
            self.worker.quit()

        if terminate_recordings:
            # Terminate threads still in the connecting phase
            for username, (thread, stop_event) in list(self._connecting_recordings.items()):
                self._emit_log(f"[Monitor] Terminating connecting stream for {username}...")
                stop_event.set()
            for username, (thread, stop_event) in list(self._connecting_recordings.items()):
                thread.join(timeout=10)
            self._connecting_recordings.clear()
            self._probe_sessions.clear()

            # Terminate threads that are actively recording
            for username, (thread, stop_event, _start_time) in list(self.active_recordings.items()):
                self._emit_log(f"[Monitor] Terminating capture stream for {username}...")
                stop_event.set()
            for username, (thread, stop_event, _start_time) in list(self.active_recordings.items()):
                thread.join(timeout=10)
            self.active_recordings.clear()

        if self.worker:
            self.worker.wait(5000)
            self.worker = None

    def start_recording(self, username, save_location):
        """Spawns a new recording thread for a live creator."""
        if username in self._connecting_recordings or username in self.active_recordings:
            self._emit_log(f"[Capture] {username} already has an active session — skip.")
            return False
        cool_until = float(self._capture_cooldown.get(username) or 0)
        now = time.time()
        if cool_until > now:
            self._emit_log(
                f"[Capture] {username} on cooldown ({int(cool_until - now)}s left) — skip."
            )
            return False
        stop_event = threading.Event()
        rec_thread = threading.Thread(
            target=self.record_stream,
            args=(username, save_location, stop_event),
            daemon=True
        )
        # Register as connecting immediately so the worker won't spawn a duplicate.
        # active_recordings is only set once the MediaRecorder is actually running.
        self._connecting_recordings[username] = (rec_thread, stop_event)
        self._capture_cooldown.pop(username, None)
        rec_thread.start()
        return True

    def start_probe(self, username, save_location=None):
        """Spawns a diagnostics probe (network/API evidence, no WebM recording)."""
        if username in self._connecting_recordings or username in self.active_recordings:
            self._emit_log(f"[Probe] {username} already has an active session — skip.")
            return
        stop_event = threading.Event()
        rec_thread = threading.Thread(
            target=self.probe_stream,
            args=(username, save_location, stop_event),
            daemon=True,
        )
        self._connecting_recordings[username] = (rec_thread, stop_event)
        self._probe_sessions.add(username)
        rec_thread.start()

    def stop_capture(self, username: str) -> bool:
        """Stop one active/connecting capture or probe without stopping the poller."""
        username = (username or "").strip()
        if not username:
            return False
        stopped = False
        if username in self._connecting_recordings:
            _thread, stop_event = self._connecting_recordings[username]
            stop_event.set()
            self._emit_log(f"[Capture] Stopping connecting session for {username}…")
            stopped = True
        if username in self.active_recordings:
            _thread, stop_event, _start = self.active_recordings[username]
            stop_event.set()
            self._emit_log(f"[Capture] Stopping active capture for {username}…")
            stopped = True
        if stopped:
            # Brief cooldown so auto-capture doesn't immediately re-spawn
            self._capture_cooldown[username] = time.time() + 30
        return stopped

    def stop_all_captures(self) -> int:
        """Stop every connecting/active capture/probe; leave monitor poller running."""
        names = set(self._connecting_recordings) | set(self.active_recordings)
        n = 0
        for u in list(names):
            if self.stop_capture(u):
                n += 1
        return n

    def api_dumps_dir(self) -> Path:
        p = self.plugin_dir / "live_api_dumps"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def fetch_live_api_dump(self, username: str) -> Path:
        """
        Diagnostics: resolve OF live join + redact Agora claims to JSON.
        Does not start a capture.
        """
        try:
            from .of_live_api import resolve_live_join, redact_cred_summary
            from .token_inspect import compare_join_to_token
        except ImportError:
            from of_live_api import resolve_live_join, redact_cred_summary  # type: ignore
            from token_inspect import compare_join_to_token  # type: ignore

        self._emit_log(f"[API] Resolving live join for {username}…")
        info = resolve_live_join(username)
        agora = info.get("agora") or {}
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.api_dumps_dir() / f"live_api_{username}_{stamp}.json"
        token_diags = []
        for i, tok in enumerate(agora.get("token_candidates") or [agora.get("token")]):
            if not tok:
                continue
            cmp = compare_join_to_token(
                token=tok,
                app_id=agora.get("app_id") or "",
                channel=agora.get("channel") or "",
                user_id=agora.get("user_id") or "",
            )
            # Never persist raw tokens
            token_diags.append(
                {
                    "index": i,
                    "parse_ok": cmp.get("parse_ok"),
                    "version": cmp.get("version"),
                    "tok_app_id": cmp.get("app_id"),
                    "tok_channel": cmp.get("channel"),
                    "tok_uid": cmp.get("uid"),
                    "wildcard": cmp.get("uid_is_wildcard"),
                    "mismatches": cmp.get("mismatches"),
                    "token_len": len(tok),
                    "error": cmp.get("error"),
                }
            )
        safe = {
            "username": username,
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "stream_id": info.get("stream_id"),
            "model_user_id": info.get("model_user_id"),
            "stream_type": info.get("stream_type"),
            "viewer_available_types": info.get("viewer_available_types"),
            "room": info.get("room"),
            "agora_summary": info.get("agora_summary") or redact_cred_summary(agora),
            "token_diagnostics": token_diags,
            "note": (
                "Native agora_python_server_sdk joins are rejected by OF "
                "(REJECTED_BY_SERVER). Playwright MediaRecorder is the capture path."
            ),
        }
        out.write_text(json.dumps(safe, indent=2), encoding="utf-8")
        self._emit_log(f"[API] agora_summary={safe.get('agora_summary')}")
        for td in token_diags:
            self._emit_log(
                f"[API] Token[{td['index']}] claims: parse_ok={td['parse_ok']} "
                f"tok_uid={td.get('tok_uid')!r} mismatches={td.get('mismatches')}"
            )
        return out

    def probe_stream(self, username, save_location, stop_event):
        """Join a live page and collect HLS/WebRTC/API evidence into a JSON report."""
        report = {
            "username": username,
            "started_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "live_url": f"https://onlyfans.com/{username}/live",
            "had_return_to_login": False,
            "joined_live": False,
            "final_url": "",
            "page_diag": None,
            "interesting_traffic": [],
            "api_json_samples": [],
            "classification": None,
            "summary_urls": None,
            "notes": [],
            "report_path": None,
        }
        try:
            config_dir = get_config_path().parent
            _browsers_path_for_plugin()

            deps_path = Path(self.plugin_dir) / "deps"
            _remove_path_entry(deps_path)
            _purge_playwright_modules()
            ok, _detail, _root = _inspect_playwright_install()
            if not ok:
                deps_pw = deps_path / "playwright"
                if deps_pw.is_dir() and _playwright_driver_node(deps_pw).is_file():
                    if str(deps_path) not in sys.path:
                        sys.path.insert(0, str(deps_path))
                    _purge_playwright_modules()

            from playwright.sync_api import sync_playwright
            from ofscraper.utils.auth.file import read_auth

            profile_dir = config_dir / "playwright_profiles" / username
            profile_dir.mkdir(parents=True, exist_ok=True)

            auth = read_auth()
            user_agent = auth.get("user_agent")
            cookies_to_add = []
            auth_id = auth.get("auth_id")
            sess = auth.get("sess")
            auth_uid = auth.get("auth_uid")
            if auth_id:
                cookies_to_add.append(
                    {"name": "auth_id", "value": str(auth_id), "domain": ".onlyfans.com", "path": "/"}
                )
            if sess:
                cookies_to_add.append(
                    {"name": "sess", "value": str(sess), "domain": ".onlyfans.com", "path": "/"}
                )
            uid_val = (auth_uid or auth_id or "").strip()
            if uid_val:
                cookies_to_add.append(
                    {"name": "auth_uid_", "value": str(uid_val), "domain": ".onlyfans.com", "path": "/"}
                )
            if auth_uid and auth_id:
                cookies_to_add.append(
                    {
                        "name": f"auth_uid_{auth_id}",
                        "value": str(auth_uid),
                        "domain": ".onlyfans.com",
                        "path": "/",
                    }
                )

            stealth_script = """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
            """
            launch_args = [
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ]
            live_url = report["live_url"]
            prefer_hidden = bool(getattr(self, "headless_capture", True))
            traffic = []
            api_samples = []
            seen_req = set()

            self._emit_log(f"[Probe] Launching browser for {username} (diagnostics only)...")

            with sync_playwright() as p:
                launch_kwargs = {
                    "user_data_dir": str(profile_dir),
                    "headless": False,
                    "viewport": {"width": 1280, "height": 720},
                    "args": list(launch_args),
                }
                extra = [
                    "--disable-backgrounding-occluded-windows",
                    "--disable-renderer-backgrounding",
                    "--disable-background-timer-throttling",
                    "--disable-background-media-suspend",
                ]
                if prefer_hidden:
                    launch_kwargs["args"] = launch_args + [
                        "--window-position=-20000,-20000",
                        "--window-size=1280,720",
                    ] + extra
                else:
                    launch_kwargs["args"] = launch_args + extra
                _apply_chromium_launch_kwargs(launch_kwargs, user_agent)

                rec_ctx = p.chromium.launch_persistent_context(**launch_kwargs)
                if cookies_to_add:
                    rec_ctx.add_cookies(cookies_to_add)
                rec_ctx.add_init_script(stealth_script)
                rec_page = rec_ctx.new_page()

                def _on_request(req):
                    try:
                        url = req.url or ""
                        if not url_is_interesting(url):
                            return
                        key = f"{req.method}:{redact_url(url)}"
                        if key in seen_req:
                            return
                        seen_req.add(key)
                        traffic.append(
                            {
                                "phase": "request",
                                "method": req.method,
                                "url": redact_url(url),
                                "resource_type": getattr(req, "resource_type", None),
                            }
                        )
                    except Exception:
                        pass

                def _on_response(resp):
                    try:
                        url = resp.url or ""
                        if not url_is_interesting(url):
                            return
                        entry = {
                            "phase": "response",
                            "status": resp.status,
                            "url": redact_url(url),
                            "content_type": (resp.headers or {}).get("content-type", ""),
                        }
                        traffic.append(entry)
                        if (
                            "onlyfans.com/api2" in url.lower()
                            and "application/json" in (entry["content_type"] or "").lower()
                            and len(api_samples) < 25
                        ):
                            try:
                                body = resp.text()
                                if body and len(body) < 200_000:
                                    try:
                                        parsed = json.loads(body)
                                        api_samples.append(
                                            {
                                                "url": redact_url(url),
                                                "status": resp.status,
                                                "json": redact_json(parsed),
                                            }
                                        )
                                    except Exception:
                                        api_samples.append(
                                            {
                                                "url": redact_url(url),
                                                "status": resp.status,
                                                "text_preview": body[:400],
                                            }
                                        )
                            except Exception:
                                pass
                        if ".m3u8" in url.lower() and len(api_samples) < 30:
                            try:
                                body = resp.text()
                                if body:
                                    lines = [
                                        ln
                                        for ln in body.splitlines()
                                        if ln.strip() and not ln.strip().startswith("#EXT-X-KEY")
                                    ][:12]
                                    api_samples.append(
                                        {
                                            "url": redact_url(url),
                                            "status": resp.status,
                                            "m3u8_preview_lines": lines,
                                        }
                                    )
                            except Exception:
                                pass
                    except Exception:
                        pass

                rec_page.on("request", _on_request)
                rec_page.on("response", _on_response)

                try:
                    rec_page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                rec_page.wait_for_timeout(5000)
                current_url = rec_page.url
                report["final_url"] = current_url
                self._emit_log(f"[Probe] Auth check URL: {current_url}")

                if "return_to" in current_url:
                    report["had_return_to_login"] = True
                    report["notes"].append(
                        "Browser hit login redirect — finish login in the window "
                        "or re-import cookies / warm playwright_profiles first."
                    )
                    if prefer_hidden:
                        try:
                            client = rec_ctx.new_cdp_session(rec_page)
                            info = client.send("Browser.getWindowForTarget")
                            wid = info.get("windowId")
                            if wid is not None:
                                client.send(
                                    "Browser.setWindowBounds",
                                    {
                                        "windowId": wid,
                                        "bounds": {
                                            "left": 80,
                                            "top": 80,
                                            "width": 1280,
                                            "height": 720,
                                            "windowState": "normal",
                                        },
                                    },
                                )
                        except Exception:
                            pass
                    self._emit_log(
                        "[Probe] Login required — waiting up to 3 minutes in this window…"
                    )
                    try:
                        rec_page.wait_for_url(
                            lambda url: _url_is_live_stream(url, username),
                            timeout=180000,
                        )
                        rec_page.wait_for_timeout(3000)
                    except Exception:
                        self._emit_log("[Probe] Login timed out — writing partial report.")
                        rec_ctx.close()
                        raise RuntimeError("login_timeout")

                if not _url_is_live_stream(rec_page.url, username):
                    report["notes"].append(f"Not on live page: {rec_page.url}")
                    self._emit_log(f"[Probe] Not on live page ({rec_page.url}).")
                    rec_ctx.close()
                    raise RuntimeError("not_live_page")

                report["joined_live"] = True
                report["final_url"] = rec_page.url
                if prefer_hidden:
                    _hide_capture_window(rec_ctx, rec_page)

                try:
                    join_btn = rec_page.locator("button:has-text('JOIN LIVE STREAM')")
                    if join_btn.count() > 0:
                        self._emit_log("[Probe] Clicking 'JOIN LIVE STREAM'...")
                        join_btn.first.click()
                        rec_page.wait_for_timeout(3000)
                except Exception as e:
                    report["notes"].append(f"Join button: {e}")

                self._emit_log("[Probe] Collecting traffic for ~45s (player + API)...")
                for _ in range(45):
                    if stop_event.is_set():
                        report["notes"].append("Stopped early by user.")
                        break
                    if not _url_is_live_stream(rec_page.url, username):
                        report["notes"].append(f"Left live page: {rec_page.url}")
                        break
                    time.sleep(1)

                try:
                    diag = rec_page.evaluate(
                        """() => {
                    const info = {};
                    info.videos = [...document.querySelectorAll('video')].map((v, i) => {
                        const d = {index: i, paused: v.paused, muted: v.muted,
                                   volume: v.volume, readyState: v.readyState,
                                   src: v.src ? v.src.slice(0, 120) : null};
                        if (v.srcObject) {
                            d.srcObjectType = v.srcObject.constructor.name;
                            if (v.srcObject instanceof MediaStream) {
                                d.videoTracks = v.srcObject.getVideoTracks().length;
                                d.audioTracks = v.srcObject.getAudioTracks().length;
                            }
                        }
                        return d;
                    });
                    info.audios = [...document.querySelectorAll('audio')].map((a, i) => {
                        const d = {index: i, paused: a.paused, muted: a.muted,
                                   src: a.src ? a.src.slice(0, 120) : null};
                        if (a.srcObject) {
                            d.srcObjectType = a.srcObject.constructor.name;
                            if (a.srcObject instanceof MediaStream) {
                                d.audioTracks = a.srcObject.getAudioTracks().length;
                            }
                        }
                        return d;
                    });
                    const sdks = ['AgoraRTC','AgoraRTCClient','agora','_agora',
                                  'Agora','LiveStream','OBS','wowza','hls','Hls'];
                    info.sdkGlobals = sdks.filter(k => typeof window[k] !== 'undefined');
                    return info;
                }"""
                    )
                    report["page_diag"] = diag
                    self._emit_log(
                        f"[Probe] Diag videos={len(diag.get('videos') or [])} "
                        f"sdk={diag.get('sdkGlobals') or []}"
                    )
                except Exception as e:
                    report["notes"].append(f"page_diag failed: {e}")

                rec_ctx.close()

            report["interesting_traffic"] = traffic[:400]
            report["api_json_samples"] = api_samples
            report["summary_urls"] = summarize_requests(traffic)
            report["classification"] = classify_delivery(
                [e.get("url") or "" for e in traffic],
                report.get("page_diag"),
            )
            cls = report["classification"]
            self._emit_log(f"[Probe] Classification: {cls.get('suggested_path')}")
            self._emit_log(f"[Probe] {cls.get('summary')}")

        except RuntimeError as rexc:
            if str(rexc) not in ("login_timeout", "not_live_page"):
                self._emit_log(f"[Probe] Error: {rexc}")
                report["notes"].append(str(rexc))
        except Exception as ex:
            self._emit_log(f"[Probe] Failed for {username}: {ex}")
            self._emit_log(traceback.format_exc())
            report["notes"].append(str(ex))
        finally:
            report["finished_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            if report.get("classification") is None:
                try:
                    report["summary_urls"] = summarize_requests(
                        report.get("interesting_traffic") or []
                    )
                    report["classification"] = classify_delivery(
                        [
                            e.get("url") or ""
                            for e in (report.get("interesting_traffic") or [])
                        ],
                        report.get("page_diag"),
                    )
                except Exception:
                    pass
            try:
                out_dir = self.probe_reports_dir()
                stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                out_path = out_dir / f"probe_{username}_{stamp}.json"
                out_path.write_text(
                    json.dumps(report, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                report["report_path"] = str(out_path)
                self._emit_log(f"[Probe] Report saved: {out_path}")
                cls = report.get("classification") or {}
                if cls.get("summary"):
                    self._emit_log(f"[Probe] Result: {cls.get('summary')}")
            except Exception as we:
                self._emit_log(f"[Probe] Could not write report: {we}")
            self._probe_sessions.discard(username)
            self._connecting_recordings.pop(username, None)

    def record_stream(self, username, save_location, stop_event):
        """Playwright-based WebRTC stream recorder task."""
        try:
            config_dir = get_config_path().parent
            _browsers_path_for_plugin()

            deps_path = Path(self.plugin_dir) / "deps"
            _remove_path_entry(deps_path)
            _purge_playwright_modules()
            ok, _detail, _root = _inspect_playwright_install()
            if not ok:
                deps_pw = deps_path / "playwright"
                if deps_pw.is_dir() and _playwright_driver_node(deps_pw).is_file():
                    if str(deps_path) not in sys.path:
                        sys.path.insert(0, str(deps_path))
                    _purge_playwright_modules()

            from playwright.sync_api import sync_playwright

            save_base = save_location or get_save_location()
            save_dir = Path(save_base) / username / "Live_Streams"
            save_dir.mkdir(parents=True, exist_ok=True)

            # Per-model persistent browser profile. Chromium saves the full session
            # (cookies, local storage, cf_clearance) after the first manual login so
            # every subsequent capture is fully automatic. Using per-model subdirs
            # allows concurrent captures of different models without profile-lock conflicts.
            profile_dir = config_dir / "playwright_profiles" / username
            profile_dir.mkdir(parents=True, exist_ok=True)

            self._emit_log(f"[Playwright] Launching browser for {username}...")

            stealth_script = """
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
                const _getParam = WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter = function(p) {
                    if (p === 37445) return 'Intel Open Source Technology Center';
                    if (p === 37446) return 'Mesa DRI Intel(R) HD Graphics 520 (Skylake GT2)';
                    return _getParam.call(this, p);
                };
                window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
                const _origQuery = navigator.permissions.query;
                navigator.permissions.query = (params) =>
                    params.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : _origQuery(params);
            """

            launch_args = [
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--password-store=basic",
            ]

            live_url = f"https://onlyfans.com/{username}/live"
            _chunk_file = None
            final_path = None
            final_name = None
            rec_start_time = None
            last_chunk_time = None
            from ofscraper.utils.auth.file import read_auth
            auth = read_auth()
            user_agent = auth.get("user_agent")
            cookies_to_add = []
            auth_id = auth.get("auth_id")
            sess = auth.get("sess")
            auth_uid = auth.get("auth_uid")
            if auth_id:
                cookies_to_add.append({
                    "name": "auth_id",
                    "value": str(auth_id),
                    "domain": ".onlyfans.com",
                    "path": "/"
                })
            if sess:
                cookies_to_add.append({
                    "name": "sess",
                    "value": str(sess),
                    "domain": ".onlyfans.com",
                    "path": "/"
                })
            # Match stock API cookies: auth_uid_ only. auth_uid_<id> is a real
            # 2FA browser cookie — only inject it when auth_uid was imported.
            uid_val = (auth_uid or auth_id or "").strip()
            if uid_val:
                cookies_to_add.append({
                    "name": "auth_uid_",
                    "value": str(uid_val),
                    "domain": ".onlyfans.com",
                    "path": "/"
                })
            if auth_uid and auth_id:
                cookies_to_add.append({
                    "name": f"auth_uid_{auth_id}",
                    "value": str(auth_uid),
                    "domain": ".onlyfans.com",
                    "path": "/"
                })

            with sync_playwright() as p:

                # Single headed context for auth + recording. True Playwright
                # headless drops the OnlyFans session (return_to login loop).
                # "Hide capture window" = move the real Chrome window off-screen.
                prefer_hidden = bool(getattr(self, "headless_capture", True))
                launch_kwargs = {
                    "user_data_dir": str(profile_dir),
                    "headless": False,
                    "viewport": {"width": 1280, "height": 720},
                    "args": list(launch_args),
                }
                if prefer_hidden:
                    launch_kwargs["args"] = launch_args + [
                        "--window-position=-20000,-20000",
                        "--window-size=1280,720",
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                        "--disable-background-timer-throttling",
                        "--disable-background-media-suspend",
                    ]
                else:
                    launch_kwargs["args"] = launch_args + [
                        "--disable-backgrounding-occluded-windows",
                        "--disable-renderer-backgrounding",
                        "--disable-background-timer-throttling",
                        "--disable-background-media-suspend",
                    ]
                _apply_chromium_launch_kwargs(launch_kwargs, user_agent)
                channel = launch_kwargs.get("channel")
                if channel:
                    self._emit_log(
                        f"[Playwright] Using system browser channel={channel} "
                        "(avoids bundled Chromium captcha loops)."
                    )
                elif _playwright_user_agent(user_agent) is None and (user_agent or "").strip():
                    self._emit_log(
                        "[Playwright] Auth user-agent is not Chromium-compatible; "
                        "not overriding the browser UA (Firefox/Zen UA on Chromium "
                        "often causes endless captchas)."
                    )
                if prefer_hidden:
                    self._emit_log(
                        "[Playwright] Capture window will stay off-screen "
                        "(true headless breaks OnlyFans login sessions)."
                    )

                rec_ctx = p.chromium.launch_persistent_context(**launch_kwargs)
                if cookies_to_add:
                    rec_ctx.add_cookies(cookies_to_add)

                audio_init_script = """
(() => {
    const _origConnect = AudioNode.prototype.connect;
    window._lsm_taps        = new Map();
    window._lsm_chunks      = [];
    window._lsm_audio_plays = [];

    AudioNode.prototype.connect = function(dest, outCh, inCh) {
        if (dest instanceof AudioDestinationNode) {
            const ctx = this.context;
            if (!window._lsm_taps.has(ctx)) {
                window._lsm_taps.set(ctx, null);
                try { window._lsm_taps.set(ctx, ctx.createMediaStreamDestination()); }
                catch(e) {}
            }
            const tap = window._lsm_taps.get(ctx);
            if (tap) {
                try {
                    inCh !== undefined ? _origConnect.call(this, tap, outCh, inCh)
                    : outCh !== undefined ? _origConnect.call(this, tap, outCh)
                    : _origConnect.call(this, tap);
                } catch(e) {}
            }
        }
        return inCh !== undefined ? _origConnect.call(this, dest, outCh, inCh)
             : outCh !== undefined ? _origConnect.call(this, dest, outCh)
             : _origConnect.call(this, dest);
    };

    window._lsm_get_audio_track = () => {
        for (const [, tap] of window._lsm_taps) {
            if (!tap) continue;
            const t = tap.stream.getAudioTracks();
            if (t.length) return t[0];
        }
        return null;
    };

    const _origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function() {
        if (this.srcObject instanceof MediaStream) {
            const at = this.srcObject.getAudioTracks();
            if (at.length && !window._lsm_audio_plays.includes(this))
                window._lsm_audio_plays.push(this);
        }
        return _origPlay.call(this);
    };
})();
"""
                rec_ctx.add_init_script(stealth_script)
                rec_ctx.add_init_script(audio_init_script)
                rec_page = rec_ctx.new_page()

                try:
                    rec_page.goto(live_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

                rec_page.wait_for_timeout(5000)
                current_url = rec_page.url
                self._emit_log(f"[Playwright] Auth check URL: {current_url}")

                if "return_to" in current_url:
                    if prefer_hidden:
                        try:
                            client = rec_ctx.new_cdp_session(rec_page)
                            info = client.send("Browser.getWindowForTarget")
                            wid = info.get("windowId")
                            if wid is not None:
                                client.send(
                                    "Browser.setWindowBounds",
                                    {
                                        "windowId": wid,
                                        "bounds": {
                                            "left": 80,
                                            "top": 80,
                                            "width": 1280,
                                            "height": 720,
                                            "windowState": "normal",
                                        },
                                    },
                                )
                        except Exception:
                            pass
                    self._emit_log(
                        "[Playwright] No saved session — login required.\n"
                        "  Prefer: Authentication tab → Import Cookies / Login in System Browser, "
                        "run Test, then retry capture.\n"
                        "  Waiting up to 3 minutes if you finish login in this window…"
                    )
                    try:
                        rec_page.wait_for_url(
                            lambda url: _url_is_live_stream(url, username),
                            timeout=180000,
                        )
                        rec_page.wait_for_timeout(5000)
                    except Exception:
                        self._emit_log("[Playwright] Login timed out — aborting capture.")
                        rec_ctx.close()
                        return

                    self._emit_log(f"[Playwright] Logged in. URL: {rec_page.url}")
                    (profile_dir / ".session_saved").touch()

                if not _url_is_live_stream(rec_page.url, username):
                    self._emit_log(
                        f"[Playwright] Not on live page ({rec_page.url}). "
                        f"Stream ended before capture could begin. Aborting."
                    )
                    rec_ctx.close()
                    return

                self._emit_log("[Playwright] Session verified. Starting recording...")
                if prefer_hidden:
                    if _hide_capture_window(rec_ctx, rec_page):
                        self._emit_log("[Playwright] Capture window hidden off-screen.")
                    else:
                        self._emit_log(
                            "[Playwright] Could not reposition window; it may stay visible."
                        )

                # Click "JOIN LIVE STREAM" if the pre-join landing screen is showing.
                # OnlyFans requires this interaction before the actual WebRTC stream loads.
                try:
                    join_btn = rec_page.locator("button:has-text('JOIN LIVE STREAM')")
                    if join_btn.count() > 0:
                        self._emit_log("[Playwright] Clicking 'JOIN LIVE STREAM'...")
                        join_btn.first.click()
                        rec_page.wait_for_timeout(3000)
                        self._emit_log("[Playwright] Joined the live stream.")
                except Exception as e:
                    self._emit_log(f"[Playwright] Join button error: {e}")

                # Wait for the <video> element before starting the poll loop.
                # WebRTC takes several seconds to establish. We poll every 5 s so we
                # can also detect if the page redirects away from /live early (which
                # OnlyFans does when the stream ends), rather than blocking for the
                # full 60 s with wait_for_selector before noticing the redirect.
                self._emit_log("[Playwright] Waiting for stream player (up to 60 s)...")
                stream_ready = False
                for _ in range(12):  # 12 × 5 s = 60 s
                    time.sleep(5)
                    if not _url_is_live_stream(rec_page.url, username):
                        self._emit_log(
                            f"[Playwright] Live page redirected to {rec_page.url} — "
                            f"stream ended or could not load. Aborting."
                        )
                        rec_ctx.close()
                        return
                    try:
                        stream_ready = rec_page.evaluate(
                            "() => document.querySelector('video') !== null"
                        )
                    except Exception:
                        pass
                    if stream_ready:
                        break

                if not stream_ready:
                    self._emit_log(
                        f"[Playwright] No video element appeared in 60 s — stream not active for {username}."
                    )
                    rec_ctx.close()
                    return

                # Give Agora's audio graph time to fully initialize before we start
                # the recorder. The lazy-tap fires on AudioNode.connect(destination),
                # which Agora typically calls 3-7 s after the video element loads.
                # Without this wait, _lsm_get_audio_track() returns null and the
                # recorder falls through to the media-element-src fallback (which
                # crashes Chromium for WebRTC video elements).
                self._emit_log("[Playwright] Waiting 8 s for audio graph to initialize...")
                for _ in range(8):
                    if stop_event.is_set():
                        rec_ctx.close()
                        return
                    time.sleep(1)

                # ── Audio architecture diagnostic ─────────────────────────────────
                # Runs once when the stream is confirmed live. Output appears in
                # the terminal so we can see exactly how OnlyFans routes audio.
                diag = rec_page.evaluate("""() => {
                    const info = {};

                    // All <video> elements
                    info.videos = [...document.querySelectorAll('video')].map((v, i) => {
                        const d = {index: i, paused: v.paused, muted: v.muted,
                                   volume: v.volume, readyState: v.readyState,
                                   src: v.src ? v.src.slice(0, 80) : null};
                        if (v.srcObject) {
                            d.srcObjectType = v.srcObject.constructor.name;
                            if (v.srcObject instanceof MediaStream) {
                                d.videoTracks = v.srcObject.getVideoTracks().map(t =>
                                    ({id: t.id.slice(0,8), enabled: t.enabled,
                                      muted: t.muted, readyState: t.readyState}));
                                d.audioTracks = v.srcObject.getAudioTracks().map(t =>
                                    ({id: t.id.slice(0,8), enabled: t.enabled,
                                      muted: t.muted, readyState: t.readyState}));
                            }
                        }
                        return d;
                    });

                    // All <audio> elements
                    info.audios = [...document.querySelectorAll('audio')].map((a, i) => {
                        const d = {index: i, paused: a.paused, muted: a.muted,
                                   volume: a.volume, src: a.src ? a.src.slice(0, 80) : null};
                        if (a.srcObject) {
                            d.srcObjectType = a.srcObject.constructor.name;
                            if (a.srcObject instanceof MediaStream) {
                                d.audioTracks = a.srcObject.getAudioTracks().map(t =>
                                    ({id: t.id.slice(0,8), enabled: t.enabled,
                                      muted: t.muted, readyState: t.readyState}));
                            }
                        }
                        return d;
                    });

                    // Known streaming SDK globals
                    const sdks = ['AgoraRTC','AgoraRTCClient','agora','_agora',
                                  'Agora','LiveStream','OBS','wowza','hls','Hls'];
                    info.sdkGlobals = sdks.filter(k => typeof window[k] !== 'undefined');

                    // Web-Audio lazy-tap state
                    const taps = window._lsm_taps || new Map();
                    info.audioTapCount = taps.size;
                    info.audioTapTrack = typeof window._lsm_get_audio_track === 'function'
                        && window._lsm_get_audio_track() !== null ? 1 : 0;

                    // Non-DOM audio elements tracked by play() patch
                    info.audioPlays = (window._lsm_audio_plays || []).map((el, i) => ({
                        i, inDom: el.isConnected,
                        srcType: el.srcObject ? el.srcObject.constructor.name : 'none',
                        audioTracks: el.srcObject instanceof MediaStream
                            ? el.srcObject.getAudioTracks().length : 0
                    }));

                    return info;
                }""")
                self._emit_log("[Diag] === Audio Architecture ===")
                for i, v in enumerate(diag.get("videos", [])):
                    self._emit_log(f"[Diag] <video[{i}]> readyState={v.get('readyState')} muted={v.get('muted')} paused={v.get('paused')} srcType={v.get('srcObjectType','none')}")
                    for t in v.get("videoTracks", []):
                        self._emit_log(f"[Diag]   videoTrack id={t['id']} enabled={t['enabled']} muted={t['muted']} state={t['readyState']}")
                    for t in v.get("audioTracks", []):
                        self._emit_log(f"[Diag]   audioTrack id={t['id']} enabled={t['enabled']} muted={t['muted']} state={t['readyState']}")
                    if not v.get("videoTracks") and not v.get("audioTracks") and v.get("srcObjectType") != "MediaStream":
                        self._emit_log(f"[Diag]   src={v.get('src')}")
                for i, a in enumerate(diag.get("audios", [])):
                    self._emit_log(f"[Diag] <audio[{i}]> paused={a.get('paused')} muted={a.get('muted')} srcType={a.get('srcObjectType','none')}")
                    for t in a.get("audioTracks", []):
                        self._emit_log(f"[Diag]   audioTrack id={t['id']} enabled={t['enabled']} muted={t['muted']} state={t['readyState']}")
                    if not a.get("audioTracks"):
                        self._emit_log(f"[Diag]   src={a.get('src')}")
                sdk_globals = diag.get("sdkGlobals", [])
                self._emit_log(f"[Diag] SDK globals: {sdk_globals if sdk_globals else 'none found'}")
                tap_count = diag.get("audioTapCount", 0)
                tap_track = diag.get("audioTapTrack", 0)
                self._emit_log(f"[Diag] AudioContext lazy-taps: {tap_count}  audio-track-ready: {bool(tap_track)}")
                for p in diag.get("audioPlays", []):
                    self._emit_log(
                        f"[Diag] AudioPlay[{p['i']}] inDom={p.get('inDom')} "
                        f"srcType={p.get('srcType')} audioTracks={p.get('audioTracks')}"
                    )
                if not diag.get("audioPlays"):
                    self._emit_log("[Diag] AudioPlay: none captured yet")
                self._emit_log("[Diag] === End ===")

                # Open output file and start MediaRecorder to capture the actual
                # WebRTC audio+video stream (captureStream pulls both tracks).
                now_str = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                final_name = f"Live_Stream_{username}_{now_str}.webm"
                final_path = save_dir / final_name
                _chunk_file = open(str(final_path), "wb")

                recorder_result = rec_page.evaluate("""() => {
                    const video = document.querySelector('video');
                    if (!video) return {ok: false, reason: 'no-video'};

                    // ── 1. Video track ─────────────────────────────────────────────────
                    let videoTrack = null;
                    if (video.srcObject instanceof MediaStream) {
                        const vt = video.srcObject.getVideoTracks();
                        if (vt.length) videoTrack = vt[0];
                    }
                    if (!videoTrack && video.captureStream) {
                        try { const vt = video.captureStream().getVideoTracks();
                              if (vt.length) videoTrack = vt[0]; } catch(e) {}
                    }

                    // ── 2. Audio track (three fallbacks) ──────────────────────────────
                    let audioTrack = null;
                    let audioSource = 'none';

                    // 2a. Direct from video srcObject (plain WebRTC MediaStream)
                    if (video.srcObject instanceof MediaStream) {
                        const at = video.srcObject.getAudioTracks();
                        if (at.length) { audioTrack = at[0]; audioTrack.enabled = true;
                                         audioSource = 'video.srcObject'; }
                    }

                    // 2b. Any audio element playing a MediaStream — including non-DOM
                    //     Audio() elements created by Agora SDK (tracked by play() patch).
                    if (!audioTrack) {
                        const seen = new Set();
                        const allAudio = [
                            ...document.querySelectorAll('audio'),
                            ...(window._lsm_audio_plays || [])
                        ];
                        for (const el of allAudio) {
                            if (seen.has(el)) continue;
                            seen.add(el);
                            if (el.srcObject instanceof MediaStream) {
                                const at = el.srcObject.getAudioTracks()
                                    .filter(t => t.readyState !== 'ended');
                                if (at.length) {
                                    audioTrack = at[0]; audioTrack.enabled = true;
                                    audioSource = el.isConnected
                                        ? 'audio-element.srcObject' : 'non-dom-audio-play';
                                    break;
                                }
                            }
                            if (!audioTrack && el.captureStream) {
                                try { const at = el.captureStream().getAudioTracks();
                                      if (at.length) { audioTrack = at[0];
                                                       audioSource = 'audio-element.captureStream'; break; }
                                } catch(e) {}
                            }
                        }
                    }

                    // 2c. Web Audio lazy-tap — catches Agora/SDK audio routed via AudioNode.connect patch
                    if (!audioTrack) {
                        const t = typeof window._lsm_get_audio_track === 'function'
                            ? window._lsm_get_audio_track() : null;
                        if (t) { audioTrack = t; audioSource = 'web-audio-lazy-tap'; }
                    }

                    // ── 3. Build combined recording stream ────────────────────────────
                    const tracks = [];
                    if (videoTrack) tracks.push(videoTrack);
                    if (audioTrack) tracks.push(audioTrack);
                    if (!tracks.length) return {ok: false, reason: 'no-tracks'};

                    const recStream = new MediaStream(tracks);
                    const types = [
                        'video/webm;codecs=vp8,opus',
                        'video/webm;codecs=vp9,opus',
                        'video/webm;codecs=h264,opus',
                        'video/webm',
                    ];
                    const mimeType = types.find(t => MediaRecorder.isTypeSupported(t)) || 'video/webm';
                    try {
                        const rec = new MediaRecorder(recStream, {mimeType});
                        rec.ondataavailable = (e) => {
                            if (!e.data || e.data.size === 0) return;
                            e.data.arrayBuffer().then(ab => {
                                const bytes = new Uint8Array(ab);
                                let binary = '';
                                for (let i = 0; i < bytes.length; i += 8192)
                                    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
                                (window._lsm_chunks = window._lsm_chunks || []).push(btoa(binary));
                            });
                        };
                        rec.start(5000);
                        window._lsm_recorder = rec;
                        return {ok: true,
                                videoTracks: videoTrack ? 1 : 0,
                                audioTracks: audioTrack ? 1 : 0,
                                audioSource, mimeType};
                    } catch (err) {
                        return {ok: false, reason: String(err)};
                    }
                }""")
                if isinstance(recorder_result, dict) and recorder_result.get("ok"):
                    at = recorder_result.get("audioTracks", 0)
                    vt = recorder_result.get("videoTracks", 0)
                    mt = recorder_result.get("mimeType", "?")
                    asrc = recorder_result.get("audioSource", "none")
                    self._emit_log(
                        f"[Playwright] Stream active — recording... "
                        f"tracks: {vt}v/{at}a  codec: {mt}  audio-src: {asrc}"
                    )
                    # MediaRecorder is running — promote to active so the GUI shows
                    # "Recording 🔴" and the duration timer starts from the right moment.
                    rec_start_time = datetime.datetime.now()
                    last_chunk_time = rec_start_time
                    self._connecting_recordings.pop(username, None)
                    self.active_recordings[username] = (
                        threading.current_thread(), stop_event, rec_start_time
                    )
                else:
                    reason = recorder_result.get("reason", "unknown") if isinstance(recorder_result, dict) else recorder_result
                    self._emit_log(f"[Playwright] Warning: MediaRecorder failed ({reason}) — stream may not be captured.")

                offline_counter = 0
                max_offline = 360  # 360 × 5 s = 30 min fallback for hung sessions
                diag_tick = 0      # re-run audio diagnostic every 12 polls (60 s)

                while not stop_event.is_set():
                    time.sleep(5)

                    # Drain MediaRecorder chunks queued in JS into the output file.
                    # This avoids expose_function threading conflicts with Playwright sync API.
                    if not rec_page.is_closed():
                        try:
                            chunks = rec_page.evaluate(
                                "() => { const c = window._lsm_chunks || []; "
                                "window._lsm_chunks = []; return c; }"
                            )
                            for c in chunks:
                                _chunk_file.write(base64.b64decode(c))
                            if chunks:
                                _chunk_file.flush()
                                last_chunk_time = datetime.datetime.now()
                        except Exception:
                            pass

                    if rec_page.is_closed():
                        self._emit_log(f"[Playwright] Page closed for {username}.")
                        break

                    # Periodic re-diagnostic so we see the DOM once actual live content starts
                    diag_tick += 1
                    if diag_tick % 12 == 0:
                        try:
                            d2 = rec_page.evaluate("""() => {
                                const vids = [...document.querySelectorAll('video')].map((v,i)=>({
                                    i, srcType: v.srcObject ? v.srcObject.constructor.name : 'none',
                                    vTracks: v.srcObject instanceof MediaStream ? v.srcObject.getVideoTracks().length : 0,
                                    aTracks: v.srcObject instanceof MediaStream ? v.srcObject.getAudioTracks().length : 0,
                                    paused: v.paused
                                }));
                                const auds = [...document.querySelectorAll('audio')].map((a,i)=>({
                                    i, srcType: a.srcObject ? a.srcObject.constructor.name : 'none',
                                    aTracks: a.srcObject instanceof MediaStream ? a.srcObject.getAudioTracks().length : 0,
                                    paused: a.paused,
                                    src: a.src ? a.src.slice(0,60) : null
                                }));
                                return {videos: vids, audios: auds};
                            }""")
                            self._emit_log("[Diag] -- periodic audio check --")
                            for v in d2.get("videos", []):
                                self._emit_log(f"[Diag] <video[{v['i']}]> srcType={v['srcType']} vTracks={v['vTracks']} aTracks={v['aTracks']} paused={v['paused']}")
                            for a in d2.get("audios", []):
                                self._emit_log(f"[Diag] <audio[{a['i']}]> srcType={a['srcType']} aTracks={a['aTracks']} paused={a['paused']} src={a['src']}")
                        except Exception:
                            pass

                    # Primary stop: URL left /live — stream ended or model navigated away
                    if not _url_is_live_stream(rec_page.url, username):
                        self._emit_log(
                            f"[Playwright] Left /live page ({rec_page.url}) — stream ended."
                        )
                        break

                    # Secondary stop: 30 min of no video activity (hung session)
                    try:
                        is_playing = rec_page.evaluate("""() => {
                            const video = document.querySelector('video');
                            return video && !video.paused && video.readyState >= 2;
                        }""")

                        if not is_playing:
                            offline_counter += 1
                            if offline_counter >= max_offline:
                                self._emit_log(
                                    f"[Playwright] Stream for {username} showed no video for 30 min — stopping."
                                )
                                break
                        else:
                            offline_counter = 0
                    except Exception as pe:
                        self._emit_log(f"[Playwright] Evaluation error for {username}: {pe}")
                        break

                # Stop MediaRecorder and wait for final chunks to flush to disk
                self._emit_log("[Playwright] Stopping recorder and saving file...")
                try:
                    rec_page.evaluate(
                        "() => { if (window._lsm_recorder && "
                        "window._lsm_recorder.state !== 'inactive') "
                        "window._lsm_recorder.stop(); }"
                    )
                    rec_page.wait_for_timeout(3000)
                    # Drain any final chunks that arrived during the stop flush
                    try:
                        final_chunks = rec_page.evaluate(
                            "() => { const c = window._lsm_chunks || []; "
                            "window._lsm_chunks = []; return c; }"
                        )
                        for c in final_chunks:
                            _chunk_file.write(base64.b64decode(c))
                        if final_chunks:
                            _chunk_file.flush()
                            last_chunk_time = datetime.datetime.now()
                    except Exception:
                        pass
                except Exception:
                    pass

                rec_ctx.close()
                if _chunk_file:
                    _chunk_file.close()
                    _chunk_file = None

            if final_path and final_path.exists() and final_path.stat().st_size > 0:
                self._emit_log(f"[Capture] Stream saved: {final_name}")
                # Compute the best duration estimate:
                # 1st choice: last WebM cluster timestamp + 5 s timeslice (actual media time)
                # 2nd choice: wall-clock from rec start to last chunk written (no shutdown time)
                # 3rd choice: wall-clock to now (includes shutdown overhead — least accurate)
                duration_ms = 0.0
                try:
                    cluster_ms = _read_webm_last_cluster_ms(final_path.read_bytes())
                    if cluster_ms > 0:
                        # Add 2 s to cover frames written after the last cluster timestamp.
                        # (Clusters start at keyframes; the cluster's content may extend
                        # a second or two past the cluster timestamp before the track ended.)
                        duration_ms = cluster_ms + 2000.0
                except Exception:
                    pass
                if duration_ms <= 0 and rec_start_time:
                    ref = last_chunk_time if last_chunk_time else datetime.datetime.now()
                    duration_ms = (ref - rec_start_time).total_seconds() * 1000.0
                # MediaRecorder writes streaming WebM without a Duration header, so VLC
                # shows 00:00 as end time. Try ffmpeg first (reads real media timestamps);
                # fall back to an in-place EBML patch using actual cluster timestamps.
                ffmpeg_bin = shutil.which("ffmpeg")
                if ffmpeg_bin:
                    tmp_path = final_path.with_name(final_path.stem + ".tmp.webm")
                    try:
                        proc = subprocess.run(
                            [ffmpeg_bin, "-y", "-i", str(final_path), "-c", "copy", str(tmp_path)],
                            capture_output=True, timeout=120
                        )
                        if proc.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
                            final_path.unlink()
                            tmp_path.rename(final_path)
                            self._emit_log("[Capture] Duration metadata written (ffmpeg).")
                        else:
                            tmp_path.unlink(missing_ok=True)
                            self._emit_log("[Capture] ffmpeg failed — trying EBML patch.")
                            _patch_webm_duration(final_path, duration_ms, self._emit_log)
                    except Exception as fe:
                        tmp_path.unlink(missing_ok=True)
                        self._emit_log(f"[Capture] ffmpeg error ({fe}) — trying EBML patch.")
                        _patch_webm_duration(final_path, duration_ms, self._emit_log)
                else:
                    _patch_webm_duration(final_path, duration_ms, self._emit_log)
            else:
                self._emit_log(f"[Capture] No data was recorded for {username}.")

        except Exception as ex:
            self._emit_log(f"[Error] Stream capture failed for {username}: {ex}")
            self._emit_log(traceback.format_exc())
            self._capture_cooldown[username] = time.time() + 120
        finally:
            if _chunk_file:
                try:
                    _chunk_file.close()
                except Exception:
                    pass
            self._connecting_recordings.pop(username, None)
            self.active_recordings.pop(username, None)

    def get_streams_count(self, username, save_location) -> int:
        """Returns the number of saved WebM live streams in the model's directory."""
        try:
            save_base = save_location or get_save_location()
            save_dir = Path(save_base) / username / "Live_Streams"
            if not save_dir.is_dir():
                return 0
            return len(list(save_dir.glob("*.webm")))
        except Exception:
            return 0
