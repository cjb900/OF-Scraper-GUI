import json
import logging
import os
import platform
import re
import struct
import subprocess
import traceback

from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QDesktopServices, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font, scale_px
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton
import ofscraper.utils.paths.common as common_paths
import ofscraper.utils.auth.request as _auth_req
import ofscraper.utils.auth.cookie_allowlist as cookie_allowlist

log = logging.getLogger("shared")

# Default hard timeout for browser login waits (SubScraper-style ~10 min).
# Set gui_settings.json "auth_login_timeout_min" to change; 0 disables.
DEFAULT_AUTH_LOGIN_TIMEOUT_MIN = 10


def _auth_login_timeout_seconds() -> int:
    """Return login wait timeout in seconds (0 = no hard timeout)."""
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        raw = load_gui_settings().get(
            "auth_login_timeout_min", DEFAULT_AUTH_LOGIN_TIMEOUT_MIN
        )
        mins = int(raw)
        if mins <= 0:
            return 0
        return mins * 60
    except Exception:
        return DEFAULT_AUTH_LOGIN_TIMEOUT_MIN * 60


def _format_login_wait_line(elapsed_s: int, timeout_s: int, *, kind: str = "login") -> str:
    mins, secs = divmod(max(0, elapsed_s), 60)
    label = "Waiting for login…" if kind == "login" else "Waiting for credentials…"
    base = f"{label} {mins}:{secs:02d} — click Cancel Login anytime to abort."
    if timeout_s <= 0:
        return base
    remaining = max(0, timeout_s - elapsed_s)
    limit_m = max(1, (timeout_s + 59) // 60)
    if remaining <= 60 and elapsed_s < timeout_s:
        return (
            f"{base} Auto-cancels in {remaining}s "
            f"(limit {limit_m} min)."
        )
    return f"{base} Auto-cancels after {limit_m} min if incomplete."


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
    "Zen Browser",
    "Opera",
    "Opera GX",
    "Edge",
    "Brave",
    "Vivaldi",
]

# Import Cookies: Firefox/Zen work from disk on Windows; Chromium-family Import is Linux-only.
# (Login in System Browser can still use any browser from the same dropdown.)
_WINDOWS_DISK_IMPORT_BROWSERS = ["Firefox", "Zen Browser"]
_LINUX_ONLY_IMPORT_BROWSERS = [
    "Chrome",
    "Chromium",
    "Opera",
    "Opera GX",
    "Edge",
    "Brave",
    "Vivaldi",
]

_IMPORT_LINUX_ONLY_SUFFIX = " (Import: Linux only)"

# Linux package / sandbox identifiers for install discovery
_LINUX_FLATPAK_IDS = {
    "firefox": ["org.mozilla.firefox"],
    "chrome": ["com.google.Chrome"],
    "chromium": ["org.chromium.Chromium"],
    "brave": ["com.brave.Browser"],
    "edge": ["com.microsoft.Edge"],
    "opera": ["com.opera.Opera"],
    "vivaldi": ["com.vivaldi.Vivaldi"],
    "zenbrowser": ["app.zen_browser.zen"],
}
_LINUX_SNAP_NAMES = {
    "firefox": ["firefox"],
    "chromium": ["chromium"],
    "brave": ["brave"],
    "edge": ["edge"],
    "opera": ["opera"],
}
_LINUX_NATIVE_CMDS = {
    "chrome": ["google-chrome-stable", "google-chrome", "chrome"],
    "chromium": ["chromium-browser", "chromium"],
    "firefox": ["firefox", "firefox-esr"],
    "brave": ["brave-browser", "brave"],
    "edge": ["microsoft-edge-stable", "microsoft-edge", "microsoft-edge-dev"],
    "opera": ["opera"],
    "operagx": ["opera"],
    "vivaldi": ["vivaldi-stable", "vivaldi"],
    "zenbrowser": ["zen-browser", "zen"],
}
_LINUX_METHOD_ORDER = ("apt", "deb", "native", "snap", "flatpak")


class LinuxBrowserInstall:
    """One detected install of a browser on Linux (apt/deb/native/snap/flatpak)."""

    __slots__ = (
        "browser",
        "method",
        "label",
        "executable",
        "profile_roots",
        "flatpak_id",
        "snap_name",
        "preferred_cookie_path",
        "preferred_user_data_dirs",
    )

    def __init__(
        self,
        browser: str,
        method: str,
        label: str,
        executable,
        profile_roots: list[str] | None = None,
        flatpak_id: str | None = None,
        snap_name: str | None = None,
        preferred_cookie_path: str | None = None,
        preferred_user_data_dirs: list[str] | None = None,
    ):
        self.browser = browser
        self.method = method
        self.label = label
        self.executable = executable
        self.profile_roots = profile_roots or []
        self.flatpak_id = flatpak_id
        self.snap_name = snap_name
        self.preferred_cookie_path = preferred_cookie_path
        self.preferred_user_data_dirs = preferred_user_data_dirs or []

    @property
    def key(self) -> str:
        return f"{self.browser}|{self.method}"


