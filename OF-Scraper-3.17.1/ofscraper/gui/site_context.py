"""Which site (OnlyFans or Fansly) this GUI process works on, and where its files live.

Each site runs in its own GUI process with its own config.json, profile and
auth file, so the two never share settings or a login:

    ~/.config/ofscraper/config.json            OnlyFans
    ~/.config/ofscraper/main_profile/auth.json
    ~/.config/ofscraper/fansly/config.json     Fansly
    ~/.config/ofscraper/fansly/main_profile/site.json         {"site": "fansly"}
    ~/.config/ofscraper/fansly/main_profile/fansly_auth.json

Downloads go to each config's save location, by default
~/Data/ofscraper/OnlyFans and ~/Data/ofscraper/Fansly.

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
# each site's downloads folder under the built-in save root (~/Data/ofscraper)
SITE_FOLDERS = {ONLYFANS: "OnlyFans", FANSLY: "Fansly"}

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


def area_default(area: str, site: str | None = None) -> bool:
    """Whether an area starts ticked. Fansly's walls re-read the timeline
    once per wall, slowly under its rate limit, so they are opt-in."""
    return not (area == "Labels" and (site or current_site()) == FANSLY)


def action_supported(action: str, site: str | None = None) -> bool:
    return (site or current_site()) != FANSLY or action not in ONLYFANS_ONLY_ACTIONS


# --- links to the site ---------------------------------------------------------------

def profile_url(username: str, site: str | None = None) -> str:
    host = "fansly.com" if (site or current_site()) == FANSLY else "onlyfans.com"
    return f"https://{host}/{username}"


def post_url(post_id, username: str = "", responsetype: str = "", site: str | None = None):
    """Page of a table row's post on its site, or None when there isn't one.

    OnlyFans: /{post_id}/{username}. Fansly: /post/{post_id}; a message has no
    page of its own, so it opens the inbox.
    """
    post_id = str(post_id or "").strip()
    if (site or current_site()) == FANSLY:
        if str(responsetype or "").strip().lower() in ("messages", "message"):
            return "https://fansly.com/messages"
        return f"https://fansly.com/post/{post_id}" if post_id else None
    username = str(username or "").strip()
    if not post_id or not username:
        return None
    return f"https://onlyfans.com/{post_id}/{username}"


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


def _same_path(a, b) -> bool:
    try:
        return pathlib.Path(a).expanduser().resolve() == pathlib.Path(b).expanduser().resolve()
    except Exception:
        return False


def uses_own_fansly_config() -> bool:
    """A run with the GUI's Fansly config.json (only ever used for Fansly).

    Its save location is Fansly's alone and is used as it is; a Fansly run on
    a config shared with OnlyFans saves to ``<save location>/Fansly``.
    Reads only the arguments: it runs while a new config.json is written,
    before the settings exist.
    """
    import ofscraper.utils.paths.common as common_paths

    return _same_path(common_paths.get_config_path(), fansly_config_path())


def _run_is_fansly() -> bool:
    """This run's site, without building the settings if they don't exist yet
    (asking for them while they're being set up would wait on their lock)."""
    import ofscraper.sites as sites
    import ofscraper.utils.settings as settings

    if settings.settings:
        return sites.is_fansly()
    return sites.normalize(getattr(settings.get_args(), "site", None)) == FANSLY


def default_save_folder() -> str | None:
    """Folder under the built-in save root for this run's site, or None for
    the bare root (a Fansly run sharing OnlyFans' config gets /Fansly later)."""
    if uses_own_fansly_config():
        return SITE_FOLDERS[FANSLY]
    return None if _run_is_fansly() else SITE_FOLDERS[ONLYFANS]


# --- OnlyFans downloads in their own folder ---------------------------------------------

# gui_settings.json key: the user chose (or didn't need to choose) where existing
# OnlyFans downloads in the bare default save location go
_ONLYFANS_SAVE_DECIDED = "onlyfans_save_folder_decided"


def _builtin_save_root() -> pathlib.Path:
    import ofscraper.utils.of_env.of_env as of_env

    return pathlib.Path(of_env.getattr("SAVE_PATH_DEFAULT")).expanduser()


def onlyfans_folder_plan():
    """What to do about OnlyFans downloads saved straight into the default
    save location (~/Data/ofscraper) from before each site had a folder.

    None: nothing to do (Fansly, already decided, or a custom save location).
    Otherwise (root, target, folders): ``folders`` are the model folders in
    ``root`` (empty: nothing saved yet, so the setting can just change).
    """
    import ofscraper.utils.paths.common as common_paths
    from ofscraper.gui.utils.gui_settings import load_gui_settings

    if is_fansly() or load_gui_settings().get(_ONLYFANS_SAVE_DECIDED):
        return None
    root = _builtin_save_root()
    if not _same_path(common_paths.get_save_location(), root):
        _mark_onlyfans_folder_decided()
        return None
    target = root / SITE_FOLDERS[ONLYFANS]
    skip = {name.lower() for name in SITE_FOLDERS.values()}
    folders = []
    if root.is_dir():
        folders = sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and not p.name.startswith(".") and p.name.lower() not in skip
        )
    return root, target, folders


