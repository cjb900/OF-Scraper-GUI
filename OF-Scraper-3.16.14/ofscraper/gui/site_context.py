"""Which site (OnlyFans or Fansly) this GUI process works on, and where its files live.

Each site runs in its own GUI process with its own config.json, profile and
auth file, so the two never share settings or a login:

    ~/.config/ofscraper/config.json            OnlyFans
    ~/.config/ofscraper/main_profile/auth.json
    ~/.config/ofscraper/fansly/config.json     Fansly
    ~/.config/ofscraper/fansly/main_profile/site.json         {"site": "fansly"}
    ~/.config/ofscraper/fansly/main_profile/fansly_auth.json

The GUI's own files (gui_settings.json, scrape history, layouts, presets,
crash logs) sit next to the config.json in use, so each site has its own too.

The tab window (site_host.py) starts one child process per site. A child talks
to it over its standard streams:
  stdout  lines starting with CHANNEL_PREFIX (window id, busy/idle, notices)
  stdin   "quit" asks the child to stop its scrape and close
"""

from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import sys
import threading

log = logging.getLogger("shared")

ONLYFANS = "onlyfans"
FANSLY = "fansly"
SITES = (ONLYFANS, FANSLY)
SITE_LABELS = {ONLYFANS: "OnlyFans", FANSLY: "Fansly"}

# Fansly's config folder, inside the default OnlyFans one
FANSLY_FOLDER = "fansly"

# set by the tab window for the processes it starts
ENV_CHILD = "OFSC_GUI_CHILD"
ENV_EMBED = "OFSC_GUI_EMBED"
# OFSC_GUI_TABS=0: no tab window, the GUI runs in this process as before
ENV_TABS = "OFSC_GUI_TABS"

CHANNEL_PREFIX = "@@OFSC_GUI "

# GUI settings copied into a new site's gui_settings.json from the OnlyFans one
SHARED_GUI_SETTINGS = ("theme", "gui_font_size", "help_font_size", "privacy_mode")


# --- this process --------------------------------------------------------------

def current_site() -> str:
    try:
        import ofscraper.sites as sites

        return sites.current_site()
    except Exception:
        return ONLYFANS


def is_fansly() -> bool:
    return current_site() == FANSLY


def site_label(site: str | None = None) -> str:
    return SITE_LABELS.get(site or current_site(), "OnlyFans")


def is_child() -> bool:
    return os.environ.get(ENV_CHILD) == "1"


def is_embedded() -> bool:
    return is_child() and os.environ.get(ENV_EMBED) == "1"


def tabs_enabled() -> bool:
    return os.environ.get(ENV_TABS, "1").strip().lower() not in ("0", "false", "no", "off")


# --- what each site supports ---------------------------------------------------------

# GUI actions that read OnlyFans only: the check tables, likes, purchases of
# every creator, metadata and manual URLs
ONLYFANS_ONLY_ACTIONS = frozenset(
    {"like", "unlike", "post_check", "msg_check", "paid_check", "story_check",
     "metadata", "paid_all", "manual_url"}
)


def site_areas(site: str | None = None) -> tuple | None:
    """Content areas the site can scrape, or None for no limit (OnlyFans)."""
    if (site or current_site()) != FANSLY:
        return None
    try:
        from ofscraper.sites.fansly import scrape as fansly_scrape

        return tuple(fansly_scrape.AREAS)
    except Exception:
        return ("Timeline", "Messages", "Purchased", "Labels")


def area_label(area: str, site: str | None = None) -> str:
    """How an area is shown: Fansly calls labels walls."""
    if area == "Labels" and (site or current_site()) == FANSLY:
        return "Walls"
    return area


def action_supported(action: str, site: str | None = None) -> bool:
    return (site or current_site()) != FANSLY or action not in ONLYFANS_ONLY_ACTIONS


# --- paths -----------------------------------------------------------------------