def _linux_flatpak_installed(app_id: str) -> bool:
    import shutil

    if not shutil.which("flatpak"):
        return False
    try:
        res = subprocess.run(
            ["flatpak", "info", app_id],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def _linux_snap_installed(snap_name: str) -> bool:
    import shutil

    if not shutil.which("snap"):
        return False
    # Presence of the snap data dir is enough (snap list can be slow/noisy)
    if os.path.isdir(os.path.expanduser(f"~/snap/{snap_name}")):
        return True
    try:
        res = subprocess.run(
            ["snap", "list", snap_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return res.returncode == 0
    except Exception:
        return False


def _linux_classify_native_binary(path: str) -> str:
    """Classify a native firefox/chrome binary as apt, deb, snap-wrapper, or native."""
    try:
        real = os.path.realpath(path)
    except Exception:
        real = path
    low = real.replace("\\", "/").lower()
    if "/snap/" in low:
        return "snap"
    if "/.var/app/" in low or "/flatpak/" in low:
        return "flatpak"
    # dpkg ownership ⇒ apt or standalone .deb
    import shutil

    if shutil.which("dpkg"):
        try:
            res = subprocess.run(
                ["dpkg", "-S", real],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                out = res.stdout.lower()
                if "flatpak" in out:
                    return "flatpak"
                # package name is before the first ':'
                pkg = res.stdout.split(":", 1)[0].strip().split(",")[0].strip()
                if pkg and shutil.which("apt-cache"):
                    try:
                        pol = subprocess.run(
                            ["apt-cache", "policy", pkg],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                        if pol.returncode == 0 and pol.stdout:
                            # Local .deb only shows /var/lib/dpkg/status as the version table source
                            # Apt-managed packages also list http/https/cdrom/ftp/mirror lines.
                            has_repo = any(
                                tok in pol.stdout.lower()
                                for tok in ("http://", "https://", "ftp://", "cdrom:", "mirror+")
                            )
                            if has_repo:
                                return "apt"
                            if "/var/lib/dpkg/status" in pol.stdout.lower():
                                return "deb"
                    except Exception:
                        pass
                return "apt"
        except Exception:
            pass
    return "native"


def _linux_display_name(browser: str) -> str:
    mapping = {
        "firefox": "Firefox",
        "chrome": "Chrome",
        "chromium": "Chromium",
        "brave": "Brave",
        "edge": "Edge",
        "opera": "Opera",
        "operagx": "Opera GX",
        "vivaldi": "Vivaldi",
        "zenbrowser": "Zen Browser",
    }
    return mapping.get(browser, browser.title())


def _linux_method_label(method: str) -> str:
    return {
        "apt": "apt",
        "deb": "deb",
        "native": "native",
        "snap": "Snap",
        "flatpak": "Flatpak",
    }.get(method, method)


def _linux_firefox_roots_for_method(method: str) -> list[str]:
    home = os.path.expanduser("~")
    if method == "flatpak":
        roots = [
            os.path.join(home, ".var/app/org.mozilla.firefox/.mozilla/firefox"),
            os.path.join(home, ".var/app/org.mozilla.firefox/.mozilla/firefox-esr"),
            os.path.join(home, ".var/app/org.mozilla.firefox/data/.mozilla/firefox"),
            os.path.join(home, ".var/app/org.mozilla.firefox/.mozilla/firefox/Profiles"),
        ]
        var_app = os.path.join(home, ".var/app")
        if os.path.isdir(var_app):
            try:
                for name in os.listdir(var_app):
                    low = name.lower()
                    if "firefox" not in low and "mozilla" not in low:
                        continue
                    for rel in (
                        ".mozilla/firefox",
                        ".mozilla/firefox-esr",
                        "data/.mozilla/firefox",
                    ):
                        p = os.path.join(var_app, name, rel)
                        if p not in roots:
                            roots.append(p)
            except Exception:
                pass
        return roots
    if method == "snap":
        return [
            os.path.join(home, "snap/firefox/common/.mozilla/firefox"),
            os.path.join(home, "snap/firefox/current/.mozilla/firefox"),
        ]
    # apt / deb / native share the classic Mozilla paths
    return [
        os.path.join(home, ".mozilla/firefox"),
        os.path.join(home, ".mozilla/firefox-esr"),
        os.path.join(home, ".config/mozilla/firefox"),
    ]


def _linux_chromium_roots_for_method(browser: str, method: str) -> list[str]:
    home = os.path.expanduser("~")
    browser = browser.lower().replace(" ", "")
    flatpak_map = {
        "chrome": ["com.google.Chrome/config/google-chrome"],
        "chromium": ["org.chromium.Chromium/config/chromium"],
        "brave": ["com.brave.Browser/config/BraveSoftware/Brave-Browser"],
        "edge": ["com.microsoft.Edge/config/microsoft-edge"],
        "opera": ["com.opera.Opera/config/opera"],
        "vivaldi": ["com.vivaldi.Vivaldi/config/vivaldi"],
    }
    native_map = {
        "chrome": [".config/google-chrome"],
        "chromium": [".config/chromium"],
        "brave": [".config/BraveSoftware/Brave-Browser"],
        "edge": [".config/microsoft-edge", ".config/microsoft-edge-stable"],
        "opera": [".config/opera"],
        "operagx": [".config/opera"],
        "vivaldi": [".config/vivaldi"],
    }
    if method == "flatpak":
        return [os.path.join(home, ".var/app", p) for p in flatpak_map.get(browser, [])]
    if method == "snap":
        return _linux_snap_chromium_user_data_dirs(browser)
    return [os.path.join(home, p) for p in native_map.get(browser, [])]


def _linux_snap_chromium_user_data_dirs(browser: str) -> list[str]:
    """Locate Chromium-family user-data dirs under ``~/snap/<name>/``.

    Brave Snap stores profiles at::
        ~/snap/brave/current/.config/BraveSoftware/Brave-Browser
        ~/snap/brave/<rev>/.config/BraveSoftware/Brave-Browser
    not the older incorrect ``~/snap/brave/common/brave`` guess.
    """
    home = os.path.expanduser("~")
    browser = browser.lower().replace(" ", "")
    snap_names = {
        "brave": ["brave"],
        "chromium": ["chromium"],
        "chrome": ["chromium", "chrome"],
        "edge": ["edge"],
        "opera": ["opera"],
        "vivaldi": ["vivaldi"],
    }.get(browser, [browser])
    rel_tails = {
        "brave": [
            ".config/BraveSoftware/Brave-Browser",
            "config/BraveSoftware/Brave-Browser",
        ],
        "chromium": [
            ".config/chromium",
            "common/chromium",
            "config/chromium",
        ],
        "chrome": [
            ".config/google-chrome",
            "config/google-chrome",
        ],
        "edge": [
            ".config/microsoft-edge",
            ".config/microsoft-edge-stable",
        ],
        "opera": [".config/opera"],
        "vivaldi": [".config/vivaldi"],
    }.get(browser, [])

    found: list[str] = []
    seen: set[str] = set()
    for snap_name in snap_names:
        snap_root = os.path.join(home, "snap", snap_name)
        if not os.path.isdir(snap_root):
            continue
        subdirs: list[str] = []
        for name in ("current", "common"):
            p = os.path.join(snap_root, name)
            if os.path.isdir(p):
                subdirs.append(p)
        try:
            for name in sorted(os.listdir(snap_root)):
                # Revision folders are numeric (e.g. 666)
                if name.isdigit():
                    p = os.path.join(snap_root, name)
                    if os.path.isdir(p):
                        subdirs.append(p)
        except Exception:
            pass
        for sub in subdirs:
            for rel in rel_tails:
                path = os.path.join(sub, rel)
                if path not in seen:
                    seen.add(path)
                    found.append(path)
            # Also discover any BraveSoftware / chromium dir under this revision
            try:
                for dirpath, dirnames, _files in os.walk(sub):
                    base = os.path.basename(dirpath)
                    parent = os.path.basename(os.path.dirname(dirpath))
                    if base in {"Brave-Browser", "chromium", "google-chrome", "microsoft-edge"} or (
                        parent == "BraveSoftware" and base
                    ):
                        if dirpath not in seen and os.path.isdir(dirpath):
                            # Prefer the user-data root (has Local State or Default/)
                            if (
                                os.path.isfile(os.path.join(dirpath, "Local State"))
                                or os.path.isdir(os.path.join(dirpath, "Default"))
                            ):
                                seen.add(dirpath)
                                found.append(dirpath)
                    # Limit walk depth
                    depth = dirpath[len(sub):].count(os.sep)
                    if depth >= 4:
                        dirnames[:] = []
            except Exception:
                continue
    return found


def _chromium_user_data_dir_from_cookies_path(cookie_path: str) -> str | None:
    """Walk up from a Cookies DB path to the Chromium user-data root."""
    if not cookie_path:
        return None
    cur = os.path.abspath(cookie_path)
    for _ in range(8):
        cur = os.path.dirname(cur)
        if not cur or cur == os.path.dirname(cur):
            break
        if os.path.isfile(os.path.join(cur, "Local State")):
            return cur
        if os.path.isdir(os.path.join(cur, "Default")) and (
            os.path.basename(cur)
            in {
                "Brave-Browser",
                "google-chrome",
                "chromium",
                "microsoft-edge",
                "microsoft-edge-stable",
                "opera",
                "vivaldi",
                "User Data",
            }
            or os.path.basename(os.path.dirname(cur)) == "BraveSoftware"
        ):
            return cur
    return None


def discover_linux_browser_installs(browser: str) -> list[LinuxBrowserInstall]:
    """Detect how a browser is installed on Linux (apt/deb/native, Snap, Flatpak)."""
    import shutil

    browser = browser.lower().replace(" ", "")
    found: dict[str, LinuxBrowserInstall] = {}
    display = _linux_display_name(browser)

    # Flatpak
    for app_id in _LINUX_FLATPAK_IDS.get(browser, []):
        roots = []
        if browser == "firefox":
            roots = _linux_firefox_roots_for_method("flatpak")
        elif browser == "zenbrowser":
            roots = [
                os.path.expanduser("~/.var/app/app.zen_browser.zen/.zen"),
                os.path.expanduser("~/.var/app/app.zen_browser.zen/.mozilla"),
            ]
        else:
            roots = _linux_chromium_roots_for_method(browser, "flatpak")
        has_profile = any(os.path.isdir(r) for r in roots)
        if _linux_flatpak_installed(app_id) or has_profile:
            found["flatpak"] = LinuxBrowserInstall(
                browser=browser,
                method="flatpak",
                label=f"{display} (Flatpak)",
                executable=["flatpak", "run", app_id],
                profile_roots=[r for r in roots if os.path.isdir(r)] or roots,
                flatpak_id=app_id,
            )
            break

    # Snap
    for snap_name in _LINUX_SNAP_NAMES.get(browser, []):
        roots = []
        if browser == "firefox":
            roots = _linux_firefox_roots_for_method("snap")
        else:
            roots = _linux_chromium_roots_for_method(browser, "snap")
        has_profile = any(os.path.isdir(r) for r in roots)
        snap_bin = f"/snap/bin/{snap_name}"
        if _linux_snap_installed(snap_name) or has_profile or os.path.exists(snap_bin):
            exe = snap_bin if os.path.exists(snap_bin) else shutil.which(snap_name)
            if not exe and not has_profile:
                continue
            found["snap"] = LinuxBrowserInstall(
                browser=browser,
                method="snap",
                label=f"{display} (Snap)",
                executable=exe or snap_bin,
                profile_roots=[r for r in roots if os.path.isdir(r)] or roots,
                snap_name=snap_name,
            )
            break

    # Native / apt / deb (PATH binary that is not a snap/flatpak shim)
    for cmd in _LINUX_NATIVE_CMDS.get(browser, []):
        path = shutil.which(cmd)
        if not path:
            continue
        method = _linux_classify_native_binary(path)
        if method in {"snap", "flatpak"}:
            continue
        if method == "apt":
            label = f"{display} (apt)"
        elif method == "deb":
            label = f"{display} (deb)"
        else:
            label = f"{display} (native)"
            method = "native"
        if browser == "firefox":
            roots = _linux_firefox_roots_for_method("apt")
        elif browser == "zenbrowser":
            roots = [
                os.path.expanduser("~/.zen"),
                os.path.expanduser("~/.mozilla/zen"),
            ]
        else:
            roots = _linux_chromium_roots_for_method(browser, "apt")
        # Prefer apt over native if both somehow collide
        if method not in found:
            found[method] = LinuxBrowserInstall(
                browser=browser,
                method=method,
                label=label,
                executable=path,
                profile_roots=[r for r in roots if os.path.isdir(r)] or roots,
            )
        break

    # Profile-only fallback: profiles exist but binary discovery missed
    if browser == "firefox" and "flatpak" not in found:
        roots = [r for r in _linux_firefox_roots_for_method("flatpak") if os.path.isdir(r)]
        if roots:
            found["flatpak"] = LinuxBrowserInstall(
                browser="firefox",
                method="flatpak",
                label=f"{display} (Flatpak)",
                executable=["flatpak", "run", "org.mozilla.firefox"],
                profile_roots=roots,
                flatpak_id="org.mozilla.firefox",
            )
    if browser == "firefox" and "snap" not in found:
        roots = [r for r in _linux_firefox_roots_for_method("snap") if os.path.isdir(r)]
        if roots:
            found["snap"] = LinuxBrowserInstall(
                browser="firefox",
                method="snap",
                label=f"{display} (Snap)",
                executable="/snap/bin/firefox",
                profile_roots=roots,
                snap_name="firefox",
            )
    if browser == "firefox" and not any(m in found for m in ("apt", "deb", "native")):
        roots = [r for r in _linux_firefox_roots_for_method("apt") if os.path.isdir(r)]
        if roots:
            found["apt"] = LinuxBrowserInstall(
                browser="firefox",
                method="apt",
                label=f"{display} (apt)",
                executable=shutil.which("firefox") or "firefox",
                profile_roots=roots,
            )

    ordered = []
    for method in _LINUX_METHOD_ORDER:
        if method in found:
            ordered.append(found[method])
    return ordered


def _parse_browser_install_key(raw: str) -> tuple[str, str | None]:
    """Parse combo UserRole into (browser_name, install_method|None)."""
    text = (raw or "").strip()
    if "|" in text:
        browser, method = text.split("|", 1)
        return browser.lower().replace(" ", ""), method.lower().strip() or None
    # Legacy labels
    low = text.lower().replace(" ", "")
    if low.endswith("(flatpak)") or low.endswith("flatpak"):
        base = low.replace("(flatpak)", "").replace("flatpak", "")
        return base, "flatpak"
    if low.endswith("(snap)") or low.endswith("snap"):
        base = low.replace("(snap)", "").replace("snap", "")
        return base, "snap"
    for suffix, method in (
        ("(apt)", "apt"),
        ("(deb)", "deb"),
        ("(native)", "native"),
    ):
        if low.endswith(suffix.replace(" ", "")) or suffix.replace("(", "").replace(")", "") in low:
            if low.endswith(suffix.replace(" ", "")):
                base = low[: -len(suffix.replace(" ", ""))]
                return base, method
    return low, None


def _resolve_linux_install(browser: str, method: str | None) -> LinuxBrowserInstall | None:
    installs = discover_linux_browser_installs(browser)
    if not installs:
        return None
    if method:
        for inst in installs:
            if inst.method == method:
                return inst
    return installs[0]


def _linux_browser_process_tokens(browser: str) -> list[str]:
    """Substrings that identify a browser in /proc cmdline or exe."""
    browser = browser.lower().replace(" ", "")
    return {
        "firefox": ["firefox", "firefox-bin", "firefox-esr", "org.mozilla.firefox"],
        "zenbrowser": ["zen-browser", "zen", "app.zen_browser.zen"],
        "chrome": ["google-chrome", "com.google.chrome", "chrome"],
        "chromium": ["chromium", "org.chromium.chromium"],
        "brave": ["brave", "com.brave.browser"],
        "edge": ["microsoft-edge", "msedge", "com.microsoft.edge"],
        "opera": ["opera", "com.opera.opera"],
        "operagx": ["opera"],
        "vivaldi": ["vivaldi", "com.vivaldi.vivaldi"],
    }.get(browser, [browser])


def _linux_process_matches_browser(browser: str, exe: str, cmdline: str) -> bool:
    """True if this Linux process looks like the selected browser (not our sandbox)."""
    browser = browser.lower().replace(" ", "")
    combined = f"{exe} {cmdline}".lower().replace("\\", "/")
    if "ofscraper_" in combined:
        return False
    # Avoid matching helper tools
    if any(x in combined for x in ("crashreporter", "plugin-container", "updater", "webapprt")):
        return False

    flatpak_ids = [x.lower() for x in _LINUX_FLATPAK_IDS.get(browser, [])]
    if any(fid in combined for fid in flatpak_ids):
        return True

    tokens = _linux_browser_process_tokens(browser)
    if browser == "chrome":
        # Prefer Google Chrome; do not treat Chromium as Chrome
        if "chromium" in combined and "google-chrome" not in combined and "com.google.chrome" not in combined:
            return False
        return any(t in combined for t in ("google-chrome", "com.google.chrome")) or (
            "/chrome" in combined and "chromium" not in combined
        )
    if browser == "chromium":
        if "google-chrome" in combined or "com.google.chrome" in combined:
            return False
        return any(t in combined for t in ("chromium", "org.chromium.chromium"))
    if browser == "firefox":
        if "thunderbird" in combined or "zen" in combined:
            return False
        return any(t in combined for t in tokens)
    if browser == "zenbrowser":
        if "app.zen_browser.zen" in combined or "zen-browser" in combined:
            return True
        # Plain "zen" binary — avoid matching unrelated names containing "zen"
        base = os.path.basename((exe or "").split(" ")[0]).lower()
        return base in {"zen", "zen-bin"} or "/zen/" in combined
    return any(t in combined for t in tokens)


def _linux_classify_process_install(pid: str, exe: str, cmdline: str) -> str:
    """Classify a running process as flatpak / snap / apt / deb / native."""
    combined = f"{exe} {cmdline}".lower().replace("\\", "/")
    cgroup = ""
    try:
        with open(f"/proc/{pid}/cgroup", "r", encoding="utf-8", errors="ignore") as fp:
            cgroup = fp.read().lower()
    except Exception:
        pass
    environ = ""
    try:
        with open(f"/proc/{pid}/environ", "rb") as fp:
            environ = fp.read().replace(b"\x00", b"\n").decode("utf-8", errors="ignore").lower()
    except Exception:
        pass

    blob = f"{combined}\n{cgroup}\n{environ}"
    # Require real Flatpak markers — bare bwrap alone is not enough (could be
    # firejail/other). FLATPAK_ID / app-flatpak cgroup are authoritative.
    if (
        "flatpak_id=" in environ
        or "app-flatpak-" in cgroup
        or "container=flatpak" in environ
        or "/.var/app/" in blob
        or ("flatpak" in combined and "run" in combined)
    ):
        return "flatpak"
    if "/snap/" in blob or "snap." in cgroup or "/snap/" in exe.replace("\\", "/").lower():
        return "snap"
    # Prefer real binary path for apt/deb classification
    path = exe
    if not path or path.endswith(" (deleted)") or "bwrap" in path.lower():
        for tok in cmdline.split():
            if tok.startswith("/") and os.path.basename(tok) not in {"flatpak", "bwrap", "snap"}:
                path = tok
                break
    if path and os.path.exists(path) and "bwrap" not in path.lower():
        return _linux_classify_native_binary(path)
    # bwrap without Flatpak markers — do not guess Flatpak
    if "bwrap" in (exe or "").lower() or cmdline.strip().startswith("bwrap"):
        return "unknown"
    return "native"


def _linux_proc_environ_map(pid: str) -> dict[str, str]:
    env: dict[str, str] = {}
    try:
        with open(f"/proc/{pid}/environ", "rb") as fp:
            raw = fp.read()
        for part in raw.split(b"\x00"):
            if not part or b"=" not in part:
                continue
            key, _, val = part.partition(b"=")
            try:
                env[key.decode("utf-8", errors="ignore")] = val.decode("utf-8", errors="ignore")
            except Exception:
                continue
    except Exception:
        pass
    return env


def _linux_cookies_via_process_fds(pid: str) -> list[str]:
    """Return cookie DB paths the process currently has open.

    Firefox uses ``cookies.sqlite``; Chromium/Brave use ``Cookies``
    (often under ``.../Network/Cookies``).
    """
    found: list[str] = []
    fd_dir = f"/proc/{pid}/fd"
    try:
        entries = os.listdir(fd_dir)
    except Exception:
        return found
    for entry in entries:
        try:
            target = os.readlink(os.path.join(fd_dir, entry))
        except Exception:
            continue
        norm = target.replace(" (deleted)", "").strip()
        base = os.path.basename(norm)
        if base not in {"cookies.sqlite", "Cookies"}:
            continue
        if os.path.isfile(norm) and norm not in found:
            found.append(norm)
        elif base in {"cookies.sqlite", "Cookies"} and norm not in found:
            found.append(norm)
    return found


def _linux_firefox_profile_roots_for_running_pid(pid: str, method: str) -> list[str]:
    """Profile roots for a live Firefox PID (handles Flatpak host-shared ~/.mozilla)."""
    env = _linux_proc_environ_map(pid)
    roots: list[str] = []
    flatpak_id = (env.get("FLATPAK_ID") or "").strip()
    home = os.path.expanduser("~")

    if flatpak_id or method == "flatpak":
        app_id = flatpak_id or "org.mozilla.firefox"
        roots.extend(
            [
                os.path.join(home, f".var/app/{app_id}/.mozilla/firefox"),
                os.path.join(home, f".var/app/{app_id}/.mozilla/firefox-esr"),
                os.path.join(home, f".var/app/{app_id}/data/.mozilla/firefox"),
            ]
        )
        # Flatpak with host filesystem access commonly uses the normal profile dir
        roots.extend(_linux_firefox_roots_for_method("apt"))

    if method == "snap":
        roots.extend(_linux_firefox_roots_for_method("snap"))
        roots.extend(_linux_firefox_roots_for_method("apt"))
    elif method in {"apt", "deb", "native"}:
        roots.extend(_linux_firefox_roots_for_method("apt"))
    elif method == "unknown":
        # Search everywhere — classify from whatever cookies we find
        roots.extend(_linux_firefox_roots_for_method("flatpak"))
        roots.extend(_linux_firefox_roots_for_method("snap"))
        roots.extend(_linux_firefox_roots_for_method("apt"))

    seen: set[str] = set()
    out: list[str] = []
    for r in roots:
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out


def _iter_firefox_cookie_files_under(roots: list[str]) -> list[str]:
    found: list[str] = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            for dirpath, _dirnames, filenames in os.walk(root):
                if "cookies.sqlite" in filenames:
                    found.append(os.path.join(dirpath, "cookies.sqlite"))
        except Exception:
            continue
    return found


def _inspect_running_linux_browser(browser: str) -> list[dict]:
    """Inspect running processes for ``browser``.

    Each result: ``{pid, method, exe, cmdline, cookie_paths, flatpak_id}``.
    """
    if platform.system() != "Linux":
        return []
    results: list[dict] = []
    try:
        pids = os.listdir("/proc")
    except Exception:
        return []
    for pid in pids:
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/cmdline", "rb") as fp:
                raw = fp.read()
            if not raw:
                continue
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
            try:
                exe = os.readlink(f"/proc/{pid}/exe")
            except Exception:
                exe = ""
            if not _linux_process_matches_browser(browser, exe, cmdline):
                continue
            method = _linux_classify_process_install(pid, exe, cmdline)
            env = _linux_proc_environ_map(pid)
            cookie_paths = _linux_cookies_via_process_fds(pid)
            # Also discover cookies under roots implied by this live process
            browser_key = browser.lower().replace(" ", "")
            if browser_key in {"firefox", "zenbrowser"}:
                for path in _iter_firefox_cookie_files_under(
                    _linux_firefox_profile_roots_for_running_pid(pid, method)
                ):
                    if path not in cookie_paths and os.path.isfile(path):
                        cookie_paths.append(path)
            elif browser_key in {
                "chrome", "chromium", "brave", "edge", "opera", "operagx", "vivaldi"
            }:
                for root in _linux_chromium_roots_for_method(browser_key, method):
                    if not os.path.isdir(root):
                        continue
                    try:
                        for dirpath, _dns, filenames in os.walk(root):
                            if "Cookies" in filenames:
                                cpath = os.path.join(dirpath, "Cookies")
                                if cpath not in cookie_paths and os.path.isfile(cpath):
                                    cookie_paths.append(cpath)
                    except Exception:
                        continue
            info = {
                "pid": pid,
                "method": method,
                "exe": exe,
                "cmdline": cmdline,
                "cookie_paths": cookie_paths,
                "flatpak_id": (env.get("FLATPAK_ID") or "").strip() or None,
            }
            results.append(info)
            log.info(
                f"Running {browser} process pid={pid} method={method} "
                f"exe={exe or '?'} cookies={len(cookie_paths)} "
                f"cmdline={cmdline[:160]!r}"
            )
        except Exception:
            continue
    return results


def _iter_running_linux_browser_methods(browser: str) -> list[str]:
    """Return unique install methods for currently running instances of ``browser``."""
    methods: list[str] = []
    seen: set[str] = set()
    for info in _inspect_running_linux_browser(browser):
        method = info.get("method") or "unknown"
        if method == "unknown":
            continue
        if method not in seen:
            seen.add(method)
            methods.append(method)
    return methods


def _pick_cookie_from_running_firefox(inspections: list[dict]) -> tuple[str | None, str | None]:
    """Pick best cookies.sqlite from running Firefox inspections.

    Returns ``(cookie_path, method)``. Method is derived from the path when possible.
    """
    candidates: list[tuple[float, str, str]] = []
    for info in inspections:
        proc_method = info.get("method") or "unknown"
        for path in info.get("cookie_paths") or []:
            if not path or not os.path.isfile(path):
                continue
            try:
                score = _score_firefox_profile_for_of(path)
            except Exception:
                score = _firefox_storage_freshness(path)
            path_method = _firefox_install_method_for_path(path)
            # Prefer path-based method; if host ~/.mozilla used by Flatpak process,
            # keep reporting flatpak when process is flatpak (user-facing accuracy
            # of "which binary") but extract from the real path.
            method = proc_method if proc_method not in {"unknown", "native"} else path_method
            if proc_method == "flatpak" and path_method == "apt":
                # Shared host profile under a Flatpak process
                method = "flatpak"
            elif proc_method == "unknown":
                method = path_method
            candidates.append((score, path, method))
    if not candidates:
        return None, None
    candidates.sort(key=lambda t: t[0], reverse=True)
    _score, path, method = candidates[0]
    log.info(f"Running Firefox cookie pick: {path} method={method} score={_score:.1f}")
    return path, method


def _best_linux_install_by_profile(browser: str, installs: list[LinuxBrowserInstall]) -> LinuxBrowserInstall | None:
    """Pick the install whose profile has the freshest OnlyFans cookies."""
    if not installs:
        return None
    if len(installs) == 1:
        return installs[0]
    browser = browser.lower().replace(" ", "")
    if browser in {"firefox", "zenbrowser"}:
        best_inst = None
        best_score = float("-inf")
        for inst in installs:
            cookie = _find_firefox_cookie_file(install_method=inst.method) if browser == "firefox" else None
            if browser == "zenbrowser":
                score = 0.0
                for root in inst.profile_roots:
                    if os.path.isdir(root):
                        try:
                            score = max(score, os.path.getmtime(root))
                        except Exception:
                            pass
            else:
                score = _score_firefox_profile_for_of(cookie) if cookie else -1.0
            if score > best_score:
                best_score = score
                best_inst = inst
        return best_inst or installs[0]
    best_inst = None
    best_mtime = -1.0
    for inst in installs:
        for root in inst.profile_roots or _linux_chromium_roots_for_method(browser, inst.method):
            if not os.path.isdir(root):
                continue
            try:
                mtime = os.path.getmtime(root)
            except Exception:
                mtime = 0.0
            if mtime >= best_mtime:
                best_mtime = mtime
                best_inst = inst
    return best_inst or installs[0]


def _resolve_linux_install_for_import(browser: str) -> tuple[LinuxBrowserInstall | None, str]:
    """Resolve which Linux install to read.

    Prefer cookies opened by a *currently running* browser process (via /proc fds
    and that process's profile roots). Falls back to the freshest OnlyFans profile
    on disk when nothing usable is found from the live process.

    Returns ``(install, source)`` where source is ``\"running\"`` or ``\"disk\"``.
    """
    browser = browser.lower().replace(" ", "")
    installs = discover_linux_browser_installs(browser)
    inspections = _inspect_running_linux_browser(browser)

    # Firefox: bind to the live process's actual cookies.sqlite when possible
    if browser == "firefox" and inspections:
        cookie_path, method = _pick_cookie_from_running_firefox(inspections)
        if cookie_path:
            path_method = _firefox_install_method_for_path(cookie_path)
            # Prefer path truth for extraction scoping; keep flatpak label if process is flatpak
            proc_methods = {i.get("method") for i in inspections}
            if "flatpak" in proc_methods and path_method == "apt":
                use_method = "flatpak"  # process is Flatpak using host profile
                label_method = "flatpak"
            else:
                use_method = method or path_method
                label_method = use_method
            chosen = _resolve_linux_install(browser, use_method if use_method != "unknown" else path_method)
            if not chosen:
                display = _linux_display_name(browser)
                chosen = LinuxBrowserInstall(
                    browser=browser,
                    method=label_method or path_method,
                    label=f"{display} ({_linux_method_label(label_method or path_method)})",
                    executable=None,
                    profile_roots=[os.path.dirname(cookie_path)],
                )
            chosen.preferred_cookie_path = cookie_path
            # Ensure extraction can see this profile even when method roots differ
            profile_dir = os.path.dirname(cookie_path)
            parent = os.path.dirname(profile_dir)
            for extra in (profile_dir, parent):
                if extra and extra not in chosen.profile_roots:
                    chosen.profile_roots = list(chosen.profile_roots) + [extra]
            # If Flatpak process uses host ~/.mozilla, force apt roots for the finder
            # by stamping preferred_cookie_path (import uses it directly).
            log.info(
                f"Import resolved {browser} from running process → "
                f"{chosen.method} cookie={cookie_path}"
            )
            return chosen, "running"

        # Running, but no cookies found yet — if method was unknown/flatpak with
        # empty data dir, fall through to disk scoring across all installs.
        running_methods = [
            m for m in {i.get("method") for i in inspections} if m and m != "unknown"
        ]
        if running_methods:
            candidates = [i for i in installs if i.method in running_methods]
            # Also allow apt when flatpak is running (shared host profile case)
            if "flatpak" in running_methods:
                for inst in installs:
                    if inst.method in {"apt", "deb", "native"} and inst not in candidates:
                        candidates.append(inst)
            if candidates:
                chosen = _best_linux_install_by_profile(browser, candidates)
                if chosen and _find_firefox_cookie_file(install_method=chosen.method):
                    # Re-check: prefer apt cookie if flatpak roots empty
                    if chosen.method == "flatpak":
                        apt_cookie = _find_firefox_cookie_file(install_method="apt")
                        flat_cookie = _find_firefox_cookie_file(install_method="flatpak")
                        if apt_cookie and not flat_cookie:
                            display = _linux_display_name(browser)
                            shared = LinuxBrowserInstall(
                                browser=browser,
                                method="flatpak",
                                label=f"{display} (Flatpak)",
                                executable=[
                                    "flatpak",
                                    "run",
                                    "org.mozilla.firefox",
                                ],
                                profile_roots=_linux_firefox_roots_for_method("apt"),
                                flatpak_id="org.mozilla.firefox",
                                preferred_cookie_path=apt_cookie,
                            )
                            log.info(
                                "Flatpak Firefox running but using host ~/.mozilla "
                                f"profile: {apt_cookie}"
                            )
                            return shared, "running"
                    log.info(
                        f"Import resolved {browser} from running method roots → {chosen.method}"
                    )
                    return chosen, "running"

    # Chromium family: attach live Cookies-fd / Snap user-data dirs to the install
    chromium_family = browser in {
        "chrome", "chromium", "edge", "brave", "opera", "operagx", "vivaldi"
    }
    if chromium_family and inspections:
        running_methods = [
            m for m in {i.get("method") for i in inspections} if m and m != "unknown"
        ]
        user_data_dirs: list[str] = []
        seen_ud: set[str] = set()
        for info in inspections:
            for cpath in info.get("cookie_paths") or []:
                if os.path.basename(cpath) != "Cookies":
                    continue
                ud = _chromium_user_data_dir_from_cookies_path(cpath)
                if ud and ud not in seen_ud:
                    seen_ud.add(ud)
                    user_data_dirs.append(ud)
                    log.info(f"Running {browser} Cookies fd → user-data {ud}")
        if running_methods:
            candidates = [i for i in installs if i.method in running_methods]
            if not candidates:
                method = running_methods[0]
                display = _linux_display_name(browser)
                candidates = [
                    LinuxBrowserInstall(
                        browser=browser,
                        method=method,
                        label=f"{display} ({_linux_method_label(method)})",
                        executable=(
                            ["flatpak", "run", (_LINUX_FLATPAK_IDS.get(browser) or [None])[0]]
                            if method == "flatpak"
                            else (
                                f"/snap/bin/{browser}"
                                if method == "snap"
                                else None
                            )
                        ),
                        profile_roots=_linux_chromium_roots_for_method(browser, method),
                        flatpak_id=(
                            (_LINUX_FLATPAK_IDS.get(browser) or [None])[0]
                            if method == "flatpak"
                            else None
                        ),
                        snap_name=browser if method == "snap" else None,
                    )
                ]
            chosen = (
                candidates[0]
                if len(candidates) == 1
                else _best_linux_install_by_profile(browser, candidates)
            )
            if chosen:
                # Merge discovered Snap/fd roots so extract does not see an empty scope
                extra_roots = list(chosen.profile_roots or [])
                for root in _linux_chromium_roots_for_method(browser, chosen.method):
                    if root not in extra_roots:
                        extra_roots.append(root)
                for ud in user_data_dirs:
                    if ud not in extra_roots:
                        extra_roots.insert(0, ud)
                chosen.profile_roots = extra_roots
                chosen.preferred_user_data_dirs = [
                    d for d in extra_roots if os.path.isdir(d)
                ] or list(user_data_dirs)
                log.info(
                    f"Import resolved {browser} from running process → {chosen.method} "
                    f"user_data={chosen.preferred_user_data_dirs}"
                )
                return chosen, "running"

    # Non-Firefox or no usable running cookie: previous method-based logic
    if not installs and not inspections:
        return None, "none"
    if not installs:
        # Synthesize from inspection only
        method = next(
            (i.get("method") for i in inspections if i.get("method") not in (None, "unknown")),
            None,
        )
        if not method:
            return None, "none"
        display = _linux_display_name(browser)
        return (
            LinuxBrowserInstall(
                browser=browser,
                method=method,
                label=f"{display} ({_linux_method_label(method)})",
                executable=(
                    ["flatpak", "run", _LINUX_FLATPAK_IDS.get(browser, ["org.mozilla.firefox"])[0]]
                    if method == "flatpak"
                    else None
                ),
                profile_roots=(
                    _linux_firefox_roots_for_method(method)
                    if browser == "firefox"
                    else _linux_chromium_roots_for_method(browser, method)
                ),
                flatpak_id=(_LINUX_FLATPAK_IDS.get(browser) or [None])[0] if method == "flatpak" else None,
            ),
            "running",
        )

    running_methods = _iter_running_linux_browser_methods(browser)
    if running_methods:
        candidates = [i for i in installs if i.method in running_methods]
        if "flatpak" in running_methods and browser == "firefox":
            for inst in installs:
                if inst.method in {"apt", "deb", "native"} and inst not in candidates:
                    candidates.append(inst)
        if not candidates:
            method = running_methods[0]
            display = _linux_display_name(browser)
            candidates = [
                LinuxBrowserInstall(
                    browser=browser,
                    method=method,
                    label=f"{display} ({_linux_method_label(method)})",
                    executable=(
                        ["flatpak", "run", _LINUX_FLATPAK_IDS.get(browser, ["org.mozilla.firefox"])[0]]
                        if method == "flatpak"
                        else None
                    ),
                    profile_roots=(
                        _linux_firefox_roots_for_method(method)
                        if browser == "firefox"
                        else _linux_chromium_roots_for_method(browser, method)
                    ),
                    flatpak_id=(_LINUX_FLATPAK_IDS.get(browser) or [None])[0] if method == "flatpak" else None,
                )
            ]
        chosen = (
            candidates[0]
            if len(candidates) == 1
            else _best_linux_install_by_profile(browser, candidates)
        )
        log.info(
            f"Import resolved {browser} from running process → "
            f"{chosen.method if chosen else '?'} (running methods={running_methods})"
        )
        return chosen, "running"

    chosen = _best_linux_install_by_profile(browser, installs)
    log.info(
        f"Import resolved {browser} from disk profiles → "
        f"{chosen.method if chosen else '?'} (browser not running)"
    )
    return chosen, "disk"


def _strip_import_linux_only_label(text: str) -> str:
    """Remove UI suffixes from combo display text."""
    t = (text or "").strip()
    for suffix in (_IMPORT_LINUX_ONLY_SUFFIX, " (Linux only)", " (not detected)"):
        t = t.replace(suffix, "")
    return t.strip()


def _populate_browser_import_combo(combo: QComboBox) -> None:
    """Fill the shared browser list (Import Cookies + Login in System Browser)."""
    combo.clear()
    if platform.system() == "Windows":
        header_cross = combo.count()
        combo.addItem("── Import Cookies (disk) ──")
        combo.model().item(header_cross).setEnabled(False)
        for name in _WINDOWS_DISK_IMPORT_BROWSERS:
            combo.addItem(name)
            combo.setItemData(combo.count() - 1, name, Qt.ItemDataRole.UserRole)

        combo.insertSeparator(combo.count())

        header_linux = combo.count()
        combo.addItem("── Also for System Browser login ──")
        combo.model().item(header_linux).setEnabled(False)
        for name in _LINUX_ONLY_IMPORT_BROWSERS:
            combo.addItem(f"{name}{_IMPORT_LINUX_ONLY_SUFFIX}")
            combo.setItemData(combo.count() - 1, name, Qt.ItemDataRole.UserRole)
        return

    # Linux: plain browser names — install method is detected at Import time
    # from the running process (apt / Flatpak / Snap / deb).
    for name in BROWSERS:
        combo.addItem(name)
        combo.setItemData(combo.count() - 1, name, Qt.ItemDataRole.UserRole)


def _combo_browser_display(combo: QComboBox) -> str:
    """Canonical browser display name (e.g. 'Chrome'), ignoring UI suffixes/headers."""
    data = combo.currentData(Qt.ItemDataRole.UserRole)
    if data:
        raw = str(data)
        if "|" in raw:
            browser, _method = _parse_browser_install_key(raw)
            return _linux_display_name(browser)
        # Strip legacy install suffixes from stored roles
        text = _strip_import_linux_only_label(raw)
        browser, _method = _parse_browser_install_key(text)
        if browser and _method:
            return _linux_display_name(browser)
        return text
    text = (combo.currentText() or "").strip()
    if text.startswith("──"):
        return "Zen Browser" if platform.system() == "Windows" else "Chrome"
    text = _strip_import_linux_only_label(text)
    browser, method = _parse_browser_install_key(text)
    if method:
        return _linux_display_name(browser)
    return text


def _combo_browser_selection(combo: QComboBox) -> tuple[str, str | None]:
    """Return (browser_name, install_method|None) from the Import Cookies combo.

    On Linux the combo only stores the browser name; install_method is resolved
    later from the running process.
    """
    data = combo.currentData(Qt.ItemDataRole.UserRole)
    if data:
        return _parse_browser_install_key(str(data))
    text = _strip_import_linux_only_label(combo.currentText() or "")
    return _parse_browser_install_key(text)


def _combo_select_browser(combo: QComboBox, display_name: str) -> bool:
    """Select a combo entry by canonical browser name. Returns True if found."""
    target = (display_name or "").strip()
    target_key, target_method = _parse_browser_install_key(target)
    for i in range(combo.count()):
        data = combo.itemData(i, Qt.ItemDataRole.UserRole)
        if data is None:
            continue
        raw = str(data)
        if raw == target:
            combo.setCurrentIndex(i)
            return True
        browser, method = _parse_browser_install_key(raw)
        if browser != target_key:
            continue
        if target_method and method and method != target_method:
            continue
        combo.setCurrentIndex(i)
        return True
    for i in range(combo.count()):
        text = combo.itemText(i).strip()
        if text == target or _strip_import_linux_only_label(text) == target:
            combo.setCurrentIndex(i)
            return True
        b, _m = _parse_browser_install_key(_strip_import_linux_only_label(text))
        if b == target_key:
            combo.setCurrentIndex(i)
            return True
    return False


def _detect_firefox_or_zen_version(browser_path) -> str:
    import glob
    import re
    import os

    def _pick_gecko_milestone(content: str) -> str:
        """Prefer Milestone/MinVersion (Gecko) over product Version (Zen 1.x)."""
        for pat in (
            r"(?i)Milestone=(\d+\.\d+(?:\.\d+)*)",
            r"(?i)MinVersion=(\d+\.\d+(?:\.\d+)*)",
            r"(?i)LastVersion=(\d+\.\d+(?:\.\d+)*)",
            r"(?i)^Version=(\d+\.\d+(?:\.\d+)*)",
        ):
            m = re.search(pat, content, re.MULTILINE)
            if not m:
                continue
            ver = m.group(1)
            major = int(ver.split(".")[0]) if ver.split(".")[0].isdigit() else 0
            # Skip Zen marketing versions like 1.11 — need Gecko >= 90
            if major >= 90:
                return ver
        return ""

    # 1. If it's flatpak
    if isinstance(browser_path, list) and "flatpak" in browser_path:
        app_id = browser_path[-1]
        for base in ["/var/lib/flatpak/app/", os.path.expanduser("~/.local/share/flatpak/app/")]:
            # Search for platform.ini first which has Milestone
            ini_pattern = os.path.join(base, app_id, "**/platform.ini")
            matches = glob.glob(ini_pattern, recursive=True)
            if not matches:
                ini_pattern = os.path.join(base, app_id, "**/application.ini")
                matches = glob.glob(ini_pattern, recursive=True)
                
            if matches:
                try:
                    with open(matches[0], "r", encoding="utf-8") as f:
                        ver = _pick_gecko_milestone(f.read())
                        if ver:
                            return ver
                except Exception:
                    pass
                    
    # 2. If it's a native file path
    elif isinstance(browser_path, str) and os.path.exists(browser_path):
        real_path = os.path.realpath(browser_path)
        base_dir = os.path.dirname(real_path)
        for name in ["platform.ini", "application.ini"]:
            ini_path = os.path.join(base_dir, name)
            if os.path.exists(ini_path):
                try:
                    with open(ini_path, "r", encoding="utf-8") as f:
                        ver = _pick_gecko_milestone(f.read())
                        if ver:
                            return ver
                except Exception:
                    pass
        # Walk up a level (some Zen layouts nest under browser/)
        for sub in ("browser", os.path.join("..", "browser"), ""):
            for name in ["platform.ini", "application.ini"]:
                ini_path = os.path.normpath(os.path.join(base_dir, sub, name)) if sub else os.path.join(base_dir, name)
                if os.path.exists(ini_path):
                    try:
                        with open(ini_path, "r", encoding="utf-8") as f:
                            ver = _pick_gecko_milestone(f.read())
                            if ver:
                                return ver
                    except Exception:
                        pass
        # CLI --version as last resort for native installs (may be Zen 1.x — ignored if < 90)
        try:
            import subprocess
            out = subprocess.check_output(
                [browser_path, "--version"], stderr=subprocess.STDOUT, timeout=5
            ).decode("utf-8", errors="ignore")
            # Prefer an explicit Firefox/Gecko token if present
            m = re.search(r"(?i)(?:firefox|gecko)[/ ](\d+\.\d+(?:\.\d+)*)", out)
            if m and int(m.group(1).split(".")[0]) >= 90:
                return m.group(1)
            m = re.search(r"(\d+\.\d+(?:\.\d+)*)", out)
            if m and int(m.group(1).split(".")[0]) >= 90:
                return m.group(1)
        except Exception:
            pass
    return ""


def _detect_user_agent(browser_name: str) -> str:
    """Try to detect the user agent string for the given browser.

    Checks the installed browser version and constructs a standard UA string.
    Chromium-based browsers use Chrome's frozen UA form (Chrome/MAJOR.0.0.0),
    which matches what DevTools / OnlyFans see — not the full binary version.
    Returns empty string if detection fails.
    """
    import subprocess

    browser_name = browser_name.lower().replace(" ", "")
    os_name = platform.system()
    version = ""

    if browser_name in {"firefox", "zenbrowser"}:
        browser_path = _find_browser_executable(browser_name)
        version = _detect_firefox_or_zen_version(browser_path)
    else:
        # Prefer Last Version from the browser's user-data dir (most accurate),
        # then --version on the resolved executable for this browser only.
        version = _chromium_last_version(browser_name)
        if not version:
            exe = _find_browser_executable(browser_name)
            if exe:
                try:
                    cmd_list = [exe, "--version"] if isinstance(exe, str) else list(exe) + ["--version"]
                    out = subprocess.check_output(
                        cmd_list, stderr=subprocess.STDOUT, timeout=5
                    ).decode("utf-8", errors="ignore")
                    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", out)
                    if match:
                        version = match.group(1)
                except Exception:
                    pass
        if not version and os_name == "Windows":
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
            }
            for cmd in version_commands.get(browser_name, []):
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=5
                    )
                    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", result.stdout or "")
                    if match:
                        version = match.group(1)
                        break
                except Exception:
                    continue
        if not version and os_name != "Windows":
            version_commands = {
                "chrome": ["google-chrome --version", "google-chrome-stable --version"],
                "chromium": ["chromium --version", "chromium-browser --version"],
                "edge": ["microsoft-edge --version", "microsoft-edge-stable --version"],
                "brave": ["brave-browser --version", "brave --version"],
                "vivaldi": ["vivaldi --version", "vivaldi-stable --version"],
                "opera": ["opera --version"],
                "operagx": ["opera --version"],
            }
            for cmd in version_commands.get(browser_name, []):
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=5
                    )
                    match = re.search(r"(\d+\.\d+(?:\.\d+)*)", result.stdout or "")
                    if match:
                        version = match.group(1)
                        break
                except Exception:
                    continue

    # Build the OS part of the UA
    if os_name == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif os_name == "Darwin":
        mac_ver = platform.mac_ver()[0] or "10_15_7"
        mac_ver = mac_ver.replace(".", "_")
        os_ua = f"Macintosh; Intel Mac OS X {mac_ver}"
    else:
        os_ua = "X11; Linux x86_64"

    # Firefox/Zen: prefer exact UA from profile when available
    profile_dir = None
    if browser_name == "zenbrowser":
        cookie_path = _find_zen_cookie_file()
        if cookie_path:
            profile_dir = os.path.dirname(cookie_path)
    elif browser_name == "firefox":
        cookie_path = _find_firefox_cookie_file()
        if cookie_path:
            profile_dir = os.path.dirname(cookie_path)

    if profile_dir:
        extracted_ua = _get_firefox_or_zen_profile_user_agent(profile_dir, browser_name)
        if extracted_ua:
            if browser_name == "firefox" and not _ua_looks_like_firefox(extracted_ua):
                extracted_ua = None
            if extracted_ua:
                return extracted_ua

    if browser_name in {"firefox", "zenbrowser"}:
        if not version:
            return ""
        # Zen is Firefox/Gecko-based on all platforms (including Windows).
        # Never synthesize a Chrome UA — that mismatches DevTools / OnlyFans.
        return _build_firefox_ua_from_version(version)

    # Chromium family: Chrome's User-Agent Reduction freezes Chrome/ to MAJOR.0.0.0
    # (what OnlyFans / DevTools see). Using the full binary version breaks auth.
    # Brand browsers still append their own token (OPR/…, Edg/…) after Safari/537.36.
    if not version:
        major = "150"
    else:
        major = version.split(".")[0]

    if browser_name in {"opera", "operagx"}:
        # Opera product major ≠ Chromium major (e.g. OPR/134 on Chrome/130).
        return _build_opera_user_agent(os_ua, browser_name=browser_name, fallback_major=major)

    ua = (
        f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.0.0 Safari/537.36"
    )
    if browser_name in {"edge", "msedge"}:
        ua = f"{ua} Edg/{major}.0.0.0"
    return ua


def _opera_product_major(browser_name: str = "opera") -> str:
    """Return Opera's product major version (the OPR/ token), if detectable."""
    import subprocess

    # Prefer Last Version under the Opera profile (same major as DevTools OPR/)
    for base in _chromium_user_data_dirs(browser_name):
        for name in ("Last Version", "last_version"):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            try:
                text = open(path, "r", encoding="utf-8", errors="ignore").read().strip()
                match = re.search(r"(\d+)\.", text) or re.search(r"^(\d+)$", text)
                if match:
                    return match.group(1)
            except Exception:
                continue

    exe = _find_browser_executable(browser_name)
    candidates = []
    if exe:
        candidates.append(exe if isinstance(exe, list) else [exe])
    candidates.extend([["opera"], ["opera-stable"]])
    for cmd in candidates:
        try:
            out = subprocess.check_output(
                list(cmd) + ["--version"], stderr=subprocess.STDOUT, timeout=5
            ).decode("utf-8", errors="ignore")
            # e.g. "Opera 134.0.5060.41" or "Opera Stable 134.0.5060.41"
            match = re.search(r"(?i)opera(?:\s+stable)?\s+(\d+)\.", out) or re.search(
                r"(\d+)\.\d+", out
            )
            if match:
                return match.group(1)
        except Exception:
            continue
    return ""


def _opera_chromium_major(browser_name: str = "opera") -> str:
    """Return the Chromium major Opera embeds (Chrome/ token in DevTools UA).

    This is often *lower* than the Opera product major (OPR/), e.g. Chrome/130 + OPR/134.
    """
    opr_major = _opera_product_major(browser_name)
    # Prefer a live UA pair scraped from the profile / binary
    pair = _opera_ua_chrome_opr_pair(browser_name)
    if pair:
        chrome_m, opr_m = pair
        if chrome_m and (not opr_major or opr_m == opr_major or not opr_m):
            if chrome_m != opr_major:
                return chrome_m
            # Same number is suspicious — keep scanning for a distinct Chromium major
        if chrome_m and chrome_m != opr_major:
            return chrome_m

    # Scan install binary for embedded reduced UA (Chrome/N … OPR/M)
    exe = _find_browser_executable(browser_name)
    exe_path = None
    if isinstance(exe, str) and os.path.isfile(exe):
        exe_path = os.path.realpath(exe)
    elif isinstance(exe, list):
        # flatpak etc. — skip binary scan
        exe_path = None
    if exe_path:
        chrome_m = _scan_file_for_opera_chrome_major(exe_path, opr_major)
        if chrome_m:
            return chrome_m
        # Also scan sibling binaries (opera-sandbox etc. rarely help; main binary is enough)
        exe_dir = os.path.dirname(exe_path)
        for name in ("opera", "opera-stable", "chrome_crashpad_handler"):
            cand = os.path.join(exe_dir, name)
            if cand != exe_path and os.path.isfile(cand):
                chrome_m = _scan_file_for_opera_chrome_major(cand, opr_major)
                if chrome_m:
                    return chrome_m

    return ""


def _opera_ua_chrome_opr_pair(browser_name: str = "opera") -> tuple[str, str] | None:
    """Find (chrome_major, opr_major) from on-disk Opera profile data."""
    pattern = re.compile(
        rb"Chrome/(\d+)\.0\.0\.0 Safari/537\.36 OPR/(\d+)\.0\.0\.0"
    )
    alt = re.compile(rb"Chrome/(\d+)(?:\.\d+){0,3}.{0,64}OPR/(\d+)", re.DOTALL)
    best: tuple[str, str] | None = None
    for base in _chromium_user_data_dirs(browser_name):
        if not os.path.isdir(base):
            continue
        # High-signal small files first
        for rel in (
            "Local State",
            "Default/Preferences",
            "Default/Secure Preferences",
            "Default/Network Persistent State",
        ):
            path = os.path.join(base, rel)
            pair = _scan_file_for_opera_ua_pair(path, pattern, alt)
            if pair:
                best = pair
                if pair[0] != pair[1]:
                    return pair
        try:
            for dirpath, dirnames, filenames in os.walk(base):
                # Keep walk shallow-ish under profile roots
                rel = os.path.relpath(dirpath, base)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth > 5:
                    dirnames[:] = []
                    continue
                for fname in filenames:
                    if not (
                        fname in {"Cookies", "Preferences", "Local State", "LOG", "CURRENT"}
                        or fname.endswith((".log", ".ldb", ".sqlite", "-wal"))
                    ):
                        continue
                    path = os.path.join(dirpath, fname)
                    try:
                        if os.path.getsize(path) > 40 * 1024 * 1024:
                            continue
                    except Exception:
                        continue
                    pair = _scan_file_for_opera_ua_pair(path, pattern, alt)
                    if pair:
                        best = pair
                        if pair[0] != pair[1]:
                            return pair
        except Exception:
            continue
    return best


def _scan_file_for_opera_ua_pair(path: str, pattern, alt) -> tuple[str, str] | None:
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as fp:
            data = fp.read()
    except Exception:
        return None
    m = pattern.search(data) or alt.search(data)
    if not m:
        return None
    return m.group(1).decode("ascii", errors="ignore"), m.group(2).decode(
        "ascii", errors="ignore"
    )


def _scan_file_for_opera_chrome_major(path: str, opr_major: str | None) -> str:
    """Scan a binary/file for Chrome/N paired with OPR/, preferring N != OPR major."""
    if not path or not os.path.isfile(path):
        return ""
    try:
        size = os.path.getsize(path)
    except Exception:
        return ""
    # Cap read for huge binaries — sample head/tail + middle if needed
    max_read = 64 * 1024 * 1024
    try:
        with open(path, "rb") as fp:
            if size <= max_read:
                data = fp.read()
            else:
                head = fp.read(24 * 1024 * 1024)
                fp.seek(max(0, size // 2 - 8 * 1024 * 1024))
                mid = fp.read(16 * 1024 * 1024)
                fp.seek(max(0, size - 24 * 1024 * 1024))
                tail = fp.read(24 * 1024 * 1024)
                data = head + mid + tail
    except Exception:
        return ""

    pairs = re.findall(
        rb"Chrome/(\d+)\.0\.0\.0 Safari/537\.36 OPR/(\d+)\.0\.0\.0", data
    )
    if not pairs:
        pairs = re.findall(rb"Chrome/(\d+)(?:\.\d+){0,3}.{0,48}OPR/(\d+)", data)
    distinct = []
    same = []
    for chrome_b, opr_b in pairs:
        chrome_m = chrome_b.decode("ascii", errors="ignore")
        opr_m = opr_b.decode("ascii", errors="ignore")
        if not chrome_m.isdigit():
            continue
        if opr_major and opr_m and opr_m != opr_major:
            continue
        if chrome_m != opr_m:
            distinct.append(chrome_m)
        else:
            same.append(chrome_m)
    if distinct:
        # Prefer the most common distinct Chromium major
        return max(set(distinct), key=distinct.count)
    return ""


def _build_opera_user_agent(
    os_ua: str, *, browser_name: str = "opera", fallback_major: str = ""
) -> str:
    """Build Opera UA with separate Chrome/ (Chromium) and OPR/ (product) majors."""
    opr_major = _opera_product_major(browser_name) or fallback_major or "134"
    chrome_major = _opera_chromium_major(browser_name) or ""
    if not chrome_major or chrome_major == opr_major:
        # Last chance: pair scrape may have returned equal majors only
        pair = _opera_ua_chrome_opr_pair(browser_name)
        if pair and pair[0] and pair[0] != opr_major:
            chrome_major = pair[0]
    if not chrome_major:
        # Better to omit a wrong Chrome/ equal to OPR than invent one — still use
        # opr as last resort so the string is well-formed; caller can verify.
        chrome_major = fallback_major or opr_major
        log.warning(
            f"Opera Chromium major not found separately; "
            f"using Chrome/{chrome_major} with OPR/{opr_major} "
            f"(DevTools may show a different Chrome/ major)"
        )
    else:
        log.info(
            f"Opera UA versions: Chrome/{chrome_major} OPR/{opr_major}"
        )
    return (
        f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_major}.0.0.0 Safari/537.36 OPR/{opr_major}.0.0.0"
    )


def _ensure_chromium_brand_ua(ua: str, browser_name: str) -> str:
    """Ensure Opera/Edge brand tokens (and Opera Chrome/ major) match DevTools."""
    ua = (ua or "").strip()
    if not ua:
        return ua
    browser_name = (browser_name or "").lower().replace(" ", "")
    if browser_name in {"opera", "operagx"}:
        os_ua = "X11; Linux x86_64"
        if "Windows NT" in ua:
            os_ua = "Windows NT 10.0; Win64; x64"
        elif "Macintosh" in ua:
            m = re.search(r"Macintosh;[^)]+", ua)
            os_ua = m.group(0) if m else os_ua
        elif "X11;" in ua:
            m = re.search(r"X11;[^)]+", ua)
            os_ua = m.group(0) if m else os_ua
        # Always rebuild from detected Chrome/ + OPR/ majors — never trust a
        # Chrome/N that was copied from Opera's product version.
        return _build_opera_user_agent(os_ua, browser_name=browser_name)
    if browser_name in {"edge", "msedge"}:
        if "Edg/" in ua:
            return ua
        m = re.search(r"Chrome/(\d+)", ua)
        if m:
            return f"{ua} Edg/{m.group(1)}.0.0.0"
    return ua


def _chromium_last_version(browser_name: str) -> str:
    """Read the browser's on-disk Last Version file (e.g. 150.0.7832.75)."""
    for base in _chromium_user_data_dirs(browser_name):
        for name in ("Last Version", "last_version"):
            path = os.path.join(base, name)
            if not os.path.isfile(path):
                continue
            try:
                text = open(path, "r", encoding="utf-8", errors="ignore").read().strip()
                match = re.search(r"(\d+\.\d+(?:\.\d+)*)", text)
                if match:
                    return match.group(1)
            except Exception:
                continue
    return ""


def _firefox_profile_roots(*, install_method: str | None = None) -> list:
    """Firefox profile root directories, optionally filtered by Linux install method."""
    from pathlib import Path

    home = Path.home()
    roots = []
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            roots.append(Path(appdata) / "Mozilla" / "Firefox" / "Profiles")
        roots.append(home / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles")
        return roots

    method = (install_method or "").lower()
    if method == "flatpak":
        return [Path(p) for p in _linux_firefox_roots_for_method("flatpak")]
    if method == "snap":
        return [Path(p) for p in _linux_firefox_roots_for_method("snap")]
    if method in {"apt", "deb", "native"}:
        return [Path(p) for p in _linux_firefox_roots_for_method("apt")]

    # No method filter — search everything
    roots.extend(Path(p) for p in _linux_firefox_roots_for_method("flatpak"))
    roots.extend(Path(p) for p in _linux_firefox_roots_for_method("snap"))
    roots.extend(Path(p) for p in _linux_firefox_roots_for_method("apt"))
    return roots


def _is_flatpak_firefox_path(path: str) -> bool:
    norm = (path or "").replace("\\", "/").lower()
    return "/.var/app/" in norm and "firefox" in norm


def _is_snap_firefox_path(path: str) -> bool:
    norm = (path or "").replace("\\", "/").lower()
    return "/snap/firefox/" in norm


def _firefox_install_method_for_path(path: str) -> str:
    if _is_flatpak_firefox_path(path):
        return "flatpak"
    if _is_snap_firefox_path(path):
        return "snap"
    return "apt"


def _iter_firefox_cookie_files(*, install_method: str | None = None) -> list[str]:
    """List cookies.sqlite paths, optionally limited to one Linux install method."""
    found: list[str] = []
    for root in _firefox_profile_roots(install_method=install_method):
        if not root.is_dir():
            continue
        try:
            # Walk recursively — some layouts use Profiles/<name>/cookies.sqlite
            for dirpath, _dirnames, filenames in os.walk(str(root)):
                if "cookies.sqlite" in filenames:
                    found.append(os.path.join(dirpath, "cookies.sqlite"))
        except Exception:
            continue
    return found


def _firefox_onlyfans_cookie_activity(cookie_path: str) -> float:
    """Return a freshness score from OnlyFans cookies (lastAccessed), or 0."""
    import sqlite3
    import tempfile
    import shutil

    if not cookie_path or not os.path.isfile(cookie_path):
        return 0.0
    temp_dir = tempfile.mkdtemp()
    temp_db = os.path.join(temp_dir, "cookies.sqlite")
    try:
        shutil.copy2(cookie_path, temp_db)
        for ext in ("-wal", "-shm"):
            if os.path.exists(cookie_path + ext):
                shutil.copy2(cookie_path + ext, temp_db + ext)
        conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT MAX(lastAccessed), MAX(creationTime), COUNT(*) FROM moz_cookies "
                "WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name IN ('sess', 'auth_id')"
            )
            row = cur.fetchone() or (None, None, 0)
            last_acc, created, count = row
            if not count:
                return 0.0
            # Firefox timestamps are microseconds since epoch
            stamp = float(last_acc or created or 0) / 1_000_000.0
            return stamp + float(count) * 0.01
        finally:
            conn.close()
    except Exception as e:
        log.debug(f"Firefox OF cookie activity score failed for {cookie_path}: {e}")
        return 0.0
    finally:
        try:
            shutil.rmtree(temp_dir)
        except Exception:
            pass


def _score_firefox_profile_for_of(cookie_path: str) -> float:
    """Higher score = more likely the profile actively used for OnlyFans."""
    profile_dir = os.path.dirname(cookie_path)
    score = 0.0
    score += _firefox_storage_freshness(cookie_path)  # cookies.sqlite + WAL mtime
    score += _firefox_onlyfans_cookie_activity(cookie_path) * 10.0
    # Prefer profiles that actually have an OnlyFans localStorage DB
    try:
        import glob

        of_stores = [
            p
            for p in glob.glob(
                os.path.join(profile_dir, "storage", "**", "data.sqlite"),
                recursive=True,
            )
            if "onlyfans" in p.lower()
        ]
        if of_stores:
            score += 1_000.0
            score += max(_firefox_storage_freshness(p) for p in of_stores)
    except Exception:
        pass
    return score


def _find_firefox_cookie_file(*, install_method: str | None = None) -> str | None:
    """Pick the Firefox profile most likely used for OnlyFans.

    When install_method is set (apt/flatpak/snap/...), only that install's
    profile roots are searched. Otherwise all installs are scored.
    """
    cookie_files = _iter_firefox_cookie_files(install_method=install_method)
    if not cookie_files:
        return None

    best = None
    best_score = float("-inf")
    for path in cookie_files:
        try:
            sc = _score_firefox_profile_for_of(path)
        except Exception:
            sc = _firefox_storage_freshness(path)
        log.debug(f"Firefox profile candidate score={sc:.1f} path={path}")
        if sc > best_score:
            best_score = sc
            best = path

    if best:
        kind = _firefox_install_method_for_path(best)
        log.info(f"Selected Firefox cookies ({kind}): {best} score={best_score:.1f}")
    return best


def _find_firefox_executable_for_profile(cookie_path: str | None):
    """Return the Firefox binary/flatpak/snap command that owns this profile."""
    if not cookie_path:
        return _find_browser_executable("firefox")
    method = _firefox_install_method_for_path(cookie_path)
    inst = _resolve_linux_install("firefox", method) if platform.system() == "Linux" else None
    if inst and inst.executable:
        return inst.executable
    if method == "flatpak":
        import shutil

        if shutil.which("flatpak"):
            return ["flatpak", "run", "org.mozilla.firefox"]
    if method == "snap" and os.path.exists("/snap/bin/firefox"):
        return "/snap/bin/firefox"
    return _find_browser_executable("firefox")


def _ua_looks_like_firefox(ua: str) -> bool:
    return bool(ua) and "Firefox/" in ua and "Chrome/" not in ua


def _ua_looks_like_chromium(ua: str) -> bool:
    return bool(ua) and "Chrome/" in ua and "Firefox/" not in ua


# Known Firefox/Zen User-Agent Switcher extension markers (prefs / AMO ids).
_UA_SWITCHER_MARKERS = (
    "user-agent-switcher@ninetailed.ninja",
    "user-agent-switcher@",
    "uaswitcher",
)


def _firefox_decode_ext_storage_key(raw) -> str:
    """Decode Mozilla extension storage-local keys (each code unit stored +1)."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    if not raw:
        return ""
    if raw[:1] == "0":
        raw = raw[1:]
    try:
        return "".join(chr(ord(c) - 1) for c in raw)
    except Exception:
        return raw


def _extract_ua_strings_from_blob(blob: bytes) -> list[str]:
    """Pull Mozilla/… User-Agent strings out of Structured Clone / UTF-16 blobs."""
    if not blob:
        return []
    found: list[str] = []

    def _push(raw: str):
        raw = (raw or "").strip()
        if "Mozilla/5.0" not in raw:
            return
        # Prefer a clean UA substring when surrounding SC junk is present
        m = re.search(
            r"(Mozilla/5\.0 \([^)]+\)(?:(?!Mozilla/5\.0).){0,160}?"
            r"(?:Firefox|Chrome)/\d+(?:\.\d+)*(?: Safari/\d+(?:\.\d+)*)?)",
            raw,
            re.IGNORECASE,
        )
        ua = _fix_user_agent_casing((m.group(1) if m else raw).strip())
        if ua and ("Firefox/" in ua or "Chrome/" in ua):
            found.append(ua)

    # latin-1 contiguous (some SC strings are Latin1)
    for m in re.finditer(
        rb"Mozilla/5\.0 \([^\x00]{8,160}\)[^\x00]{0,160}?"
        rb"(?:Firefox|Chrome)/\d+(?:\.\d+)*(?:[^\x00]{0,40}Safari/\d+(?:\.\d+)*)?",
        blob,
    ):
        _push(m.group(0).decode("latin-1", "ignore"))

    # Rebuild UTF-16LE ASCII runs and scan for UAs (handles SC length prefixes)
    chars: list[str] = []
    i = 0
    n = len(blob)
    while i + 1 < n:
        if blob[i + 1] == 0 and 32 <= blob[i] < 127:
            chars.append(chr(blob[i]))
            i += 2
            continue
        if chars:
            text = "".join(chars)
            if "Mozilla/5.0" in text:
                _push(text)
            chars = []
        i += 1
    if chars:
        text = "".join(chars)
        if "Mozilla/5.0" in text:
            _push(text)

    # Dedupe while preserving order
    out: list[str] = []
    seen: set[str] = set()
    for ua in found:
        if ua not in seen:
            seen.add(ua)
            out.append(ua)
    return out


def _structured_clone_truthy(blob: bytes) -> bool | None:
    """Best-effort boolean from a tiny Structured Clone blob (null/true/false)."""
    if not blob:
        return None
    # Common Firefox IDB patterns for null / false / true
    hx = blob.hex()
    if hx.endswith("0000ffff") or b"\x00\x00\xff\xff" in blob[-6:]:
        # distinguish null (00) vs true (02) vs false (01) near end
        if len(blob) >= 4 and blob[-4] == 0x02:
            return True
        if len(blob) >= 4 and blob[-4] == 0x01:
            return False
        if len(blob) >= 4 and blob[-4] == 0x00:
            return None
    if b"\x02\x00\xff\xff" in blob:
        return True
    if b"\x01\x00\xff\xff" in blob:
        return False
    return None


def _firefox_ua_switcher_addon_status(profile_dir: str | None) -> dict:
    """Return {installed, active} for User-Agent Switcher from extensions.json.

    Disabled-but-still-installed addons leave prefs + IndexedDB behind; those must
    not trigger Import Cookies paste prompts or override the native Gecko UA.
    """
    status = {"installed": False, "active": False}
    if not profile_dir or not os.path.isdir(profile_dir):
        return status
    path = os.path.join(profile_dir, "extensions.json")
    if not os.path.isfile(path):
        # Fall back to prefs markers (presence only — cannot know enabled state)
        for name in ("prefs.js", "user.js"):
            pfile = os.path.join(profile_dir, name)
            if not os.path.isfile(pfile):
                continue
            try:
                text = open(pfile, "r", encoding="utf-8", errors="ignore").read().lower()
            except Exception:
                continue
            if "user-agent-switcher@" in text or "uaswitcher" in text:
                status["installed"] = True
                break
        return status
    try:
        import json as _json

        data = _json.load(open(path, "r", encoding="utf-8"))
        addons = data.get("addons") or []
    except Exception:
        return status
    for addon in addons:
        if not isinstance(addon, dict):
            continue
        aid = str(addon.get("id") or "").lower()
        name = ""
        loc = addon.get("defaultLocale") or {}
        if isinstance(loc, dict):
            name = str(loc.get("name") or "").lower()
        is_ua_switcher = (
            "user-agent-switcher@" in aid
            or "uaswitcher" in aid
            or ("user-agent" in aid and "switch" in aid)
            or name == "user-agent switcher"
            or ("user-agent switcher" in name)
        )
        if not is_ua_switcher:
            continue
        status["installed"] = True
        # Prefer explicit active flag; treat userDisabled/appDisabled as inactive.
        active = bool(addon.get("active"))
        if addon.get("userDisabled") or addon.get("appDisabled"):
            active = False
        status["active"] = active
        if active:
            break
    return status


def _firefox_ua_switcher_installed(profile_dir: str | None) -> bool:
    """True when a User-Agent Switcher extension is present (enabled or not)."""
    return bool(_firefox_ua_switcher_addon_status(profile_dir).get("installed"))


def _read_firefox_ua_switcher_state(profile_dir: str | None) -> dict:
    """Read ninetailed (and similar) UA Switcher storage from a Firefox/Zen profile.

    Returns keys:
      installed, active, random_enabled, current_ua, overrides (host -> ua),
      onlyfans_ua (best override for onlyfans.com if any)

    Spoofed UA fields are only populated when the addon is currently active.
    """
    status = _firefox_ua_switcher_addon_status(profile_dir)
    state = {
        "installed": bool(status.get("installed")),
        "active": bool(status.get("active")),
        "random_enabled": False,
        "current_ua": "",
        "overrides": {},
        "onlyfans_ua": "",
    }
    if not profile_dir or not os.path.isdir(profile_dir):
        return state

    # Disabled addon: ignore leftover IndexedDB (random flags / old overrides).
    if not state["active"]:
        return state

    storage_root = os.path.join(profile_dir, "storage", "default")
    if not os.path.isdir(storage_root):
        return state

    import glob
    import shutil
    import sqlite3
    import tempfile

    # Extension IndexedDB lives under moz-extension+++<uuid>/idb/*.sqlite
    idb_files = glob.glob(
        os.path.join(storage_root, "moz-extension+++*", "idb", "*.sqlite")
    )
    # Prefer the known ninetailed UUID when present
    idb_files.sort(
        key=lambda p: (
            0 if "67ddb6c7-8f0e-4f76-875b-293e1ee489d4" in p else 1,
            -os.path.getmtime(p) if os.path.isfile(p) else 0,
        )
    )

    for db_path in idb_files[:12]:
        # Skip huge unrelated DBs
        try:
            if os.path.getsize(db_path) > 8_000_000:
                continue
        except Exception:
            continue
        temp_dir = tempfile.mkdtemp()
        try:
            temp_db = os.path.join(temp_dir, "ext.sqlite")
            shutil.copy2(db_path, temp_db)
            for ext in ("-wal", "-shm"):
                if os.path.exists(db_path + ext):
                    shutil.copy2(db_path + ext, temp_db + ext)
            conn = sqlite3.connect(temp_db)
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='object_data'"
                )
                if not cur.fetchone():
                    conn.close()
                    continue
                cur.execute("SELECT key, data FROM object_data")
                rows = cur.fetchall()
            except Exception:
                conn.close()
                continue
            conn.close()

            keys_decoded = []
            for key, data in rows:
                dk = _firefox_decode_ext_storage_key(key)
                keys_decoded.append(dk)
                if not isinstance(data, bytes):
                    continue
                if dk in {"random-enabled", "random.enabled"}:
                    truth = _structured_clone_truthy(data)
                    if truth is True:
                        state["random_enabled"] = True
                elif dk in {"current", "current-ua", "current.ua"}:
                    uas = _extract_ua_strings_from_blob(data)
                    if uas:
                        state["current_ua"] = uas[0]
                elif dk.startswith("override:") or dk.startswith("override;"):
                    host = dk.split(":", 1)[-1].split(";", 1)[-1].strip().lower()
                    uas = _extract_ua_strings_from_blob(data)
                    if host and uas:
                        state["overrides"][host] = uas[0]

            # Treat as UA-switcher DB if we saw its known keys
            if any(
                k.startswith("override")
                or k in {"current", "random-enabled", "available", "random-categories"}
                for k in keys_decoded
            ):
                state["installed"] = True
                # Prefer OnlyFans host overrides
                for host, ua in state["overrides"].items():
                    if "onlyfans.com" in host:
                        state["onlyfans_ua"] = ua
                        break
                break
        except Exception as e:
            log.debug(f"UA switcher storage read failed for {db_path}: {e}")
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    if not state["onlyfans_ua"] and state["current_ua"]:
        state["onlyfans_ua"] = state["current_ua"]
    return state


def _firefox_ua_major(ua: str) -> int:
    m = re.search(r"Firefox/(\d+)", ua or "", re.IGNORECASE)
    return int(m.group(1)) if m else 0


def _firefox_pref_bool(profile_dir: str | None, pref_name: str) -> bool | None:
    """Read a boolean user_pref from prefs.js / user.js, or None if unset."""
    if not profile_dir or not pref_name:
        return None
    pat = re.compile(
        rf'user_pref\s*\(\s*["\']{re.escape(pref_name)}["\']\s*,\s*(true|false)\s*\)',
        re.IGNORECASE,
    )
    found: bool | None = None
    for name in ("user.js", "prefs.js"):
        path = os.path.join(profile_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for m in pat.finditer(text):
            found = m.group(1).lower() == "true"
    return found


def _firefox_fingerprinting_ua_spoof_enabled(profile_dir: str | None) -> bool:
    """True when RFP/FPP will spoof Navigator / HTTP User-Agent.

    Zen/Firefox with privacy.fingerprintingProtection (or resistFingerprinting)
    send the frozen Firefox/115 rv:109 UA in Network headers — not the install
    Gecko milestone (e.g. Firefox/154).
    """
    if not profile_dir:
        return False
    if _firefox_pref_bool(profile_dir, "privacy.resistFingerprinting") is True:
        return True
    if _firefox_pref_bool(profile_dir, "privacy.fingerprintingProtection") is not True:
        return False
    # Granular FPP can disable the UA target via overrides, e.g. -NavigatorUserAgent
    overrides = ""
    for name in ("user.js", "prefs.js"):
        path = os.path.join(profile_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            text = open(path, "r", encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        m = re.search(
            r'user_pref\s*\(\s*["\']privacy\.fingerprintingProtection\.overrides["\']\s*,\s*["\']([^"\']*)["\']\s*\)',
            text,
        )
        if m:
            overrides = m.group(1)
    low = overrides.lower()
    if "-navigatoruseragent" in low.replace(" ", ""):
        return False
    return True


def _build_firefox_fpp_spoofed_ua() -> str:
    """UA Firefox/Zen send when RFP/FPP spoofs NavigatorUserAgent (matches DevTools)."""
    if platform.system() == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif platform.system() == "Darwin":
        os_ua = "Macintosh; Intel Mac OS X 10.15"
    else:
        os_ua = "X11; Linux x86_64"
    # Frozen values from mozilla nsRFPService (MOZILLA_UAVERSION / legacy rv).
    return (
        f"Mozilla/5.0 ({os_ua}; rv:109.0) Gecko/20100101 Firefox/115.0"
    )


def _probe_cdp_http(port: int, path: str = "/json/version", timeout: float = 0.4) -> dict | None:
    import urllib.request

    try:
        raw = urllib.request.urlopen(
            f"http://127.0.0.1:{port}{path}", timeout=timeout
        ).read()
        return json.loads(raw)
    except Exception:
        return None


def _firefox_remote_debugging_ports(browser_name: str = "zenbrowser") -> list[int]:
    """Discover likely CDP ports from running Zen/Firefox process cmdlines + commons."""
    browser_name = (browser_name or "").lower().replace(" ", "")
    found: list[int] = []

    def _add(port: int):
        if 1 <= port <= 65535 and port not in found:
            found.append(port)

    if platform.system() == "Windows":
        try:
            if browser_name == "zenbrowser":
                ps = (
                    "Get-CimInstance Win32_Process | Where-Object { "
                    "$_.Name -eq 'zen.exe' -and $_.CommandLine "
                    "} | ForEach-Object { $_.CommandLine }"
                )
            else:
                ps = (
                    "Get-CimInstance Win32_Process | Where-Object { "
                    "$_.Name -eq 'firefox.exe' -and $_.CommandLine "
                    "} | ForEach-Object { $_.CommandLine }"
                )
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    ps,
                ],
                timeout=10,
                stderr=subprocess.DEVNULL,
                text=True,
                errors="ignore",
            )
            for line in out.splitlines():
                m = re.search(r"--remote-debugging-port(?:=|\s+)(\d+)", line)
                if m:
                    _add(int(m.group(1)))
                elif "--remote-debugging-port" in line:
                    _add(9222)
        except Exception as e:
            log.debug(f"Process CDP port scan failed: {e}")

    for port in (9222, 9223, 9229, 9333, 9400):
        _add(port)
    return found


def _cdp_ws_runtime_user_agent(ws_url: str, timeout: float = 3.0) -> str:
    """Runtime.evaluate(navigator.userAgent) over a CDP websocket URL."""
    import base64
    import socket
    import time
    from urllib.parse import urlparse

    parsed = urlparse(ws_url)
    host = parsed.hostname or "127.0.0.1"
    port = int(parsed.port or 9222)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    sock = None
    try:
        sock = socket.create_connection((host, port), timeout=2)
        nonce = base64.b64encode(os.urandom(16)).decode()
        hs = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {nonce}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(hs.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                return ""
            buf += chunk

        def _ws_send(payload: str):
            data = payload.encode("utf-8")
            header = bytearray([0x81])
            ln = len(data)
            mask = os.urandom(4)
            if ln < 126:
                header.append(0x80 | ln)
            elif ln < 65536:
                header.append(0x80 | 126)
                header.extend(ln.to_bytes(2, "big"))
            else:
                header.append(0x80 | 127)
                header.extend(ln.to_bytes(8, "big"))
            header.extend(mask)
            masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
            sock.sendall(header + masked)

        def _ws_recv(deadline: float) -> str | None:
            while time.time() < deadline:
                sock.settimeout(max(0.05, deadline - time.time()))
                try:
                    hdr = sock.recv(2)
                except socket.timeout:
                    return None
                if len(hdr) < 2:
                    return None
                opcode = hdr[0] & 0x0F
                masked = (hdr[1] & 0x80) != 0
                ln = hdr[1] & 0x7F
                if ln == 126:
                    ext = sock.recv(2)
                    ln = int.from_bytes(ext, "big")
                elif ln == 127:
                    ext = sock.recv(8)
                    ln = int.from_bytes(ext, "big")
                mask_key = sock.recv(4) if masked else b""
                data = b""
                while len(data) < ln:
                    chunk = sock.recv(ln - len(data))
                    if not chunk:
                        break
                    data += chunk
                if masked and mask_key:
                    data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
                if opcode == 0x1:
                    return data.decode("utf-8", "ignore")
                if opcode == 0x8:
                    return None
            return None

        _ws_send(json.dumps({"id": 1, "method": "Runtime.enable", "params": {}}))
        _ws_send(
            json.dumps(
                {
                    "id": 2,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": "navigator.userAgent",
                        "returnByValue": True,
                    },
                }
            )
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = _ws_recv(deadline)
            if not msg:
                continue
            try:
                evt = json.loads(msg)
            except Exception:
                continue
            if evt.get("id") == 2 and "result" in evt:
                val = (
                    evt.get("result", {})
                    .get("result", {})
                    .get("value")
                )
                if isinstance(val, str) and val.strip():
                    return _fix_user_agent_casing(val.strip())
        return ""
    except Exception as e:
        log.debug(f"CDP Runtime.evaluate UA failed ({ws_url}): {e}")
        return ""
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass


def _capture_live_firefox_family_user_agent(
    browser_name: str = "zenbrowser",
    *,
    profile_dir: str | None = None,
) -> tuple[str, str]:
    """Try to read the live UA from a running Firefox/Zen remote-debugging port.

    Returns ``(ua, source)`` where source is ``live_navigator`` or ``\"\"``.
    Requires the browser to already be listening on ``--remote-debugging-port``.
    Prefer page targets whose URL contains onlyfans.com when present.
    """
    del profile_dir  # reserved for future profile-scoped attach
    browser_name = (browser_name or "firefox").lower().replace(" ", "")
    ports = _firefox_remote_debugging_ports(browser_name)
    for port in ports:
        listing = _probe_cdp_http(port, "/json/list") or _probe_cdp_http(port, "/json")
        if listing is None:
            continue
        targets = listing if isinstance(listing, list) else []
        if not targets:
            continue
        # Prefer OnlyFans tabs, then any page target with a websocket debugger URL.
        ranked: list[dict] = []
        for t in targets:
            if not isinstance(t, dict):
                continue
            if (t.get("type") or "") not in {"page", "tab"}:
                continue
            ws = t.get("webSocketDebuggerUrl") or ""
            if not ws:
                continue
            url = str(t.get("url") or "").lower()
            score = 0
            if "onlyfans.com" in url:
                score += 10
            if url.startswith("http"):
                score += 1
            ranked.append((score, ws, url))
        ranked.sort(key=lambda x: x[0], reverse=True)
        for score, ws, url in ranked[:6]:
            ua = _cdp_ws_runtime_user_agent(ws, timeout=2.5)
            if ua and (_ua_looks_like_firefox(ua) or _ua_looks_like_chromium(ua)):
                log.info(
                    f"Live CDP navigator.userAgent from port {port} "
                    f"(score={score}, url={url[:80]}): {ua}"
                )
                return ua, "live_navigator"
    return "", ""


def _is_stale_firefox_remote_ua(ua: str, *, fpp_spoof: bool = False) -> bool:
    """Firefox's CDP /json/version often returns a frozen legacy UA (rv:109 / Firefox/115).

    That string is NOT what OnlyFans request headers use on modern Firefox — unless
    fingerprinting protection (RFP/FPP) is enabled, in which case Network *does*
    send exactly this spoofed UA.
    """
    if not ua or fpp_spoof:
        return False
    return ("rv:109.0" in ua and "Firefox/115.0" in ua) or (
        "rv:109.0" in ua and _firefox_ua_major(ua) <= 115
    )


def _pick_best_firefox_ua(*candidates: str, fpp_spoof: bool = False) -> str:
    """Choose the UA that best matches live Firefox traffic (not CDP /json/version junk)."""
    best = ""
    best_score = -10_000_000
    for raw in candidates:
        ua = (raw or "").strip()
        if not _ua_looks_like_firefox(ua):
            continue
        score = _firefox_ua_major(ua) * 100
        if _is_stale_firefox_remote_ua(ua, fpp_spoof=fpp_spoof):
            score -= 100_000
        elif fpp_spoof and _firefox_ua_major(ua) == 115 and "rv:109.0" in ua:
            # Prefer the FPP spoof over a higher install milestone
            score += 50_000
        # Prefer the reduced MAJOR.0 form DevTools shows over application.ini X.Y.Z
        if re.search(r"Firefox/\d+\.\d+\.\d+", ua):
            score -= 5
        if score > best_score:
            best_score = score
            best = _fix_user_agent_casing(ua)
    return best


def _build_firefox_ua_from_version(version: str) -> str:
    """Build a Gecko UA. Always MAJOR.0 — matches Firefox's reduced navigator.userAgent."""
    if platform.system() == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif platform.system() == "Darwin":
        os_ua = "Macintosh; Intel Mac OS X 10.15"
    else:
        os_ua = "X11; Linux x86_64"
    parts = [p for p in (version or "").split(".") if p.isdigit()]
    if not parts:
        return ""
    major_i = int(parts[0])
    # Zen product versions are often 1.x — that is NOT the Gecko/Firefox token in DevTools.
    if major_i < 90:
        return ""
    ver_str = f"{major_i}.0"
    return f"Mozilla/5.0 ({os_ua}; rv:{ver_str}) Gecko/20100101 Firefox/{ver_str}"


def _resolve_firefox_family_user_agent_ex(
    browser_name: str,
    *,
    browser_path=None,
    profile_dir: str | None = None,
    preferred_ua: str | None = None,
    allow_live: bool = True,
) -> tuple[str, str]:
    """Resolve Firefox/Zen UA and report how it was obtained.

    Returns ``(ua, source)`` where source is one of:
      live_navigator, switcher_override, preferred, fpp_prefs,
      profile, gecko_milestone, or \"\".
    Live CDP capture is preferred when the browser exposes remote debugging.
    """
    browser_name = (browser_name or "firefox").lower().replace(" ", "")
    preferred_ua = (preferred_ua or "").strip()
    fpp_spoof = _firefox_fingerprinting_ua_spoof_enabled(profile_dir)

    # 1) Live extraction from a running browser (actual navigator.userAgent).
    if allow_live:
        live_ua, live_src = _capture_live_firefox_family_user_agent(
            browser_name, profile_dir=profile_dir
        )
        if live_ua:
            return live_ua, live_src

    # 2) Explicit preferred (e.g. already captured / pasted) when trustworthy.
    if preferred_ua and _ua_looks_like_firefox(preferred_ua):
        # Never keep the frozen rv:109/Firefox/115 string as a silent preferred
        # value — it is often CDP junk or an incorrect FPP assumption. Live CDP
        # or an explicit user paste sets source accordingly instead.
        if _is_stale_firefox_remote_ua(preferred_ua, fpp_spoof=False):
            preferred_ua = ""
        else:
            return _fix_user_agent_casing(preferred_ua), "preferred"
    if preferred_ua and _ua_looks_like_chromium(preferred_ua):
        preferred_ua = ""

    # 3) Active User-Agent Switcher overrides stored on disk.
    switcher = _read_firefox_ua_switcher_state(profile_dir) if profile_dir else {}
    if switcher.get("active"):
        for candidate in (
            switcher.get("onlyfans_ua") or "",
            switcher.get("current_ua") or "",
        ):
            candidate = (candidate or "").strip()
            if candidate and (
                _ua_looks_like_firefox(candidate) or _ua_looks_like_chromium(candidate)
            ):
                return _fix_user_agent_casing(candidate), "switcher_override"

    # NOTE: Do NOT assume privacy.fingerprintingProtection always spoofs UA to
    # Firefox/115. Zen/Firefox FPP can be on while Network still sends the real
    # Gecko milestone (verified: FPP=true but DevTools shows Firefox/154).
    # Only a live CDP read (above) or an explicit paste should supply the FPP
    # frozen string. Prefer profile / install milestone next.

    # 4) Profile-derived / binary milestone.
    extracted = ""
    if profile_dir:
        extracted = _get_firefox_or_zen_profile_user_agent(profile_dir, browser_name) or ""
        if extracted and not _ua_looks_like_firefox(extracted):
            extracted = ""
        # If FPP is on and the profile somehow stored the frozen 115 string,
        # prefer the install milestone instead — Network often still uses Gecko.
        if (
            extracted
            and fpp_spoof
            and _is_stale_firefox_remote_ua(extracted, fpp_spoof=False)
        ):
            extracted = ""

    built_from_binary = ""
    if browser_path:
        version = _detect_firefox_or_zen_version(browser_path)
        built_from_binary = _build_firefox_ua_from_version(version)

    if extracted:
        picked = (
            _pick_best_firefox_ua(
                extracted, built_from_binary, preferred_ua, fpp_spoof=fpp_spoof
            )
            or extracted
        )
        src = "gecko_milestone" if picked == built_from_binary else "profile"
        return picked, src

    if built_from_binary:
        return built_from_binary, "gecko_milestone"

    detected = _detect_user_agent(browser_name)
    if detected and _ua_looks_like_firefox(detected):
        if _is_stale_firefox_remote_ua(detected, fpp_spoof=fpp_spoof):
            version = _detect_firefox_or_zen_version(
                browser_path or _find_browser_executable(browser_name)
            )
            rebuilt = _build_firefox_ua_from_version(version) or detected
            return rebuilt, "gecko_milestone"
        picked = (
            _pick_best_firefox_ua(detected, built_from_binary, fpp_spoof=fpp_spoof)
            or detected
        )
        return picked, "profile"

    version = _detect_firefox_or_zen_version(
        browser_path or _find_browser_executable(browser_name)
    )
    return _build_firefox_ua_from_version(version) or "", "gecko_milestone"


def _resolve_firefox_family_user_agent(
    browser_name: str,
    *,
    browser_path=None,
    profile_dir: str | None = None,
    preferred_ua: str | None = None,
    allow_live: bool = True,
) -> str:
    """Resolve UA for Firefox/Zen — never invent a Chrome UA for Zen."""
    ua, _src = _resolve_firefox_family_user_agent_ex(
        browser_name,
        browser_path=browser_path,
        profile_dir=profile_dir,
        preferred_ua=preferred_ua,
        allow_live=allow_live,
    )
    return ua


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

    from ofscraper.gui.utils.auth_errors import (
        format_cred_test_failure,
        wrong_user_help_message,
    )

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

        # Clear ofscraper's in-memory & disk signing-rules cache so it re-fetches live rules
        try:
            _auth_req.curr_auth = None
            _auth_req.last_check = None
            import ofscraper.utils.cache.cache as _cache
            _cache.delete("api_onlyfans_sign")
            import ofscraper.utils.profiles.data as _prof_data
            _prof_data.currentData = None
            import ofscraper.managers.manager as _mgr
            if hasattr(_mgr, "Manager") and _mgr.Manager:
                _mgr.Manager.session = None
        except Exception:
            pass

        # First validate user profile with me.scrape_user()
        import ofscraper.data.api.me as _me
        user_info = None
        try:
            user_info = _me.scrape_user()
        except Exception as e:
            return False, format_cred_test_failure(e)

        if not user_info or not isinstance(user_info, dict):
            return False, wrong_user_help_message(
                detail=(
                    "\n\nDetail: OnlyFans returned an empty profile payload "
                    "(often the same root cause as Wrong user)."
                )
            )
        if not user_info.get("isAuth"):
            return False, (
                "Auth error — OnlyFans returned unauthorized for this session "
                "(isAuth was false).\n\n"
                "Re-import cookies or copy sess + auth_id from the same Network "
                "request, then Save and Test again. See Help → Auth Issues."
            )

        # Fetch model list to confirm full API access
        loop = _aio.new_event_loop()
        try:
            models = loop.run_until_complete(
                _aio.wait_for(_retriver.get_models(), timeout=45)
            )
        finally:
            loop.close()

        # If credentials succeeded, set _old_auth to None so they stay saved!
        _old_auth = None

        if models:
            return True, (
                f"Credentials valid — loaded {len(models)} model(s) successfully.\n\n"
                f"Logged in as: {user_info.get('name', '')} (@{user_info.get('username', '')})"
            )
        else:
            return True, (
                f"Credentials valid for @{user_info.get('username', '')}.\n"
                "Note: No active model subscriptions were returned."
            )

    except _aio.TimeoutError:
        return False, (
            "Timed out waiting for model list — OnlyFans did not respond in 45 s.\n"
            "Check your internet connection or try again."
        )
    except Exception as e:
        return False, format_cred_test_failure(e)

    finally:
        # Always restore original auth.json ONLY IF test failed
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


def _collect_browser_cookies(
    *,
    browser_name: str,
    install_method,
    browser_display: str,
    linux_install,
    linux_resolve_source: str,
    should_cancel,
):
    """Heavy cookie/UA extraction. Must not touch Qt widgets (runs on worker thread)."""
    import browser_cookie3

    cookies = {}
    clear_xbc = False
    if should_cancel():
        return {"status": "cancelled"}
    if browser_name == "zenbrowser":
        cookie_path = _find_zen_cookie_file()
        if not cookie_path:
            return {
                "status": "warning",
                "title": "Zen Profile Not Found",
                "message": (
                    "Could not locate Zen Browser profile directories.\n\n"
                    "Make sure Zen Browser is installed and has been run at least once."
                ),
                "browser_name": browser_name,
                "browser_display": browser_display,
                "install_method": install_method,
                "linux_resolve_source": linux_resolve_source,
                "clear_xbc": clear_xbc,
            }
        import tempfile
        import shutil
        import sqlite3

        temp_dir = tempfile.mkdtemp()
        temp_db = os.path.join(temp_dir, "cookies.sqlite")
        try:
            shutil.copy2(cookie_path, temp_db)
            for ext in ["-wal", "-shm"]:
                if os.path.exists(cookie_path + ext):
                    shutil.copy2(cookie_path + ext, temp_db + ext)

            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name='auth_id' ORDER BY lastAccessed DESC, id DESC LIMIT 1")
            auth_id_row = cursor.fetchone()
            if auth_id_row:
                cookies["auth_id"] = auth_id_row[0]

            cursor.execute("SELECT value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name='sess' ORDER BY lastAccessed DESC, id DESC LIMIT 1")
            sess_row = cursor.fetchone()
            if sess_row:
                cookies["sess"] = sess_row[0]

            cursor.execute("SELECT name, value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name LIKE 'auth_uid%' ORDER BY lastAccessed DESC, id DESC LIMIT 1")
            uid_row = cursor.fetchone()
            if uid_row:
                cookies[uid_row[0]] = uid_row[1]

            conn.close()
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

        # Extract x-bc from storage/**/data.sqlite (OnlyFans localStorage)
        zen_profile_dir = os.path.dirname(cookie_path)
        xbc = _extract_firefox_bctoken(zen_profile_dir)
        if xbc:
            cookies["x-bc"] = xbc

        # Resolve UA: prefer live CDP navigator.userAgent, then prefs/profile.
        zen_exe = _find_browser_executable("zenbrowser")
        switcher = _read_firefox_ua_switcher_state(zen_profile_dir)
        cookies["_ua_switcher"] = switcher
        resolved_ua, ua_source = _resolve_firefox_family_user_agent_ex(
            "zenbrowser",
            browser_path=zen_exe,
            profile_dir=zen_profile_dir,
            allow_live=True,
        )
        # Only reduce real Gecko strings — leave intentional switcher spoofs untouched.
        if _ua_looks_like_firefox(resolved_ua) and ua_source not in {
            "live_navigator",
            "switcher_override",
            "fpp_prefs",
        }:
            resolved_ua = _normalize_firefox_ua_reduction(resolved_ua)
        elif _ua_looks_like_firefox(resolved_ua) and ua_source == "live_navigator":
            # Keep live value as-is aside from casing; FPP spoof must stay rv:109.
            resolved_ua = _fix_user_agent_casing(resolved_ua)
        cookies["user_agent"] = resolved_ua
        cookies["_ua_source"] = ua_source
        cookies["_firefox_profile"] = zen_profile_dir

        # Do NOT synthesize x-bc when sess exists — synthetic tokens cause "Wrong user".
        if "x-bc" not in cookies or not cookies["x-bc"]:
            log.warning("Zen import: bcTokenSha not found in profile localStorage")
    elif browser_name == "firefox":
        if should_cancel():
            return {"status": "cancelled"}
        # Dedicated Firefox disk import (never call Chromium extractors — they
        # fall back to Chrome User Data on Windows and poison x-bc / UA).
        # Clear stale x-bc from a previous apt/Flatpak/Snap import so it cannot linger.
        clear_xbc = True
        cookie_path = None
        if linux_install and getattr(linux_install, "preferred_cookie_path", None):
            pref = linux_install.preferred_cookie_path
            if pref and os.path.isfile(pref):
                cookie_path = pref
                log.info(f"Using cookie DB from running Firefox process: {cookie_path}")
        if not cookie_path:
            cookie_path = _find_firefox_cookie_file(install_method=install_method)
        # Last resort: ignore method filter and score every Firefox profile
        if not cookie_path and platform.system() == "Linux":
            log.warning(
                f"No cookies under method={install_method}; scanning all Firefox profiles"
            )
            cookie_path = _find_firefox_cookie_file(install_method=None)
        if not cookie_path:
            which = browser_display or "Firefox"
            return {
                "status": "warning",
                "title": f"{which} Profile Not Found",
                "message": (
                    f"Could not locate a {which} profile with cookies.sqlite.\n\n"
                    "Make sure Firefox is installed, has been run at least once, "
                    "and you are logged into OnlyFans there.\n\n"
                    "If both apt and Flatpak Firefox exist, leave the one you use "
                    "for OnlyFans open, then try Import again."
                ),
                "browser_name": browser_name,
                "browser_display": browser_display,
                "install_method": install_method,
                "linux_resolve_source": linux_resolve_source,
                "clear_xbc": clear_xbc,
            }
        import tempfile
        import shutil
        import sqlite3

        temp_dir = tempfile.mkdtemp()
        temp_db = os.path.join(temp_dir, "cookies.sqlite")
        try:
            shutil.copy2(cookie_path, temp_db)
            for ext in ["-wal", "-shm"]:
                if os.path.exists(cookie_path + ext):
                    shutil.copy2(cookie_path + ext, temp_db + ext)

            conn = sqlite3.connect(temp_db)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') "
                "AND name='auth_id' ORDER BY lastAccessed DESC, id DESC LIMIT 1"
            )
            auth_id_row = cursor.fetchone()
            if auth_id_row:
                cookies["auth_id"] = auth_id_row[0]

            cursor.execute(
                "SELECT value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') "
                "AND name='sess' ORDER BY lastAccessed DESC, id DESC LIMIT 1"
            )
            sess_row = cursor.fetchone()
            if sess_row:
                cookies["sess"] = sess_row[0]

            cursor.execute(
                "SELECT name, value FROM moz_cookies WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') "
                "AND name LIKE 'auth_uid%' ORDER BY lastAccessed DESC, id DESC LIMIT 1"
            )
            uid_row = cursor.fetchone()
            if uid_row:
                cookies[uid_row[0]] = uid_row[1]
            conn.close()
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

        ff_profile_dir = os.path.dirname(cookie_path)
        xbc = _extract_firefox_bctoken(ff_profile_dir)
        if xbc:
            cookies["x-bc"] = xbc
        else:
            log.warning(
                "Firefox import: bcTokenSha not found in profile localStorage "
                f"({ff_profile_dir})"
            )

        ff_exe = (
            linux_install.executable
            if linux_install and linux_install.executable
            else _find_firefox_executable_for_profile(cookie_path)
        )
        switcher = _read_firefox_ua_switcher_state(ff_profile_dir)
        cookies["_ua_switcher"] = switcher
        resolved_ua, ua_source = _resolve_firefox_family_user_agent_ex(
            "firefox",
            browser_path=ff_exe,
            profile_dir=ff_profile_dir,
            allow_live=True,
        )
        if _ua_looks_like_firefox(resolved_ua) and ua_source not in {
            "live_navigator",
            "switcher_override",
            "fpp_prefs",
        }:
            resolved_ua = _normalize_firefox_ua_reduction(resolved_ua)
        elif _ua_looks_like_firefox(resolved_ua) and ua_source == "live_navigator":
            resolved_ua = _fix_user_agent_casing(resolved_ua)
        cookies["user_agent"] = resolved_ua
        cookies["_ua_source"] = ua_source
        cookies["_firefox_profile"] = ff_profile_dir
        cookies["_firefox_install"] = (
            (linux_install.method if linux_install and linux_install.method else None)
            or _firefox_install_method_for_path(cookie_path)
        )
        cookies["_firefox_flatpak"] = (
            cookies["_firefox_install"] == "flatpak"
            or _is_flatpak_firefox_path(cookie_path)
        )
    else:
        if should_cancel():
            return {"status": "cancelled"}
        browser_func_map = {
            "chrome": browser_cookie3.chrome,
            "chromium": browser_cookie3.chromium,
            "opera": browser_cookie3.opera,
            "operagx": browser_cookie3.opera_gx,
            "edge": browser_cookie3.edge,
            "brave": browser_cookie3.brave,
            "vivaldi": browser_cookie3.vivaldi,
        }

        func = browser_func_map.get(browser_name)
        if not func:
            return {
                "status": "warning",
                "title": "Error",
                "message": f"Unsupported browser: {browser_name}",
                "browser_name": browser_name,
                "browser_display": browser_display,
                "install_method": install_method,
                "linux_resolve_source": linux_resolve_source,
                "clear_xbc": clear_xbc,
            }

        # Clear stale x-bc from a previous apt/Flatpak import before Chromium extract
        clear_xbc = True

        # Try native Chrome/Chromium decryption engine first (handles KWallet, SecretService, DPAPI, & open-browser locks)
        extra_dirs = []
        if linux_install and getattr(linux_install, "preferred_user_data_dirs", None):
            extra_dirs = list(linux_install.preferred_user_data_dirs)
        elif linux_install and linux_install.profile_roots:
            extra_dirs = list(linux_install.profile_roots)
        extracted_native = _extract_chrome_family_cookies(
            browser_name,
            install_method=install_method,
            extra_user_data_dirs=extra_dirs or None,
            should_cancel=should_cancel,
        )
        if should_cancel():
            return {"status": "cancelled"}
        if extracted_native:
            cookies.update(extracted_native)

        # Fall back to browser_cookie3 when native decrypt missed sess/auth_id
        if "sess" not in cookies or "auth_id" not in cookies:
            try:
                jar = func(domain_name="onlyfans.com")
                for i, c in enumerate(jar):
                    if i % 25 == 0 and should_cancel():
                        return {"status": "cancelled"}
                    name = getattr(c, "name", "") or ""
                    value = getattr(c, "value", "") or ""
                    if not name or not value:
                        continue
                    if name in {"sess", "auth_id"} or name.startswith("auth_uid"):
                        if name not in cookies or not cookies[name]:
                            cookies[name] = value
                            log.info(
                                f"browser_cookie3 filled {name} from {browser_display}"
                            )
            except Exception as e:
                log.warning(f"browser_cookie3 fallback failed for {browser_display}: {e}")

        # Prefer a real bcTokenSha from disk over a synthetic token.
        # Never invent x-bc when sess is missing — that mismatches DevTools and
        # causes "Wrong user" after a failed Snap/Flatpak path lookup.
        if cookies.get("sess") and cookies.get("auth_id") and not cookies.get("x-bc"):
            target_ua = cookies.get("user_agent") or _detect_user_agent(browser_name)
            if not (
                platform.system() == "Windows"
                and browser_name in {
                    "chrome", "chromium", "edge", "brave", "opera", "operagx", "vivaldi"
                }
            ):
                log.warning(
                    f"{browser_display}: sess present but x-bc missing; "
                    "leaving x-bc empty (will not synthesize)"
                )
        elif not cookies.get("sess"):
            cookies.pop("x-bc", None)

    if should_cancel():
        return {"status": "cancelled"}
    cookies = cookie_allowlist.filter_cookie_map(
        cookies, keep_meta=True, keep_headers=True
    )
    return {
        "status": "ok",
        "cookies": cookies,
        "browser_name": browser_name,
        "browser_display": browser_display,
        "install_method": install_method,
        "linux_install": linux_install,
        "linux_resolve_source": linux_resolve_source,
        "clear_xbc": clear_xbc,
    }


class _CookieImportWorker(QThread):
    """Extract OnlyFans cookies from a local browser off the UI thread."""

    result_ready = pyqtSignal(object)  # dict result

    def __init__(
        self,
        browser_name: str,
        install_method,
        browser_display: str,
        linux_install,
        linux_resolve_source: str,
        parent=None,
    ):
        super().__init__(parent)
        self._browser_name = browser_name
        self._install_method = install_method
        self._browser_display = browser_display
        self._linux_install = linux_install
        self._linux_resolve_source = linux_resolve_source
        self._cancel = False

    def request_cancel(self):
        self._cancel = True
        self.requestInterruption()

    def _cancelled(self) -> bool:
        return self._cancel or self.isInterruptionRequested()

    def run(self):
        try:
            result = _collect_browser_cookies(
                browser_name=self._browser_name,
                install_method=self._install_method,
                browser_display=self._browser_display,
                linux_install=self._linux_install,
                linux_resolve_source=self._linux_resolve_source,
                should_cancel=self._cancelled,
            )
            if self._cancelled():
                self.result_ready.emit({"status": "cancelled"})
            else:
                self.result_ready.emit(result)
        except Exception as e:
            log.error(f"Browser import failed: {e}")
            log.debug(traceback.format_exc())
            if self._cancelled():
                self.result_ready.emit({"status": "cancelled"})
            else:
                self.result_ready.emit(
                    {
                        "status": "error",
                        "title": "Import Failed",
                        "message": (
                            f"Could not import cookies from {self._browser_display}:\n{e}\n\n"
                            "Make sure the browser is fully closed and try again."
                        ),
                        "browser_display": self._browser_display,
                    }
                )


# Module-level remote debugging port — set once before the first QWebEngineView
# is created so Chromium picks it up.  Reused for every subsequent open of the
# dialog (Chromium keeps the same browser process alive).
_USE_CDP = False
_WEBENGINE_DEBUG_PORT: "int | None" = None


def _get_or_create_debug_port() -> int:
    """Return the Chromium remote-debugging port allocated at startup."""
    global _WEBENGINE_DEBUG_PORT
    if _WEBENGINE_DEBUG_PORT is None:
        port_str = os.environ.get("OFSCRAPER_WEBENGINE_DEBUG_PORT")
        if port_str:
            try:
                _WEBENGINE_DEBUG_PORT = int(port_str)
            except Exception:
                _WEBENGINE_DEBUG_PORT = 9208
        else:
            import random
            _WEBENGINE_DEBUG_PORT = random.randint(9200, 9299)
            existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            flags = "--disable-blink-features=AutomationControlled"
            if _USE_CDP:
                flags = f"--remote-debugging-port={_WEBENGINE_DEBUG_PORT} " + flags
            os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = f"{existing} {flags}".strip()
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
                    f"http://127.0.0.1:{self._port}/json/list", timeout=2
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
            host = u.hostname or "127.0.0.1"
            if host in {"localhost", "::1"}:
                host = "127.0.0.1"
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
    """One-shot CDP thread: reads OnlyFans cookies from the browser debugger target."""

    result_ready = pyqtSignal(dict)

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self._port = port
        self._running = True
        self._sock = None

    def stop(self):
        """Ask the thread to exit; safe to call from the GUI thread."""
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def run(self):
        import base64 as _b64
        import socket as _sock_mod
        import time
        import urllib.request as _ureq
        from urllib.parse import urlparse

        result = {}
        try:
            if not self._running:
                return
            # Prefer the *browser* WebSocket from /json/version — page targets flood
            # Network events and make getAllCookies easy to time out on.
            ws_url = ""
            try:
                ver = json.loads(
                    _ureq.urlopen(
                        f"http://127.0.0.1:{self._port}/json/version", timeout=3
                    ).read()
                )
                ws_url = ver.get("webSocketDebuggerUrl", "") or ""
            except Exception:
                pass

            if not self._running:
                return

            if not ws_url:
                targets = json.loads(
                    _ureq.urlopen(
                        f"http://127.0.0.1:{self._port}/json/list", timeout=3
                    ).read()
                )
                # Prefer an onlyfans.com page if present
                ws_url = next(
                    (
                        t.get("webSocketDebuggerUrl", "")
                        for t in targets
                        if t.get("type") == "page"
                        and "onlyfans" in (t.get("url") or "").lower()
                        and t.get("webSocketDebuggerUrl")
                    ),
                    "",
                )
                if not ws_url:
                    ws_url = next(
                        (
                            t.get("webSocketDebuggerUrl", "")
                            for t in targets
                            if t.get("type") == "page" and t.get("webSocketDebuggerUrl")
                        ),
                        "",
                    )

            if not ws_url or not self._running:
                if self._running:
                    self.result_ready.emit(result)
                return

            u = urlparse(ws_url)
            host = u.hostname or "127.0.0.1"
            if host in {"localhost", "::1"}:
                host = "127.0.0.1"
            port = u.port or 80
            path = u.path + (f"?{u.query}" if u.query else "")

            sock = _sock_mod.create_connection((host, port), timeout=5)
            self._sock = sock
            if not self._running:
                try:
                    sock.close()
                except Exception:
                    pass
                return
            nonce = _b64.b64encode(os.urandom(16)).decode()
            hs = (
                f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {nonce}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            )
            sock.sendall(hs.encode())
            buf = b""
            while b"\r\n\r\n" not in buf:
                if not self._running:
                    return
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("CDP websocket handshake closed")
                buf += chunk

            def _ws_send(payload: str):
                data = payload.encode("utf-8")
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

            def _ws_recv_message(timeout_s: float = 15.0) -> str | None:
                """Read one full WebSocket text message (handles fragmentation)."""
                sock.settimeout(min(2.0, float(timeout_s)))
                assembled = bytearray()
                deadline = time.time() + float(timeout_s)
                while self._running and time.time() < deadline:
                    try:
                        hdr = b""
                        while len(hdr) < 2:
                            if not self._running:
                                return None
                            chunk = sock.recv(2 - len(hdr))
                            if not chunk:
                                return None
                            hdr += chunk
                        b1, b2 = hdr[0], hdr[1]
                        fin = bool(b1 & 0x80)
                        opcode = b1 & 0x0F
                        masked = bool(b2 & 0x80)
                        length = b2 & 0x7F
                        if length == 126:
                            ext = b""
                            while len(ext) < 2:
                                ext += sock.recv(2 - len(ext))
                            length = struct.unpack(">H", ext)[0]
                        elif length == 127:
                            ext = b""
                            while len(ext) < 8:
                                ext += sock.recv(8 - len(ext))
                            length = struct.unpack(">Q", ext)[0]
                        mask_key = b""
                        if masked:
                            mask_key = b""
                            while len(mask_key) < 4:
                                mask_key += sock.recv(4 - len(mask_key))
                        payload = b""
                        while len(payload) < length:
                            if not self._running:
                                return None
                            payload += sock.recv(min(65536, length - len(payload)))
                        if masked and mask_key:
                            payload = bytes(
                                b ^ mask_key[i % 4] for i, b in enumerate(payload)
                            )
                        if opcode == 0x8:  # close
                            return None
                        if opcode in (0x1, 0x0, 0x2):
                            assembled.extend(payload)
                            if fin:
                                return assembled.decode("utf-8", errors="replace")
                        # ignore ping/pong/etc.
                    except _sock_mod.timeout:
                        continue
                return None

            def _ingest_cookies(cookies_list):
                for c in cookies_list or []:
                    domain = (c.get("domain") or "").lower()
                    if not cookie_allowlist.is_onlyfans_host(domain):
                        continue
                    n = c.get("name", "")
                    v = c.get("value", "")
                    if not cookie_allowlist.is_allowed_cookie_name(n) or not v:
                        continue
                    if n == "sess":
                        result["sess"] = v
                    elif n == "auth_id":
                        result["auth_id"] = v
                    elif n.startswith("auth_uid") and "auth_uid" not in result:
                        result["auth_uid"] = v

            # Ask for cookies a couple of ways — browser target supports both.
            req_id = 1
            _ws_send(json.dumps({"id": req_id, "method": "Network.getAllCookies"}))
            pending = {req_id}
            req_id += 1
            _ws_send(
                json.dumps(
                    {
                        "id": req_id,
                        "method": "Network.getCookies",
                        "params": {
                            "urls": [
                                "https://onlyfans.com",
                                "https://onlyfans.com/",
                                "https://www.onlyfans.com",
                            ]
                        },
                    }
                )
            )
            pending.add(req_id)
            req_id += 1
            _ws_send(
                json.dumps(
                    {
                        "id": req_id,
                        "method": "Storage.getCookies",
                        "params": {},
                    }
                )
            )
            pending.add(req_id)

            deadline_reads = 40
            while pending and deadline_reads > 0 and self._running:
                deadline_reads -= 1
                msg = _ws_recv_message(timeout_s=12.0)
                if msg is None:
                    break
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue
                eid = evt.get("id")
                if eid not in pending:
                    continue
                pending.discard(eid)
                if evt.get("error"):
                    log.debug(f"CDP cookie method error id={eid}: {evt.get('error')}")
                    continue
                _ingest_cookies(evt.get("result", {}).get("cookies", []))
                if result.get("sess") and result.get("auth_id"):
                    break

            try:
                sock.close()
            except Exception:
                pass
            if result and self._running:
                log.info(
                    "CDP cookies captured: "
                    + ", ".join(
                        f"{k}={'yes' if result.get(k) else 'no'}"
                        for k in ("sess", "auth_id", "auth_uid")
                    )
                )
        except Exception as e:
            log.debug(f"CDPCookieFetcher error: {e}")
        finally:
            self._sock = None
        if self._running:
            try:
                self.result_ready.emit(result)
            except Exception:
                pass


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
        self._use_cdp = _USE_CDP
        self._cancelled = False
        self._timed_out = False
        self._wait_seconds = 0
        self._wait_timer = None
        self._login_timeout_s = _auth_login_timeout_seconds()
        self._hint_label = None
        self._cancel_btn = None
        # Allocate debug port BEFORE any QWebEngineView is created so Chromium
        # picks up the QTWEBENGINE_CHROMIUM_FLAGS env-var.
        self._debug_port = _get_or_create_debug_port()

        self._setup_webengine()  # raises ImportError if PyQt6-WebEngine missing
        self._setup_ui()
        self._start_wait_timer()

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

        # Set a standard, stable stable Chrome version (e.g. Chrome 126) to bypass CloudflareTurnstile
        # which blocks future/unreleased versions like Chrome 140 reported by QtWebEngine.
        import platform
        os_name = platform.system()
        if os_name == "Windows":
            os_ua = "Windows NT 10.0; Win64; x64"
        elif os_name == "Darwin":
            os_ua = "Macintosh; Intel Mac OS X 10_15_7"
        else:
            os_ua = "X11; Linux x86_64"
        
        stable_ua = f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self._profile.setHttpUserAgent(stable_ua)

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

        # Connect permission request handlers to allow cookies/storage/web-security features to load
        try:
            page.permissionRequested.connect(self._handle_permission_requested)
        except AttributeError:
            try:
                page.featurePermissionRequested.connect(self._handle_feature_permission_requested)
            except AttributeError:
                pass

        # Set a solid background colour so the view never appears transparent
        # while the page is loading — critical on Linux compositing managers
        # (KDE, GNOME with Mutter) that otherwise show the desktop through it.
        from PyQt6.QtGui import QColor as _QColor
        page.setBackgroundColor(_QColor(30, 30, 46))  # #1e1e2e — matches UI chrome

        self._cookie_store = self._profile.cookieStore()
        self._cookie_store.cookieAdded.connect(self._on_cookie_added)

        # Set a cookie filter that always returns True to allow third-party cookies
        try:
            self._cookie_store.setCookieFilter(lambda request: True)
        except Exception:
            pass

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
        if self._use_cdp:
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
            "once you are logged in and the page makes API calls.\n"
            + _format_login_wait_line(0, getattr(self, "_login_timeout_s", 0), kind="login")
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: #cdd6f4; font-size: {scale_px(12)}px;")
        self._hint_label = hint
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
            f"color: #fab387; font-size: {scale_px(11)}px; font-weight: bold; font-family: monospace;"
        )
        self._login_status_lbl.setToolTip(
            "Credentials are only usable after you have logged in to OnlyFans.\n"
            "Some fields (user-agent, x-bc, sess) are captured from pre-login page\n"
            "requests and are not yet valid auth credentials.\n"
            "Once auth_id is detected, you are logged in and all credentials are ready."
        )
        footer_layout.addWidget(self._login_status_lbl)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: #45475a; font-size: {scale_px(11)}px;")
        footer_layout.addWidget(sep)

        for label_key, display in [
            ("sess", "sess"),
            ("auth_id", "auth_id"),
            ("x-bc", "x-bc"),
            ("user_agent", "user-agent"),
        ]:
            lbl = QLabel(f"{display}: —")
            lbl.setStyleSheet(f"color: #6c7086; font-size: {scale_px(11)}px; font-family: monospace;")
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
        xbc_hint.setStyleSheet(f"color: #fab387; font-size: {scale_px(11)}px;")
        xbc_hint.setWordWrap(False)
        xbc_layout.addWidget(xbc_hint)

        from PyQt6.QtWidgets import QLineEdit as _QLE
        self._xbc_input = _QLE()
        self._xbc_input.setPlaceholderText("Paste x-bc value here…")
        self._xbc_input.setMaximumWidth(360)
        self._xbc_input.setStyleSheet(
            f"QLineEdit {{ background: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; "
            f"border-radius: 4px; padding: 4px 8px; font-family: monospace; font-size: {scale_px(11)}px; }}"
            f"QLineEdit:focus {{ border-color: #89b4fa; }}"
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

        cancel_btn = QPushButton("Cancel Login")
        cancel_btn.setToolTip(
            "Stop waiting, close the embedded browser session, and return without importing credentials."
        )
        cancel_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #cdd6f4; border-radius: 4px; padding: 6px 14px; }"
            "QPushButton:hover { background: #45475a; }"
            "QPushButton:disabled { background: #1e1e2e; color: #6c7086; }"
        )
        cancel_btn.clicked.connect(self._on_cancel_login)
        self._cancel_btn = cancel_btn
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
            lbl.setStyleSheet(f"color: #a6e3a1; font-size: {scale_px(11)}px; font-family: monospace;")
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
                    f"color: #a6e3a1; font-size: {scale_px(11)}px; font-weight: bold; font-family: monospace;"
                )
            else:
                self._login_status_lbl.setText("⚠ Not logged in")
                self._login_status_lbl.setStyleSheet(
                    f"color: #fab387; font-size: {scale_px(11)}px; font-weight: bold; font-family: monospace;"
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
                lbl.setStyleSheet(f"color: #6c7086; font-size: {scale_px(11)}px; font-family: monospace;")
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
            lbl.setStyleSheet(f"color: #6c7086; font-size: {scale_px(11)}px; font-family: monospace;")
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
        if getattr(self, "_wait_timer", None) and self._wait_timer.isActive():
            self._wait_timer.stop()
        if self._cdp_listener and self._cdp_listener.isRunning():
            self._cdp_listener.stop()
            self._cdp_listener.wait(2000)
        fetcher = getattr(self, "_cookie_fetcher", None)
        if fetcher is not None:
            try:
                if hasattr(fetcher, "stop"):
                    fetcher.stop()
            except Exception:
                pass
            try:
                if fetcher.isRunning():
                    if not fetcher.wait(3000):
                        fetcher.terminate()
                        fetcher.wait(1000)
            except Exception:
                pass
            try:
                fetcher.setParent(None)
            except Exception:
                pass
            self._cookie_fetcher = None

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

    def _start_wait_timer(self):
        self._wait_seconds = 0
        self._wait_timer = QTimer(self)
        self._wait_timer.setInterval(1000)
        self._wait_timer.timeout.connect(self._on_wait_tick)
        self._wait_timer.start()

    def _on_wait_tick(self):
        if self._cancelled or self._logged_in:
            return
        self._wait_seconds += 1
        timeout_s = int(getattr(self, "_login_timeout_s", 0) or 0)
        if self._hint_label:
            self._hint_label.setText(
                "Log in to OnlyFans below. Credentials are captured automatically "
                "once you are logged in and the page makes API calls.\n"
                + _format_login_wait_line(self._wait_seconds, timeout_s, kind="login")
            )
        if timeout_s > 0 and self._wait_seconds >= timeout_s:
            self._on_login_timeout()

    def _on_login_timeout(self):
        """Hard timeout — abort incomplete browser login."""
        if self._cancelled or self._logged_in:
            return
        self._timed_out = True
        limit_m = max(1, (int(getattr(self, "_login_timeout_s", 0) or 0) + 59) // 60)
        try:
            if self._hint_label:
                self._hint_label.setText(
                    f"Login timed out after {limit_m} min — closing without importing credentials."
                )
        except Exception:
            pass
        try:
            app_signals.status_message.emit(
                f"Browser login timed out after {limit_m} min"
            )
        except Exception:
            pass
        log.info(f"[GUI] Embedded browser login timed out after {self._wait_seconds}s")
        self._on_cancel_login()

    def _on_cancel_login(self):
        """User aborted embedded browser login — stop WebEngine/CDP and close."""
        if self._cancelled:
            return
        self._cancelled = True
        try:
            if self._cancel_btn:
                self._cancel_btn.setEnabled(False)
                self._cancel_btn.setText("Cancelling…")
        except Exception:
            pass
        try:
            if self._hint_label and not getattr(self, "_timed_out", False):
                self._hint_label.setText(
                    "Cancelling login… closing embedded browser session."
                )
        except Exception:
            pass
        try:
            if self._login_status_lbl:
                self._login_status_lbl.setText(
                    "Timed out" if getattr(self, "_timed_out", False) else "Cancelled"
                )
                self._login_status_lbl.setStyleSheet(
                    f"color: #f38ba8; font-size: {scale_px(11)}px; font-weight: bold; font-family: monospace;"
                )
        except Exception:
            pass
        try:
            if not getattr(self, "_timed_out", False):
                app_signals.status_message.emit("Browser login cancelled")
        except Exception:
            pass
        self.reject()

    def _handle_permission_requested(self, permission):
        try:
            permission.grant()
        except Exception:
            pass

    def _handle_feature_permission_requested(self, security_origin, feature):
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePage

            self._view.page().setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser,
            )
        except Exception:
            pass




def _auth_help_btn_qss():
    return (
        f"QToolButton {{ border: 1px solid {c('surface1')}; border-radius: 9px;"
        f" background-color: {c('surface0')}; color: {c('text')}; font-weight: bold; }}"
        f" QToolButton:hover {{ border-color: {c('blue')}; background-color: {c('surface1')}; }}"
    )


def _login_sync_style(kind: str) -> str:
    """Theme-aware styles for ChromeLoginMonitorDialog (System Browser Login Sync)."""
    if kind == "title":
        return f"color: {c('blue')};"
    if kind == "body":
        return f"color: {c('text')}; font-size: {scale_px(12)}px;"
    if kind == "wait":
        return f"color: {c('peach')}; font-size: {scale_px(11)}px; font-weight: bold;"
    if kind == "wait_error":
        return f"color: {c('red')}; font-size: {scale_px(11)}px; font-weight: bold;"
    if kind == "field_label":
        return (
            f"color: {c('subtext')}; font-weight: bold; font-family: monospace;"
        )
    if kind == "waiting":
        return f"color: {c('muted')}; font-family: monospace;"
    if kind == "captured":
        return f"color: {c('green')}; font-family: monospace;"
    if kind == "error":
        return f"color: {c('red')}; font-family: monospace;"
    if kind == "pending_login":
        return f"color: {c('yellow')}; font-family: monospace;"
    return f"color: {c('text')};"


def _make_auth_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help for this authentication option")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(_auth_help_btn_qss())
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b


class AuthPage(QWidget):
    """Authentication credential editor page — replaces the InquirerPy auth prompt.
    Displayed inline as a page in the main window stack."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._inputs = {}
        self._setup_ui()
        self._load_auth()
        try:
            app_signals.privacy_mode_changed.connect(self._on_privacy_mode_changed)
            self._apply_privacy_mode()
        except Exception:
            pass
        try:
            app_signals.theme_changed.connect(self._apply_help_btn_theme)
        except Exception:
            pass

    def _apply_help_btn_theme(self, _is_dark=True):
        for btn in self.findChildren(QToolButton):
            if btn.text() == "?":
                btn.setStyleSheet(_auth_help_btn_qss())

    def _setup_ui(self):
        """Auth page with full guidance text; sticky footer; scroll when needed.

        Keeps Credentials at a comfortable field height. Long sections scroll so
        small screens do not crush the form; Save/Test stay pinned below.
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 12)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(10)

        # Header
        header = QLabel("Authentication")
        apply_font(header, "Segoe UI", 20, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Enter your OnlyFans authentication credentials. "
            "These are stored in auth.json in your profile directory. "
            "Use the (?) buttons for help on each option."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Credential fields — same single-column form as large screens; fixed field height
        form_group = QGroupBox("Credentials")
        form_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        form_outer = QVBoxLayout(form_group)
        form_outer.setContentsMargins(10, 8, 10, 10)
        form_outer.setSpacing(6)

        cred_hint_row = QHBoxLayout()
        cred_hint = QLabel(
            "Paste sess / auth_id / x-bc / user-agent from DevTools, "
            "or use Import Cookies / Login in Browser below. "
            "Hover field labels for DevTools tips."
        )
        cred_hint.setProperty("hint", True)
        cred_hint.setWordWrap(True)
        cred_hint_row.addWidget(cred_hint, stretch=1)
        cred_hint_row.addWidget(_make_auth_help_btn("auth-credentials"))
        form_outer.addLayout(cred_hint_row)

        form_layout = QFormLayout()
        form_layout.setSpacing(8)
        form_layout.setHorizontalSpacing(12)
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        form_outer.addLayout(form_layout)

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
            line_edit.setMinimumHeight(28)
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if field_key == "sess":
                self._sess_toggle = QAction(self)
                self._sess_toggle.setIcon(self._make_eye_icon(visible=True))
                self._sess_toggle.setToolTip("Show/hide session cookie")
                self._sess_toggle.triggered.connect(self._toggle_sess_visibility)
                line_edit.addAction(self._sess_toggle, QLineEdit.ActionPosition.TrailingPosition)
            form_layout.addRow(label_text + ":", line_edit)
            self._inputs[field_key] = line_edit

        layout.addWidget(form_group)

        # Local browser cookie extraction
        extract_group = QGroupBox("Import Cookies from Local Browser (Recommended)")
        extract_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        extract_inner = QVBoxLayout(extract_group)
        extract_inner.setContentsMargins(10, 8, 10, 10)
        extract_inner.setSpacing(6)

        if platform.system() == "Windows":
            extract_info = QLabel(
                "This dropdown is shared by Import Cookies and Login in System Browser.\n\n"
                "Import Cookies (reads cookies already on disk):\n"
                "• On Windows use Zen Browser or Firefox — disk import works.\n"
                "• Chrome / Chromium / Edge / Brave / Opera Import Cookies is Linux-only "
                "on this build (Windows App-Bound Encryption + Chrome DevTools restrictions; "
                "profile relaunch is disabled because it can corrupt Chrome / log you out).\n"
                "• For Chrome on Windows: paste sess / auth_id / x-bc / user-agent from DevTools, "
                "use Zen/Firefox → Import Cookies, or use Login in System Browser / App Browser below.\n\n"
                "Login in System Browser (below) can use any browser in this list, including Chrome on Windows — "
                "it opens a temporary profile and is not limited by the Import Cookies Linux-only note."
            )
        else:
            extract_info = QLabel(
                "This dropdown is shared by Import Cookies and Login in System Browser.\n"
                "Stay logged into OnlyFans in that browser, then select it and click Import Cookies.\n"
                "On Linux, which install is used (apt / Flatpak / Snap / deb) is detected automatically "
                "from the running browser — you do not need to know how it was installed.\n"
                "Login in System Browser (below) uses the same selection with a temporary profile."
            )
        extract_info.setWordWrap(True)
        extract_info.setProperty("hint", True)
        extract_row_hint = QHBoxLayout()
        extract_row_hint.addWidget(extract_info, stretch=1)
        extract_row_hint.addWidget(_make_auth_help_btn("auth-import-cookies"))
        extract_inner.addLayout(extract_row_hint)

        extract_row = QHBoxLayout()
        extract_row.setSpacing(8)
        self.browser_combo = QComboBox()
        _populate_browser_import_combo(self.browser_combo)
        self.browser_combo.setMinimumWidth(200)
        self.browser_combo.setMaximumWidth(280)
        # Do not set a local stylesheet — hardcoded dark colors override light mode.
        # App theme QSS already styles QComboBox + dropdown view.

        try:
            default_browser = _get_default_browser_name()
            display_map = {
                "chrome": "Chrome",
                "chromium": "Chromium",
                "firefox": "Firefox",
                "zenbrowser": "Zen Browser",
                "opera": "Opera",
                "operagx": "Opera GX",
                "edge": "Edge",
                "brave": "Brave",
                "vivaldi": "Vivaldi",
            }
            if platform.system() == "Windows" and _find_browser_executable("zenbrowser"):
                default_display = "Zen Browser"
            elif platform.system() == "Windows" and default_browser in {
                "chrome", "chromium", "edge", "brave", "opera", "operagx", "vivaldi"
            }:
                default_display = (
                    "Firefox" if _find_browser_executable("firefox") else "Zen Browser"
                )
            else:
                default_display = display_map.get(default_browser, "Chrome")
            if not _combo_select_browser(self.browser_combo, default_display):
                if not _combo_select_browser(self.browser_combo, "Zen Browser"):
                    _combo_select_browser(self.browser_combo, "Firefox")
        except Exception:
            pass

        self.import_browser_btn = StyledButton("Import Cookies")
        self.import_browser_btn.setToolTip(
            "Import Cookies: extract session cookies and User-Agent from the selected browser profile on disk.\n"
            "Linux: detects whether the running browser is apt, Flatpak, Snap, or deb.\n"
            "Windows: Zen/Firefox for disk import. Chrome-family Import Cookies is Linux-only "
            "(Login in System Browser can still use Chrome on Windows)."
        )
        self.import_browser_btn.clicked.connect(self._import_from_browser)

        extract_row.addWidget(QLabel("Select Browser:"))
        extract_row.addWidget(self.browser_combo)
        extract_row.addWidget(self.import_browser_btn)
        extract_row.addStretch()
        extract_inner.addLayout(extract_row)
        layout.addWidget(extract_group)

        # Browser login
        import_group = QGroupBox("Login in Browser")
        import_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        import_inner = QVBoxLayout(import_group)
        import_inner.setContentsMargins(10, 8, 10, 10)
        import_inner.setSpacing(6)

        info_label = QLabel(
            "Log in to OnlyFans in a browser and capture credentials automatically.\n\n"
            "• Login in System Browser: Opens a temporary copy of whichever browser is selected "
            "in Select Browser above — including Chrome / Edge / Brave on Windows. "
            "Fresh empty profile (not your everyday session); you must log in again.\n"
            "• Prefer Import Cookies above when you are already logged in "
            "(Zen/Firefox on Windows; any listed browser on Linux).\n"
            "• Login in App Browser: Opens an embedded OnlyFans window inside this app."
        )
        info_label.setWordWrap(True)
        info_label.setProperty("hint", True)
        login_hint_row = QHBoxLayout()
        login_hint_row.addWidget(info_label, stretch=1)
        login_hint_row.addWidget(_make_auth_help_btn("auth-login-browser"))
        import_inner.addLayout(login_hint_row)

        login_row = QHBoxLayout()
        login_row.setSpacing(6)
        login_row.addStretch()

        system_chrome_btn = StyledButton("Login in System Browser…", primary=True)
        system_chrome_btn.setToolTip(
            "Uses the browser selected in Select Browser above.\n"
            "Works with any listed browser (including Chrome on Windows) — "
            "the Import Cookies Linux-only limit does not apply here.\n"
            "Opens that browser with a temporary/fresh profile — not your normal profile.\n"
            "Log in to OnlyFans in that window; credentials are captured automatically.\n"
            "Use Cancel Login in the sync dialog to abort and close that browser.\n"
            "For an existing logged-in session, use Import Cookies instead."
        )
        system_chrome_btn.clicked.connect(self._open_system_browser_login)
        self._system_browser_login_btn = system_chrome_btn
        login_row.addWidget(system_chrome_btn)
        login_row.addWidget(_make_auth_help_btn("auth-login-system-browser"))

        login_btn = StyledButton("Login in App Browser…")
        login_btn.setToolTip(
            "Opens an embedded OnlyFans browser window.\n"
            "Log in and all auth fields are captured automatically.\n"
            "Use Cancel Login in that window to abort without importing.\n"
            "Requires: pip install PyQt6-WebEngine"
        )
        login_btn.clicked.connect(self._open_browser_login)
        self._app_browser_login_btn = login_btn
        login_row.addWidget(login_btn)
        login_row.addWidget(_make_auth_help_btn("auth-login-app-browser"))
        import_inner.addLayout(login_row)
        layout.addWidget(import_group)

        # Troubleshooting help
        help_group = QGroupBox("Still having issues?")
        help_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        help_layout = QVBoxLayout(help_group)
        help_layout.setContentsMargins(10, 8, 10, 10)
        help_layout.setSpacing(6)

        help_label = QLabel(
            "If authentication keeps failing, try the following:\n"
            "\n"
            "1. Make sure you are logged into OnlyFans in your browser\n"
            "2. Try changing the Dynamic Rules setting in Configuration > General\n"
            "    (try 'digitalcriminals', 'datawhores', or 'xagler')\n"
            "3. Clear your browser cookies for OnlyFans, log in again, and re-import\n"
            "4. Manually copy all values from browser DevTools "
            "(F12 > Network tab > any API request headers)\n"
            "5. Check the OF-Scraper docs / Open Auth Help Docs below"
        )
        help_label.setWordWrap(True)
        help_label.setProperty("hint", True)
        issues_row = QHBoxLayout()
        issues_row.addWidget(help_label, stretch=1)
        issues_row.addWidget(_make_auth_help_btn("auth-issues"))
        help_layout.addLayout(issues_row)

        docs_btn = StyledButton("Open Auth Help Docs")
        docs_btn.setToolTip(
            "Open the in-app Auth Issues help section (same Help page every time)"
        )
        docs_btn.clicked.connect(
            lambda: app_signals.help_anchor_requested.emit("auth-issues")
        )
        help_layout.addWidget(docs_btn)
        layout.addWidget(help_group)
        layout.addStretch(1)

        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        # Action buttons — always visible below the scroll area
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 4, 0, 0)
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

        root.addLayout(btn_layout)

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
        try:
            from ofscraper.gui.utils.privacy_mode import is_privacy_mode

            if is_privacy_mode():
                app_signals.status_message.emit(
                    "Turn off Privacy mode to reveal credentials"
                )
                return
        except Exception:
            pass
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

    def _on_privacy_mode_changed(self, enabled: bool):
        self._apply_privacy_mode(enabled)

    def _apply_privacy_mode(self, enabled=None):
        """Mask credential fields with password echo when privacy / demo mode is on."""
        try:
            from ofscraper.gui.utils.privacy_mode import is_privacy_mode

            on = is_privacy_mode() if enabled is None else bool(enabled)
        except Exception:
            on = False
        for field_key, _ in AUTH_FIELDS:
            w = self._inputs.get(field_key)
            if not w:
                continue
            if on:
                w.setEchoMode(QLineEdit.EchoMode.Password)
            elif field_key == "sess" and w.text():
                w.setEchoMode(QLineEdit.EchoMode.Password)
            else:
                w.setEchoMode(QLineEdit.EchoMode.Normal)
        try:
            if hasattr(self, "_sess_toggle") and self._sess_toggle:
                self._sess_toggle.setEnabled(not on)
                self._sess_toggle.setToolTip(
                    "Turn off Privacy mode to show/hide session cookie"
                    if on
                    else "Show/hide session cookie"
                )
        except Exception:
            pass

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

            self._apply_privacy_mode()

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
            # write_auth allowlists keys + hardens file permissions
            write_auth(auth)
            log.info(
                "Auth saved successfully. Keys with values: "
                f"{[k for k in required if auth.get(k)]}"
            )
            # Mask session cookie after saving
            sess = self._inputs.get("sess")
            if sess and sess.text():
                sess.setEchoMode(QLineEdit.EchoMode.Password)

            app_signals.status_message.emit("Auth credentials saved")
            try:
                app_signals.auth_updated.emit()
            except Exception:
                pass
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

    @staticmethod
    def _is_docker() -> bool:
        """Return True when running inside a Docker / OCI container."""
        if os.path.exists("/.dockerenv"):
            return True
        try:
            with open("/proc/1/cgroup", errors="ignore") as _f:
                _c = _f.read()
                return "docker" in _c or "containerd" in _c
        except OSError:
            pass
        return False

    def _open_browser_login(self):
        """Open embedded browser login dialog and populate fields from captured credentials."""
        # QtWebEngine (Chromium) cannot run reliably in Docker — no GPU and
        # Docker's default 64 MB /dev/shm causes an immediate Chromium crash.
        if self._is_docker():
            QMessageBox.information(
                self,
                "Login in Browser — Not Supported in Docker",
                "The embedded browser login is not available when running inside Docker.\n\n"
                "To authenticate, copy your credentials manually from your browser:\n\n"
                "1. Open OnlyFans in your regular browser and log in\n"
                "2. Press F12 → Network tab → click any OnlyFans API request\n"
                "3. Copy the following from the request headers:\n"
                "     • cookie: sess=…  (the sess value)\n"
                "     • cookie: auth_id=…  (the auth_id value)\n"
                "     • user-agent\n"
                "     • x-bc\n"
                "4. Paste each value into the fields above",
            )
            return
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
        self._set_browser_login_busy(True, "App browser login in progress — use Cancel Login to abort")
        dlg.credentials_ready.connect(self._apply_browser_credentials)
        try:
            dlg.exec()
        finally:
            self._set_browser_login_busy(False)

    def _set_browser_login_busy(self, busy: bool, status: str = ""):
        """Disable login launchers while a login dialog is open."""
        try:
            if getattr(self, "_system_browser_login_btn", None):
                self._system_browser_login_btn.setEnabled(not busy)
            if getattr(self, "_app_browser_login_btn", None):
                self._app_browser_login_btn.setEnabled(not busy)
        except Exception:
            pass
        if busy and status:
            try:
                app_signals.status_message.emit(status)
            except Exception:
                pass
        elif not busy:
            try:
                app_signals.status_message.emit("Ready")
            except Exception:
                pass

    def _apply_browser_credentials(self, creds: dict):
        """Populate auth fields from credentials captured by BrowserLoginDialog."""
        mapping = {
            "sess": "sess",
            "auth_id": "auth_id",
            "auth_uid": "auth_uid",
            "user_agent": "user_agent",
            "x-bc": "x-bc",
        }
        # Last-resort guard: never leave a Chrome UA after Firefox/Zen capture
        browser_hint = (creds.get("_browser_name") or "").lower().replace(" ", "")
        ua_val = (creds.get("user_agent") or "").strip()
        if browser_hint in {"firefox", "zenbrowser"} and ua_val and not _ua_looks_like_firefox(ua_val):
            fixed = _resolve_firefox_family_user_agent(
                browser_hint if browser_hint in {"firefox", "zenbrowser"} else "firefox",
                browser_path=_find_browser_executable(
                    browser_hint if browser_hint in {"firefox", "zenbrowser"} else "firefox"
                ),
                preferred_ua=None,
            )
            if fixed:
                creds = dict(creds)
                creds["user_agent"] = fixed
                log.warning(
                    f"Rejected non-Firefox UA after {browser_hint} capture; using {fixed}"
                )

        imported = []
        for cred_key, field_key in mapping.items():
            value = creds.get(cred_key, "").strip()
            if value and field_key in self._inputs:
                self._inputs[field_key].setText(value)
                imported.append(cred_key)

        xbc_generated = creds.get("_xbc_generated", False)
        missing = [k for k in ("sess", "auth_id", "x-bc") if not creds.get(k)]
        msg_parts = [f"Imported: {', '.join(imported) if imported else 'nothing'}"]
        if creds.get("user_agent"):
            msg_parts.append(f"user-agent:\n{creds['user_agent']}")
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
        if getattr(self, "_cookie_import_busy", False):
            return

        browser_name, install_method = _combo_browser_selection(self.browser_combo)
        browser_display = _combo_browser_display(self.browser_combo)
        linux_install = None
        linux_resolve_source = "none"
        if platform.system() == "Linux":
            # Ignore any leftover method in the combo role — resolve from the
            # running process (or freshest disk profile if the browser is closed).
            linux_install, linux_resolve_source = _resolve_linux_install_for_import(browser_name)
            if linux_install:
                install_method = linux_install.method
                browser_display = (
                    f"{_linux_display_name(browser_name)} "
                    f"({_linux_method_label(linux_install.method)})"
                )
                log.info(
                    f"Using Linux browser install: {browser_display} "
                    f"(source={linux_resolve_source}, exe={linux_install.executable})"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Browser Not Detected",
                    f"No install of {_linux_display_name(browser_name)} was detected "
                    f"(apt/deb, Snap, or Flatpak).\n\n"
                    f"Install the browser, open OnlyFans once, then try Import again.",
                )
                return

        chromium_family = browser_name in {
            "chrome", "chromium", "edge", "brave", "opera", "operagx", "vivaldi"
        }
        # Windows Chrome-family: auto-import is not reliable (ABE + Chrome 136+). Do not
        # launch browsers or touch the live profile — steer users to Zen/Firefox or manual.
        if platform.system() == "Windows" and chromium_family:
            self._warn_windows_chromium_import_unsupported(browser_display)
            return

        self._cookie_import_busy = True
        self._cookie_import_cancelled = False
        self.import_browser_btn.setEnabled(False)
        self.import_browser_btn.setText("Importing…")
        app_signals.status_message.emit(
            f"Importing cookies from {browser_display}… (Cancel to abort)"
        )

        self._cookie_import_progress = QDialog(self)
        self._cookie_import_progress.setWindowTitle("Import Cookies")
        self._cookie_import_progress.setWindowFlags(
            self._cookie_import_progress.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._cookie_import_progress.setMinimumWidth(420)
        self._cookie_import_progress.setModal(True)
        _vbox = QVBoxLayout(self._cookie_import_progress)
        _vbox.setSpacing(12)
        _vbox.setContentsMargins(20, 20, 20, 20)
        _lbl = QLabel(
            f"Reading session cookies from {browser_display}…\n\n"
            "This can take a few seconds while cookie databases are copied and decrypted.\n"
            "Click Cancel to abort and return to Authentication."
        )
        _lbl.setWordWrap(True)
        _vbox.addWidget(_lbl)
        _bar = QProgressBar()
        _bar.setRange(0, 0)
        _bar.setTextVisible(False)
        _vbox.addWidget(_bar)
        _cancel = StyledButton("Cancel")
        _cancel.setToolTip("Stop waiting and discard this import")
        _row = QHBoxLayout()
        _row.addStretch()
        _row.addWidget(_cancel)
        _vbox.addLayout(_row)

        self._cookie_import_worker = _CookieImportWorker(
            browser_name=browser_name,
            install_method=install_method,
            browser_display=browser_display,
            linux_install=linux_install,
            linux_resolve_source=linux_resolve_source,
            parent=self,
        )
        self._cookie_import_worker.result_ready.connect(self._on_cookie_import_done)

        def _on_cancel():
            if self._cookie_import_cancelled:
                return
            self._cookie_import_cancelled = True
            _cancel.setEnabled(False)
            _cancel.setText("Cancelling…")
            _lbl.setText("Cancelling cookie import…")
            app_signals.status_message.emit("Cancelling cookie import…")
            try:
                self._cookie_import_worker.request_cancel()
            except Exception:
                pass
            # Close dialog immediately so the Auth page stays responsive;
            # late worker results are discarded in _on_cookie_import_done.
            try:
                self._cookie_import_progress.accept()
            except Exception:
                pass
            self._reset_cookie_import_ui()
            app_signals.status_message.emit("Cookie import cancelled")

        _cancel.clicked.connect(_on_cancel)
        self._cookie_import_progress.rejected.connect(_on_cancel)
        self._cookie_import_worker.start()
        self._cookie_import_progress.exec()

    def _reset_cookie_import_ui(self):
        self._cookie_import_busy = False
        try:
            self.import_browser_btn.setEnabled(True)
            self.import_browser_btn.setText("Import Cookies")
        except Exception:
            pass

    def _on_cookie_import_done(self, result):
        try:
            dlg = getattr(self, "_cookie_import_progress", None)
            if dlg is not None:
                dlg.accept()
                self._cookie_import_progress = None
        except Exception:
            pass

        cancelled = getattr(self, "_cookie_import_cancelled", False)
        self._reset_cookie_import_ui()

        if cancelled or not result or result.get("status") == "cancelled":
            if not cancelled:
                app_signals.status_message.emit("Cookie import cancelled")
            return

        if result.get("status") == "error":
            app_signals.status_message.emit("Cookie import failed")
            QMessageBox.critical(
                self,
                result.get("title") or "Import Failed",
                result.get("message") or "Import failed.",
            )
            return

        if result.get("status") == "warning":
            QMessageBox.warning(
                self,
                result.get("title") or "Import",
                result.get("message") or "Import could not complete.",
            )
            return

        self._apply_cookie_import_result(result)

    def _apply_cookie_import_result(self, result: dict):
        """Apply extracted cookies to the form and show Import Results / follow-ups."""
        cookies = cookie_allowlist.filter_cookie_map(
            dict(result.get("cookies") or {}),
            keep_meta=True,
            keep_headers=True,
        )
        browser_name = result.get("browser_name")
        browser_display = result.get("browser_display") or browser_name
        install_method = result.get("install_method")
        linux_install = result.get("linux_install")
        linux_resolve_source = result.get("linux_resolve_source") or "none"
        if result.get("clear_xbc"):
            self._inputs["x-bc"].setText("")

        imported = []
        if cookies.get("sess"):
            self._inputs["sess"].setText(cookies["sess"])
            imported.append("sess")
        if cookies.get("auth_id"):
            self._inputs["auth_id"].setText(cookies["auth_id"])
            imported.append("auth_id")
        auth_uid_val = cookies.get("auth_uid")
        if not auth_uid_val:
            auth_uid_key = next(
                (k for k in cookies if str(k).startswith("auth_uid") and not str(k).startswith("_")),
                None,
            )
            if auth_uid_key:
                auth_uid_val = cookies[auth_uid_key]
        if auth_uid_val:
            self._inputs["auth_uid"].setText(auth_uid_val)
            imported.append("auth_uid")
        if cookies.get("x-bc"):
            cleaned = _normalize_bctoken_value(cookies["x-bc"])
            if cleaned:
                cookies["x-bc"] = cleaned
                self._inputs["x-bc"].setText(cleaned)
                imported.append("x-bc")
            else:
                log.warning(
                    f"Discarded invalid x-bc from {browser_display}: "
                    f"{str(cookies['x-bc'])[:48]}"
                )
                cookies.pop("x-bc", None)

        # Check if essential session cookies (sess & auth_id) are missing
        if "sess" not in cookies or "auth_id" not in cookies:
            # Never auto-offer System Browser from Import Cookies on Windows Chromium —
            # that opens a separate blank profile and confuses users.
            if platform.system() == "Windows" and browser_name in {
                "chrome", "chromium", "edge", "brave", "opera", "operagx", "vivaldi"
            }:
                self._warn_windows_chromium_import_unsupported(browser_display)
                return

            reply = QMessageBox.question(
                self,
                "System Browser Recommended",
                f"Direct cookie file extraction from {browser_display} returned incomplete session data.\n"
                f"(Common when {browser_display} is still running, or the OS keyring password "
                f"for cookie decryption was unavailable.)\n\n"
                f"Recommended:\n"
                f"1. Fully quit {browser_display}\n"
                f"2. Click Import Cookies again\n\n"
                f"Or launch {browser_display} in System Browser mode to capture credentials "
                f"in a temporary profile (you will need to log into OnlyFans again there).\n\n"
                f"Open System Browser capture now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_system_browser_login()
                return

        # Missing real x-bc with a live sess is worse than empty — never invent one.
        if (
            browser_name in {"firefox", "zenbrowser"}
            and cookies.get("sess")
            and cookies.get("auth_id")
            and not cookies.get("x-bc")
        ):
            reply = QMessageBox.question(
                self,
                "x-bc Not Found",
                f"Imported sess / auth_id from {browser_display}, but could not read the "
                f"real bcTokenSha (x-bc) from localStorage.\n\n"
                f"A synthetic x-bc will NOT work with OnlyFans (Wrong user).\n\n"
                f"Tips:\n"
                f"• Fully quit {browser_display}, then Import Cookies again\n"
                f"• Or use Login in System Browser to capture x-bc from live headers\n"
                f"• Or paste x-bc from DevTools → Network → any /api2/ request\n\n"
                f"Open System Browser capture now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_system_browser_login()
                return

        # Always refresh User-Agent on import. Preserving a stale field value
        # (e.g. old Chrome/145 full version) causes OnlyFans "Wrong user" even when
        # sess/auth_id/x-bc match DevTools.
        ua_detected = False
        ua_source = str(cookies.get("_ua_source") or "")
        ua_confirm_prompted = False
        try:
            if browser_name in {"firefox", "zenbrowser"}:
                ua = (cookies.get("user_agent") or "").strip()
                if not ua:
                    ua, ua_source = _resolve_firefox_family_user_agent_ex(
                        browser_name,
                        browser_path=(
                            linux_install.executable
                            if linux_install and linux_install.executable
                            else _find_browser_executable(browser_name)
                        ),
                        profile_dir=cookies.get("_firefox_profile"),
                        allow_live=True,
                    )
                    cookies["_ua_source"] = ua_source
                switcher = cookies.get("_ua_switcher") or {}
                if not isinstance(switcher, dict):
                    switcher = {}
                if not switcher and cookies.get("_firefox_profile"):
                    switcher = _read_firefox_ua_switcher_state(
                        cookies.get("_firefox_profile")
                    )
                spoof_from_switcher = bool(
                    switcher.get("active")
                    and (switcher.get("onlyfans_ua") or switcher.get("current_ua") or "")
                )
                # Do not "reduce" live / FPP / switcher values — they must match Network.
                if (
                    ua
                    and _ua_looks_like_firefox(ua)
                    and ua_source
                    not in {"live_navigator", "fpp_prefs", "switcher_override"}
                ):
                    ua = _normalize_firefox_ua_reduction(ua)
                elif ua and _ua_looks_like_chromium(ua) and not spoof_from_switcher:
                    log.warning(
                        f"Discarding Chromium UA after {browser_display} import: {ua}"
                    )
                    ua, ua_source = _resolve_firefox_family_user_agent_ex(
                        browser_name,
                        browser_path=_find_browser_executable(browser_name),
                        profile_dir=cookies.get("_firefox_profile"),
                        allow_live=True,
                    )
                    cookies["_ua_source"] = ua_source

                # When we did not capture live navigator.userAgent, ask the user to
                # paste/confirm the DevTools Network header (actual request UA).
                needs_confirm = ua_source not in {
                    "live_navigator",
                    "gecko_milestone",
                    "profile",
                } or bool(
                    switcher.get("active") and switcher.get("random_enabled")
                )
                if needs_confirm:
                    source_notes = {
                        "fpp_prefs": (
                            "Candidate is derived from Fingerprinting Protection "
                            "prefs (frozen Firefox/115), not a live read."
                        ),
                        "switcher_override": (
                            "Candidate came from an active User-Agent Switcher override."
                        ),
                        "gecko_milestone": (
                            "Candidate is built from the browser Gecko milestone "
                            "(install version)."
                        ),
                        "profile": (
                            "Candidate came from profile files on disk."
                        ),
                        "preferred": (
                            "Candidate came from a previously preferred value."
                        ),
                    }
                    note = source_notes.get(
                        ua_source,
                        "Could not attach to a live remote-debugging port.",
                    )
                    pasted, ok = QInputDialog.getMultiLineText(
                        self,
                        "Confirm Live User-Agent",
                        (
                            f"{note}\n\n"
                            "Paste Request Headers → user-agent from an onlyfans.com "
                            f"request in {browser_display} DevTools (Network tab).\n\n"
                            "For automatic live capture next time, start the browser with "
                            "--remote-debugging-port=9222 then Import again.\n\n"
                            "OK keeps the candidate below if you leave it unchanged."
                        ),
                        (ua or "").strip(),
                    )
                    ua_confirm_prompted = True
                    if ok and (pasted or "").strip():
                        pasted = pasted.strip()
                        if "Mozilla/" in pasted:
                            ua = _fix_user_agent_casing(pasted)
                            ua_source = "user_paste"
                            cookies["_ua_source"] = ua_source
            else:
                ua = cookies.get("user_agent") or _detect_user_agent(browser_name)
                ua = _ensure_chromium_brand_ua(ua, browser_name)
                ua_source = "chromium_detect"
            if ua:
                self._inputs["user_agent"].setText(ua)
                if "user_agent" not in imported:
                    imported.append("user_agent")
                ua_detected = True
                log.info(
                    f"Import set user-agent from {browser_display} "
                    f"(source={ua_source or 'unknown'}): {ua}"
                )
            else:
                log.debug("User agent detection returned empty")
        except Exception as e:
            log.debug(f"User agent detection failed: {e}")

        if imported:
            app_signals.status_message.emit(
                f"Imported {', '.join(imported)} from {browser_display}"
            )

            # Build result message
            msg_parts = [f"Imported: {', '.join(imported)}"]
            if browser_name in {"zenbrowser", "firefox"}:
                src = cookies.get("_firefox_profile") or ""
                method = cookies.get("_firefox_install") or (
                    "flatpak" if cookies.get("_firefox_flatpak") else "apt"
                )
                msg_parts.append(
                    f"Profile source: {_linux_display_name(browser_name)} "
                    f"({_linux_method_label(method)})"
                    + (f"\n{src}" if src else "")
                    + (
                        "\nDetected from the running browser process."
                        if linux_resolve_source == "running"
                        else "\nBrowser was not running — used the most recent OnlyFans profile on disk."
                        if linux_resolve_source == "disk"
                        else ""
                    )
                )
                msg_parts.append(
                    "⚠️  IMPORTANT FOR FIREFOX/ZEN:\n"
                    "Firefox-based browsers keep active login sessions in RAM. "
                    "If you just logged in or your credentials test fails, you MUST close "
                    "Firefox/Zen fully and click Import Cookies again so it can read the "
                    "flushed session from disk.\n"
                    "Tip: leave the browser open when importing so Linux can detect "
                    "whether it is apt, Flatpak, Snap, or a .deb install."
                )
            elif install_method and platform.system() == "Linux":
                how = (
                    "running process"
                    if linux_resolve_source == "running"
                    else "disk profile"
                )
                msg_parts.append(
                    f"Profile source: {_linux_display_name(browser_name)} "
                    f"({_linux_method_label(install_method)}) — via {how}"
                )
            if ua_confirm_prompted:
                src = str(cookies.get("_ua_source") or ua_source or "")
                if src == "user_paste":
                    msg_parts.append(
                        "User-Agent was pasted from DevTools Network headers."
                    )
                elif src == "live_navigator":
                    msg_parts.append(
                        "User-Agent was read live from the browser "
                        "(remote debugging / navigator.userAgent)."
                    )
                else:
                    msg_parts.append(
                        f"User-Agent source: {src or 'unknown'}. "
                        "Confirm it matches DevTools → Network → user-agent."
                    )
            elif ua_detected:
                src = str(cookies.get("_ua_source") or ua_source or "")
                if src == "live_navigator":
                    msg_parts.append(
                        "User-Agent was read live from the browser "
                        "(navigator.userAgent via remote debugging)."
                    )
                else:
                    msg_parts.append(
                        "User-Agent was taken from the browser profile / Gecko version "
                        "(Firefox/Zen) or the Chromium install (Chrome-family).\n"
                        "It should match DevTools → Network → Request Headers → user-agent."
                    )
            else:
                msg_parts.append(
                    "User-Agent could not be read automatically. "
                    "Paste it from DevTools → Network → Request Headers → user-agent "
                    "(preferred) or Console → navigator.userAgent."
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

    def _warn_windows_chromium_import_unsupported(self, browser_display: str):
        """Explain that Chrome-family auto-import is Linux-only; offer Zen or manual paste."""
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(f"{browser_display} Import — Linux Only")
        msg.setText(
            f"Automatic cookie import from {browser_display} is not supported on Windows."
        )
        msg.setInformativeText(
            f"On Windows, {browser_display} uses App-Bound Encryption and Chrome 136+ blocks "
            f"DevTools on the default profile. OF-Scraper cannot reliably read sess / auth_id "
            f"from that browser without risking Profile errors or OnlyFans logouts "
            f"(that relaunch path has been disabled).\n\n"
            f"This limit applies to Import Cookies only. Chrome-family Import Cookies works on Linux.\n\n"
            f"On Windows, use one of:\n"
            f"• Zen Browser or Firefox → select it above → Import Cookies\n"
            f"• Paste sess / auth_id / x-bc / user-agent manually from DevTools "
            f"(Network → request → Request Headers)\n"
            f"• Login in System Browser… (temporary Chrome/Edge/Brave window — any browser in the dropdown)\n"
            f"• Login in App Browser… (embedded)\n"
        )
        paste_btn = msg.addButton("Paste Cookie Header…", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
        msg.exec()
        if msg.clickedButton() is paste_btn:
            self._prompt_windows_chromium_cookie_paste(browser_display, [])

    def _prompt_windows_chromium_cookie_paste(
        self, browser_display: str, already_imported: list | None = None
    ):
        """Windows Chrome/Edge/Brave cannot safely auto-read sess under App-Bound Encryption.

        Chrome 136+ also blocks DevTools on the default profile. Older sync attempts that
        killed Chrome or junctioned the live profile can corrupt it (Profile error + logout).
        This helper keeps the browser untouched and accepts a DevTools Cookie header paste.
        """
        already_imported = already_imported or []
        imported_note = (
            f"Already filled from browser storage: {', '.join(already_imported)}.\n\n"
            if already_imported
            else ""
        )

        # Best-effort soft repair if a prior sync left crash flags / singleton locks.
        try:
            browser_name = browser_display.lower().replace(" ", "")
            _repair_chromium_profile_flags(browser_name)
        except Exception as e:
            log.debug(f"Chrome profile flag repair skipped: {e}")

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Finish Import — {browser_display}")
        dlg.setMinimumWidth(560)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        info = QLabel(
            f"{imported_note}"
            f"On Windows, {browser_display} encrypts sess / auth_id (App-Bound Encryption) and "
            f"Chrome 136+ blocks DevTools on your real profile. OF-Scraper will not close, "
            f"relaunch, or modify {browser_display} to read those cookies — that path caused "
            f"Profile errors and OnlyFans logouts.\n\n"
            f"Keep OnlyFans open in {browser_display}, then paste the Cookie request header:\n"
            f"DevTools (F12) → Network → any onlyfans.com/api2 request → Request Headers → cookie\n\n"
            f"Or use Zen Browser and click Import Cookies (disk import works on Windows)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(info)

        paste = QTextEdit()
        paste.setPlaceholderText(
            "Paste the full cookie header here, e.g.\n"
            "auth_id=…; sess=…; auth_uid_=…; …"
        )
        paste.setMinimumHeight(120)
        paste.setStyleSheet(f"font-family: Consolas, 'Courier New', monospace; font-size: {scale_px(12)}px;")
        layout.addWidget(paste)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Parse & Fill")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            QMessageBox.information(
                self,
                "Import Incomplete",
                "sess / auth_id were not imported.\n\n"
                "• Paste the DevTools cookie header when ready, or\n"
                "• Use Zen Browser → Import Cookies, or\n"
                "• Fill sess / auth_id / x-bc manually.\n\n"
                "If Chrome currently shows “Profile error” or OnlyFans is logged out after an "
                "earlier sync attempt, sign back into OnlyFans once in normal Chrome — v195+ "
                "no longer touches your live profile.",
            )
            return

        parsed = _parse_cookie_header(paste.toPlainText())
        filled = []
        for key in ("sess", "auth_id", "auth_uid", "x-bc"):
            val = parsed.get(key) or parsed.get(key.replace("-", "_"))
            if not val:
                # auth_uid may be named auth_uid_XXXX
                if key == "auth_uid":
                    for pk, pv in parsed.items():
                        if pk.startswith("auth_uid") and pv:
                            self._inputs["auth_uid"].setText(pv)
                            filled.append("auth_uid")
                            break
                continue
            if key in self._inputs and val:
                self._inputs[key].setText(val)
                filled.append(key)

        if not filled:
            QMessageBox.warning(
                self,
                "Nothing Parsed",
                "Could not find sess / auth_id in that paste.\n"
                "Copy the full cookie header value from an onlyfans.com request.",
            )
            return

        app_signals.status_message.emit(f"Parsed from cookie header: {', '.join(filled)}")
        QMessageBox.information(
            self,
            "Cookies Applied",
            f"Filled: {', '.join(filled)}\n\n"
            "Click Save, then Test Credentials.",
        )

    def _sync_existing_chromium_profile_via_cdp(
        self, browser_name: str, seed_creds: dict | None = None
    ):
        """Deprecated: Chrome profile relaunch/junction sync is disabled (corrupts live profiles).

        Kept as a stub so older patched call sites fail safe.
        """
        log.warning(
            "Refusing Chromium CDP profile sync — Windows Chrome auto-import is unsupported."
        )
        self._warn_windows_chromium_import_unsupported(_combo_browser_display(self.browser_combo))

    def _open_system_browser_login(self):
        """Open selected system browser in a secure debugging sandbox and auto-capture credentials."""
        browser_name, _ignored_method = _combo_browser_selection(self.browser_combo)
        browser_display = _combo_browser_display(self.browser_combo)
        linux_install = None
        browser_path = None
        install_method = None

        if platform.system() == "Linux" and browser_name:
            # Prefer the install of a currently running instance; else freshest disk install
            linux_install, src = _resolve_linux_install_for_import(browser_name)
            if linux_install:
                install_method = linux_install.method
                browser_path = linux_install.executable
                browser_display = (
                    f"{_linux_display_name(browser_name)} "
                    f"({_linux_method_label(linux_install.method)})"
                )
                log.info(
                    f"System browser login: using {browser_display} "
                    f"(source={src}, exe={browser_path})"
                )

        if not browser_path:
            # Legacy Flatpak label fallback / non-Linux
            display_key = browser_display.lower().replace(" ", "")
            if display_key in {"firefoxflatpak", "firefox(flatpak)"} or install_method == "flatpak":
                browser_name = browser_name or "firefox"
                browser_display = f"{_linux_display_name(browser_name)} (Flatpak)"
                app_ids = _LINUX_FLATPAK_IDS.get(browser_name, ["org.mozilla.firefox"])
                browser_path = ["flatpak", "run", app_ids[0]]
            else:
                browser_path = _find_browser_executable(browser_name)

        if not browser_path:
            QMessageBox.critical(
                self,
                "Browser Not Found",
                f"Could not locate {browser_display} executable "
                f"(apt / Snap / Flatpak / deb) on your system.\n\n"
                f"Please make sure {browser_display} is installed, then re-open this dialog."
            )
            return

        import random
        port = random.randint(9300, 9399)

        import tempfile
        base_dir = tempfile.gettempdir()
        if platform.system() == "Linux" and isinstance(browser_path, list) and "flatpak" in browser_path:
            try:
                app_id = browser_path[-1]
                flatpak_cache = os.path.expanduser(f"~/.var/app/{app_id}/cache")
                if os.path.isdir(flatpak_cache):
                    base_dir = flatpak_cache
            except Exception as e:
                log.error(f"Flatpak path detection failed: {e}")

        profile_dir = os.path.join(base_dir, f"ofscraper_{browser_name}_profile_{port}")
        os.makedirs(profile_dir, exist_ok=True)

        is_firefox_based = browser_name in {"firefox", "zenbrowser"}

        if is_firefox_based:
            prefs_path = os.path.join(profile_dir, "prefs.js")
            try:
                with open(prefs_path, "w", encoding="utf-8") as f:
                    f.write('user_pref("remote.active-protocols", 2);\n')
                    f.write('user_pref("remote.enabled", true);\n')
                    f.write('user_pref("devtools.chrome.enabled", true);\n')
                    f.write('user_pref("devtools.debugger.remote-enabled", true);\n')
                    f.write('user_pref("devtools.debugger.prompt-connection", false);\n')
                    f.write('user_pref("browser.shell.checkDefaultBrowser", false);\n')
                    f.write('user_pref("browser.startup.firstrunRedirection.enabled", false);\n')
                    f.write('user_pref("browser.aboutwelcome.enabled", false);\n')
                    f.write('user_pref("browser.startup.homepage_override.mstone", "ignore");\n')
                    f.write('user_pref("startup.homepage_welcome_url", "");\n')
                    f.write('user_pref("startup.homepage_welcome_url.additional", "");\n')
                    f.write('user_pref("browser.messaging-system.whatsNewPanel.enabled", false);\n')
                    f.write('user_pref("zen.welcome-screen.seen", true);\n')
                    f.write('user_pref("zen.welcomeScreen.seen", true);\n')
            except Exception as e:
                log.error(f"Failed to write Firefox prefs: {e}")

        # Build execution command
        if is_firefox_based:
            if isinstance(browser_path, list):
                cmd = browser_path + [
                    "-profile", profile_dir,
                    "--remote-debugging-port", str(port),
                    "-no-remote",
                    "-url", "https://onlyfans.com"
                ]
            else:
                cmd = [
                    browser_path,
                    "-profile", profile_dir,
                    "--remote-debugging-port", str(port),
                    "-no-remote",
                    "-url", "https://onlyfans.com"
                ]
        else:
            if isinstance(browser_path, list):
                cmd = browser_path + [
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "https://onlyfans.com"
                ]
            else:
                cmd = [
                    browser_path,
                    f"--remote-debugging-port={port}",
                    f"--user-data-dir={profile_dir}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "https://onlyfans.com"
                ]

        kwargs = {}
        if platform.system() != "Windows":
            kwargs["preexec_fn"] = os.setsid

        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Launch Failed",
                f"Failed to start {browser_display}:\n{e}"
            )
            return

        # Start the sync dialog
        dlg = ChromeLoginMonitorDialog(
            port,
            proc,
            profile_dir,
            self,
            browser_display=browser_display,
            browser_name=browser_name,
            browser_path=browser_path if isinstance(browser_path, str) else None,
            cleanup_profile_dir=True,
        )
        dlg.setWindowTitle(f"{browser_display} Login Sync")
        dlg.credentials_ready.connect(self._apply_browser_credentials)
        self._set_browser_login_busy(
            True,
            f"{browser_display} login in progress — use Cancel Login to abort",
        )
        try:
            dlg.exec()
        finally:
            self._set_browser_login_busy(False)


# Match OnlyFans bcTokenSha in Chromium LevelDB (40–128 hex; never random nearby hashes).
_BCTOKEN_RE = re.compile(rb"bcTokenSha[\x00-\xff]{0,64}?([a-fA-F0-9]{40,128})", re.IGNORECASE)
_BCTOKEN_HEX_RE = re.compile(r"^[a-fA-F0-9]{40,128}$")


def _decode_firefox_ls_value(val) -> str:
    """Decode a Firefox localStorage value (UTF-8 / UTF-16, strip NULs/quotes)."""
    if val is None:
        return ""
    if isinstance(val, memoryview):
        val = val.tobytes()
    if isinstance(val, bytes):
        text = ""
        for enc in ("utf-8", "utf-16-le", "utf-16"):
            try:
                text = val.decode(enc)
                break
            except Exception:
                continue
        if not text:
            text = val.decode("utf-8", errors="ignore")
    else:
        text = str(val)
    text = text.replace("\x00", "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1].strip()
    return text


def _normalize_bctoken_value(raw: str) -> str | None:
    """Return a clean bcTokenSha hex string, or None if invalid."""
    text = _decode_firefox_ls_value(raw) if not isinstance(raw, str) else raw
    text = (text or "").replace("\x00", "").strip().strip("\"'")
    # Sometimes stored as JSON string
    if text.startswith("{") and "bcTokenSha" in text:
        m = re.search(r"bcTokenSha[\"']?\s*[:=]\s*[\"']([a-fA-F0-9]{40,128})[\"']", text)
        if m:
            text = m.group(1)
    if _BCTOKEN_HEX_RE.match(text):
        return text
    # Embedded hex in noisy blob
    m = re.search(r"([a-fA-F0-9]{40,128})", text)
    if m and _BCTOKEN_HEX_RE.match(m.group(1)):
        return m.group(1)
    return None


def _normalize_firefox_ua_reduction(ua: str) -> str:
    """Collapse Firefox/X.Y.Z and rv:X.Y.Z to the reduced MAJOR.0 form DevTools shows."""
    if not _ua_looks_like_firefox(ua):
        return ua
    ua = re.sub(r"Firefox/(\d+)(?:\.\d+)+", r"Firefox/\1.0", ua)
    ua = re.sub(r"rv:(\d+)(?:\.\d+)+", r"rv:\1.0", ua)
    return _fix_user_agent_casing(ua)


def _firefox_storage_freshness(path: str) -> float:
    """Newest mtime among data.sqlite and its WAL (Firefox keeps fresh LS in the WAL)."""
    best = 0.0
    for candidate in (path, path + "-wal", path + "-shm"):
        try:
            if os.path.exists(candidate):
                best = max(best, os.path.getmtime(candidate))
        except Exception:
            pass
    return best


def _extract_firefox_bctoken(profile_dir: str) -> str | None:
    """Extract the newest OnlyFans bcTokenSha from a Firefox/Zen profile.

    Searches storage/**/data.sqlite (prefer onlyfans origins), merges WAL copies,
    validates hex tokens, and falls back to a raw bcTokenSha binary scan.
    """
    import glob
    import sqlite3
    import tempfile
    import shutil

    if not profile_dir or not os.path.isdir(profile_dir):
        return None

    data_candidates = glob.glob(
        os.path.join(profile_dir, "storage", "**", "data.sqlite"),
        recursive=True,
    )
    if not data_candidates:
        return None

    def _origin_rank(path: str) -> tuple:
        low = path.lower().replace("\\", "/")
        # Prefer real OnlyFans https origin; deprioritize non-OF storage
        if "https+++onlyfans.com" in low or "https%3a%2f%2fonlyfans.com" in low:
            of = 0
        elif "onlyfans" in low:
            of = 1
        else:
            of = 2
        # fresher first
        return (of, -_firefox_storage_freshness(path))

    data_candidates.sort(key=_origin_rank)

    best: tuple[float, str] | None = None

    for data_path in data_candidates:
        if not os.path.isfile(data_path):
            continue
        freshness = _firefox_storage_freshness(data_path)
        temp_dir = tempfile.mkdtemp()
        temp_db = os.path.join(temp_dir, "data.sqlite")
        try:
            shutil.copy2(data_path, temp_db)
            for ext in ("-wal", "-shm"):
                src = data_path + ext
                if os.path.exists(src):
                    shutil.copy2(src, temp_db + ext)

            tokens: list[str] = []
            wal_tokens: list[str] = []
            try:
                conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
                try:
                    cur = conn.cursor()
                    # Exact key first, then fuzzy (some builds store odd key blobs)
                    for sql in (
                        "SELECT value FROM data WHERE key = 'bcTokenSha'",
                        "SELECT value FROM data WHERE lower(key) = 'bctokensha'",
                        "SELECT value FROM data WHERE key LIKE '%bcTokenSha%'",
                    ):
                        try:
                            cur.execute(sql)
                        except Exception:
                            continue
                        for (val,) in cur.fetchall():
                            token = _normalize_bctoken_value(
                                _decode_firefox_ls_value(val)
                            )
                            if token:
                                tokens.append(token)
                        if tokens:
                            break
                finally:
                    conn.close()
            except Exception as e:
                log.debug(f"Firefox data.sqlite query failed for {data_path}: {e}")

            # Raw scan: WAL bytes are the freshest localStorage writes while Firefox is open
            try:
                wal = temp_db + "-wal"
                if os.path.exists(wal):
                    with open(wal, "rb") as fp:
                        wal_blob = fp.read()
                    for match in _BCTOKEN_RE.findall(wal_blob):
                        token = match.decode("ascii", errors="ignore")
                        if _BCTOKEN_HEX_RE.match(token):
                            wal_tokens.append(token)
                with open(temp_db, "rb") as fp:
                    blob = fp.read()
                for match in _BCTOKEN_RE.findall(blob):
                    token = match.decode("ascii", errors="ignore")
                    if _BCTOKEN_HEX_RE.match(token):
                        tokens.append(token)
            except Exception:
                pass

            # Prefer WAL-sourced tokens (live session) over older main-DB values
            ordered = (wal_tokens + tokens) if wal_tokens else tokens
            for token in ordered:
                # WAL hits get a freshness boost so they beat stale main-DB tokens
                tok_fresh = freshness + (1.0 if token in wal_tokens else 0.0)
                if best is None or tok_fresh >= best[0]:
                    best = (tok_fresh, token)
            if ordered:
                log.debug(
                    f"Candidate bcTokenSha from {data_path} "
                    f"(freshness={freshness:.0f}, wal={len(wal_tokens)}, "
                    f"prefix={ordered[-1][:12]}, n={len(ordered)})"
                )
        except Exception as e:
            log.debug(f"Firefox bcToken extract failed for {data_path}: {e}")
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    if best:
        log.info(
            f"Extracted Firefox bcTokenSha x-bc (len={len(best[1])}, prefix={best[1][:12]})"
        )
        return best[1]
    return None


def _extract_bctoken_from_leveldb_dir(ldb_dir: str) -> str | None:
    """Return the newest bcTokenSha found in a Chromium Local Storage leveldb dir."""
    if not ldb_dir or not os.path.isdir(ldb_dir):
        return None
    best = None  # (mtime, token)
    try:
        names = os.listdir(ldb_dir)
    except Exception:
        return None
    for name in names:
        if not (name.endswith(".log") or name.endswith(".ldb")):
            continue
        path = os.path.join(ldb_dir, name)
        try:
            try:
                with open(path, "rb") as fp:
                    content = fp.read()
            except Exception:
                # Windows: leveldb files can be locked; shared read via PowerShell helper path
                content = b""
                if platform.system() == "Windows":
                    content = _read_file_bytes_shared(path)
            if not content:
                continue
            matches = _BCTOKEN_RE.findall(content)
            if not matches:
                continue
            # Prefer the last match in the file (most recently written value)
            token = matches[-1].decode("ascii")
            mtime = os.path.getmtime(path) if os.path.exists(path) else 0
            if best is None or mtime >= best[0]:
                best = (mtime, token)
        except Exception:
            continue
    return best[1] if best else None


def _read_file_bytes_shared(path: str) -> bytes:
    """Best-effort shared read of a possibly locked file (Windows)."""
    try:
        with open(path, "rb") as fp:
            return fp.read()
    except Exception:
        pass
    if platform.system() != "Windows":
        return b""
    try:
        import base64 as _b64

        p_c = path.replace("\\", "/")
        ps_code = f'''
        try {{
            $s = [IO.File]::Open("{p_c}", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
            $ms = New-Object IO.MemoryStream
            $s.CopyTo($ms)
            $s.Close()
            [Console]::OpenStandardOutput().Write($ms.ToArray(), 0, $ms.Length)
        }} catch {{
        }}
        '''
        b64_ps = _b64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64_ps],
            timeout=5,
        )
    except Exception:
        return b""


def _chromium_process_image_names(browser_name: str) -> list[str]:
    name = browser_name.lower().replace(" ", "")
    if name in {"chrome", "googlechrome", "chromium"}:
        return ["chrome.exe", "chromium.exe"]
    if name in {"edge", "msedge"}:
        return ["msedge.exe"]
    if name in {"brave"}:
        return ["brave.exe"]
    if name in {"opera", "operagx"}:
        return ["opera.exe"]
    if name in {"vivaldi"}:
        return ["vivaldi.exe"]
    return ["chrome.exe"]


def _parse_cookie_header(raw: str) -> dict:
    """Parse a DevTools Cookie header into allowlisted name→value map only."""
    text = (raw or "").strip()
    if not text:
        return {}
    # Allow pasting the whole headers block; keep the cookie line if present.
    lower = text.lower()
    if "cookie:" in lower:
        for line in text.splitlines():
            if line.strip().lower().startswith("cookie:"):
                text = line.split(":", 1)[1].strip()
                break
    out = {}
    for part in text.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        lname = name.lower()
        if lname == "sess":
            out["sess"] = value
        elif lname == "auth_id":
            out["auth_id"] = value
        elif lname.startswith("auth_uid"):
            out["auth_uid"] = value
        elif lname in {"x-bc", "x_bc", "bctokensha"}:
            out["x-bc"] = value
        # Drop all other cookie names (csrf, tracking, etc.)
    return cookie_allowlist.filter_cookie_map(out, keep_meta=False, keep_headers=True)


def _repair_chromium_profile_flags(browser_name: str) -> None:
    """Clear singleton locks + crash exit flags without launching Chrome or touching cookies.

    Safe recovery aid after earlier CDP/junction sync attempts left Profile error bubbles.
    Does nothing if Chrome is currently running (avoid writing Preferences while locked).
    """
    if platform.system() != "Windows":
        return
    image_names = _chromium_process_image_names(browser_name)
    for image in image_names:
        try:
            listed = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
                errors="replace",
            )
            out = (listed.stdout or "").lower()
            if image.lower() in out and "no tasks" not in out:
                log.debug("Chrome still running — skip Preferences repair")
                return
        except Exception:
            return

    user_data_dir, profile_directory = _get_chromium_user_data_and_profile(browser_name)
    if not user_data_dir:
        return
    _clear_chromium_singleton_locks(user_data_dir)
    _mark_chromium_exit_clean(os.path.join(user_data_dir, profile_directory))
    # Remove any leftover temp CDP junctions under %TEMP% (junction only, never target).
    try:
        import tempfile
        temp_root = tempfile.gettempdir()
        for name in os.listdir(temp_root):
            if not name.startswith("ofscraper_") or "_cdp_" not in name:
                continue
            _safe_remove_cdp_user_data(os.path.join(temp_root, name))
    except Exception as e:
        log.debug(f"Temp CDP cleanup skipped: {e}")


def _terminate_chromium_processes(image_names: list[str]) -> None:
    """Terminate browser processes by image name (Windows) or pkill (elsewhere)."""
    import time

    if platform.system() == "Windows":
        # Soft close first so Chrome flushes Cookies / avoids "didn't shut down correctly".
        for image in image_names:
            try:
                subprocess.run(
                    ["taskkill", "/IM", image],
                    capture_output=True,
                    timeout=15,
                )
            except Exception as e:
                log.debug(f"soft taskkill {image} failed: {e}")
        time.sleep(1.5)

        for _ in range(25):
            still_running = False
            for image in image_names:
                try:
                    listed = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        errors="replace",
                    )
                    out = (listed.stdout or "").lower()
                    if image.lower() in out and "no tasks" not in out:
                        still_running = True
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/IM", image],
                            capture_output=True,
                            timeout=15,
                        )
                except Exception as e:
                    log.debug(f"taskkill {image} failed: {e}")
            if not still_running:
                break
            time.sleep(0.2)
        return
    # Best-effort on Linux/macOS for profile sync callers
    for image in image_names:
        base = image.replace(".exe", "")
        try:
            subprocess.run(["pkill", "-f", base], capture_output=True, timeout=10)
        except Exception:
            pass


