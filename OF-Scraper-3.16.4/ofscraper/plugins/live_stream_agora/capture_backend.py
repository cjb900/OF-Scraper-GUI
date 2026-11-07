"""OS-aware capture backend selection for Live Stream Agora."""

from __future__ import annotations

import os
import platform

# Process-wide override from GUI / env (None = use OS default)
_FORCE_BACKEND: str | None = None

# Agora connection_changed reasons we care about
AGORA_REASON_NAMES = {
    0: "CONNECTING",
    1: "JOIN_SUCCESS",
    2: "INTERRUPTED",
    3: "BANNED_BY_SERVER",
    4: "JOIN_FAILED",
    5: "LEAVE_CHANNEL",
    6: "INVALID_APP_ID",
    7: "INVALID_CHANNEL_NAME",
    8: "INVALID_TOKEN",
    9: "TOKEN_EXPIRED",
    10: "REJECTED_BY_SERVER",
    11: "SETTING_PROXY_SERVER",
    12: "RENEW_TOKEN",
    14: "KEEP_ALIVE_TIMEOUT",
    19: "SAME_UID_LOGIN",
}


def host_os() -> str:
    """Return 'windows', 'linux', 'darwin', or lowercase platform.system()."""
    s = platform.system()
    if s == "Windows":
        return "windows"
    if s == "Linux":
        return "linux"
    if s == "Darwin":
        return "darwin"
    return (s or "unknown").lower()


def set_force_backend(backend: str | None) -> None:
    """
    Override preferred backend for this process.

    ``backend`` is ``\"playwright\"``, ``\"agora\"``, or ``None`` (clear).
    """
    global _FORCE_BACKEND
    if backend is None or str(backend).strip() == "":
        _FORCE_BACKEND = None
        return
    b = str(backend).strip().lower()
    if b not in ("playwright", "agora"):
        raise ValueError(f"unsupported backend: {backend}")
    _FORCE_BACKEND = b


def get_force_backend() -> str | None:
    return _FORCE_BACKEND


def preferred_capture_backend() -> str:
    """
    Capture engine for this host.

    Defaults (OF's Agora edge rejects agora_python_server_sdk joins with
    CONNECTION_CHANGED_REJECTED_BY_SERVER / reason 10 — browser WebRTC /
    Playwright MediaRecorder is the reliable path on all OS):

    - windows → playwright (SDK has no Windows natives anyway)
    - linux / darwin → playwright (same MediaRecorder path as Windows)
    - override via set_force_backend() or env OFSC_LIVE_AGORA_BACKEND=agora|playwright
    """
    if _FORCE_BACKEND:
        return _FORCE_BACKEND
    env = (os.environ.get("OFSC_LIVE_AGORA_BACKEND") or "").strip().lower()
    if env in ("playwright", "agora"):
        return env
    os_id = host_os()
    if os_id == "windows":
        return "playwright"
    if os_id in ("linux", "darwin"):
        # Native Agora join is rejected by OF (see agoraapi.log reason:10).
        # Playwright works on Linux the same way as Windows.
        return "playwright"
    return "playwright"


def backend_label(backend: str | None = None) -> str:
    b = backend or preferred_capture_backend()
    if b == "playwright":
        return "Playwright (Chromium MediaRecorder)"
    if b == "agora":
        return "Native Agora RTC (experimental)"
    return b


def agora_reason_name(reason: int | str | None) -> str:
    try:
        code = int(reason)  # type: ignore[arg-type]
    except Exception:
        return str(reason)
    return AGORA_REASON_NAMES.get(code, f"UNKNOWN({code})")


def os_capture_summary() -> str:
    os_id = host_os()
    backend = preferred_capture_backend()
    if os_id == "windows":
        return (
            f"Windows detected — capture uses {backend_label(backend)}. "
            "Native Agora SDK has no Windows libs; Fetch Agora creds is "
            "API-only diagnostics."
        )
    if os_id == "darwin":
        return (
            f"macOS detected — capture uses {backend_label(backend)}. "
            "OF rejects native agora_python_server_sdk joins (reason 10); "
            "Playwright is the default. Enable experimental Agora only to test."
        )
    if os_id == "linux":
        return (
            f"Linux detected — capture uses {backend_label(backend)}. "
            "OF rejects native Agora Server SDK channel joins "
            "(CONNECTION_CHANGED_REJECTED_BY_SERVER). Playwright MediaRecorder "
            "is the working path (same as Windows)."
        )
    return f"OS={os_id} — default capture backend: {backend_label(backend)}."


def find_playwright_live_plugin():
    """Return loaded live_stream_monitor Plugin instance, or None."""
    try:
        from ofscraper.plugins.manager import PluginManager

        pm = PluginManager()
        return pm.get_loaded_plugin("live_stream_monitor")
    except Exception:
        return None


def ensure_playwright_live_plugin(main_window=None, log=None):
    """
    Ensure live_stream_monitor is loaded (enable + Load now if needed).

    Returns (plugin_or_None, message).
    """
    emit = log or (lambda m: None)
    existing = find_playwright_live_plugin()
    if existing is not None:
        return existing, "already loaded"

    try:
        from ofscraper.plugins.manager import PluginManager

        pm = PluginManager()
    except Exception as e:
        return None, f"PluginManager unavailable: {e}"

    if not pm.plugins_dir:
        return None, "Plugins folder unavailable"

    plugin_dir = pm.plugins_dir / "live_stream_monitor"
    if not plugin_dir.is_dir() or not (plugin_dir / "main.py").is_file():
        return (
            None,
            "live_stream_monitor is not installed under the plugins folder. "
            "Copy example_plugins/live_stream_monitor there first.",
        )

    try:
        enabled = pm.read_enabled_flag(plugin_dir / "main.py")
    except Exception:
        enabled = True
    if not enabled:
        emit("[Capture] Enabling live_stream_monitor (was disabled)…")
        try:
            pm.set_enabled_flag("live_stream_monitor", True)
        except Exception as e:
            return None, f"Could not enable live_stream_monitor: {e}"

    emit("[Capture] Loading Live Stream Monitor for Playwright capture…")
    try:
        ok, msg = pm.load_plugin_now("live_stream_monitor", main_window=main_window)
    except Exception as e:
        return None, f"load_plugin_now failed: {e}"

    plugin = find_playwright_live_plugin()
    if plugin is not None:
        emit(f"[Capture] {msg}")
        return plugin, msg

    return None, msg or "Live Stream Monitor failed to load"