def default_config_home() -> pathlib.Path:
    """The OnlyFans config folder used without --config (~/.config/ofscraper)."""
    try:
        import ofscraper.utils.of_env.of_env as of_env

        return pathlib.Path.home() / of_env.getattr("configPath")
    except Exception:
        return pathlib.Path.home() / ".config" / "ofscraper"


def config_file_name() -> str:
    try:
        import ofscraper.utils.of_env.of_env as of_env

        return of_env.getattr("configFile") or "config.json"
    except Exception:
        return "config.json"


def fansly_config_home() -> pathlib.Path:
    return default_config_home() / FANSLY_FOLDER


def fansly_config_path() -> pathlib.Path:
    return fansly_config_home() / config_file_name()


def site_config_home(site: str) -> pathlib.Path:
    return fansly_config_home() if site == FANSLY else default_config_home()


# --- starting a site's GUI process ------------------------------------------------

_VALUE_OPTIONS = ("--site", "--config")


def strip_site_args(argv: list[str]) -> list[str]:
    """argv without --gui, --site X and --config X (the tab window sets those)."""
    out, skip = [], False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg == "--gui":
            continue
        if arg in _VALUE_OPTIONS:
            skip = True
            continue
        if any(arg.startswith(opt + "=") for opt in _VALUE_OPTIONS):
            continue
        out.append(arg)
    return out


def site_arguments(site: str, extra: list[str] | None = None, config: str | None = None) -> list[str]:
    """ofscraper arguments for one site's GUI process."""
    args = ["--gui", "--site", site]
    if site == FANSLY:
        args += ["--config", str(fansly_config_path())]
    elif config:
        # an OnlyFans --config the user gave keeps working
        args += ["--config", config]
    return args + list(extra or [])


def site_command(site: str, extra: list[str] | None = None, config: str | None = None) -> list[str]:
    """Full command line that starts a site's GUI process."""
    args = site_arguments(site, extra, config)
    if getattr(sys, "frozen", False):  # PyInstaller build: the executable is ofscraper
        return [sys.executable, *args]
    return [sys.executable, "-m", "ofscraper", *args]


def child_environment(embed: bool) -> dict:
    env = dict(os.environ)
    env[ENV_CHILD] = "1"
    env[ENV_EMBED] = "1" if embed else "0"
    # the child's channel lines must reach the tab window unbuffered and whole
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


# --- preparing this site's files ----------------------------------------------------

def prepare_site_files() -> None:
    """Make sure this site's profile and auth file exist (called by launch_gui).

    OnlyFans: auth.json. Fansly: site.json, so the profile stays a Fansly profile
    for CLI runs too, and fansly_auth.json. A new site's gui_settings.json starts
    from the OnlyFans one's look (theme, font size).
    """
    import ofscraper.utils.paths.common as common_paths

    profile = common_paths.get_profile_path()
    profile.mkdir(parents=True, exist_ok=True)
    if is_fansly():
        import ofscraper.sites as sites
        import ofscraper.sites.fansly.auth as fansly_auth

        if not (profile / sites.SITE_FILE).exists():
            sites.write_profile_site(profile, FANSLY)
            log.info(f"Marked {profile} as a Fansly profile")
        path = fansly_auth.auth_path()
        if not path.exists():
            path.write_text(json.dumps(fansly_auth.empty(), indent=4), encoding="utf-8")
            log.info(f"Created empty Fansly auth file at {path}")
        _seed_gui_settings()
        return
    import ofscraper.utils.auth.utils.dict as auth_dict

    auth_file = common_paths.get_auth_file()
    if not auth_file.exists():
        auth_file.write_text(json.dumps(auth_dict.get_empty(), indent=4), encoding="utf-8")
        log.info(f"Created empty auth.json at {auth_file}")