def _clear_chromium_singleton_locks(user_data_dir: str) -> None:
    """Remove Chromium singleton lock files so a new process can start cleanly."""
    if not user_data_dir:
        return
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"):
        path = os.path.join(user_data_dir, name)
        try:
            if os.path.exists(path) or os.path.islink(path):
                os.remove(path)
        except Exception as e:
            log.debug(f"Could not remove {path}: {e}")


def _wait_for_cdp_port(port: int, timeout_s: float = 30.0) -> bool:
    """Return True once Chromium answers on the remote-debugging HTTP endpoint."""
    import time
    import urllib.request

    deadline = time.time() + timeout_s
    url = f"http://127.0.0.1:{port}/json/version"
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1).read()
            return True
        except Exception:
            time.sleep(0.25)
    return False


def _fetch_cdp_user_agent(port: int, *, allow_firefox_json_version: bool = False) -> str:
    """Read User-Agent from a browser remote-debugging endpoint.

    WARNING: Firefox's /json/version User-Agent is often a stale frozen string
    (rv:109 / Firefox/115) and must NOT be trusted for OnlyFans auth. Prefer
    Network request headers or Runtime.evaluate(navigator.userAgent) instead.
    """
    import urllib.request

    try:
        raw = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version", timeout=2
        ).read()
        data = json.loads(raw)
        for key in ("User-Agent", "userAgent", "user_agent"):
            ua = data.get(key)
            if not (isinstance(ua, str) and ua.strip()):
                continue
            ua = _fix_user_agent_casing(ua.strip())
            if _ua_looks_like_firefox(ua):
                if not allow_firefox_json_version or _is_stale_firefox_remote_ua(ua):
                    log.debug(
                        f"Ignoring untrusted Firefox /json/version UA: {ua}"
                    )
                    continue
            return ua
        browser = data.get("Browser") or data.get("browser") or ""
        if isinstance(browser, str) and "Firefox/" in browser and allow_firefox_json_version:
            m = re.search(r"Firefox/(\d+(?:\.\d+)*)", browser)
            if m and not _is_stale_firefox_remote_ua(
                _build_firefox_ua_from_version(m.group(1))
            ):
                return _build_firefox_ua_from_version(m.group(1))
    except Exception as e:
        log.debug(f"CDP /json/version UA fetch failed on port {port}: {e}")
    return ""


