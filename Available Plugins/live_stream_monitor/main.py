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
import re
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ofscraper.plugins.base import BasePlugin
from ofscraper.utils.paths.common import get_save_location, get_config_path

try:
    from .live_probe import (
        classify_delivery,
        redact_json,
        redact_text,
        redact_url,
        summarize_requests,
        url_is_interesting,
    )
except ImportError:
    from live_probe import (  # type: ignore
        classify_delivery,
        redact_json,
        redact_text,
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


def _probe_chromium_launch(
    *,
    channel: str | None = None,
    browsers_path: Path | None = None,
    timeout: int = 90,
) -> tuple[bool, str]:
    """Launch Chromium in a *subprocess* (never inside the Qt GUI process).

    In-process ``playwright.launch()`` from a QThread under PyQt regularly
    hard-crashes Windows GUIs (empty dialog close / access violation). Probe
    out-of-process so Install Chromium cannot take down OF-Scraper.
    """
    bp = str(browsers_path or _browsers_path_for_plugin())
    ch = (channel or "").strip() or None
    script = (
        "import os, sys\n"
        f"os.environ['PLAYWRIGHT_BROWSERS_PATH'] = {bp!r}\n"
        "from playwright.sync_api import sync_playwright\n"
        "try:\n"
        "    with sync_playwright() as p:\n"
        f"        kwargs = {{'headless': True}}\n"
        f"        channel = {ch!r}\n"
        "        if channel:\n"
        "            kwargs['channel'] = channel\n"
        "        browser = p.chromium.launch(**kwargs)\n"
        "        browser.close()\n"
        "    print('OK', flush=True)\n"
        "except Exception as e:\n"
        "    print(f'{type(e).__name__}:{e!r}', flush=True)\n"
        "    sys.exit(1)\n"
    )
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = bp
    env["PYTHONUNBUFFERED"] = "1"
    popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "env": env,
    }
    if sys.platform == "win32":
        # Avoid flashing a console window; keep install UX in the dialog log.
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-u", "-c", script],
            **popen_kwargs,
        )
    except Exception as e:
        return False, f"probe_start_failed:{e!r}"
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        return False, f"probe_timeout_after_{timeout}s"
    except Exception as e:
        try:
            proc.kill()
        except Exception:
            pass
        return False, f"probe_error:{e!r}"
    detail = (out or "").strip() or f"exit_{proc.returncode}"
    if proc.returncode == 0 and "OK" in detail:
        return True, detail
    return False, detail


def _playwright_user_agent(auth_ua: str | None) -> str | None:
    """The Authentication user-agent, whatever browser it came from.

    OnlyFans ties the imported ``sess`` to the user-agent it was created with;
    with any other UA (e.g. Chrome's own when the login came from Firefox) the
    site shows the login page. Tested live 2026-10-29: Firefox UA on Chromium
    logged in, no captcha.
    """
    ua = (auth_ua or "").strip()
    return ua or None


# While recording: ask OnlyFans whether the stream is still on, and give up
# when no data has arrived for this long (the page can stay on /live with a
# frozen "playing" video after the stream ends).
_LIVE_CHECK_SECONDS = 60
_NOT_LIVE_CHECKS_TO_STOP = 2
_NO_DATA_STOP_SECONDS = 300


def _stream_still_live(username: str):
    """True / False from OnlyFans' /streams/active; None if the check failed."""
    try:
        try:
            from .of_live_api import fetch_active_stream
        except ImportError:
            from of_live_api import fetch_active_stream  # type: ignore
        return fetch_active_stream(username) is not None
    except Exception:
        return None


class _StreamEndWatch:
    """Decides when a recording should stop because the stream is over."""

    def __init__(self, username: str, check=None, clock=time.monotonic):
        self.username = username
        self._check = check or _stream_still_live
        self._clock = clock
        self._last_check = self._last_data = clock()
        self._not_live = 0

    def got_data(self) -> None:
        self._last_data = self._clock()

    def reason(self):
        """A message to stop with, or None to keep recording."""
        now = self._clock()
        if now - self._last_check >= _LIVE_CHECK_SECONDS:
            self._last_check = now
            live = self._check(self.username)
            # A failed check (None) doesn't count either way.
            self._not_live = self._not_live + 1 if live is False else 0
            if self._not_live >= _NOT_LIVE_CHECKS_TO_STOP:
                return f"OnlyFans says {self.username}'s stream has ended"
        if now - self._last_data >= _NO_DATA_STOP_SECONDS:
            return (
                f"No new data from {self.username}'s stream for "
                f"{_NO_DATA_STOP_SECONDS // 60} min"
            )
        return None


def _session_init_script(auth: dict) -> str:
    """Put x-bc where the OnlyFans web app reads it, before any page script runs.

    The app keeps it in localStorage "bcTokenSha"; without the imported value it
    makes a new one and treats the imported ``sess`` as logged out.
    """
    xbc = str((auth or {}).get("x-bc") or "").strip()
    if not xbc:
        return ""
    return (
        "try { if (location.hostname.endsWith('onlyfans.com')) "
        f"localStorage.setItem('bcTokenSha', {json.dumps(xbc)}); }} catch (e) {{}}"
    )


def _reset_profile(profile_dir: Path) -> Path:
    """Start each capture from a clean browser profile.

    The login always comes from Authentication; leftovers from an older session
    in a saved profile made OnlyFans show the login page even with the right
    cookies, user-agent and x-bc.
    """
    shutil.rmtree(profile_dir, ignore_errors=True)
    return _private_dir(profile_dir)


def _apply_chromium_launch_kwargs(kwargs: dict, user_agent: str | None) -> dict:
    """Mutate launch kwargs: real Chrome channel + the Authentication UA."""
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


def _find_pipx_binary() -> str | None:
    """Return the pipx executable, or None."""
    found = shutil.which("pipx")
    if found:
        return found
    home = Path.home()
    for c in (home / ".local" / "bin" / "pipx", home / ".local" / "bin" / "pipx.exe"):
        if c.is_file():
            return str(c)
    return None


def _pipx_venv_name(executable: str | None = None) -> str | None:
    """Name of the pipx app whose venv runs *executable* (".../pipx/venvs/<name>/...")."""
    parts = Path(executable or sys.executable).parts
    pipx_home = os.environ.get("PIPX_HOME")
    for i in range(1, len(parts) - 1):
        if parts[i].lower() != "venvs":
            continue
        parent = parts[i - 1].lower()
        if "pipx" in parent or (pipx_home and Path(*parts[:i]) == Path(pipx_home)):
            return parts[i + 1]
    return None


