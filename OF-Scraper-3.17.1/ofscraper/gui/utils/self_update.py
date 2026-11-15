"""Update now: download the new GUI patch script, close the GUI, run it.

1. ``download_patch`` saves the patch script from GitHub to
   ``<config>/gui_updates/`` and checks it: it must be Python that compiles
   and carry the patch number the update check found.
2. ``launch_after_exit`` starts a helper in a new console window. The helper
   waits for the GUI process to exit, then runs the patch script in that
   console, where its prompts can be answered; the script itself offers to
   start the GUI again at the end.
3. The caller closes the GUI.

The patch script runs with a Python outside OF-Scraper's own pipx / uv
environment (``patch_python``): the patch may rebuild that environment, and
Windows can't replace a python.exe that is running.
"""

from __future__ import annotations

import logging
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys

log = logging.getLogger("shared")

_PATCH_NAME_RE = re.compile(r"patch_ofscraper_\d+(?:\.\d+)+_gui\.py$")


class UpdateFailed(Exception):
    """The update couldn't be prepared; the message says why."""


def updates_dir() -> pathlib.Path:
    import ofscraper.utils.paths.common as common_paths

    return pathlib.Path(common_paths.get_config_home()) / "gui_updates"


def _patch_id(text: str) -> str | None:
    m = re.search(r'^PATCH_ID\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else None


def verify_patch(path, expected_patch: int | None) -> str:
    """The PATCH_ID of a downloaded patch script; UpdateFailed if it isn't one."""
    from ofscraper.gui.utils.version_check import parse_patch_id

    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise UpdateFailed(f"the download can't be read: {e}") from e
    try:
        compile(text, str(path), "exec")
    except SyntaxError as e:
        raise UpdateFailed("the download isn't a complete patch script") from e
    patch_id = _patch_id(text)
    if not patch_id or "ZIP_B64" not in text:
        raise UpdateFailed("the download isn't a GUI patch script")
    found = parse_patch_id(patch_id).patch
    if expected_patch is not None and found != expected_patch:
        raise UpdateFailed(
            f"the download is patch v{found}, not v{expected_patch} as expected; try again"
        )
    return patch_id


def download_patch(url: str, expected_patch: int | None, timeout: float = 60.0) -> pathlib.Path:
    """Download the patch script; returns its path once verified."""
    if not url:
        raise UpdateFailed("this update has no patch script to download")
    name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if not _PATCH_NAME_RE.search(name):
        raise UpdateFailed(f"unexpected download name: {name}")
    folder = updates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    partial = folder / (name + ".part")
    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(partial, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
    except Exception as e:
        partial.unlink(missing_ok=True)
        raise UpdateFailed(f"the download failed: {e}") from e
    try:
        verify_patch(partial, expected_patch)
    except UpdateFailed:
        partial.unlink(missing_ok=True)
        raise
    os.replace(partial, target)
    log.info(f"[GUI] Downloaded the GUI update to {target}")
    return target


# --- the Python and console that run it ------------------------------------------------


def _inside(path: str, folder: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), os.path.realpath(folder)]) == os.path.realpath(folder)
    except ValueError:  # different drives
        return False


def patch_python() -> list[str]:
    """A Python command outside OF-Scraper's own environment, else []."""
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if not in_venv:
        # pip install into this Python: the patch updates it in place
        return [sys.executable]
    base = getattr(sys, "_base_executable", "") or ""
    if base and os.path.isfile(base) and not _inside(base, sys.prefix):
        return [base]
    if platform.system() == "Windows" and shutil.which("py"):
        return [shutil.which("py"), "-3"]
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and not _inside(found, sys.prefix):
            return [found]
    return []


# Waits for the GUI (argv[1] = its pid) to exit, then runs the patch script
# (argv[2:] = python command + script) here, then waits for Enter.
HELPER = r'''
import os, subprocess, sys, time
pid = int(sys.argv[1]); cmd = sys.argv[2:]

def alive(p):
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x00100000 | 0x1000, False, p)  # SYNCHRONIZE | QUERY_LIMITED
        if not h:
            return False
        try:
            return k.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT
        finally:
            k.CloseHandle(h)
    try:
        os.kill(p, 0)
        return True
    except OSError:
        return False

print("OF-Scraper GUI update")
print("Waiting for OF-Scraper to close...", flush=True)
start = time.time()
while alive(pid):
    if time.time() - start > 600:
        print("OF-Scraper is still open after 10 minutes. Close it, then run:")
        print("  " + " ".join('"%s"' % c if " " in c else c for c in cmd))
        input("Press Enter to close this window.")
        sys.exit(1)
    time.sleep(0.5)
time.sleep(1)
print("Running " + cmd[-1], flush=True)
print()
code = subprocess.call(cmd, cwd=os.path.dirname(cmd[-1]) or None)
print()
print("The patch script finished." if code == 0 else "The patch script stopped (exit code %d)." % code)
input("Press Enter to close this window.")
'''