def _relaunch_chromium_normal(browser_path) -> None:
    """Reopen the browser without remote-debugging flags (user's normal session)."""
    try:
        cmd = list(browser_path) if isinstance(browser_path, list) else [browser_path]
        subprocess.Popen(cmd)
    except Exception as e:
        log.debug(f"Normal browser relaunch failed: {e}")


def _is_windows_reparse_point(path: str) -> bool:
    if platform.system() != "Windows" or not path:
        return False
    try:
        import ctypes

        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs == -1:
            return False
        return bool(attrs & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT
    except Exception:
        return False


def _mark_chromium_exit_clean(profile_dir: str) -> None:
    """Set profile.exit_type=Normal so Chrome skips the crash-restore bubble."""
    prefs_path = os.path.join(profile_dir, "Preferences")
    if not os.path.isfile(prefs_path):
        return
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        profile = prefs.setdefault("profile", {})
        profile["exit_type"] = "Normal"
        profile["exited_cleanly"] = True
        with open(prefs_path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, separators=(",", ":"))
    except Exception as e:
        log.debug(f"Could not mark Chromium exit clean: {e}")


def _safe_remove_cdp_user_data(path: str) -> None:
    """Remove a temp CDP user-data-dir without deleting junction targets (real profiles)."""
    import shutil

    if not path or not os.path.exists(path):
        return
    real_markers = (
        os.path.join("Google", "Chrome", "User Data"),
        os.path.join("Microsoft", "Edge", "User Data"),
        os.path.join("BraveSoftware", "Brave-Browser", "User Data"),
        os.path.join("Chromium", "User Data"),
    )
    norm = os.path.normpath(path)
    if any(os.path.normpath(m) in norm for m in real_markers):
        log.warning(f"Refusing to delete real browser profile path: {norm}")
        return

    try:
        for name in os.listdir(path):
            full = os.path.join(path, name)
            try:
                if _is_windows_reparse_point(full) or os.path.islink(full):
                    # Junction/symlink only — never follow into the real profile.
                    if os.path.isdir(full) and not os.path.islink(full):
                        os.rmdir(full)
                    else:
                        os.unlink(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full, ignore_errors=True)
                else:
                    os.remove(full)
            except Exception as e:
                log.debug(f"Cleanup entry failed {full}: {e}")
        try:
            os.rmdir(path)
        except Exception:
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        log.debug(f"CDP user-data cleanup failed: {e}")


def _clone_chromium_profile_for_cdp(
    src_user_data: str, profile_directory: str, dest_user_data: str
) -> None:
    """Disabled: junctioning/copying the live profile for CDP corrupted Chrome installs.

    Chrome 136+ requires a non-default ``--user-data-dir`` for DevTools, but attaching that
    to the real profile (junction) or writing Preferences through it caused Profile errors
    and OnlyFans session loss. Callers must use cookie-header paste or Zen Browser instead.
    """
    raise RuntimeError(
        "Chromium CDP profile clone/junction is disabled to protect the live browser profile"
    )


def _windows_unlock_chromium_cookie_db(browser_name: str) -> bool:
    """Briefly restart Chromium Network/Storage utility processes so Cookies can be copied.

    Chrome 114+ on Windows takes an exclusive SQLite lock on the Cookies DB. Killing only
    the utility subprocesses (not the whole browser UI) often releases the lock long enough
    to snapshot the file; Chrome respawns the utilities automatically.
    Returns True if CreateFileW can open the Default Network Cookies path afterward.
    """
    if platform.system() != "Windows":
        return False
    import time
    import ctypes

    image_names = _chromium_process_image_names(browser_name)
    # Find NetworkService + StorageService utility PIDs for matching chrome.exe images
    try:
        ps = (
            "Get-CimInstance Win32_Process | Where-Object { "
            + " -or ".join([f"$_.Name -eq '{n}'" for n in image_names])
            + " } | Where-Object { $_.CommandLine -match "
            "'network\\.mojom\\.NetworkService|storage\\.mojom\\.StorageService' } "
            "| Select-Object -ExpandProperty ProcessId"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            text=True,
            timeout=15,
            errors="replace",
        )
        pids = [int(x) for x in out.split() if x.strip().isdigit()]
    except Exception as e:
        log.debug(f"utility pid lookup failed: {e}")
        pids = []

    for pid in pids:
        try:
            h = ctypes.windll.kernel32.OpenProcess(0x0001, False, pid)  # TERMINATE
            if h:
                ctypes.windll.kernel32.TerminateProcess(h, 1)
                ctypes.windll.kernel32.CloseHandle(h)
                log.debug(f"Terminated Chromium utility pid {pid} to unlock Cookies DB")
        except Exception as e:
            log.debug(f"Failed terminating pid {pid}: {e}")

    if not pids:
        return False

    # Probe Default cookies path under known user-data roots
    appdata = os.environ.get("LOCALAPPDATA", "")
    probe_paths = []
    for base in _chromium_user_data_dirs(browser_name):
        probe_paths.append(os.path.join(base, "Default", "Network", "Cookies"))
        probe_paths.append(os.path.join(base, "Default", "Cookies"))

    GENERIC_READ = 0x80000000
    SHARE = 0x00000001 | 0x00000002 | 0x00000004
    for _ in range(30):
        for src in probe_paths:
            if not os.path.exists(src):
                continue
            h = ctypes.windll.kernel32.CreateFileW(
                src, GENERIC_READ, SHARE, None, 3, 0x80, None
            )
            if h not in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
                ctypes.windll.kernel32.CloseHandle(h)
                return True
        time.sleep(0.05)
    return False


def _chromium_user_data_dirs(
    browser_name: str, *, install_method: str | None = None
) -> list[str]:
    system_os = platform.system()
    home = os.path.expanduser("~")
    browser_clean = browser_name.lower().replace(" ", "")
    if system_os == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", "")
        appdata_roaming = os.environ.get("APPDATA", "")
        if browser_clean in {"chrome", "googlechrome"}:
            return [os.path.join(appdata, "Google", "Chrome", "User Data")]
        if browser_clean in {"chromium"}:
            return [os.path.join(appdata, "Chromium", "User Data")]
        if browser_clean in {"edge", "msedge"}:
            return [os.path.join(appdata, "Microsoft", "Edge", "User Data")]
        if browser_clean in {"brave"}:
            return [os.path.join(appdata, "BraveSoftware", "Brave-Browser", "User Data")]
        if browser_clean in {"opera", "operagx"}:
            return [os.path.join(appdata_roaming, "Opera Software", "Opera Stable")]
        if browser_clean in {"vivaldi"}:
            return [os.path.join(appdata, "Vivaldi", "User Data")]
        return []

    # Linux: when install method is known, only search that install's profile roots
    method = (install_method or "").lower() or None
    if method:
        roots = _linux_chromium_roots_for_method(browser_clean, method)
        if roots:
            return roots
        # Snap/flatpak with no mapped roots — fall through to broad search

    # Linux / other — broad search across apt + Flatpak (+ Snap when mapped)
    if browser_clean in {"chrome", "googlechrome"}:
        return [
            os.path.join(home, ".config/google-chrome"),
            os.path.join(home, ".var/app/com.google.Chrome/config/google-chrome"),
            os.path.join(home, ".config/chromium"),
        ]
    if browser_clean in {"brave"}:
        return [
            os.path.join(home, ".config/BraveSoftware/Brave-Browser"),
            os.path.join(home, ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"),
        ] + _linux_snap_chromium_user_data_dirs("brave")
    if browser_clean in {"chromium"}:
        return [
            os.path.join(home, ".config/chromium"),
            os.path.join(home, ".var/app/org.chromium.Chromium/config/chromium"),
        ] + _linux_snap_chromium_user_data_dirs("chromium")
    if browser_clean in {"edge"}:
        return [
            os.path.join(home, ".config/microsoft-edge-stable"),
            os.path.join(home, ".config/microsoft-edge"),
            os.path.join(home, ".var/app/com.microsoft.Edge/config/microsoft-edge"),
        ]
    if browser_clean in {"opera"}:
        return [
            os.path.join(home, ".config/opera"),
            os.path.join(home, ".var/app/com.opera.Opera/config/opera"),
        ]
    if browser_clean in {"vivaldi"}:
        return [
            os.path.join(home, ".config/vivaldi"),
            os.path.join(home, ".var/app/com.vivaldi.Vivaldi/config/vivaldi"),
        ]
    return []


def _get_chromium_user_data_and_profile(
    browser_name: str, *, install_method: str | None = None
) -> tuple[str | None, str]:
    """Return (user_data_dir, profile_directory) for CDP relaunch."""
    import json as _json

    for base in _chromium_user_data_dirs(browser_name, install_method=install_method):
        if not os.path.isdir(base):
            continue
        profile = "Default"
        info = {}
        local_state = os.path.join(base, "Local State")
        try:
            with open(local_state, "r", encoding="utf-8") as f:
                js = _json.load(f)
            last = js.get("profile", {}).get("last_used")
            if last and os.path.isdir(os.path.join(base, last)):
                profile = last
            info = js.get("profile", {}).get("info_cache", {}) or {}
        except Exception:
            pass
        candidates = [profile]
        for name in ("Default", "Profile 1", "Profile 2", "Profile 3"):
            if name not in candidates:
                candidates.append(name)
        if isinstance(info, dict):
            for name in info.keys():
                if name not in candidates:
                    candidates.append(name)
        for cand in candidates:
            ldb = os.path.join(base, cand, "Local Storage", "leveldb")
            if _extract_bctoken_from_leveldb_dir(ldb):
                return base, cand
        return base, profile
    return None, "Default"


def _extract_chrome_family_cookies(
    browser_name: str,
    *,
    install_method: str | None = None,
    extra_user_data_dirs: list[str] | None = None,
    should_cancel=None,
) -> dict:
    """Extracts OnlyFans cookies from Chrome, Chromium, Brave, Edge, Opera, Vivaldi on Linux and Windows.
    Handles DPAPI (Windows), SecretService & KWallet DBus (Linux), and temp-file copying so it works
    whether the browser is open or closed.

    On Linux, ``install_method`` (apt/flatpak/snap/deb/native) scopes profile roots so
    Flatpak Chrome is not mixed with apt Chromium cookies.
    ``extra_user_data_dirs`` forces additional roots (e.g. Snap paths discovered from /proc fds).
    """
    import os
    import glob
    import sqlite3
    import tempfile
    import shutil
    import base64
    import json
    import platform
    import re

    system_os = platform.system()
    home = os.path.expanduser("~")

    def _cancelled() -> bool:
        try:
            return bool(should_cancel and should_cancel())
        except Exception:
            return False

    if _cancelled():
        return {}

    extracted_cookies = {}
    base_dirs = []
    browser_clean = browser_name.lower().replace(" ", "")

    if system_os == "Windows":
        appdata = os.environ.get("LOCALAPPDATA", "")
        appdata_roaming = os.environ.get("APPDATA", "")
        if browser_clean in {"chrome", "googlechrome"}:
            base_dirs = [os.path.join(appdata, "Google", "Chrome", "User Data")]
        elif browser_clean in {"chromium"}:
            base_dirs = [os.path.join(appdata, "Chromium", "User Data")]
        elif browser_clean in {"edge", "msedge"}:
            base_dirs = [os.path.join(appdata, "Microsoft", "Edge", "User Data")]
        elif browser_clean in {"brave"}:
            base_dirs = [os.path.join(appdata, "BraveSoftware", "Brave-Browser", "User Data")]
        elif browser_clean in {"opera", "operagx"}:
            base_dirs = [os.path.join(appdata_roaming, "Opera Software", "Opera Stable")]
        elif browser_clean in {"vivaldi"}:
            base_dirs = [os.path.join(appdata, "Vivaldi", "User Data")]
        else:
            base_dirs = []
    else:
        # Scoped by install method when known; otherwise broad multi-install search
        base_dirs = _chromium_user_data_dirs(
            browser_name, install_method=install_method
        )
        if not base_dirs:
            if browser_clean in {"chrome", "googlechrome"}:
                base_dirs = [
                    os.path.join(home, ".config/google-chrome"),
                    os.path.join(home, ".var/app/com.google.Chrome/config/google-chrome"),
                    os.path.join(home, ".config/chromium"),
                    os.path.join(home, ".var/app/org.chromium.Chromium/config/chromium"),
                ]
            elif browser_clean in {"chromium"}:
                base_dirs = [
                    os.path.join(home, ".config/chromium"),
                    os.path.join(home, ".var/app/org.chromium.Chromium/config/chromium"),
                    os.path.join(home, ".config/google-chrome"),
                    os.path.join(home, ".var/app/com.google.Chrome/config/google-chrome"),
                ]
            elif browser_clean in {"brave"}:
                base_dirs = [
                    os.path.join(home, ".config/BraveSoftware/Brave-Browser"),
                    os.path.join(home, ".var/app/com.brave.Browser/config/BraveSoftware/Brave-Browser"),
                ] + _linux_snap_chromium_user_data_dirs("brave")
            elif browser_clean in {"edge"}:
                base_dirs = [
                    os.path.join(home, ".config/microsoft-edge-stable"),
                    os.path.join(home, ".config/microsoft-edge"),
                ]
            elif browser_clean in {"opera"}:
                base_dirs = [os.path.join(home, ".config/opera")]
            elif browser_clean in {"vivaldi"}:
                base_dirs = [os.path.join(home, ".config/vivaldi")]

    # Prefer shared helper for user-data roots (keeps Windows/Linux paths consistent)
    base_dirs = (
        _chromium_user_data_dirs(browser_name, install_method=install_method) or base_dirs
    )
    # Snap/fd-discovered roots from the running process
    if extra_user_data_dirs:
        merged: list[str] = []
        seen: set[str] = set()
        for d in list(extra_user_data_dirs) + list(base_dirs):
            if d and d not in seen:
                seen.add(d)
                merged.append(d)
        base_dirs = merged
    # If snap scope still has no existing dirs, expand via snap discovery
    if (
        system_os == "Linux"
        and install_method == "snap"
        and not any(os.path.isdir(d) for d in base_dirs)
    ):
        discovered = _linux_snap_chromium_user_data_dirs(browser_clean)
        if discovered:
            log.info(f"Snap user-data rediscovery for {browser_clean}: {discovered}")
            base_dirs = discovered + list(base_dirs)
    if install_method and system_os == "Linux":
        extracted_cookies["_chromium_install"] = install_method
        log.info(
            f"Chromium import scoped to {install_method}: "
            f"{[d for d in base_dirs if os.path.isdir(d)]}"
        )

    # 1. Search LevelDB for real x-bc token (bcTokenSha only — never random 40-char hex)
    best_xbc = None
    best_mtime = -1.0
    for b in base_dirs:
        if not os.path.exists(b):
            continue
        for root, dirs, files in os.walk(b):
            if not root.endswith(os.path.join("Local Storage", "leveldb")):
                continue
            token = _extract_bctoken_from_leveldb_dir(root)
            if not token:
                continue
            try:
                mtime = max(
                    (
                        os.path.getmtime(os.path.join(root, f))
                        for f in files
                        if f.endswith(".log") or f.endswith(".ldb")
                    ),
                    default=0,
                )
            except Exception:
                mtime = 0
            if mtime >= best_mtime:
                best_mtime = mtime
                best_xbc = token
    if best_xbc:
        extracted_cookies["x-bc"] = best_xbc
        log.info(f"Extracted bcTokenSha x-bc from LevelDB (len={len(best_xbc)}, prefix={best_xbc[:12]})")

    # 2. Search all Cookie databases across profiles recursively
    cookie_paths = []
    local_state_paths = []
    for b in base_dirs:
        if os.path.exists(b):
            local_state_paths.append(os.path.join(b, "Local State"))
            for root, dirs, files in os.walk(b):
                if _cancelled():
                    return extracted_cookies
                for filename in files:
                    if filename == "Cookies":
                        cookie_paths.append(os.path.join(root, filename))

    cookie_paths.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)

    # Windows App-Bound Encryption: if Local State has app_bound_encrypted_key, cookie
    # values are v20 and cannot be decrypted with the DPAPI AES key from a third-party
    # process. Skip disruptive unlock/decrypt and let the caller use CDP profile sync.
    app_bound = False
    if system_os == "Windows":
        for lsp in [os.path.join(b, "Local State") for b in base_dirs if os.path.exists(b)]:
            try:
                with open(lsp, "r", encoding="utf-8") as f:
                    osc = json.load(f).get("os_crypt", {})
                if osc.get("app_bound_encrypted_key"):
                    app_bound = True
                    log.debug(
                        "Chrome App-Bound Encryption key present — skipping disk cookie decrypt"
                    )
                    break
            except Exception:
                pass
    if app_bound:
        return extracted_cookies

    # Windows (non-ABE): briefly unlock Cookies DB held by Network/Storage utilities
    if system_os == "Windows" and cookie_paths:
        try:
            _windows_unlock_chromium_cookie_db(browser_name)
        except Exception as e:
            log.debug(f"Windows cookie unlock helper failed: {e}")

    keys_gcm_win = []
    keys_cbc_linux = []

    def _win_dpapi_unprotect(b_data: bytes) -> bytes:
        if not b_data:
            return b""
        try:
            import win32crypt
            return win32crypt.CryptUnprotectData(b_data, None, None, None, 0)[1]
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes
            class DATA_BLOB(ctypes.Structure):
                _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]
            p_in = ctypes.create_string_buffer(b_data, len(b_data))
            b_in = DATA_BLOB(len(b_data), p_in)
            b_out = DATA_BLOB()
            if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(b_in), None, None, None, None, 0, ctypes.byref(b_out)):
                res = ctypes.string_at(b_out.pbData, b_out.cbData)
                ctypes.windll.kernel32.LocalFree(b_out.pbData)
                return res
        except Exception:
            pass
        try:
            import subprocess
            b64_str = base64.b64encode(b_data).decode("ascii")
            ps_script = f'''
            [Reflection.Assembly]::LoadWithPartialName("System.Security") | Out-Null
            $b = [Convert]::FromBase64String("{b64_str}")
            $u = [Security.Cryptography.ProtectedData]::Unprotect($b, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
            [Console]::Write([Convert]::ToBase64String($u))
            '''
            encoded_ps = base64.b64encode(ps_script.encode("utf-16le")).decode("ascii")
            cmd = ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_ps]
            res = subprocess.check_output(cmd, text=True, timeout=5).strip()
            if res:
                lines = [l.strip() for l in res.splitlines() if l.strip()]
                if lines:
                    return base64.b64decode(lines[-1])
        except Exception as e:
            log.debug(f"PowerShell EncodedCommand DPAPI unprotect failed: {e}")
        return b""

    if system_os == "Windows":
        for lsp in local_state_paths:
            if os.path.exists(lsp):
                try:
                    with open(lsp, "r", encoding="utf-8") as f:
                        js = json.load(f)
                        enc_k = base64.b64decode(js["os_crypt"]["encrypted_key"])[5:]
                        aes_k = _win_dpapi_unprotect(enc_k)
                        if aes_k:
                            keys_gcm_win.append(aes_k)
                            log.debug(f"Successfully decrypted Windows Chrome master key from {lsp}")
                except Exception as e:
                    log.debug(f"Failed to read/decrypt Local State key from {lsp}: {e}")
        log.debug(f"Total Windows GCM master keys loaded: {len(keys_gcm_win)}")
    elif system_os == "Linux":
        candidate_passwords = [b"peanuts", b"chromium", b"chrome", b"brave", b"", b"password"]
        # Pull Safe Storage secrets from libsecret / gnome-keyring / KWallet.
        # Brave stores "Brave Safe Storage"; Chrome/Chromium use their own labels.
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            for col in secretstorage.get_all_collections(bus):
                try:
                    for item in col.get_all_items():
                        try:
                            label = (item.get_label() or "").lower()
                            attrs = {}
                            try:
                                attrs = {str(k).lower(): str(v).lower() for k, v in (item.get_attributes() or {}).items()}
                            except Exception:
                                attrs = {}
                            attr_blob = " ".join(attrs.values())
                            interesting = any(
                                tok in label or tok in attr_blob
                                for tok in (
                                    "chrome",
                                    "chromium",
                                    "brave",
                                    "edge",
                                    "safe storage",
                                    "chromium keys",
                                    "chrome keys",
                                )
                            )
                            if not interesting:
                                continue
                            sec = item.get_secret()
                            if not sec:
                                continue
                            if isinstance(sec, str):
                                sec = sec.encode("utf-8")
                            if sec and sec not in candidate_passwords:
                                candidate_passwords.insert(0, sec)
                                log.info(
                                    f"Loaded keyring secret for cookie decrypt "
                                    f"(label={item.get_label()!r}, len={len(sec)})"
                                )
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception as e:
            log.debug(f"secretstorage Safe Storage lookup failed: {e}")

        # Fallback: secret-tool CLI (often available when secretstorage isn't)
        try:
            import shutil as _shutil

            if _shutil.which("secret-tool"):
                for schema_key, schema_val in (
                    ("application", "brave"),
                    ("application", "chrome"),
                    ("application", "chromium"),
                    ("xdg:schema", "chrome_libsecret_os_crypt_password_v2"),
                    ("xdg:schema", "chrome_libsecret_os_crypt_password_v1"),
                ):
                    try:
                        res = subprocess.run(
                            ["secret-tool", "lookup", schema_key, schema_val],
                            capture_output=True,
                            timeout=3,
                        )
                        if res.returncode == 0 and res.stdout:
                            sec = res.stdout.rstrip(b"\n")
                            if sec and sec not in candidate_passwords:
                                candidate_passwords.insert(0, sec)
                                log.info(
                                    f"Loaded secret-tool secret ({schema_key}={schema_val}, len={len(sec)})"
                                )
                    except Exception:
                        continue
        except Exception as e:
            log.debug(f"secret-tool lookup failed: {e}")

        try:
            from jeepney import DBusAddress, new_method_call
            from jeepney.io.blocking import open_dbus_connection
            conn = open_dbus_connection()
            kwallet = DBusAddress('/modules/kwalletd5', bus_name='org.kde.kwalletd5', interface='org.kde.KWallet')
            msg_name = new_method_call(kwallet, 'networkWallet')
            w_name = conn.send_and_get_reply(msg_name).body[0]
            msg_open = new_method_call(kwallet, 'open', 'sxs', (w_name, 0, 'OF-Scraper'))
            h_val = conn.send_and_get_reply(msg_open).body[0]
            for f_name in ['Chromium Keys', 'Chrome Keys', 'Brave Keys', 'Passwords']:
                msg_has = new_method_call(kwallet, 'hasFolder', 'iss', (h_val, f_name, 'OF-Scraper'))
                if conn.send_and_get_reply(msg_has).body[0]:
                    for e_name in [
                        'Brave Safe Storage',
                        'Chromium Safe Storage',
                        'Chrome Safe Storage',
                        'Brave Keys',
                    ]:
                        msg_p = new_method_call(kwallet, 'readPassword', 'isss', (h_val, f_name, e_name, 'OF-Scraper'))
                        try:
                            pwd_str = conn.send_and_get_reply(msg_p).body[0]
                            if pwd_str:
                                pwd_bytes = pwd_str.encode('utf-8')
                                if pwd_bytes not in candidate_passwords:
                                    candidate_passwords.insert(0, pwd_bytes)
                                    log.info(f"Loaded KWallet secret {e_name!r}")
                        except Exception:
                            pass
            msg_close = new_method_call(kwallet, 'close', 'ibs', (h_val, False, 'OF-Scraper'))
            conn.send_and_get_reply(msg_close)
            conn.close()
        except Exception as e:
            log.debug(f"KWallet Safe Storage lookup failed: {e}")

        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Hash import SHA1
        keys_cbc_linux = [PBKDF2(p, b'saltysalt', 16, 1, hmac_hash_module=SHA1) for p in candidate_passwords]
        log.info(
            f"Linux cookie decrypt: {len(candidate_passwords)} password candidates, "
            f"{len(cookie_paths)} Cookies DB(s)"
        )

    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad

    def copy_file_safe(src: str, dst: str) -> bool:
        if not os.path.exists(src):
            return False
        try:
            shutil.copy2(src, dst)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                return True
        except Exception:
            pass

        # Linux: browser often holds a write lock; a plain open/read still works
        try:
            with open(src, "rb") as fp:
                data = fp.read()
            if data:
                with open(dst, "wb") as out:
                    out.write(data)
                if os.path.exists(dst) and os.path.getsize(dst) > 0:
                    return True
        except Exception as e:
            log.debug(f"Linux byte-copy failed for {src}: {e}")

        if system_os == "Windows":
            # Tier 1: PowerShell .NET FileStream with FileShare.ReadWrite (bypasses active Chrome locks)
            try:
                import subprocess
                src_c = src.replace("\\", "/")
                dst_c = dst.replace("\\", "/")
                ps_code = f'''
                try {{
                    $s = [IO.File]::Open("{src_c}", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                    $d = [IO.File]::Open("{dst_c}", [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
                    $s.CopyTo($d)
                    $s.Close()
                    $d.Close()
                }} catch {{
                    [IO.File]::Copy("{src_c}", "{dst_c}", $true)
                }}
                '''
                b64_ps = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
                subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64_ps],
                    capture_output=True,
                    timeout=5,
                )
                if os.path.exists(dst) and os.path.getsize(dst) > 0:
                    return True
            except Exception as e:
                log.debug(f"PowerShell FileShare.ReadWrite copy failed for {src}: {e}")

            # Tier 2: Windows CTypes raw CreateFileW with FILE_SHARE_READ | FILE_SHARE_WRITE
            try:
                import ctypes
                GENERIC_READ = 0x80000000
                FILE_SHARE_READ = 0x00000001
                FILE_SHARE_WRITE = 0x00000002
                FILE_SHARE_DELETE = 0x00000004
                OPEN_EXISTING = 3
                FILE_ATTRIBUTE_NORMAL = 0x80

                for share in [FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, FILE_SHARE_READ | FILE_SHARE_WRITE]:
                    h = ctypes.windll.kernel32.CreateFileW(
                        ctypes.c_wchar_p(src),
                        ctypes.c_uint32(GENERIC_READ),
                        ctypes.c_uint32(share),
                        None,
                        ctypes.c_uint32(OPEN_EXISTING),
                        ctypes.c_uint32(FILE_ATTRIBUTE_NORMAL),
                        None,
                    )
                    if h and h != -1 and h != 0xFFFFFFFFFFFFFFFF and h != 0xFFFFFFFF:
                        CHUNK = 64 * 1024
                        buf = ctypes.create_string_buffer(CHUNK)
                        br = ctypes.c_uint32(0)
                        with open(dst, "wb") as out_f:
                            while True:
                                res = ctypes.windll.kernel32.ReadFile(h, buf, ctypes.c_uint32(CHUNK), ctypes.byref(br), None)
                                if not res or br.value == 0:
                                    break
                                out_f.write(buf.raw[: br.value])
                        ctypes.windll.kernel32.CloseHandle(h)
                        if os.path.exists(dst) and os.path.getsize(dst) > 0:
                            return True
            except Exception as e:
                log.debug(f"CTypes CreateFileW copy failed for {src}: {e}")

        return False

    def read_file_bytes_safe(path: str) -> bytes:
        try:
            with open(path, "rb") as fp:
                data = fp.read()
                if data:
                    return data
        except Exception:
            pass

        if system_os == "Windows":
            try:
                import subprocess
                p_c = path.replace("\\", "/")
                ps_code = f'''
                try {{
                    $s = [IO.File]::Open("{p_c}", [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
                    $ms = New-Object IO.MemoryStream
                    $s.CopyTo($ms)
                    $s.Close()
                    [Console]::OpenStandardOutput().Write($ms.ToArray(), 0, $ms.Length)
                }} catch {{
                    $b = [IO.File]::ReadAllBytes("{p_c}")
                    [Console]::OpenStandardOutput().Write($b, 0, $b.Length)
                }}
                '''
                b64_ps = base64.b64encode(ps_code.encode("utf-16le")).decode("ascii")
                res = subprocess.check_output(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", b64_ps],
                    timeout=5,
                )
                if res:
                    return res
            except Exception as e:
                log.debug(f"PowerShell FileShare.ReadWrite read failed for {path}: {e}")

        return b""

    for cp in cookie_paths:
        if _cancelled():
            log.info("Chrome cookie decrypt cancelled by user")
            return extracted_cookies
        if not os.path.exists(cp):
            continue
        temp_dir = tempfile.mkdtemp()
        temp_db = os.path.join(temp_dir, "Cookies")
        try:
            if not copy_file_safe(cp, temp_db):
                # One more unlock attempt then retry (Windows exclusive lock)
                if system_os == "Windows":
                    try:
                        _windows_unlock_chromium_cookie_db(browser_name)
                    except Exception:
                        pass
                    if not copy_file_safe(cp, temp_db):
                        log.warning(f"Failed to copy cookie file from {cp}")
                        continue
                else:
                    log.warning(f"Failed to copy cookie file from {cp} (browser may be locking it)")
                    continue
            for ext in ["-journal", "-wal", "-shm"]:
                if os.path.exists(cp + ext):
                    copy_file_safe(cp + ext, temp_db + ext)

            conn = sqlite3.connect(temp_db)
            cur = conn.cursor()
            cur.execute(
                "SELECT name, value, encrypted_value, host_key FROM cookies "
                "WHERE (host_key = 'onlyfans.com' OR host_key = '.onlyfans.com' OR host_key LIKE '%.onlyfans.com' OR host_key = 'www.onlyfans.com') "
                "AND (name IN ('sess', 'auth_id') OR name LIKE 'auth_uid%')"
            )
            rows = cur.fetchall()
            if not rows:
                log.info(f"No OnlyFans cookies in DB {cp}")
            else:
                log.info(f"Found {len(rows)} OnlyFans cookie row(s) in {cp}")

            for name, val, enc, host_key in rows:
                if not cookie_allowlist.is_onlyfans_host(host_key):
                    continue
                if not cookie_allowlist.is_allowed_cookie_name(name):
                    continue
                if name in extracted_cookies and extracted_cookies[name]:
                    continue
                if val:
                    extracted_cookies[name] = val
                    log.info(f"Cookie {name} plaintext from {host_key}")
                    continue
                if not enc:
                    continue

                if system_os == "Windows":
                    if enc.startswith(b"v20"):
                        # App-Bound Encryption — DPAPI master key cannot decrypt these.
                        # Caller should fall back to CDP sync of the existing profile.
                        log.debug(
                            f"Cookie {name} uses v20 App-Bound Encryption; disk decrypt skipped"
                        )
                        continue
                    if enc.startswith(b'v10') or enc.startswith(b'v11'):
                        enc_data = enc[3:]
                        nonce, tag = enc_data[:12], enc_data[-16:]
                        for k in keys_gcm_win:
                            try:
                                cipher = AES.new(k, AES.MODE_GCM, nonce=nonce)
                                dec = cipher.decrypt_and_verify(enc_data[12:-16], tag)
                                decrypted_str = dec.decode('utf-8', errors='ignore')
                                if decrypted_str:
                                    extracted_cookies[name] = decrypted_str
                                    break
                            except Exception:
                                pass
                    else:
                        try:
                            dec = _win_dpapi_unprotect(enc)
                            if dec:
                                decrypted_str = dec.decode('utf-8', errors='ignore')
                                if decrypted_str:
                                    extracted_cookies[name] = decrypted_str
                        except Exception:
                            pass

                elif system_os == "Linux" and keys_cbc_linux:
                    prefix = enc[:3]
                    if prefix in (b"v10", b"v11"):
                        enc_data = enc[3:]
                        decrypted_ok = False
                        for k in keys_cbc_linux:
                            try:
                                cipher = AES.new(k, AES.MODE_CBC, b" " * 16)
                                dec = cipher.decrypt(enc_data)
                                unp = unpad(dec, 16)
                                # Linux OSCrypt: plaintext is the cookie value.
                                # macOS/Windows may prepend a 32-byte SHA256(host) hash —
                                # only strip when the prefix looks non-textual.
                                plain = unp
                                if len(unp) > 40:
                                    head = unp[:32]
                                    non_text = sum(1 for b in head if b < 32 or b > 126)
                                    if non_text >= 8:
                                        plain = unp[32:]
                                clean_val = (
                                    plain.decode("utf-8", errors="ignore")
                                    .strip("\x00")
                                    .strip()
                                )
                                if not clean_val:
                                    continue
                                # sess / auth_id are alphanumeric; reject obvious garbage
                                if name in {"sess", "auth_id"} or name.startswith("auth_uid"):
                                    if not re.fullmatch(r"[A-Za-z0-9._\-]{4,}", clean_val):
                                        # try latin1 salvage of full buffer
                                        m = re.search(
                                            r"[A-Za-z0-9._\-]{8,}",
                                            unp.decode("latin1", errors="ignore"),
                                        )
                                        if not m:
                                            continue
                                        clean_val = m.group(0)
                                extracted_cookies[name] = clean_val
                                decrypted_ok = True
                                log.info(
                                    f"Decrypted Linux cookie {name} "
                                    f"(prefix={prefix.decode()}, len={len(clean_val)})"
                                )
                                break
                            except Exception:
                                continue
                        if not decrypted_ok:
                            log.warning(
                                f"Failed to decrypt cookie {name} from {cp} "
                                f"(prefix={prefix!r}, enc_len={len(enc)}, "
                                f"keys_tried={len(keys_cbc_linux)})"
                            )
                    else:
                        log.debug(
                            f"Cookie {name} has unexpected encryption prefix {prefix!r}"
                        )
            conn.close()
        except Exception as e:
            log.warning(f"Cookie DB extract failed for {cp}: {e}")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if "sess" in extracted_cookies and "auth_id" in extracted_cookies:
            # Bind x-bc to the leveldb in this specific profile folder
            prof_dir = os.path.dirname(cp)
            # Cookies may live under .../Profile/Network/Cookies → profile is parent
            if os.path.basename(prof_dir).lower() == "network":
                prof_dir = os.path.dirname(prof_dir)
            ldb_candidates = [
                os.path.join(prof_dir, "Local Storage", "leveldb"),
                os.path.join(os.path.dirname(prof_dir), "Local Storage", "leveldb"),
            ]
            for ldb_dir in ldb_candidates:
                token = _extract_bctoken_from_leveldb_dir(ldb_dir)
                if token:
                    extracted_cookies["x-bc"] = token
                    break
            break

    return extracted_cookies