PLAYWRIGHT_REQ = "playwright>=1.40.0"


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


def _prepare_playwright(deps_path: Path) -> bool:
    """Make a usable playwright importable.

    A playwright that is already loaded and working is left alone, so checks and
    new captures never pull the module out from under captures that are running.
    """
    ok, _detail, _root = _inspect_playwright_install()
    if ok:
        return True
    # Prefer the active venv/site-packages over the plugin's deps folder.
    _remove_path_entry(deps_path)
    _purge_playwright_modules()
    ok, _detail, _root = _inspect_playwright_install()
    if ok:
        return True
    # Use deps only when it has a native driver (not a Windows mount in Linux).
    deps_pw = deps_path / "playwright"
    if deps_pw.is_dir() and _playwright_driver_node(deps_pw).is_file():
        if str(deps_path) not in sys.path:
            sys.path.insert(0, str(deps_path))
        _purge_playwright_modules()
        ok, _detail, _root = _inspect_playwright_install()
    return ok


def _in_container() -> bool:
    """True inside Docker / Podman / Kubernetes."""
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    try:
        with open("/proc/1/cgroup", errors="ignore") as f:
            text = f.read()
        return any(k in text for k in ("docker", "containerd", "kubepods"))
    except OSError:
        return False


def _is_root() -> bool:
    try:
        return os.geteuid() == 0
    except AttributeError:  # Windows
        return False


def _install_deps_hint() -> str:
    """Command a Linux user can run themselves to add Chromium's system libraries."""
    return f"sudo {sys.executable} -m playwright install-deps chromium"


def _needs_no_sandbox() -> bool:
    """Chrome's sandbox can't start as root or in most containers.

    Everywhere else it stays on: the capture browser opens OnlyFans pages
    (and the ads they load), and the sandbox keeps a bad page away from the PC.
    """
    if not sys.platform.startswith("linux"):
        return False
    return _is_root() or _in_container()


_BACKGROUND_ARGS = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--disable-background-media-suspend",
]


def _capture_launch_kwargs(
    profile_dir: Path, prefer_hidden: bool, user_agent, headless: bool = False
) -> dict:
    """launch_persistent_context() arguments shared by capture and probe.

    *headless*: no window at all (Chrome's new headless mode). Otherwise a real
    window, moved off-screen when *prefer_hidden*.
    """
    no_sandbox = _needs_no_sandbox()
    args = [
        "--autoplay-policy=no-user-gesture-required",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--password-store=basic",
    ]
    if no_sandbox:
        args += ["--no-sandbox", "--disable-setuid-sandbox"]
    if prefer_hidden and not headless:
        args += ["--window-position=-20000,-20000", "--window-size=1280,720"]
    args += _BACKGROUND_ARGS
    kwargs = {
        "user_data_dir": str(profile_dir),
        "headless": bool(headless),
        "viewport": {"width": 1280, "height": 720},
        "args": args,
        # Playwright turns the sandbox off unless asked; ask for it.
        "chromium_sandbox": not no_sandbox,
    }
    kwargs = _apply_chromium_launch_kwargs(kwargs, user_agent)
    if headless:
        # A Chrome channel runs Chrome's new headless mode (the full browser);
        # Playwright's default build would be the stripped "headless shell".
        kwargs.setdefault("channel", "chromium")
    return kwargs