_LINUX_TERMINALS = (
    ("x-terminal-emulator", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("foot", []),
    ("tilix", ["-e"]),
    ("mate-terminal", ["-x"]),
    ("lxterminal", ["-e"]),
    ("xterm", ["-e"]),
)


def terminal_command(inner: list[str]) -> list[str] | None:
    """inner wrapped to run in a terminal emulator (Linux), or None."""
    for name, flag in _LINUX_TERMINALS:
        exe = shutil.which(name)
        if exe:
            return [exe, *flag, *inner]
    return None


def gui_pid() -> int:
    """The process to wait for: the tab window when this GUI runs in a tab."""
    from ofscraper.gui import site_context

    return os.getppid() if site_context.is_child() else os.getpid()


def launch_after_exit(script: pathlib.Path, wait_pid: int | None = None) -> None:
    """Open a console that runs ``script`` once the GUI has exited."""
    python = patch_python()
    if not python:
        raise UpdateFailed(
            "no Python outside OF-Scraper's own environment was found to run the patch"
        )
    # a file, not -c: terminal programs can mangle a long multi-line argument
    helper = pathlib.Path(script).parent / "run_gui_update.py"
    helper.write_text(HELPER, encoding="utf-8")
    inner = [*python, str(helper), str(wait_pid or gui_pid()), *python, str(script)]
    system = platform.system()
    if system == "Windows":
        flags = (getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
                 | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x200))
        try:  # outlive the GUI even inside a job that would close with it
            subprocess.Popen(inner, creationflags=flags | 0x01000000, close_fds=True)  # BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(inner, creationflags=flags, close_fds=True)
        return
    if system == "Linux":
        cmd = terminal_command(inner)
        if cmd is None:
            raise UpdateFailed("no terminal window program was found to run the patch in")
        subprocess.Popen(cmd, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return
    raise UpdateFailed(f"updating from the GUI isn't supported on {system}")


def manual_command(script: pathlib.Path) -> str:
    python = patch_python() or ["python"]
    return " ".join(f'"{p}"' if " " in p else p for p in [*python, str(script)])


# --- the GUI side --------------------------------------------------------------------


def close_gui() -> None:
    """Close the whole GUI: the tab window when this runs in a tab (it asks
    first if a site is downloading), else this window."""
    from ofscraper.gui import site_context

    if site_context.is_child():
        site_context.send("close_all")
        return
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        app.closeAllWindows()


def start_update(parent, result) -> None:
    """Ask, download the patch, open the console that runs it, close the GUI."""
    from PyQt6.QtCore import QThreadPool, QUrl
    from PyQt6.QtGui import QDesktopServices
    from PyQt6.QtWidgets import QMessageBox

    from ofscraper.gui.utils.thread_worker import Worker

    testing = getattr(result, "channel", "") == "testing"
    answer = QMessageBox.question(
        parent,
        "Update now",
        ("Download the new testing build and install it?\n\n" if testing
         else "Download the new GUI release and install it?\n\n")
        + "OF-Scraper closes (a running scrape is asked about first), and a console "
        "window runs the patch script. Answer its questions there; at the end it "
        "offers to start the GUI again.",
    )
    if answer != QMessageBox.StandardButton.Yes:
        return

    def _prepare():
        script = download_patch(result.download_url, getattr(result, "latest_patch", None))
        try:
            launch_after_exit(script)
        except UpdateFailed as e:
            return script, str(e)
        return script, None

    def _ready(outcome):
        script, problem = outcome
        if problem:
            QMessageBox.information(
                parent, "Run the update yourself",
                f"The patch script was downloaded, but it can't be started from here: "
                f"{problem}.\n\nClose OF-Scraper, then run:\n{manual_command(script)}",
            )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(script.parent)))
            return
        close_gui()

    def _failed(message):
        QMessageBox.warning(parent, "Update failed", f"Couldn't update: {message}")

    worker = Worker(_prepare)
    worker.signals.finished.connect(_ready)
    worker.signals.error.connect(_failed)
    parent._update_now_worker = worker  # keep it alive
    QThreadPool.globalInstance().start(worker)