def _mark_onlyfans_folder_decided() -> None:
    from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

    settings = load_gui_settings()
    settings[_ONLYFANS_SAVE_DECIDED] = True
    save_gui_settings(settings, quiet=True)


def _set_save_location(location) -> None:
    import ofscraper.utils.config.file as config_file
    import ofscraper.utils.paths.common as common_paths

    path = common_paths.get_config_path()
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    config = config.get("config") or config
    config.setdefault("file_options", {})["save_location"] = str(location)
    config.pop("save_location", None)
    config_file.write_config(config)


def _relocated(directory, moves):
    for old, new in moves:
        try:
            return str(pathlib.Path(new) / pathlib.Path(directory).relative_to(old))
        except ValueError:
            continue
    return None


def _update_download_paths(moves, databases) -> int:
    """Point the databases' download folders (medias.directory) at the moved folders."""
    import sqlite3

    changed = 0
    for db in databases:
        try:
            conn = sqlite3.connect(str(db))
        except sqlite3.Error:
            continue
        try:
            rows = conn.execute(
                "SELECT rowid, directory FROM medias WHERE directory IS NOT NULL"
            ).fetchall()
            for rowid, directory in rows:
                new = _relocated(directory, moves)
                if new:
                    conn.execute("UPDATE medias SET directory=? WHERE rowid=?", (new, rowid))
                    changed += 1
            conn.commit()
        except sqlite3.Error as e:
            log.warning(f"Could not update download paths in {db}: {e}")
        finally:
            conn.close()
    return changed


def _onlyfans_databases(target: pathlib.Path):
    """OnlyFans user_data.db files: in the config folder (not Fansly's), and in
    the save location when the metadata format puts them there."""
    import ofscraper.utils.config.data as config_data

    fansly_home = fansly_config_home()
    found = [
        db for db in default_config_home().rglob("user_data.db")
        if fansly_home not in db.parents
    ]
    try:
        metadata = str(config_data.get_metadata() or "")
    except Exception:
        metadata = ""
    if any(key in metadata for key in ("save_location", "savelocation", "{root}")):
        found += list(target.rglob("user_data.db"))
    return found


def apply_onlyfans_folder(plan, move: bool) -> dict:
    """Carry out the choice for onlyfans_folder_plan().

    move=True (or nothing saved yet): model folders go into ``target``, the
    databases follow, and OnlyFans saves to ``target`` from now on.
    move=False: everything stays where it is, the save location too.
    The question is never asked again either way.
    """
    import shutil

    root, target, folders = plan
    result = {"moved": [], "skipped": [], "failed": [], "paths_updated": 0}
    if move or not folders:
        target.mkdir(parents=True, exist_ok=True)
        moves = []
        for name in folders:
            src, dst = root / name, target / name
            if dst.exists():
                result["skipped"].append(name)
                continue
            try:
                shutil.move(str(src), str(dst))
                moves.append((src, dst))
                result["moved"].append(name)
            except OSError as e:
                log.warning(f"Could not move {src} to {dst}: {e}")
                result["failed"].append(name)
        if moves:
            result["paths_updated"] = _update_download_paths(moves, _onlyfans_databases(target))
        _set_save_location(target)
        log.info(f"OnlyFans downloads now go to {target}; moved {len(result['moved'])} model folder(s)")
    _mark_onlyfans_folder_decided()
    return result


# gui_settings.json key: the Fansly save location already names its own folder
_FANSLY_SAVE_MIGRATED = "fansly_save_location_is_own"


def migrate_fansly_save_location() -> None:
    """Fansly's config.json from before its save location was used as it is
    (v426) meant ``<save location>/Fansly``; write that, once, so its files
    keep going to the same folder."""
    import ofscraper.utils.config.file as config_file
    import ofscraper.utils.paths.common as common_paths
    from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

    if not uses_own_fansly_config():
        return
    settings = load_gui_settings()
    if settings.get(_FANSLY_SAVE_MIGRATED):
        return
    path = common_paths.get_config_path()
    if path.exists():
        config = json.loads(path.read_text(encoding="utf-8"))
        config = config.get("config") or config
        options = config.setdefault("file_options", {})
        location = options.get("save_location") or config.get("save_location")
        if location and pathlib.PurePath(str(location)).name.lower() != FANSLY:
            options["save_location"] = str(pathlib.Path(str(location)) / SITE_FOLDERS[FANSLY])
            config.pop("save_location", None)
            config_file.write_config(config)
            log.info(f"Fansly save location is now {options['save_location']} (same folder as before)")
    settings[_FANSLY_SAVE_MIGRATED] = True
    save_gui_settings(settings)


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


def standalone_environment(env=None) -> dict:
    """``env`` (default: this process's) without the tab-child variables, for a
    program that must start its own GUI window, not an embedded tab."""
    env = dict(os.environ if env is None else env)
    for name in (ENV_CHILD, ENV_EMBED):
        env.pop(name, None)
    return env


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
        try:
            migrate_fansly_save_location()
        except Exception as e:
            log.warning(f"Could not update the Fansly save location: {e}")
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