def _launch_capture_context(p, launch_kwargs: dict, emit):
    """Launch the persistent context; fall back to no sandbox only if it can't start."""
    try:
        return p.chromium.launch_persistent_context(**launch_kwargs)
    except Exception as e:
        if not launch_kwargs.get("chromium_sandbox") or "sandbox" not in str(e).lower():
            raise
        emit(
            "[Playwright] Chrome's sandbox can't start on this system "
            f"({type(e).__name__}) — retrying without it. Captures still work, "
            "but are less isolated from the pages they open."
        )
        retry = dict(launch_kwargs)
        retry["chromium_sandbox"] = False
        retry["args"] = list(retry.get("args") or []) + [
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        return p.chromium.launch_persistent_context(**retry)


def _wait_for_live_url(page, username: str, stop_event, seconds: float) -> bool:
    """Wait for the browser to reach the creator's /live page (e.g. after a login).

    Returns False on timeout or when Stop is pressed, checking once a second.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if stop_event.is_set():
            return False
        try:
            if _url_is_live_stream(page.url, username):
                return True
            page.wait_for_timeout(1000)
        except Exception:
            return False
    return False


def _private_dir(path: Path) -> Path:
    """Create *path* readable only by this user (it holds browser logins)."""
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def _ffmpeg_binary() -> str | None:
    """FFmpeg from Configuration (same lookup as downloads), else PATH."""
    try:
        from ofscraper.utils.system.ffmpeg import get_ffmpeg

        return get_ffmpeg()
    except Exception:
        return shutil.which("ffmpeg")


def _remux_timeout(path: Path) -> int:
    """Seconds to allow a stream-copy remux: 5 min, or 10 MB/s for big files."""
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 0
    return int(max(300, size_mb / 10))


_AUTH_MESSAGES = (
    "auth fields not configured",
    "authentication validation failed",
    "isauth=false",
    "wrong user",
)
_AUTH_STATUS_RE = re.compile(
    r"(?:status|http|code|error)\D{0,15}\b(400|401|403)\b", re.IGNORECASE
)


def _http_status(exc) -> int | None:
    for obj in (exc, getattr(exc, "response", None)):
        if obj is None:
            continue
        for attr in ("status", "status_code"):
            value = getattr(obj, attr, None)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _is_auth_error(exc) -> bool:
    """True for login problems: HTTP 400/401/403 or our own auth messages.

    Looks at real status codes (and "status 401"-style text), not at any "400"
    in a message, so timeouts or ids containing 400 don't stop the monitor.
    """
    seen = set()
    cur = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if _http_status(cur) in (400, 401, 403):
            return True
        text = str(cur)
        if any(m in text.lower() for m in _AUTH_MESSAGES):
            return True
        if _AUTH_STATUS_RE.search(text):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


# ---------------------------------------------------------------------------

# WebM post-processing works on the file, never on the whole recording in
# memory: a one-hour MediaRecorder capture is about 1 GB.
_WEBM_HEAD_BYTES = 8192
_WEBM_TAIL_BYTES = 16 * 1024 * 1024
_WEBM_SCAN_CHUNK = 8 * 1024 * 1024


def _patch_webm_duration(path: Path, duration_ms: float, log_fn=None) -> bool:
    """
    Write a Duration element into a MediaRecorder WebM file.

    Chrome's MediaRecorder omits the Duration field entirely from the Segment Info
    block, causing VLC and other players to show 00:00 as the total length.

    Strategy:
      1. If Segment Info already has a Duration → overwrite its value in place.
      2. Otherwise, insert an 11-byte Duration element at the end of the Segment
         Info block: write the rebuilt header to a new file and stream the rest
         of the recording after it.

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
        if offset >= len(data):
            return None, 0
        b = data[offset]
        for width, mask in enumerate([0x80, 0x40, 0x20, 0x10, 0x08], start=1):
            if b & mask:
                if offset + width > len(data):
                    return None, 0
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
        with open(path, "rb") as f:
            head = f.read(_WEBM_HEAD_BYTES)

        SI_ID = b'\x15\x49\xA9\x66'
        si_pos = head.find(SI_ID)
        if si_pos == -1:
            if log_fn:
                log_fn("[Capture] Segment Info not found — cannot add Duration.")
            return False

        size_offset = si_pos + 4
        seg_size, size_len = _read_vint(head, size_offset)
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
        if content_end > len(head):
            if log_fn:
                log_fn("[Capture] Segment Info is unexpectedly large — skipping.")
            return False

        # --- Pass 1: Duration already in Segment Info → overwrite in place ---
        dur_pos = head.find(b'\x44\x89', content_start, content_end)
        if dur_pos != -1 and dur_pos + 3 <= content_end:
            size_byte = head[dur_pos + 2]
            if size_byte == 0x88:
                payload = struct.pack('>d', duration_ms)
            elif size_byte == 0x84:
                payload = struct.pack('>f', duration_ms)
            else:
                if log_fn:
                    log_fn("[Capture] Duration element already present.")
                return True
            with open(path, "r+b") as f:
                f.seek(dur_pos + 3)
                f.write(payload)
            if log_fn:
                log_fn(f"[Capture] Duration metadata written ({duration_ms/1000:.1f}s).")
            return True

        # --- Pass 2: Duration absent → insert into Segment Info block ---
        # New header = up to the SegInfo size field, new size, original SegInfo
        # content, the Duration element; then the rest of the file unchanged.
        new_seg_size = seg_size + len(DURATION_ELEM)
        new_head = (
            head[:si_pos + 4]
            + _encode_vint(new_seg_size)
            + head[content_start:content_end]
            + DURATION_ELEM
        )

        tmp_path = path.with_name(path.stem + ".tmp.webm")
        try:
            with open(path, "rb") as src, open(tmp_path, "wb") as dst:
                dst.write(new_head)
                src.seek(content_end)
                shutil.copyfileobj(src, dst, _WEBM_SCAN_CHUNK)
            os.replace(tmp_path, path)
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


def _last_cluster_ts_in(buf: bytes) -> int:
    """Return the largest WebM Cluster timestamp (ms) found in *buf*, or 0."""
    CLUSTER_ID = b'\x1F\x43\xB6\x75'
    max_ts = 0
    pos = 0
    while True:
        pos = buf.find(CLUSTER_ID, pos)
        if pos == -1:
            break
        # The Cluster Timestamp element (EBML ID 0xE7) is always the first element
        # inside a Cluster. Chrome uses an 8-byte unknown-size VINT for cluster size
        # (01 FF FF FF FF FF FF FF), placing E7 at pos+12. We search pos+5..pos+22
        # to also handle clusters with explicit sizes (1-4 byte VINTs).
        window_start = pos + 5
        window_end = min(pos + 22, len(buf))
        e7_idx = buf.find(b'\xe7', window_start, window_end)
        if e7_idx != -1 and e7_idx + 1 < len(buf):
            size_b = buf[e7_idx + 1]
            if size_b & 0x80:  # 1-byte VINT
                ts_size = size_b & 0x7F
                ts_bytes = buf[e7_idx + 2: e7_idx + 2 + ts_size]
                if len(ts_bytes) == ts_size:
                    ts_val = int.from_bytes(ts_bytes, 'big')
                    if 0 < ts_val < 86_400_000:  # sanity: > 0 and < 24 hours
                        max_ts = max(max_ts, ts_val)
        pos += 4
    return max_ts


def _read_webm_last_cluster_ms(path: Path) -> float:
    """
    Return the last WebM Cluster timestamp in *path*, in milliseconds.

    Chrome MediaRecorder writes a new Cluster every keyframe (~2-5 seconds for VP8).
    The last cluster's timestamp + 2000ms gives a close estimate of the true content
    duration — much more accurate than wall-clock time.

    Only the end of the file is read; the whole file is scanned (in chunks)
    only when the tail has no cluster. Returns 0.0 if none is found.
    """
    size = path.stat().st_size
    with open(path, "rb") as f:
        tail_start = max(0, size - _WEBM_TAIL_BYTES)
        f.seek(tail_start)
        best = _last_cluster_ts_in(f.read())
        if best or tail_start == 0:
            return float(best)
        f.seek(0)
        carry = b""
        while True:
            chunk = f.read(_WEBM_SCAN_CHUNK)
            if not chunk:
                break
            buf = carry + chunk
            best = max(best, _last_cluster_ts_in(buf))
            carry = buf[-32:]
    return float(best)


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
        # Signing rules / profile state are refreshed on the first poll only.
        self._first_poll = True
        # Read by the page's status line (plain values, set by this thread).
        self.polling = False
        self.last_poll_at = None
        self.last_poll_ok = None
        self.next_poll_at = None

    def run(self):
        self.log_msg.emit("[System] Monitoring worker thread active.")
        
        while self.running:
            self.polling = True
            poll_ok = False
            try:
                # 1. Fetch subscribed models
                self.log_msg.emit("[Monitor] Polling subscriptions status...")
                models = self.fetch_models(refresh_auth=self._first_poll)
                self._first_poll = False

                # 2. Build current status dict
                sessions = self.plugin.session_snapshot()
                model_statuses = {}
                for m in models:
                    if not m.active:
                        continue

                    username = m.name
                    is_live = m.model.get("hasStream", False)
                    expired_date = m.expired_string or "Active"

                    status = "Offline"
                    kind = (sessions.get(username) or (None, None))[0]
                    if kind == "recording":
                        status = "Recording 🔴"
                    elif kind == "probing":
                        status = "Probing 🔬"
                    elif kind == "connecting":
                        status = "Connecting 🟡"
                    elif is_live:
                        status = "Live 🟢"

                    # File counts are read here, not on the GUI thread.
                    count, tooltip = self.plugin.stream_files_summary(
                        username, self.save_location
                    )
                    model_statuses[username] = {
                        "username": username,
                        "subscription": expired_date,
                        "status": status,
                        "is_live": is_live,
                        "streams_count": count,
                        "streams_tooltip": tooltip,
                    }

                    # 3. If live and not already recording or connecting, spawn a session
                    already_active = kind is not None
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
                poll_ok = True
                self.status_updated.emit(model_statuses)
                
            except Exception as e:
                err_msg = str(e)
                if _is_auth_error(e):
                    running = list(self.plugin.session_snapshot())
                    self.log_msg.emit(f"\n[Error] {err_msg}")
                    if running:
                        self.log_msg.emit(
                            "[Monitor] API auth failed — pausing auto-capture polls, "
                            "but leaving in-progress capture(s) running: "
                            + ", ".join(running)
                        )
                    self.auth_error.emit()
                    break
                else:
                    self.log_msg.emit(f"[Error] Error in monitor loop: {e}")
                    self.log_msg.emit(traceback.format_exc())
                
            self.last_poll_at = time.time()
            self.last_poll_ok = poll_ok
            self.next_poll_at = self.last_poll_at + self.interval
            self.polling = False

            # Wait for next poll interval
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

        self.log_msg.emit("[System] Monitoring worker thread terminated.")

    def fetch_models(self, refresh_auth: bool = False):
        """Fetch subscriptions via the same API path as Areas / Select Models.

        Uses a Windows ``SelectorEventLoop`` (avoids Proactor under Qt) and mutes
        Rich Live activity updates so the poll works from this QThread.

        With *refresh_auth* (first poll of a monitor run) the signing-rule and
        profile caches are reset and /users/me is checked, like Authentication →
        Test. Later polls don't: resetting every poll re-downloaded the signing
        rules each minute and cleared them under a scrape running at the time.
        """
        import asyncio
        import sys
        from ofscraper.data.models.utils.retriver import get_models
        from ofscraper.utils.auth.file import read_auth
        from ofscraper.utils.live import updater as live_updater

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

        if refresh_auth:
            self._refresh_auth_state()

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

    def _refresh_auth_state(self):
        """Drop stale signing rules / profile cache, then check /users/me."""
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
            if of_wrong_user or _is_auth_error(e):
                hint = (
                    " Re-import cookies from a logged-in OnlyFans tab "
                    "(include auth_uid_ if 2FA is enabled)."
                )
            raise Exception(f"{msg}{detail}.{hint}".replace("..", ".").strip())



def _popen_logged(cmd, emit, env=None, timeout=None, cwd=None) -> int:
    """Run *cmd*, stream lines to *emit*, return exit code (Windows-safe unbuffered)."""
    run_env = os.environ.copy()
    if env:
        run_env.update(env)
    run_env["PYTHONUNBUFFERED"] = "1"
    run_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    emit(f"[Playwright] Running: {' '.join(str(c) for c in cmd)}")
    popen_kwargs: dict = {
        # No terminal input: a sudo password prompt fails fast instead of
        # waiting forever behind the GUI.
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "env": run_env,
        "bufsize": 1,
        "cwd": cwd,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except Exception as e:
        emit(f"[Playwright] Failed to start process: {e}")
        return 1
    try:
        assert proc.stdout is not None
        # Playwright progress often uses '\\r' without newlines; flush chunks.
        buf = ""
        while True:
            chunk = proc.stdout.read(256)
            if not chunk:
                break
            buf += chunk.replace("\r", "\n")
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                line = line.strip()
                if line:
                    emit(f"  {line}")
        if buf.strip():
            emit(f"  {buf.strip()}")
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
    # Do NOT name this ``finished`` — that shadows QThread.finished and can
    # close the install dialog / call slots with bad args when the thread ends.
    completed = pyqtSignal(bool)

    def __init__(self, browsers_path, deps_path):
        super().__init__()
        self.browsers_path = browsers_path
        self.deps_path = Path(deps_path)

    def _emit(self, msg: str) -> None:
        self.log_msg.emit(msg)

    def _pipx_inject(self) -> bool:
        """pipx venvs have no pip of their own: add playwright the pipx way."""
        pipx_bin = _find_pipx_binary()
        app = _pipx_venv_name() or "ofscraper"
        if not pipx_bin:
            self._emit("[Playwright] pipx not found on PATH.")
            return False
        self._emit(f"[Playwright] Adding playwright to the pipx app '{app}' (may take a few minutes)...")
        code = _popen_logged(
            [pipx_bin, "inject", "--force", app, PLAYWRIGHT_REQ],
            self._emit,
            timeout=900,
            cwd=str(Path.home()),  # like the patch: avoid a local package dir shadowing
        )
        if code == 0:
            self._emit("[Playwright] playwright installed via pipx inject.")
            return True
        self._emit(f"[Playwright] pipx inject failed (exit {code}).")
        return False

    def _uv_install(self) -> bool:
        """Add playwright to OF-Scraper's uv tool environment.

        Not ``uv tool install ofscraper --with playwright``: that reinstalls
        OF-Scraper and would remove the GUI patch.
        """
        uv_bin = _find_uv_binary()
        if not uv_bin:
            self._emit("[Playwright] uv not found (OF-Scraper was installed with uv).")
            return False
        self._emit("[Playwright] Installing playwright with uv (may take a few minutes)...")
        code = _popen_logged(
            [uv_bin, "pip", "install", PLAYWRIGHT_REQ, "--python", sys.executable],
            self._emit,
            timeout=900,
        )
        if code == 0:
            self._emit("[Playwright] playwright installed via uv pip.")
            return True
        self._emit(f"[Playwright] uv pip failed (exit {code}).")
        return False

    def _ensure_pip(self) -> bool:
        """True when ``python -m pip`` works, setting it up with ensurepip if needed."""
        def _has_pip() -> bool:
            try:
                return subprocess.run(
                    [sys.executable, "-m", "pip", "--version"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=60,
                    **(
                        {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
                        if sys.platform == "win32"
                        else {}
                    ),
                ).returncode == 0
            except Exception:
                return False

        if _has_pip():
            return True
        self._emit("[Playwright] pip is missing in this Python — setting it up with ensurepip...")
        _popen_logged(
            [sys.executable, "-u", "-m", "ensurepip", "--upgrade"], self._emit, timeout=300
        )
        if _has_pip():
            return True
        self._emit("[Playwright] pip is not available in this Python.")
        return False

    def _pip_install_venv(self) -> bool:
        if not self._ensure_pip():
            return False
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "pip",
            "install",
            "--upgrade",
            PLAYWRIGHT_REQ,
        ]
        self._emit("[Playwright] Installing playwright package into active Python (may take a few minutes)...")
        code = _popen_logged(cmd, self._emit, timeout=900)
        if code == 0:
            self._emit("[Playwright] playwright installed into the active Python environment.")
            return True
        self._emit(f"[Playwright] pip install failed (exit {code}).")
        return False

    def _pip_install_target(self) -> bool:
        if not self._ensure_pip():
            return False
        self.deps_path.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            "-u",
            "-m",
            "pip",
            "install",
            "--upgrade",
            PLAYWRIGHT_REQ,
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

        # Install with the same tool that installed OF-Scraper (as the GUI patch
        # does for PyQt6): pipx → pipx inject, uv → uv, pip → pip. pipx venvs
        # have no pip of their own ("No module named pip").
        attempts = {
            "pipx": [self._pipx_inject],
            "uv": [self._uv_install],
        }.get(
            install_method,
            # pip (also Docker's /opt/venv); the plugin's deps folder is the
            # last resort and must match this OS (never reuse host deps).
            [self._pip_install_venv, self._pip_install_target],
        )
        installed = False
        for attempt in attempts:
            if attempt():
                installed = True
                break

        if not installed:
            if install_method == "pipx":
                manual = f"pipx inject {_pipx_venv_name() or 'ofscraper'} playwright"
            elif install_method == "uv":
                manual = f"uv pip install playwright --python {sys.executable}"
            else:
                manual = f"{sys.executable} -m pip install playwright"
            self._emit(
                "[Error] Could not install playwright automatically. "
                f"Run this in a terminal: {manual}  — then click Install Chromium "
                f"again. Also delete {self.deps_path / 'playwright'} if it came "
                "from another OS."
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
        ok = False
        try:
            ok = self._run_install()
        except Exception as e:
            self._emit(f"[Error] Chromium install crashed: {type(e).__name__}: {e!r}")
            self._emit(traceback.format_exc())
            ok = False
        self.completed.emit(bool(ok))

    def _run_install(self) -> bool:
        self._emit("[Playwright] Initiating Chromium installation...")
        if not self._ensure_playwright_package():
            return False

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
            if _is_root():
                # Docker / root: install Chromium's system libraries with apt.
                deps_cmd = [sys.executable, "-m", "playwright", "install-deps", "chromium"]
                self._emit("[Playwright] Ensuring OS libs (apt)...")
                code = _popen_logged(deps_cmd, self._emit, env=env, timeout=600)
                if code != 0:
                    self._emit(
                        f"[Playwright] install-deps exited {code} "
                        "(continuing; the image may already have the libraries)."
                    )
            else:
                # As a normal user install-deps runs sudo, which asks for your
                # password (or fingerprint) in the terminal. Never do that from
                # the GUI: desktops usually have the libraries already, and the
                # launch check below says what to run if they don't.
                self._emit(
                    "[Playwright] Skipping system-library install (needs admin "
                    "rights). If Chromium can't start, run: "
                    + _install_deps_hint()
                )

        # If system Chrome/Edge works, skip the large Chromium download.
        # Probe in a subprocess — in-process launch under Qt crashes Windows GUIs.
        channel = _chromium_channel_for_host()
        if channel:
            self._emit(
                f"[Playwright] System browser channel={channel} detected — "
                "verifying launch out-of-process "
                "(bundled Chromium download not required)..."
            )
            ready, probe_detail = _probe_chromium_launch(
                channel=channel,
                browsers_path=self.browsers_path,
            )
            if ready:
                self._emit(f"[Playwright] System {channel} is ready for Live Monitor.")
                return True
            self._emit(
                f"[Playwright] System {channel} launch failed ({probe_detail}); "
                "falling back to bundled Chromium download..."
            )

        cmd = [sys.executable, "-u", "-m", "playwright", "install", "chromium"]
        self._emit(f"[Playwright] Target folder: {self.browsers_path}")
        self._emit("[Playwright] Downloading Chromium (this can take several minutes)...")
        code = _popen_logged(cmd, self._emit, env=env, timeout=1800)
        if code != 0:
            self._emit(f"[Error] playwright install chromium failed (exit {code}).")
            return False

        self._emit("[Playwright] Chromium download finished — verifying launch...")
        ready, probe_detail = _probe_chromium_launch(
            channel=None,
            browsers_path=self.browsers_path,
        )
        if ready:
            self._emit("[Playwright] Chromium browser install finished.")
            return True
        hint = (
            f"\n  If system libraries are missing: {_install_deps_hint()}"
            if sys.platform.startswith("linux")
            else ""
        )
        self._emit(
            f"[Error] Chromium installed but launch probe failed ({probe_detail}). "
            "Try closing OF-Scraper and re-running Install, or install manually:\n"
            f"  {sys.executable} -m playwright install chromium" + hint
        )
        return False


class ChromiumCheckWorker(QThread):
    """Run Playwright Chromium probe off the GUI thread."""
    completed = pyqtSignal(bool)

    def __init__(self, plugin):
        super().__init__()
        self._plugin = plugin

    def run(self):
        ok = False
        try:
            ok = bool(self._plugin.check_chromium_installed())
        except Exception:
            ok = False
        self.completed.emit(ok)


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
        # Stopped monitor workers still finishing a poll (kept so Qt doesn't
        # destroy a running QThread).
        self._retired_workers: list = []
        # Cached result of the Chromium check (None = not checked yet).
        self.chromium_ready = None

        # Guards the three session collections below: capture threads, the
        # poller and the GUI all use them.
        self._state_lock = threading.RLock()
        # username -> (thread, stop_event)  [browser launching / joining stream]
        self._connecting_recordings = {}
        # username -> (thread, stop_event, start_time)  [MediaRecorder actually running]
        self.active_recordings = {}
        # usernames currently in diagnostics-probe sessions (subset of connecting)
        self._probe_sessions: set = set()
        # username -> .webm being written (for the size shown in the table)
        self._recording_files: dict = {}

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
        # Remembered page settings: poll seconds, capture folder ("" = the
        # OF-Scraper save location) and whether Auto-Capture was left on.
        self.poll_interval = 60
        self.capture_dir = ""
        self.auto_capture = False
        # Desktop notification when a recording starts, is saved or fails.
        self.notify = True
        # Capture browser without any window (Chrome's new headless mode).
        self.no_window = True
        self._load_settings()

        self.log = logging.getLogger("ofscraper_plugins")
        self._log_bridge = _LogBridge()

    def on_load(self):
        self.log.info(f"Live Stream Monitor v{self.version} loaded.")

    @property
    def version(self) -> str:
        return str((getattr(self, "metadata", None) or {}).get("version") or "?")

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
                if "poll_interval" in data:
                    try:
                        self.poll_interval = min(
                            3600, max(10, int(data.get("poll_interval")))
                        )
                    except (TypeError, ValueError):
                        pass
                if isinstance(data.get("capture_dir"), str):
                    self.capture_dir = data["capture_dir"]
                if "auto_capture" in data:
                    self.auto_capture = bool(data.get("auto_capture"))
                if "notify" in data:
                    self.notify = bool(data.get("notify"))
                if "no_window" in data:
                    self.no_window = bool(data.get("no_window"))
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
                        "poll_interval": int(self.poll_interval),
                        "capture_dir": str(self.capture_dir or ""),
                        "auto_capture": bool(self.auto_capture),
                        "notify": bool(self.notify),
                        "no_window": bool(self.no_window),
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

    def set_page_settings(self, **values):
        """Save any of poll_interval / capture_dir / auto_capture / notify (only on change)."""
        changed = False
        for key in ("poll_interval", "capture_dir", "auto_capture", "notify", "no_window"):
            if key in values and getattr(self, key) != values[key]:
                setattr(self, key, values[key])
                changed = True
        if changed:
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
            # Give captures a moment to save their files.
            self.stop_monitor(wait_seconds=15)
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
        self.stop_monitor(wait_seconds=15)
        for worker in self._retired_workers:
            try:
                worker.wait(2000)
            except Exception:
                pass

    # ── Session state (thread-safe) ───────────────────────────────────────────

    def session_snapshot(self) -> dict:
        """Copy of current sessions: {username: (kind, start_time)}.

        kind is "recording", "connecting" or "probing"; start_time is set for
        recordings only. Safe to call from any thread.
        """
        with self._state_lock:
            out = {
                u: ("probing" if u in self._probe_sessions else "connecting", None)
                for u in self._connecting_recordings
            }
            for u, (_thread, _stop, start) in self.active_recordings.items():
                out[u] = ("recording", start)
            return out

    def _set_cooldown(self, username: str, seconds: float) -> None:
        with self._state_lock:
            self._capture_cooldown[username] = time.time() + seconds

    def _cooldown_left(self, username: str) -> float:
        with self._state_lock:
            return float(self._capture_cooldown.get(username) or 0) - time.time()

    def _end_session(self, username: str) -> None:
        with self._state_lock:
            self._connecting_recordings.pop(username, None)
            self.active_recordings.pop(username, None)
            self._probe_sessions.discard(username)
            self._recording_files.pop(username, None)

    def recording_size(self, username: str):
        """Bytes written so far by *username*'s recording, or None."""
        with self._state_lock:
            path = self._recording_files.get(username)
        if path is None:
            return None
        try:
            return os.stat(path).st_size
        except OSError:
            return None

    def _notify(self, title: str, username: str, detail: str = "") -> None:
        """Desktop notification (any thread); the name is masked in Privacy mode."""
        if not self.notify:
            return
        try:
            from ofscraper.gui.signals import app_signals
            from ofscraper.gui.utils.privacy_mode import mask_username

            name = mask_username(username) or username
            app_signals.show_notification.emit(title, f"{name}{detail}")
        except Exception as e:
            self.log.debug(f"Live monitor notification failed: {e}")

    def check_chromium_installed(self) -> bool:
        """Verify Playwright and a Chromium browser are installed and launchable.

        Slow (launches a browser in a subprocess): call it off the GUI thread.
        """
        browsers_path = _browsers_path_for_plugin()
        deps_path = Path(self.plugin_dir) / "deps"
        if not _prepare_playwright(deps_path):
            self.chromium_ready = False
            return False

        # Out-of-process probes only — never launch Chromium inside the Qt process
        # just to check install status (that path hard-crashes Windows GUIs).
        channel = _chromium_channel_for_host()
        if channel:
            ready, _detail = _probe_chromium_launch(
                channel=channel, browsers_path=browsers_path
            )
            if ready:
                self.chromium_ready = True
                return True
        ready, _detail = _probe_chromium_launch(
            channel=None, browsers_path=browsers_path
        )
        self.chromium_ready = bool(ready)
        return bool(ready)

    def install_chromium(self, log_sink=None, finished_cb=None):
        """Spawns background installer worker to download Chromium binary.

        Optional *log_sink* / *finished_cb* let modal dialogs own the UX while
        still falling back to the Live Monitor tab console.
        """
        from PyQt6.QtCore import Qt

        browsers_path = _browsers_path_for_plugin()
        deps_path = Path(self.plugin_dir) / "deps"

        self.install_worker = ChromiumInstallWorker(browsers_path, deps_path)
        sink = log_sink or (self.gui.append_log if self.gui else self._emit_log)
        self.install_worker.log_msg.connect(
            sink, Qt.ConnectionType.QueuedConnection
        )

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

        self.install_worker.completed.connect(
            _done, Qt.ConnectionType.QueuedConnection
        )
        self.install_worker.start()

    def start_monitor(self, interval, save_location):
        """Instantiates and starts the polling monitor worker thread."""
        self._retired_workers = [w for w in self._retired_workers if not w.isFinished()]
        self.worker = LiveMonitorWorker(self, interval, save_location)
        self.worker.log_msg.connect(self.gui.append_log)
        self.worker.status_updated.connect(self.gui.update_status_table)
        self.worker.auth_error.connect(self.gui.handle_auth_error)
        self.worker.start()

    def stop_monitor(self, *, terminate_recordings: bool = True, wait_seconds: float = 0):
        """Stops the monitor poll loop without blocking the GUI.

        When *terminate_recordings* is True (manual Stop), connecting/active
        capture threads are asked to stop; each one saves its file and removes
        itself. When False (API auth failure mid-capture), polls stop but
        Playwright recordings keep running until the stream ends or the user
        stops them. *wait_seconds* > 0 (unload / shutdown) waits up to that long
        in total for the captures to finish saving.
        """
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.running = False
            # The poll thread exits within ~1 s (or after the current poll);
            # keep a reference until then instead of waiting here.
            self._retired_workers.append(worker)

        if not terminate_recordings:
            return

        with self._state_lock:
            sessions = [
                (u, t, e) for u, (t, e) in self._connecting_recordings.items()
            ] + [
                (u, t, e) for u, (t, e, _start) in self.active_recordings.items()
            ]
        for username, _thread, stop_event in sessions:
            self._emit_log(f"[Monitor] Stopping capture for {username}...")
            stop_event.set()

        if wait_seconds > 0:
            deadline = time.monotonic() + wait_seconds
            for _username, thread, _stop in sessions:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                thread.join(timeout=remaining)

    def start_recording(self, username, save_location):
        """Spawns a new recording thread for a live creator."""
        with self._state_lock:
            if username in self._connecting_recordings or username in self.active_recordings:
                self._emit_log(f"[Capture] {username} already has an active session — skip.")
                return False
            left = self._cooldown_left(username)
            if left > 0:
                self._emit_log(f"[Capture] {username} on cooldown ({int(left)}s left) — skip.")
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
        with self._state_lock:
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
        with self._state_lock:
            connecting = self._connecting_recordings.get(username)
            active = self.active_recordings.get(username)
        if connecting is not None:
            connecting[1].set()
            self._emit_log(f"[Capture] Stopping connecting session for {username}…")
            stopped = True
        if active is not None:
            active[1].set()
            self._emit_log(f"[Capture] Stopping active capture for {username}…")
            stopped = True
        if stopped:
            # Brief cooldown so auto-capture doesn't immediately re-spawn
            self._set_cooldown(username, 30)
        return stopped

    def stop_all_captures(self) -> int:
        """Stop every connecting/active capture/probe; leave monitor poller running."""
        n = 0
        for u in list(self.session_snapshot()):
            if self.stop_capture(u):
                n += 1
        return n

    def stream_files_summary(self, username, save_location) -> tuple:
        """(count, tooltip) for a creator's recorded streams. Reads the disk:
        call it from the poll thread, not the GUI thread."""
        try:
            save_base = save_location or get_save_location()
            path = Path(save_base) / username / "Live_Streams"
            if not path.is_dir():
                return 0, "Directory does not exist yet (no captures started)"
            files = []
            for f in path.glob("*.webm"):
                if f.name.endswith(".tmp.webm") or not f.is_file():
                    continue
                st = f.stat()
                files.append((st.st_mtime, st.st_size, f.name))
            if not files:
                return 0, "No recorded streams found in directory"
            files.sort(reverse=True)
            lines = []
            for mtime, size, name in files[:10]:
                when = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                lines.append(f"  • {name} ({size / (1024 * 1024):.1f} MB) - {when}")
            if len(files) > 10:
                lines.append(f"  • ... and {len(files) - 10} more stream(s)")
            return len(files), "Recent Captures:\n" + "\n".join(lines)
        except Exception:
            return 0, ""

    def browser_profiles_dir(self) -> Path:
        return get_config_path().parent / "playwright_profiles"

    def clear_browser_profiles(self) -> int:
        """Delete the saved capture-browser logins (one Chrome profile per creator).

        Refuses while a capture is running. Returns how many were removed.
        """
        if self.session_snapshot():
            raise RuntimeError("Stop all captures first.")
        root = self.browser_profiles_dir()
        if not root.is_dir():
            return 0
        count = sum(1 for p in root.iterdir() if p.is_dir())
        shutil.rmtree(root)
        return count

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
        try:
            info = resolve_live_join(username)
        except Exception as e:
            # Always surface the message in the plugin log (Qt/faulthandler
            # may otherwise make a bare raise look like a silent crash).
            self._emit_log(f"[API] resolve_live_join failed: {type(e).__name__}: {e}")
            raise
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

            _prepare_playwright(Path(self.plugin_dir) / "deps")

            from playwright.sync_api import sync_playwright
            from ofscraper.utils.auth.file import read_auth

            # Holds this creator's browser login: keep it private to the user.
            _private_dir(config_dir / "playwright_profiles")
            profile_dir = _reset_profile(config_dir / "playwright_profiles" / username)

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
            live_url = report["live_url"]
            prefer_hidden = bool(getattr(self, "headless_capture", True)) and not bool(
                getattr(self, "no_window", False)
            )
            traffic = []
            api_samples = []
            seen_req = set()

            self._emit_log(f"[Probe] Launching browser for {username} (diagnostics only)...")

            with sync_playwright() as p:
                launch_kwargs = _capture_launch_kwargs(
                    profile_dir, prefer_hidden, user_agent,
                    headless=bool(getattr(self, "no_window", False)),
                )
                rec_ctx = _launch_capture_context(p, launch_kwargs, self._emit_log)
                if cookies_to_add:
                    rec_ctx.add_cookies(cookies_to_add)
                session_script = _session_init_script(auth)
                if session_script:
                    rec_ctx.add_init_script(session_script)
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
                                                "text_preview": redact_text(body[:400]),
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
                    if not _wait_for_live_url(rec_page, username, stop_event, 180):
                        self._emit_log(
                            "[Probe] Login not finished (timed out or stopped) — "
                            "writing partial report."
                        )
                        rec_ctx.close()
                        raise RuntimeError("login_timeout")
                    rec_page.wait_for_timeout(3000)

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
                    stop_event.wait(1)

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
            self._end_session(username)

    def record_stream(self, username, save_location, stop_event):
        """Playwright-based WebRTC stream recorder task."""
        final_path = None
        recording_started = False
        login_timed_out = False
        _chunk_file = None
        try:
            config_dir = get_config_path().parent
            _browsers_path_for_plugin()

            _prepare_playwright(Path(self.plugin_dir) / "deps")

            from playwright.sync_api import sync_playwright

            save_base = save_location or get_save_location()
            save_dir = Path(save_base) / username / "Live_Streams"
            save_dir.mkdir(parents=True, exist_ok=True)

            # Per-model persistent browser profile. Chromium saves the full session
            # (cookies, local storage, cf_clearance) after the first manual login so
            # every subsequent capture is fully automatic. Using per-model subdirs
            # allows concurrent captures of different models without profile-lock conflicts.
            # Holds this creator's browser login: keep it private to the user.
            _private_dir(config_dir / "playwright_profiles")
            profile_dir = _reset_profile(config_dir / "playwright_profiles" / username)

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


            live_url = f"https://onlyfans.com/{username}/live"
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

                # One context for auth + recording. The login comes from
                # Authentication: cookies + its user-agent + x-bc (bcTokenSha).
                no_window = bool(getattr(self, "no_window", False))
                prefer_hidden = bool(getattr(self, "headless_capture", True)) and not no_window
                launch_kwargs = _capture_launch_kwargs(
                    profile_dir, prefer_hidden, user_agent, headless=no_window
                )
                channel = launch_kwargs.get("channel")
                if channel:
                    self._emit_log(f"[Playwright] Using browser channel={channel}.")
                if no_window:
                    self._emit_log("[Playwright] Capture browser runs without a window (headless).")
                elif prefer_hidden:
                    self._emit_log("[Playwright] Capture window will stay off-screen.")

                rec_ctx = _launch_capture_context(p, launch_kwargs, self._emit_log)
                if cookies_to_add:
                    rec_ctx.add_cookies(cookies_to_add)
                session_script = _session_init_script(auth)
                if session_script:
                    rec_ctx.add_init_script(session_script)

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

                if "return_to" in current_url and no_window:
                    login_timed_out = True
                    self._emit_log(
                        "[Playwright] OnlyFans didn't accept the Authentication login "
                        "(it showed the login page). Re-import cookies in the "
                        "Authentication tab and make sure Test passes; or untick "
                        "\"No window\" to log in by hand in the capture window."
                    )
                    rec_ctx.close()
                    return

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
                    if not _wait_for_live_url(rec_page, username, stop_event, 180):
                        if stop_event.is_set():
                            self._emit_log("[Playwright] Stopped while waiting for login.")
                        else:
                            login_timed_out = True
                            self._emit_log(
                                "[Playwright] Login timed out — aborting capture "
                                "(auto-capture retries this creator in 10 min)."
                            )
                        rec_ctx.close()
                        return
                    rec_page.wait_for_timeout(5000)

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
                    if stop_event.wait(5):
                        self._emit_log("[Playwright] Stopped while waiting for the player.")
                        rec_ctx.close()
                        return
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
                if not self.show_diagnostics:
                    self._emit_log(
                        f"[Playwright] Player: {len(diag.get('videos') or [])} video "
                        f"element(s), audio tap ready: {bool(diag.get('audioTapTrack'))}"
                    )
                else:
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
                    for ap in diag.get("audioPlays", []):
                        self._emit_log(
                            f"[Diag] AudioPlay[{ap['i']}] inDom={ap.get('inDom')} "
                            f"srcType={ap.get('srcType')} audioTracks={ap.get('audioTracks')}"
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
                    recording_started = True
                    with self._state_lock:
                        self._connecting_recordings.pop(username, None)
                        self.active_recordings[username] = (
                            threading.current_thread(), stop_event, rec_start_time
                        )
                        self._recording_files[username] = final_path
                    self._notify("Live recording started", username)
                else:
                    reason = recorder_result.get("reason", "unknown") if isinstance(recorder_result, dict) else recorder_result
                    self._emit_log(f"[Playwright] Warning: MediaRecorder failed ({reason}) — stream may not be captured.")

                offline_counter = 0
                max_offline = 360  # 360 × 5 s = 30 min fallback for hung sessions
                diag_tick = 0      # re-run audio diagnostic every 12 polls (60 s)
                end_watch = _StreamEndWatch(username)

                while not stop_event.is_set():
                    stop_event.wait(5)

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
                                end_watch.got_data()
                        except Exception:
                            pass

                    if rec_page.is_closed():
                        self._emit_log(f"[Playwright] Page closed for {username}.")
                        break

                    # Periodic re-diagnostic so we see the DOM once actual live content starts
                    diag_tick += 1
                    if self.show_diagnostics and diag_tick % 12 == 0:
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

                    # After a stream ends the page can stay on /live with a frozen
                    # "playing" video, so ask OnlyFans (twice, to ride out a blip).
                    end_reason = end_watch.reason()
                    if end_reason:
                        self._emit_log(f"[Playwright] {end_reason} — stopping.")
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
                self._finalize_recording(final_path, rec_start_time, last_chunk_time)
                self._notify("Live recording saved", username)
            else:
                self._emit_log(f"[Capture] No data was recorded for {username}.")

        except Exception as ex:
            self._emit_log(f"[Error] Stream capture failed for {username}: {ex}")
            self._emit_log(traceback.format_exc())
        finally:
            if _chunk_file:
                try:
                    _chunk_file.close()
                except Exception:
                    pass
            # Don't leave empty files behind (they'd count as recorded streams).
            try:
                if final_path is not None and final_path.exists() and final_path.stat().st_size == 0:
                    final_path.unlink()
            except OSError:
                pass
            # Any start that didn't reach recording waits before auto-capture
            # tries again (a manual Stop sets its own 30 s cooldown).
            if not recording_started and not stop_event.is_set():
                self._set_cooldown(username, 600 if login_timed_out else 120)
                self._notify(
                    "Live capture failed", username, " — see the Live Monitor console"
                )
            self._end_session(username)

    def _finalize_recording(self, final_path: Path, rec_start_time, last_chunk_time):
        """Write the duration into a finished WebM (players show 00:00 otherwise)."""
        # Best duration estimate, used only if ffmpeg can't remux:
        # 1st choice: last WebM cluster timestamp (actual media time)
        # 2nd choice: wall-clock from rec start to last chunk written
        duration_ms = 0.0
        try:
            cluster_ms = _read_webm_last_cluster_ms(final_path)
            if cluster_ms > 0:
                # Add 2 s to cover frames written after the last cluster timestamp.
                duration_ms = cluster_ms + 2000.0
        except Exception:
            pass
        if duration_ms <= 0 and rec_start_time:
            ref = last_chunk_time if last_chunk_time else datetime.datetime.now()
            duration_ms = (ref - rec_start_time).total_seconds() * 1000.0

        # ffmpeg reads the real media timestamps; the EBML patch is the fallback.
        ffmpeg_bin = _ffmpeg_binary()
        if not ffmpeg_bin:
            _patch_webm_duration(final_path, duration_ms, self._emit_log)
            return
        tmp_path = final_path.with_name(final_path.stem + ".tmp.webm")
        timeout = _remux_timeout(final_path)
        try:
            proc = subprocess.run(
                [ffmpeg_bin, "-y", "-i", str(final_path), "-c", "copy", str(tmp_path)],
                capture_output=True, timeout=timeout,
            )
            if proc.returncode == 0 and tmp_path.exists() and tmp_path.stat().st_size > 0:
                os.replace(tmp_path, final_path)
                self._emit_log("[Capture] Duration metadata written (ffmpeg).")
                return
            tmp_path.unlink(missing_ok=True)
            self._emit_log("[Capture] ffmpeg failed — trying EBML patch.")
        except subprocess.TimeoutExpired:
            tmp_path.unlink(missing_ok=True)
            self._emit_log(f"[Capture] ffmpeg took over {timeout}s — trying EBML patch.")
        except Exception as fe:
            tmp_path.unlink(missing_ok=True)
            self._emit_log(f"[Capture] ffmpeg error ({fe}) — trying EBML patch.")
        _patch_webm_duration(final_path, duration_ms, self._emit_log)

    def get_streams_count(self, username, save_location) -> int:
        """Returns the number of saved WebM live streams in the model's directory."""
        try:
            return self.stream_files_summary(username, save_location)[0]
        except Exception:
            return 0