def _find_zen_cookie_file() -> str | None:
    import glob
    import platform
    home = os.path.expanduser("~")
    candidates = []
    
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "zen"))
    elif platform.system() == "Darwin":
        candidates.append(os.path.join(home, "Library", "Application Support", "zen"))
    else:
        candidates.extend([
            os.path.join(home, ".var/app/app.zen_browser.zen/.zen/"),
            os.path.join(home, ".zen/"),
            os.path.join(home, ".mozilla/zen/"),
        ])
        
    for base in candidates:
        if os.path.isdir(base):
            matches = glob.glob(os.path.join(base, "**/cookies.sqlite"), recursive=True)
            if matches:
                # Return the newest/most recently updated cookies.sqlite database
                matches_sorted = sorted(matches, key=os.path.getmtime, reverse=True)
                return matches_sorted[0]
    return None


def _fix_user_agent_casing(ua: str) -> str:
    if not ua:
        return ua
    import re
    ua = re.sub(r'(?i)mozilla/5\.0', 'Mozilla/5.0', ua)
    ua = re.sub(r'(?i)x11;\s*linux\s*x86_64', 'X11; Linux x86_64', ua)
    ua = re.sub(r'(?i)windows\s*nt\s*10\.0;\s*win64;\s*x64', 'Windows NT 10.0; Win64; x64', ua)
    ua = re.sub(r'(?i)gecko/20100101', 'Gecko/20100101', ua)
    ua = re.sub(r'(?i)firefox/', 'Firefox/', ua)
    ua = re.sub(r'(?i)chrome/', 'Chrome/', ua)
    ua = re.sub(r'(?i)safari/', 'Safari/', ua)
    ua = re.sub(r'(?i)applewebkit/', 'AppleWebKit/', ua)
    return ua