def _seed_gui_settings() -> None:
    try:
        import ofscraper.utils.paths.common as common_paths

        target = common_paths.get_config_home() / "gui_settings.json"
        source = default_config_home() / "gui_settings.json"
        if target.exists() or not source.exists() or target == source:
            return
        data = json.loads(source.read_text(encoding="utf-8"))
        seed = {k: data[k] for k in SHARED_GUI_SETTINGS if k in data}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    except Exception as e:
        log.debug(f"[GUI] could not copy the GUI look to the new site: {e}")


def temp_folder_conflict() -> str | None:
    """A warning when both sites download to the same temp folder.

    A run cleans up stray .part/temp_ files in its temp folder when it starts,
    which would delete the other site's files mid-download.
    """
    try:
        import ofscraper.utils.config.data as config_data

        mine = config_data.get_TempDir()
        if not mine:
            return None
        other_site = ONLYFANS if is_fansly() else FANSLY
        other_path = site_config_home(other_site) / config_file_name()
        if not other_path.exists():
            return None
        other_config = json.loads(other_path.read_text(encoding="utf-8"))
        # same unwrapping as config_file.open_config
        other_config = other_config.get("config") or other_config
        other = config_data.get_TempDir(config=other_config)
        if other and pathlib.Path(other).expanduser().resolve() == pathlib.Path(mine).expanduser().resolve():
            return (
                f"OnlyFans and Fansly use the same temp folder ({mine}). A run cleans "
                "up leftover temporary files there when it starts, which can delete "
                "the other site's downloads in progress. Set a different temp folder "
                "for one of them in Configuration."
            )
    except Exception as e:
        log.debug(f"[GUI] temp folder check skipped: {e}")
    return None


# --- child side of the channel to the tab window ------------------------------------

def send(kind: str, payload=None) -> None:
    """Send a message to the tab window (no-op outside a child process)."""
    if not is_child():
        return
    line = CHANNEL_PREFIX + kind
    if payload is not None:
        line += " " + base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    try:
        stream = sys.__stdout__ or sys.stdout
        stream.write(line + "\n")
        stream.flush()
    except Exception:
        pass


def parse_channel_line(line: str):
    """(kind, payload) for a channel line, else None."""
    if not line.startswith(CHANNEL_PREFIX):
        return None
    rest = line[len(CHANNEL_PREFIX):].strip()
    kind, _, data = rest.partition(" ")
    payload = None
    if data:
        try:
            payload = json.loads(base64.b64decode(data).decode("utf-8"))
        except Exception:
            payload = None
    return kind, payload


def install_child_channel(app, window) -> None:
    """In a child process: report the window, busy/idle and notices to the tab
    window, and quit cleanly when it sends "quit" on stdin."""
    if not is_child():
        return
    from PyQt6.QtCore import QObject, QTimer, pyqtSignal

    from ofscraper.gui.signals import app_signals

    class _Bridge(QObject):
        quit_requested = pyqtSignal()

    bridge = _Bridge(app)
    app._ofs_site_bridge = bridge  # keep it alive

    def _quit():
        try:
            from ofscraper.gui.utils.shutdown import request_shutdown

            request_shutdown(app, window.workflow)
        except Exception as e:
            log.warning(f"[GUI] stop from the tab window failed: {e}")
            app.quit()

    bridge.quit_requested.connect(_quit)

    def _read_stdin():
        try:
            for line in sys.stdin:
                if line.strip() == "quit":
                    bridge.quit_requested.emit()
                    return
        except Exception:
            pass
        # stdin closed: the tab window is gone
        bridge.quit_requested.emit()

    threading.Thread(target=_read_stdin, name="site-host-stdin", daemon=True).start()

    app_signals.scrape_started.connect(lambda: send("busy"))
    app_signals.scraping_finished.connect(lambda: send("idle"))
    app_signals.show_notification.connect(
        lambda title, message: send("notify", {"title": title, "message": message})
    )

    if is_embedded():
        # after show(): the window id must exist and the window be mapped
        QTimer.singleShot(0, lambda: send("window", {"id": int(window.winId())}))
    send("ready", {"site": current_site()})
