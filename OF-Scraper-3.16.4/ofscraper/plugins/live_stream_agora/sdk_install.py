"""Install agora_python_server_sdk into the same environment as ofscraper."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

PKG = "agora_python_server_sdk>=2.4.9"
RECOMMENDED_SDK_VERSION = "2.4.9"
MIN_SDK_VERSION = "2.4.6"
LogFn = Callable[[str], None]


def installed_sdk_version() -> str | None:
    """Return installed agora_python_server_sdk version string, or None."""
    try:
        from importlib.metadata import version

        return version("agora_python_server_sdk")
    except Exception:
        try:
            import agora  # type: ignore

            return getattr(agora, "__version__", None)
        except Exception:
            return None


def _version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for p in (v or "").split("."):
        digits = "".join(c for c in p if c.isdigit())
        if digits:
            parts.append(int(digits))
        else:
            break
    return tuple(parts) if parts else (0,)


def sdk_version_status() -> tuple[str | None, bool, str]:
    """
    Return (version, ok_enough, message).

    ``ok_enough`` is True when version >= MIN_SDK_VERSION (2.4.6).
    """
    ver = installed_sdk_version()
    if not ver:
        return None, False, "agora_python_server_sdk version unknown (not installed?)"
    if _version_tuple(ver) < _version_tuple(MIN_SDK_VERSION):
        return (
            ver,
            False,
            f"agora_python_server_sdk {ver} < {MIN_SDK_VERSION} "
            f"(Agora fixed same-UID join bugs in 2.4.6+; upgrade to {RECOMMENDED_SDK_VERSION})",
        )
    if _version_tuple(ver) < _version_tuple(RECOMMENDED_SDK_VERSION):
        return (
            ver,
            True,
            f"agora_python_server_sdk {ver} OK (>= {MIN_SDK_VERSION}); "
            f"recommend {RECOMMENDED_SDK_VERSION}",
        )
    return ver, True, f"agora_python_server_sdk {ver} OK"


def detect_ofscraper_install_method() -> str:
    """Return 'uv', 'pipx', or 'pip' based on how ofscraper is installed."""
    home = Path.home()
    is_win = platform.system() == "Windows"

    uv_tool_env = os.environ.get("UV_TOOL_DIR")
    if uv_tool_env:
        uv_cands = [Path(uv_tool_env)]
    elif is_win:
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        uv_cands = [
            Path(appdata) / "uv" / "data" / "tools",
            Path(appdata) / "uv" / "tools",
        ]
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
        uv_cands = [Path(xdg) / "uv" / "tools"]
    for d in uv_cands:
        if (d / "ofscraper").is_dir():
            return "uv"

    pipx_env = os.environ.get("PIPX_HOME")
    if pipx_env:
        pipx_cands = [Path(pipx_env)]
    elif is_win:
        pipx_cands = [
            home / "pipx",
            home / "AppData" / "Local" / "pipx",
            home / ".local" / "pipx",
        ]
    else:
        pipx_cands = [
            home / ".local" / "share" / "pipx",
            home / ".local" / "pipx",
        ]
    for d in pipx_cands:
        if (d / "venvs" / "ofscraper").is_dir():
            return "pipx"

    exe = str(sys.executable).replace("\\", "/").lower()
    if "uv" in exe and "tools" in exe:
        return "uv"
    if "pipx" in exe:
        return "pipx"
    return "pip"


def find_uv_binary() -> str | None:
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


def find_pipx_binary() -> str | None:
    found = shutil.which("pipx")
    if found:
        return found
    home = Path.home()
    is_win = platform.system() == "Windows"
    if is_win:
        candidates = [
            home / ".local" / "bin" / "pipx.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "pipx" / "pipx.exe",
        ]
    else:
        candidates = [
            home / ".local" / "bin" / "pipx",
        ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def describe_install_plan() -> tuple[str, list[str], str]:
    """
    Return (method, argv, human_summary).

    Maps to how ofscraper itself was installed:
      - uv   → ``uv pip install … --python <ofscraper python>``
      - pipx → ``pipx inject ofscraper …`` (fallback: pip into active venv)
      - pip  → ``python -m pip install …`` into ``sys.executable``
    """
    method = detect_ofscraper_install_method()

    if method == "uv":
        uv = find_uv_binary()
        if uv:
            cmd = [uv, "pip", "install", PKG, "--python", sys.executable]
            return (
                method,
                cmd,
                f"uv tool env -> uv pip install into {sys.executable}",
            )
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PKG]
        return (
            method,
            cmd,
            f"uv detected but uv binary missing -> pip into {sys.executable}",
        )

    if method == "pipx":
        pipx = find_pipx_binary()
        if pipx:
            cmd = [pipx, "inject", "ofscraper", PKG]
            return method, cmd, "pipx -> pipx inject ofscraper <pkg>"
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PKG]
        return (
            method,
            cmd,
            f"pipx detected but pipx binary missing -> pip into {sys.executable}",
        )

    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", PKG]
    return method, cmd, f"pip/venv -> {sys.executable} -m pip install"


def _popen_logged(cmd: list[str], emit: LogFn, timeout: int = 900) -> int:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    emit(f"[SDK] Running: {' '.join(str(c) for c in cmd)}")
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
    except Exception as e:
        emit(f"[SDK] Failed to start process: {e}")
        return 1
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            emit(f"  {line.rstrip()}")
        return int(proc.wait(timeout=timeout) if timeout else proc.wait())
    except subprocess.TimeoutExpired:
        emit(f"[SDK] Timed out after {timeout}s — killing process.")
        try:
            proc.kill()
        except Exception:
            pass
        return 1
    except Exception as e:
        emit(f"[SDK] Process error: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return 1


def install_agora_sdk(emit: LogFn | None = None) -> bool:
    """
    Install agora_python_server_sdk into ofscraper's environment.

    Returns True if the install command exited 0. Caller should re-check
    ``sdk_available()`` afterward (Windows still won't have native RTC libs).
    """
    log = emit or (lambda m: None)
    method, cmd, summary = describe_install_plan()
    log(f"[SDK] Detected ofscraper install method: {method}")
    log(f"[SDK] Plan: {summary}")

    if platform.system() == "Windows":
        log(
            "[SDK] Note: even if pip/pipx/uv reports success, Agora's Python "
            "Server SDK has no Windows native binaries — join still needs "
            "Linux/macOS or WSL2."
        )

    code = _popen_logged(cmd, log, timeout=900)
    if code == 0:
        log("[SDK] Install command finished OK.")
        # Secondary fallback: if pipx inject worked but import still fails from
        # a different interpreter, also try active-venv pip (rare).
        return True

    log(f"[SDK] Primary install failed (exit {code}).")

    # Fallbacks mirror Live Stream Monitor / GUI patch behavior
    if method == "uv":
        log("[SDK] Falling back to active-interpreter pip…")
        fb = [sys.executable, "-m", "pip", "install", "--upgrade", PKG]
        if _popen_logged(fb, log, timeout=900) == 0:
            log("[SDK] Fallback pip install OK.")
            return True
    elif method == "pipx":
        log("[SDK] Falling back to pip inside active ofscraper venv…")
        fb = [sys.executable, "-m", "pip", "install", "--upgrade", PKG]
        if _popen_logged(fb, log, timeout=900) == 0:
            log("[SDK] Fallback pip install OK.")
            return True

    log(
        "[SDK] Install failed. Manual options:\n"
        "  uv:   uv pip install agora_python_server_sdk --python <ofscraper python>\n"
        "  pipx: pipx inject ofscraper agora_python_server_sdk\n"
        "  pip:  python -m pip install agora_python_server_sdk\n"
        f"  (this process python: {sys.executable})"
    )
    return False