def _get_firefox_or_zen_profile_user_agent(profile_dir: str, browser_name: str = "firefox") -> str | None:
    import re
    import glob
    import platform
    import subprocess
    import tempfile
    import shutil
    import sqlite3

    system_os = platform.system()
    if system_os == "Windows":
        os_ua = "Windows NT 10.0; Win64; x64"
    elif system_os == "Darwin":
        os_ua = "Macintosh; Intel Mac OS X 10_15_7"
    else:
        os_ua = "X11; Linux x86_64"

    browser_name = browser_name.lower().replace(" ", "")
    is_firefox = browser_name in {"firefox", "zenbrowser"}

    # 1. Check user.js / prefs.js for explicit general.useragent.override
    if profile_dir and os.path.exists(profile_dir):
        for filename in ["user.js", "prefs.js"]:
            pfile = os.path.join(profile_dir, filename)
            if os.path.exists(pfile):
                try:
                    with open(pfile, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        m = (
                            re.search(r'user_pref\s*\(\s*["\']general\.useragent\.override["\']\s*,\s*["\']([^"\']+)["\']\s*\)', content)
                        )
                        if m:
                            override = _fix_user_agent_casing(m.group(1).strip())
                            # Firefox/Zen must not adopt a Chrome UA override by accident
                            if browser_name in {"firefox", "zenbrowser"}:
                                if _ua_looks_like_firefox(override):
                                    return override
                            elif "Firefox/" in override or "Chrome/" in override:
                                return override
                except Exception:
                    pass

    # 2. Dynamic LocalStorage Extraction: Search profile data.sqlite databases for full exact User-Agent string
    if profile_dir and os.path.exists(profile_dir):
        data_files = glob.glob(os.path.join(profile_dir, "storage", "**", "data.sqlite"), recursive=True)
        # Prioritize data.sqlite from onlyfans or popular web app origins
        data_files.sort(key=lambda p: (0 if "onlyfans" in p.lower() else 1, os.path.getmtime(p) * -1))

        for df in data_files:
            if os.path.exists(df):
                temp_dir = tempfile.mkdtemp()
                temp_db = os.path.join(temp_dir, "data.sqlite")
                try:
                    shutil.copy2(df, temp_db)
                    for ext in ["-wal", "-shm"]:
                        if os.path.exists(df + ext):
                            shutil.copy2(df + ext, temp_db + ext)
                    conn = sqlite3.connect(temp_db)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT key, value FROM data WHERE key LIKE '%user%agent%' "
                        "OR key LIKE '%ua%' OR key IN ('tnsApp', 'imagex_ua', 'userAgent')"
                    )
                    rows = cursor.fetchall()
                    for key, val in rows:
                        if isinstance(val, bytes):
                            val_str = val.decode("utf-8", errors="ignore")
                        else:
                            val_str = str(val)
                        if is_firefox:
                            # Match live Firefox/Zen DevTools UA, e.g.
                            # Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0
                            m = re.search(
                                r"(Mozilla/5\.0\s*\([^)]+\)\s*Gecko/\d+\s*Firefox/\d+(?:\.\d+)*)",
                                val_str,
                                re.IGNORECASE,
                            )
                        else:
                            m = re.search(
                                r"(Mozilla/5\.0\s*\([^)]+\)\s*AppleWebKit/\d+(?:\.\d+)*\s*"
                                r"\(KHTML,\s*like\s*Gecko\)\s*Chrome/\d+(?:\.\d+)*\s*"
                                r"Safari/\d+(?:\.\d+)*)",
                                val_str,
                                re.IGNORECASE,
                            )
                        if m:
                            found = _fix_user_agent_casing(m.group(1).strip())
                            if is_firefox and not _ua_looks_like_firefox(found):
                                continue
                            if (not is_firefox) and not _ua_looks_like_chromium(found):
                                continue
                            conn.close()
                            shutil.rmtree(temp_dir)
                            return found
                    conn.close()
                except Exception:
                    pass
                finally:
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception:
                        pass

    # 3. Dynamic Installation Config Scan: Check platform.ini / application.ini / compatibility.ini for Gecko Milestone/MinVersion
    exe = _find_browser_executable(browser_name)
    if is_firefox:
        ini_candidates = []
        if exe and isinstance(exe, str):
            exe_dir = os.path.dirname(exe)
            ini_candidates.extend([
                os.path.join(exe_dir, "platform.ini"),
                os.path.join(exe_dir, "application.ini"),
                os.path.join(exe_dir, "browser", "application.ini"),
                os.path.join(exe_dir, "browser", "platform.ini"),
            ])
        if profile_dir:
            ini_candidates.append(os.path.join(profile_dir, "compatibility.ini"))
        ini_candidates.extend(glob.glob("/var/lib/flatpak/app/**/platform.ini", recursive=True))
        ini_candidates.extend(glob.glob("/var/lib/flatpak/app/**/application.ini", recursive=True))
        ini_candidates.extend(glob.glob("/app/**/platform.ini", recursive=True))
        ini_candidates.extend(glob.glob("/app/**/application.ini", recursive=True))
        ini_candidates.extend(glob.glob(os.path.expanduser("~/.var/app/**/platform.ini"), recursive=True))
        ini_candidates.extend(glob.glob(os.path.expanduser("~/.var/app/**/application.ini"), recursive=True))

        for ini_path in ini_candidates:
            if os.path.exists(ini_path):
                try:
                    with open(ini_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        m = re.search(r'(?:Milestone|MinVersion|LastVersion|Version)=(\d+\.\d+(?:\.\d+)?)', content)
                        if m:
                            raw_v = m.group(1).split('_')[0]
                            parts = [int(x) for x in raw_v.split(".") if x.isdigit()]
                            if parts and parts[0] >= 90:
                                ver_str = f"{parts[0]}.0"
                                return f"Mozilla/5.0 ({os_ua}; rv:{ver_str}) Gecko/20100101 Firefox/{ver_str}"
                except Exception:
                    pass

    # 4. Dynamic CLI Executable Query
    if exe:
        try:
            cmd = [exe, "--version"] if isinstance(exe, str) else exe + ["--version"]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=3).decode("utf-8", errors="ignore")
            m = re.search(r'(\d+\.\d+(?:\.\d+)?)', out)
            if m:
                ver = m.group(1)
                parts = [int(x) for x in ver.split(".") if x.isdigit()]
                if parts and parts[0] >= 90:
                    ver_str = f"{parts[0]}.0"
                    if not is_firefox:
                        return f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{ver_str} Safari/537.36"
                    else:
                        return f"Mozilla/5.0 ({os_ua}; rv:{ver_str}) Gecko/20100101 Firefox/{ver_str}"
        except Exception:
            pass

    # 5. Dynamic Profile Storage Scan (Firefox/x.x or Chrome/x.x binary search)
    if profile_dir and os.path.exists(profile_dir):
        profile_files = (
            glob.glob(os.path.join(profile_dir, "storage", "**", "*.sqlite"), recursive=True) +
            glob.glob(os.path.join(profile_dir, "*.sqlite"), recursive=True)
        )
        found_versions = []
        pattern = rb'Firefox/(\d+(?:\.\d+)*)' if is_firefox else rb'Chrome/(\d+(?:\.\d+)*)'
        for pfile in profile_files:
            try:
                with open(pfile, "rb") as f:
                    content = f.read()
                    matches = re.findall(pattern, content)
                    for m in matches:
                        v_str = m.decode("utf-8", errors="ignore")
                        parts = [int(x) for x in v_str.split(".") if x.isdigit()]
                        if parts and parts[0] >= 90:
                            found_versions.append((parts, v_str))
            except Exception:
                pass

        if found_versions:
            found_versions.sort(key=lambda x: x[0], reverse=True)
            highest_v = found_versions[0][1]
            if is_firefox:
                return f"Mozilla/5.0 ({os_ua}; rv:{highest_v}) Gecko/20100101 Firefox/{highest_v}"
            else:
                return f"Mozilla/5.0 ({os_ua}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{highest_v} Safari/537.36"

    return None


def _find_browser_executable(browser_name: str) -> "str | list[str] | None":
    import shutil
    import platform
    import subprocess

    browser_name = browser_name.lower().replace(" ", "")

    # Windows-specific search paths
    if platform.system() == "Windows":
        import os
        paths = []
        if browser_name in {"chrome", "chromium"}:
            paths = [
                r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
                r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
                r"%LocalAppData%\Google\Chrome\Application\chrome.exe"
            ]
        elif browser_name == "edge":
            paths = [
                r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
                r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
            ]
        elif browser_name == "brave":
            paths = [
                r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"%LocalAppData%\BraveSoftware\Brave-Browser\Application\brave.exe"
            ]
        elif browser_name == "firefox":
            paths = [
                r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
                r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"
            ]
        elif browser_name == "zenbrowser":
            paths = [
                r"%LocalAppData%\Programs\zen\zen.exe",
                r"%LocalAppData%\Programs\Zen Browser\zen.exe",
                r"%LocalAppData%\Zen Browser\zen.exe",
                r"%LocalAppData%\Zen\zen.exe",
                r"%ProgramFiles%\Zen Browser\zen.exe",
                r"%ProgramFiles%\Zen\zen.exe",
                r"%ProgramFiles(x86)%\Zen Browser\zen.exe",
                r"%ProgramFiles(x86)%\Zen\zen.exe",
                r"%AppData%\Zen\zen.exe",
                r"%USERPROFILE%\scoop\apps\zen-browser\current\zen.exe"
            ]

        for p in paths:
            expanded = os.path.expandvars(p)
            if os.path.exists(expanded):
                return expanded

        # Zen-only PATH fallback (must not run for Firefox/Chrome lookups)
        if browser_name == "zenbrowser":
            for exe_cmd in ["zen", "zen-browser", "zen.exe"]:
                w = shutil.which(exe_cmd)
                if w:
                    return w

    # macOS-specific search paths
    if platform.system() == "Darwin":
        import os
        mac_paths = []
        if browser_name in {"chrome", "chromium"}:
            mac_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium"
            ]
        elif browser_name == "firefox":
            mac_paths = ["/Applications/Firefox.app/Contents/MacOS/firefox"]
        elif browser_name == "zenbrowser":
            mac_paths = ["/Applications/Zen Browser.app/Contents/MacOS/zen"]
        elif browser_name == "brave":
            mac_paths = ["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
        elif browser_name == "edge":
            mac_paths = ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]

        for p in mac_paths:
            if os.path.exists(p):
                return p

    # Standard Linux/POSIX path commands search
    cmd_map = {
        "chrome": ["google-chrome", "google-chrome-stable", "chrome", "chromium-browser", "chromium"],
        "chromium": ["chromium-browser", "chromium", "google-chrome", "google-chrome-stable", "chrome"],
        "firefox": ["firefox", "firefox-esr"],
        "zenbrowser": ["zen-browser", "zen"],
        "brave": ["brave-browser", "brave"],
        "edge": ["microsoft-edge", "edge", "msedge"],
        "opera": ["opera"],
        "operagx": ["opera"],
        "vivaldi": ["vivaldi"]
    }

    cmds = cmd_map.get(browser_name, [])
    for cmd in cmds:
        path = shutil.which(cmd)
        if path:
            return path

    # Check Flatpaks on Linux
    if platform.system() == "Linux" and shutil.which("flatpak"):
        flatpak_ids = {
            "zenbrowser": ["app.zen_browser.zen"],
            "firefox": ["org.mozilla.firefox"],
            "chrome": ["com.google.Chrome", "org.chromium.Chromium"],
            "chromium": ["org.chromium.Chromium", "com.google.Chrome"],
            "brave": ["com.brave.Browser"]
        }
        f_ids = flatpak_ids.get(browser_name, [])
        for f_id in f_ids:
            try:
                res = subprocess.run(["flatpak", "info", f_id], capture_output=True, text=True)
                if res.returncode == 0:
                    return ["flatpak", "run", f_id]
            except Exception:
                pass

    return None


def _get_default_browser_name() -> str:
    import platform
    import subprocess
    import shutil

    # 1. Linux / POSIX using xdg-settings
    if platform.system() == "Linux":
        try:
            res = subprocess.run(["xdg-settings", "get", "default-web-browser"], capture_output=True, text=True, timeout=2)
            if res.returncode == 0:
                desktop_file = res.stdout.strip().lower()
                if "zen" in desktop_file:
                    return "zenbrowser"
                elif "chrome" in desktop_file:
                    return "chrome"
                elif "chromium" in desktop_file:
                    return "chromium"
                elif "firefox" in desktop_file:
                    return "firefox"
                elif "brave" in desktop_file:
                    return "brave"
                elif "edge" in desktop_file:
                    return "edge"
                elif "opera" in desktop_file:
                    return "opera"
        except Exception:
            pass

    # 2. Windows using Registry associations
    if platform.system() == "Windows":
        try:
            import winreg
            path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                prog_id = winreg.QueryValueEx(key, "ProgId")[0]
                prog_id_lower = prog_id.lower()
                
                # Check associated command path to see if it points to Zen Browser
                try:
                    cmd_path = f"Software\\Classes\\{prog_id}\\shell\\open\\command"
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cmd_path) as cmd_key:
                        cmd_val = winreg.QueryValueEx(cmd_key, "")[0].lower()
                        if "zen" in cmd_val:
                            return "zenbrowser"
                except Exception:
                    try:
                        cmd_path = f"{prog_id}\\shell\\open\\command"
                        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, cmd_path) as cmd_key:
                            cmd_val = winreg.QueryValueEx(cmd_key, "")[0].lower()
                            if "zen" in cmd_val:
                                return "zenbrowser"
                    except Exception:
                        pass

                if "chrome" in prog_id_lower:
                    return "chrome"
                elif "zen" in prog_id_lower:
                    return "zenbrowser"
                elif "firefox" in prog_id_lower:
                    return "firefox"
                elif "edge" in prog_id_lower or "ie.https" in prog_id_lower:
                    return "edge"
                elif "brave" in prog_id_lower:
                    return "brave"
        except Exception:
            pass

    # Fallback to the first browser we actually find installed on the system
    for name in ["chrome", "chromium", "zenbrowser", "firefox", "brave", "edge", "opera", "vivaldi"]:
        if _find_browser_executable(name):
            return name

    return "chrome"


class _SystemChromeCDPListener(_CDPListener):
    """CDP listener for system Chrome. Captures both x-bc and user-agent from headers."""
    xbc_captured = pyqtSignal(str, str)

    def run(self):
        import base64 as _b64
        import socket as _sock_mod
        import time
        import urllib.request as _ureq
        from urllib.parse import urlparse

        # Wait up to 30 s for the CDP endpoint to come up
        targets = None
        for _ in range(30):
            if not self._running:
                return
            try:
                raw = _ureq.urlopen(
                    f"http://127.0.0.1:{self._port}/json/list", timeout=2
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
            ws_url = next(
                (t.get("webSocketDebuggerUrl", "") for t in targets if t.get("webSocketDebuggerUrl")),
                "",
            )
        if not ws_url:
            return

        try:
            u = urlparse(ws_url)
            host = u.hostname or "127.0.0.1"
            if host in {"localhost", "::1"}:
                host = "127.0.0.1"
            port = u.port or 80
            path = u.path + (f"?{u.query}" if u.query else "")

            self._sock = _sock_mod.create_connection((host, port), timeout=5)

            # Handshake
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

            # Enable Network + Runtime so we can read navigator.userAgent even
            # before OnlyFans fires authenticated API calls.
            self._ws_send(json.dumps({"id": 1, "method": "Network.enable", "params": {}}))
            self._ws_send(json.dumps({"id": 2, "method": "Runtime.enable", "params": {}}))
            self._ws_send(
                json.dumps(
                    {
                        "id": 3,
                        "method": "Runtime.evaluate",
                        "params": {
                            "expression": "navigator.userAgent",
                            "returnByValue": True,
                        },
                    }
                )
            )
            self._sock.settimeout(2.0)

            x_bc = ""
            user_agent = ""

            while self._running:
                try:
                    msg = self._ws_recv()
                except _sock_mod.timeout:
                    # Keep asking for navigator.userAgent until we get one
                    if not user_agent:
                        try:
                            self._ws_send(
                                json.dumps(
                                    {
                                        "id": 3,
                                        "method": "Runtime.evaluate",
                                        "params": {
                                            "expression": "navigator.userAgent",
                                            "returnByValue": True,
                                        },
                                    }
                                )
                            )
                        except Exception:
                            pass
                    continue
                if msg is None:
                    break
                try:
                    evt = json.loads(msg)
                except Exception:
                    continue

                # Runtime.evaluate result for navigator.userAgent
                if evt.get("id") == 3 and "result" in evt:
                    try:
                        val = (
                            evt.get("result", {})
                            .get("result", {})
                            .get("value")
                        )
                        if isinstance(val, str) and val.strip():
                            user_agent = val.strip()
                            if self._running:
                                self.xbc_captured.emit(x_bc, user_agent)
                    except Exception:
                        pass
                    continue

                method = evt.get("method", "")
                if method not in (
                    "Network.requestWillBeSent",
                    "Network.requestWillBeSentExtraInfo",
                ):
                    continue

                params = evt.get("params", {})
                req = params.get("request") or {}
                url = str(params.get("documentURL") or req.get("url") or "")
                hdrs = params.get("headers") or req.get("headers") or {}
                if not isinstance(hdrs, dict):
                    continue

                updated = False
                for k, v in hdrs.items():
                    k_lower = k.lower()
                    if k_lower == "x-bc" and v:
                        x_bc = str(v)
                        updated = True
                    elif k_lower == "user-agent" and v:
                        # Prefer OnlyFans traffic when available
                        if (not user_agent) or ("onlyfans.com" in url.lower()):
                            user_agent = str(v)
                            updated = True

                if updated and (x_bc or user_agent):
                    if self._running:
                        self.xbc_captured.emit(x_bc, user_agent)
        except Exception:
            pass


class ChromeLoginMonitorDialog(QDialog):
    """Monitors an external Chrome window running in debugging mode to capture auth credentials."""

    credentials_ready = pyqtSignal(dict)

    def __init__(
        self,
        port: int,
        process,
        profile_dir: str,
        parent=None,
        existing_profile: bool = False,
        browser_display: str = "Chrome",
        seed_creds: dict | None = None,
        cleanup_profile_dir: bool = True,
        browser_name: str | None = None,
        browser_path=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("System Browser Login Sync")
        self.resize(550, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.port = port
        self.process = process
        self.profile_dir = profile_dir
        self.existing_profile = existing_profile
        self.browser_display = browser_display
        self.cleanup_profile_dir = cleanup_profile_dir
        inferred = "zenbrowser" if "zenbrowser" in (profile_dir or "").lower() else (
            "firefox" if "firefox" in (profile_dir or "").lower() else "chrome"
        )
        self.browser_name = (browser_name or inferred).lower().replace(" ", "")
        self.browser_path = browser_path
        self.is_firefox = self.browser_name in {"firefox", "zenbrowser"}
        self._ua_from_network = False
        self.found = {
            "sess": "",
            "auth_id": "",
            "auth_uid": "",
            "user_agent": "",
            "x-bc": "",
        }
        if seed_creds:
            for k in ("sess", "auth_id", "auth_uid", "user_agent", "x-bc"):
                if seed_creds.get(k):
                    self.found[k] = seed_creds[k]
        self._cookie_fetcher = None
        self._cancelled = False
        self._timed_out = False
        self._cleaned = False
        self._wait_seconds = 0
        self._login_timeout_s = _auth_login_timeout_seconds()
        self._wait_timer = None
        self._info_label = None
        self._cancel_btn = None

        self._setup_ui()

        # Reflect any seeded values in the status grid
        for k, v in list(self.found.items()):
            if v and k in self._status_labels:
                self._status_labels[k].setText("Captured ✓")
                self._status_labels[k].setStyleSheet(_login_sync_style("captured"))
        self._check_ready()

        # CDP captures real request User-Agent + x-bc for Chromium and Firefox/Zen
        # (Firefox exposes --remote-debugging-port over the Chrome DevTools Protocol).
        self._cdp_listener = _SystemChromeCDPListener(self.port, self)
        self._cdp_listener.xbc_captured.connect(self._on_cdp_headers_captured)
        self._cdp_listener.start()

        # Poll cookies/storage every second
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll_cookies)
        self._poll_timer.start()

        self._wait_timer = QTimer(self)
        self._wait_timer.setInterval(1000)
        self._wait_timer.timeout.connect(self._on_wait_tick)
        self._wait_timer.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel(
            "Existing Profile Sync Active"
            if self.existing_profile
            else "Browser Sync Session Active"
        )
        apply_font(title, "Segoe UI", 16, QFont.Weight.Bold)
        title.setStyleSheet(_login_sync_style("title"))
        layout.addWidget(title)

        if self.is_firefox:
            info_text = (
                "A secure browser window has been opened on your desktop.\n\n"
                "1. ⚠️  LOG IN to your OnlyFans account inside that window.\n"
                "2. Complete any Turnstile or reCAPTCHA challenges.\n"
                "3. Once logged in and on your feed, CLOSE the browser window to finish."
            )
        elif self.existing_profile:
            info_text = (
                f"Your real {self.browser_display} profile is open via a temporary DevTools session.\n\n"
                "1. Wait for OnlyFans to load — you should already be logged in.\n"
                "2. Browse the feed briefly if capture stalls — that triggers API headers.\n"
                "3. When sess / auth_id / x-bc show Captured, click Use Captured Credentials "
                "(or wait for auto-apply).\n\n"
                f"Your normal {self.browser_display} window will reopen when this dialog closes."
            )
        else:
            info_text = (
                "A secure browser window has been opened on your desktop.\n\n"
                "1. Log in to your OnlyFans account inside that window.\n"
                "2. Complete any Turnstile or reCAPTCHA challenges there (they will pass normally).\n"
                "3. Once logged in, the credentials below will be captured automatically."
            )
        info = QLabel(info_text)
        info.setWordWrap(True)
        info.setStyleSheet(_login_sync_style("body"))
        self._info_label = info
        layout.addWidget(info)

        self._wait_lbl = QLabel(
            _format_login_wait_line(0, getattr(self, "_login_timeout_s", 0), kind="credentials")
        )
        self._wait_lbl.setStyleSheet(_login_sync_style("wait"))
        layout.addWidget(self._wait_lbl)

        # Fields status
        grid = QGridLayout()
        grid.setSpacing(8)
        self._status_labels = {}
        for row, (key, display) in enumerate([
            ("sess", "sess"),
            ("auth_id", "auth_id"),
            ("x-bc", "x-bc"),
            ("user_agent", "user-agent"),
        ]):
            lbl_title = QLabel(f"{display}:")
            lbl_title.setStyleSheet(_login_sync_style("field_label"))
            lbl_val = QLabel("Waiting...")
            lbl_val.setStyleSheet(_login_sync_style("waiting"))
            grid.addWidget(lbl_title, row, 0)
            grid.addWidget(lbl_val, row, 1)
            self._status_labels[key] = lbl_val
        layout.addLayout(grid)

        layout.addStretch()

        # Actions
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._use_btn = StyledButton("Use Captured Credentials", primary=True)
        self._use_btn.setEnabled(False)
        self._use_btn.clicked.connect(self._on_use_credentials)
        btn_layout.addWidget(self._use_btn)

        cancel_btn = StyledButton("Cancel Login")
        cancel_btn.setToolTip(
            "Abort login sync, close the temporary browser window, and discard captured credentials."
        )
        cancel_btn.clicked.connect(self._on_cancel_login)
        self._cancel_btn = cancel_btn
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _on_wait_tick(self):
        if self._cancelled:
            return
        if self.found.get("sess") and self.found.get("auth_id") and self.found.get("x-bc"):
            return
        self._wait_seconds += 1
        timeout_s = int(getattr(self, "_login_timeout_s", 0) or 0)
        try:
            self._wait_lbl.setText(
                _format_login_wait_line(
                    self._wait_seconds, timeout_s, kind="credentials"
                )
            )
        except Exception:
            pass
        if timeout_s > 0 and self._wait_seconds >= timeout_s:
            self._on_login_timeout()

    def _on_login_timeout(self):
        if self._cancelled:
            return
        if self.found.get("sess") and self.found.get("auth_id") and self.found.get("x-bc"):
            return
        self._timed_out = True
        limit_m = max(1, (int(getattr(self, "_login_timeout_s", 0) or 0) + 59) // 60)
        try:
            self._wait_lbl.setText(
                f"Login timed out after {limit_m} min — closing without importing credentials."
            )
            self._wait_lbl.setStyleSheet(_login_sync_style("wait_error"))
        except Exception:
            pass
        try:
            app_signals.status_message.emit(
                f"System browser login timed out after {limit_m} min"
            )
        except Exception:
            pass
        log.info(f"[GUI] System browser login timed out after {self._wait_seconds}s")
        self._on_cancel_login()

    def _on_cancel_login(self):
        """User aborted system-browser login — kill browser + CDP and close."""
        if self._cancelled:
            return
        self._cancelled = True
        try:
            if self._cancel_btn:
                self._cancel_btn.setEnabled(False)
                self._cancel_btn.setText("Cancelling…")
        except Exception:
            pass
        try:
            if self._use_btn:
                self._use_btn.setEnabled(False)
        except Exception:
            pass
        try:
            if not getattr(self, "_timed_out", False):
                self._wait_lbl.setText("Cancelling… closing browser session.")
                self._wait_lbl.setStyleSheet(_login_sync_style("wait_error"))
        except Exception:
            pass
        try:
            if not getattr(self, "_timed_out", False):
                app_signals.status_message.emit("System browser login cancelled")
        except Exception:
            pass
        self.reject()

    def _on_cdp_headers_captured(self, xbc: str, ua: str):
        """CDP Network/Runtime UAs are authoritative (not /json/version)."""
        if self._cancelled:
            return
        self._on_xbc_captured(xbc, ua, from_network=True)

    def _on_xbc_captured(self, xbc: str, ua: str, *, from_network: bool = False):
        if xbc:
            self.found["x-bc"] = xbc
            self._status_labels["x-bc"].setText("Captured ✓")
            self._status_labels["x-bc"].setStyleSheet(_login_sync_style("captured"))
        if ua:
            ua = ua.strip()
            if self.browser_name == "firefox":
                # Network headers are authoritative — including FPP's frozen
                # Firefox/115 rv:109 spoof (that looks like CDP /json/version junk).
                if from_network and _ua_looks_like_firefox(ua):
                    self._ua_from_network = True
                elif not _ua_looks_like_firefox(ua) or (
                    _is_stale_firefox_remote_ua(ua)
                    and not getattr(self, "_ua_from_network", False)
                ):
                    rejected = ua
                    if getattr(self, "_ua_from_network", False) and _ua_looks_like_firefox(
                        self.found.get("user_agent") or ""
                    ):
                        ua = self.found["user_agent"]
                    else:
                        ua = _resolve_firefox_family_user_agent(
                            "firefox",
                            browser_path=self.browser_path,
                            profile_dir=self.profile_dir,
                        )
                    log.warning(
                        f"Ignored bad Firefox UA from capture ({rejected[:80]}); "
                        f"using {ua}"
                    )
                elif getattr(self, "_ua_from_network", False):
                    # Keep authoritative network UA; ignore later binary guesses
                    ua = self.found.get("user_agent") or ua
                else:
                    ua = _pick_best_firefox_ua(self.found.get("user_agent") or "", ua) or ua
            elif self.browser_name == "zenbrowser":
                ua = _resolve_firefox_family_user_agent(
                    "zenbrowser",
                    browser_path=self.browser_path,
                    profile_dir=self.profile_dir,
                    preferred_ua=ua,
                )
            if ua:
                self.found["user_agent"] = ua
                preview = ua if len(ua) <= 64 else ua[:61] + "..."
                self._status_labels["user_agent"].setText(preview)
                self._status_labels["user_agent"].setStyleSheet(
                    _login_sync_style("captured")
                )
                self._status_labels["user_agent"].setToolTip(ua)
        self._check_ready()

    def _ensure_live_user_agent(self) -> str:
        """Prefer Network/Runtime-captured UA; never trust Firefox /json/version."""
        existing = self.found.get("user_agent") or ""
        if self.browser_name == "firefox":
            # Authoritative: UA already taken from OnlyFans request headers / navigator
            if getattr(self, "_ua_from_network", False) and _ua_looks_like_firefox(existing):
                if not _is_stale_firefox_remote_ua(existing):
                    return existing
            # Do not call /json/version for Firefox — returns frozen Firefox/115.
            best = _pick_best_firefox_ua(existing)
            if best:
                return best
            return _resolve_firefox_family_user_agent(
                "firefox",
                browser_path=self.browser_path,
                profile_dir=self.profile_dir,
            )
        if self.browser_name == "zenbrowser":
            live = _fetch_cdp_user_agent(self.port)
            if live:
                return _resolve_firefox_family_user_agent(
                    "zenbrowser",
                    browser_path=self.browser_path,
                    profile_dir=self.profile_dir,
                    preferred_ua=live,
                )
            return _resolve_firefox_family_user_agent(
                "zenbrowser",
                browser_path=self.browser_path,
                profile_dir=self.profile_dir,
                preferred_ua=existing or None,
            )
        live = _fetch_cdp_user_agent(self.port)
        return live or existing

    def _poll_firefox_sqlite(self) -> dict:
        import sqlite3
        import tempfile
        import shutil

        result = {}

        # 1. Read cookies.sqlite
        cookie_path = os.path.join(self.profile_dir, "cookies.sqlite")
        if os.path.exists(cookie_path):
            temp_dir = tempfile.mkdtemp()
            temp_db = os.path.join(temp_dir, "cookies.sqlite")
            try:
                shutil.copy2(cookie_path, temp_db)
                for ext in ["-wal", "-shm"]:
                    if os.path.exists(cookie_path + ext):
                        shutil.copy2(cookie_path + ext, temp_db + ext)

                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT value FROM moz_cookies "
                    "WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name='auth_id' "
                    "ORDER BY creationTime DESC LIMIT 1"
                )
                auth_id_row = cursor.fetchone()
                if auth_id_row:
                    result["auth_id"] = auth_id_row[0]

                cursor.execute(
                    "SELECT value FROM moz_cookies "
                    "WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name='sess' "
                    "ORDER BY creationTime DESC LIMIT 1"
                )
                sess_row = cursor.fetchone()
                if sess_row:
                    result["sess"] = sess_row[0]

                cursor.execute(
                    "SELECT name, value FROM moz_cookies "
                    "WHERE (host = 'onlyfans.com' OR host = '.onlyfans.com' OR host LIKE '%.onlyfans.com' OR host = 'www.onlyfans.com') AND name LIKE 'auth_uid%' "
                    "ORDER BY creationTime DESC LIMIT 1"
                )
                uid_row = cursor.fetchone()
                if uid_row:
                    result[uid_row[0]] = uid_row[1]

                conn.close()
            except Exception:
                pass
            finally:
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass

        # 2. Read data.sqlite for x-bc (bcTokenSha in localStorage)
        xbc = _extract_firefox_bctoken(self.profile_dir)
        if xbc:
            result["x-bc"] = xbc

        return result

    def _poll_cookies(self):
        if self.is_firefox:
            browser_exited = (self.process.poll() is not None) if self.process else True
            # Always try to refresh UA from the live debugging endpoint first
            live_ua = self._ensure_live_user_agent()
            if live_ua and live_ua != self.found.get("user_agent"):
                self._on_xbc_captured(self.found.get("x-bc") or "", live_ua)

            res = self._poll_firefox_sqlite()
            if res:
                self._on_cookies_fetched(res)
                if "x-bc" in res and res["x-bc"]:
                    ua = self._ensure_live_user_agent()
                    self._on_xbc_captured(res["x-bc"], ua)
            
            if browser_exited:
                self._poll_timer.stop()
                import time
                time.sleep(1.5)
                # Run one final poll after exit to grab freshly-flushed cookies
                res = self._poll_firefox_sqlite()
                if res:
                    self._on_cookies_fetched(res)
                # Final UA pass — never finish Firefox with a Chrome UA
                self.found["user_agent"] = self._ensure_live_user_agent()
                if self.found.get("sess") and self.found.get("auth_id") and self.found.get("x-bc"):
                    self._on_use_credentials()
                else:
                    if "auth_id" in self._status_labels:
                        self._status_labels["auth_id"].setText("Closed before login!")
                        self._status_labels["auth_id"].setStyleSheet(
                            _login_sync_style("error")
                        )
            return

        if self._cookie_fetcher and self._cookie_fetcher.isRunning():
            return
        self._cookie_fetcher = _CDPCookieFetcher(self.port, self)
        self._cookie_fetcher.result_ready.connect(self._on_cookies_fetched)
        self._cookie_fetcher.start()

    def _on_cookies_fetched(self, cookies: dict):
        for k, v in cookies.items():
            if v:
                self.found[k] = v
                if k in self._status_labels:
                    self._status_labels[k].setText("Captured ✓")
                    self._status_labels[k].setStyleSheet(_login_sync_style("captured"))
        if not self.found.get("auth_id"):
            if "auth_id" in self._status_labels:
                self._status_labels["auth_id"].setText("Waiting for login...")
                self._status_labels["auth_id"].setStyleSheet(
                    _login_sync_style("pending_login")
                )
        self._check_ready()

    def _check_ready(self):
        # We need sess, auth_id, and x-bc to be ready
        if self.found["sess"] and self.found["auth_id"] and self.found["x-bc"]:
            self._use_btn.setEnabled(True)
            # Existing-profile sync: finish automatically once CDP has everything
            if self.existing_profile and not getattr(self, "_auto_applied", False):
                self._auto_applied = True
                QTimer.singleShot(400, self._on_use_credentials)

    def _on_use_credentials(self):
        if self.browser_name == "firefox":
            self.found["user_agent"] = self._ensure_live_user_agent()
        payload = dict(self.found)
        payload["_browser_name"] = self.browser_name
        self.credentials_ready.emit(payload)
        self.accept()

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def reject(self):
        self._cleanup()
        super().reject()

    def accept(self):
        self._cleanup()
        super().accept()

    def _stop_qthread(self, thread, *, wait_ms: int = 5000) -> None:
        """Stop a child QThread and wait so the dialog can be destroyed safely."""
        if thread is None:
            return
        try:
            if hasattr(thread, "stop"):
                thread.stop()
        except Exception:
            pass
        try:
            thread.result_ready.disconnect()
        except Exception:
            pass
        try:
            thread.xbc_captured.disconnect()
        except Exception:
            pass
        try:
            if thread.isRunning():
                if not thread.wait(wait_ms):
                    # Last resort — avoid "QThread: Destroyed while still running"
                    thread.terminate()
                    thread.wait(2000)
        except Exception:
            pass
        try:
            # Detach so dialog destruction cannot kill a still-finishing thread.
            thread.setParent(None)
        except Exception:
            pass

    def _cleanup(self):
        if getattr(self, "_cleaned", False):
            return
        self._cleaned = True
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("login_sync_cleanup_start")
        except Exception:
            pass

        # Stop timers first so they do not spawn new fetchers during teardown.
        try:
            if self._wait_timer and self._wait_timer.isActive():
                self._wait_timer.stop()
        except Exception:
            pass
        try:
            if self._poll_timer and self._poll_timer.isActive():
                self._poll_timer.stop()
        except Exception:
            pass

        # Cookie fetcher was not waited on before — Cancel Login destroyed it mid-run.
        self._stop_qthread(getattr(self, "_cookie_fetcher", None), wait_ms=5000)
        self._cookie_fetcher = None
        self._stop_qthread(getattr(self, "_cdp_listener", None), wait_ms=5000)
        self._cdp_listener = None

        # Terminate Chrome/Firefox process safely
        if self.process:
            import platform
            try:
                if platform.system() != "Windows":
                    import os
                    import signal
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
                self.process.wait(2000)
            except Exception:
                try:
                    if platform.system() != "Windows":
                        import os
                        import signal
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    else:
                        self.process.kill()
                except Exception:
                    pass
            self.process = None
        # Clean up temp CDP user-data-dir (junction-aware — never wipe real Chrome profiles)
        if self.cleanup_profile_dir and self.profile_dir:
            _safe_remove_cdp_user_data(self.profile_dir)
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("login_sync_cleanup_done")
        except Exception:
            pass
