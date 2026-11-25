"""The GUI's side of upstream's optional PostgreSQL database (POSTGRESQL.md).

The scraper keeps a creator's rows in PostgreSQL when OFSC_DATABASE_URL is
set. The address holds a password, so upstream never reads it from
config.json: it comes from the environment or from a .env file listed under
advanced_options.env_files. The GUI writes it to one such file of its own
(``postgresql.env`` in the OnlyFans config folder, readable only by the user)
and lists that file in the OnlyFans and Fansly config.json, so both tabs, the
command line and upstream's tools all use the same database.

The scraper connects once at startup, so a change here takes effect when the
GUI is restarted.

Moving the user_data.db files in (postgres_import) and back out
(postgres_export) runs upstream's own commands in a separate process: they
load the scraper's settings themselves, which must not mix with the GUI's.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import pathlib
import shutil
import stat
import sys
from dataclasses import dataclass
from urllib.parse import quote, unquote, urlsplit

log = logging.getLogger("shared")

URL_KEY = "OFSC_DATABASE_URL"
ENV_FILE_NAME = "postgresql.env"
DEFAULT_PORT = 5432
DRIVER_REQUIREMENT = "psycopg[binary,pool]>=3.3.9,<3.4"


# --- the address ----------------------------------------------------------------


def build_url(host, port, database, user, password) -> str:
    """postgresql://user:password@host:port/database, each part
    percent-encoded so that @, :, / and spaces in it can't change the
    meaning (POSTGRESQL.md)."""
    host = str(host or "").strip()
    if not host:
        raise ValueError("Enter the server's host name or address.")
    database = str(database or "").strip()
    if not database:
        raise ValueError("Enter the database name.")
    user = str(user or "").strip()
    if not user:
        raise ValueError("Enter the PostgreSQL user name.")
    try:
        port = int(str(port or DEFAULT_PORT).strip())
    except ValueError:
        raise ValueError("The port must be a number.") from None
    if not 0 < port < 65536:
        raise ValueError("The port must be between 1 and 65535.")
    # an IPv6 address is written in brackets
    shown_host = f"[{host}]" if ":" in host and not host.startswith("[") else host
    login = quote(user, safe="")
    if password:
        login += ":" + quote(str(password), safe="")
    return f"postgresql://{login}@{shown_host}:{port}/{quote(database, safe='')}"


def parse_url(url) -> dict:
    """The parts of a postgresql:// address, for filling in the fields.
    Empty when it isn't one (for example PostgreSQL's keyword form)."""
    url = str(url or "").strip()
    if not url.lower().startswith(("postgresql://", "postgres://")):
        return {}
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return {}
    return {
        "host": parts.hostname or "",
        "port": port or DEFAULT_PORT,
        "database": unquote(parts.path.lstrip("/")),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
    }


def describe(url=None) -> str:
    """host:port/database, never the login."""
    try:
        import ofscraper.db.postgres as postgres

        return postgres.describe(url)
    except Exception:
        parts = parse_url(url or "")
        if parts:
            return f"{parts['host']}:{parts['port']}/{parts['database']}"
        return "the configured database"


def masked(text, url=None) -> str:
    """text with the address and its password hidden."""
    try:
        import ofscraper.db.postgres as postgres

        return postgres.masked(text, url)
    except Exception:
        password = parse_url(url or "").get("password")
        text = str(text)
        if url:
            text = text.replace(str(url), "{hidden}")
        return text.replace(password, "{hidden}") if password else text


# --- what this process uses -----------------------------------------------------


def enabled() -> bool:
    """Whether this GUI process keeps its data in PostgreSQL (the address
    it was started with)."""
    try:
        import ofscraper.db.postgres as postgres

        return postgres.enabled()
    except Exception:
        return False


def active_url() -> str:
    try:
        import ofscraper.db.postgres as postgres

        return postgres.url()
    except Exception:
        return ""


def driver_installed() -> bool:
    # an install from this window is seen without a restart
    importlib.invalidate_caches()
    return all(importlib.util.find_spec(name) is not None for name in ("psycopg", "psycopg_pool"))


def standalone_build() -> bool:
    """The single-file download: upstream doesn't include the driver, and
    nothing can be installed into it."""
    return bool(getattr(sys, "frozen", False))


# --- the env file and config.json ------------------------------------------------


def env_file_path() -> pathlib.Path:
    from ofscraper.gui import site_context

    return site_context.default_config_home() / ENV_FILE_NAME


def saved_url() -> str:
    """The address saved in the GUI's env file ("" when there is none)."""
    path = env_file_path()
    if not path.is_file():
        return ""
    try:
        from dotenv import dotenv_values

        return str(dotenv_values(path).get(URL_KEY) or "").strip()
    except Exception as e:
        log.debug(f"[PostgreSQL] couldn't read {path}: {e}")
        return ""


def config_files() -> list[tuple[str, pathlib.Path]]:
    """(site label, config.json) for the OnlyFans and the Fansly settings.
    This process's own config.json comes first (it may be a --config one)."""
    from ofscraper.gui import site_context

    try:
        import ofscraper.utils.paths.common as common_paths

        own = pathlib.Path(common_paths.get_config_path())
    except Exception:
        own = None
    onlyfans = site_context.default_config_home() / site_context.config_file_name()
    fansly = site_context.fansly_config_path()
    if site_context.is_fansly():
        found = [("Fansly", own or fansly), ("OnlyFans", onlyfans)]
    else:
        found = [("OnlyFans", own or onlyfans), ("Fansly", fansly)]
    unique, seen = [], set()
    for label, path in found:
        key = str(path.expanduser().resolve()) if path else ""
        if path and key not in seen:
            seen.add(key)
            unique.append((label, path))
    return unique


def _read_config(path: pathlib.Path) -> tuple[dict, dict]:
    """(the file's JSON, the settings in it: the "config" object when the
    file wraps them in one)."""
    whole = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(whole, dict):
        raise ValueError(f"{path} doesn't hold settings")
    inner = whole.get("config") if isinstance(whole.get("config"), dict) else whole
    return whole, inner


def _same_file(a, b) -> bool:
    try:
        return pathlib.Path(str(a)).expanduser().resolve() == pathlib.Path(str(b)).expanduser().resolve()
    except Exception:
        return False


def _env_files(settings: dict) -> list:
    value = (settings.get("advanced_options") or {}).get("env_files")
    if isinstance(value, str):
        return [x for x in value.replace(",", " ").split() if x]
    return [x for x in (value or []) if x]


def _write_config(path: pathlib.Path, whole: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(whole, indent=4), encoding="utf-8")
    os.replace(tmp, path)
    try:
        import ofscraper.utils.config.file as config_file

        config_file._cached_config = None
    except Exception:
        pass


def _set_listed(path: pathlib.Path, env_file: pathlib.Path, listed: bool) -> bool:
    """List (or stop listing) env_file in a config.json's env_files.
    Returns whether the file was changed."""
    whole, settings = _read_config(path)
    current = _env_files(settings)
    others = [x for x in current if not _same_file(x, env_file)]
    wanted = others + [str(env_file)] if listed else others
    if wanted == current:
        return False
    settings.setdefault("advanced_options", {})["env_files"] = wanted
    _write_config(path, whole)
    return True


def is_listed(path: pathlib.Path) -> bool:
    try:
        _, settings = _read_config(path)
    except Exception:
        return False
    return any(_same_file(x, env_file_path()) for x in _env_files(settings))


def _write_env_file(url: str) -> pathlib.Path:
    path = env_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Written by the OF-Scraper GUI (Merge DBs > PostgreSQL).\n"
        "# Holds the PostgreSQL password: keep this file private.\n"
        f"{URL_KEY}='{url}'\n"
    )
    tmp = path.with_name(path.name + ".tmp")
    # readable by this user only, from the moment it exists
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return path


def save(url: str) -> list[str]:
    """Write the address to the GUI's env file and list that file in each
    site's config.json. Returns what was done, one sentence each."""
    if "'" in url or "\n" in url:
        raise ValueError("The address can't contain quotes or line breaks.")
    path = _write_env_file(url)
    done = [f"Saved the address to {path} (only your user can read it)."]
    for label, config in config_files():
        if not config.is_file():
            done.append(
                f"{label}: no config.json yet. Open the {label} tab once, then"
                " save here again so it uses PostgreSQL too."
            )
            continue
        try:
            changed = _set_listed(config, path, True)
        except Exception as e:
            done.append(f"{label}: couldn't update {config}: {e}")
            continue
        done.append(
            f"{label}: {'added to' if changed else 'already listed in'}"
            f" env_files in {config}."
        )
    return done


def remove() -> list[str]:
    """Go back to the user_data.db files: stop listing the env file and
    delete it (it holds the password)."""
    path = env_file_path()
    done = []
    for label, config in config_files():
        if not config.is_file():
            continue
        try:
            if _set_listed(config, path, False):
                done.append(f"{label}: removed from env_files in {config}.")
        except Exception as e:
            done.append(f"{label}: couldn't update {config}: {e}")
    if path.exists():
        try:
            path.unlink()
            done.append(f"Deleted {path}.")
        except OSError as e:
            done.append(f"Couldn't delete {path}: {e}")
    if os.environ.get(URL_KEY, "").strip() and not saved_url():
        done.append(
            f"{URL_KEY} may also be set outside the GUI (for example under"
            " environment: in docker-compose.yml). Remove it there too."
        )
    return done


# --- checking a server ----------------------------------------------------------


def test_connection(url: str) -> str:
    """Connect read-only and return a sentence naming the server. Raises
    RuntimeError with one sentence (the password hidden) when it can't be
    used."""
    if not driver_installed():
        raise RuntimeError(driver_missing_text())
    import ofscraper.db.postgres as postgres

    reader = None
    try:
        reader = postgres.Reader(url)
        version = int(reader.rows("SHOW server_version_num")[0][0])
    except postgres.PostgresUnavailable as e:
        raise RuntimeError(masked(" ".join(str(e).split()), url)) from None
    except Exception as e:
        raise RuntimeError(
            f"Couldn't connect to {describe(url)}: {masked(' '.join(str(e).split()), url)}"
        ) from None
    finally:
        if reader is not None:
            reader.close()
    major = version // 10000
    if major < postgres.MIN_SERVER:
        raise RuntimeError(
            f"The server at {describe(url)} is PostgreSQL {major};"
            f" {postgres.MIN_SERVER} or newer is needed."
        )
    return f"Connected to PostgreSQL {major}.{version % 10000} at {describe(url)}."


def driver_missing_text() -> str:
    if standalone_build():
        return (
            "The PostgreSQL driver isn't included in the standalone download."
            " Use the pip or Docker install to use PostgreSQL."
        )
    return (
        "The PostgreSQL driver (psycopg) isn't installed. Use Install driver,"
        f" or run: {install_driver_plan().manual}"
    )


# --- upstream's commands --------------------------------------------------------


def python_command() -> list[str]:
    """This environment's Python, with a console-capable interpreter on
    Windows (pythonw.exe has no stdout to read)."""
    exe = sys.executable
    name = os.path.basename(exe).lower()
    if name == "pythonw.exe":
        console = os.path.join(os.path.dirname(exe), "python.exe")
        if os.path.isfile(console):
            exe = console
    return [exe, "-u"]


def install_method() -> str:
    """How this ofscraper was installed: "pipx", "uv" (uv tool) or "pip".
    pipx and uv tool environments have no pip of their own, so the driver
    goes in the way they were made."""
    prefix = pathlib.Path(sys.prefix)
    if (prefix / "pipx_metadata.json").is_file():
        return "pipx"
    if (prefix / "uv-receipt.toml").is_file():
        return "uv"
    parts = [p.lower() for p in prefix.parts]
    parent = prefix.parent.name.lower()
    if parent == "venvs" and any("pipx" in p for p in parts):
        return "pipx"
    if parent == "tools" and "uv" in parts:
        return "uv"
    return "pip"


def _find_tool(name: str) -> str | None:
    """A tool on PATH, or where its installers put it when the GUI was
    started without that folder on PATH."""
    found = shutil.which(name)
    if found:
        return found
    home = pathlib.Path.home()
    exe = f"{name}.exe" if sys.platform == "win32" else name
    folders = [home / ".local" / "bin", home / ".cargo" / "bin"]
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            folders += sorted(pathlib.Path(appdata, "Python").glob("Python3*/Scripts"), reverse=True)
    for folder in folders:
        candidate = folder / exe
        if candidate.is_file():
            return str(candidate)
    return None


def _pip_available() -> bool:
    return importlib.util.find_spec("pip") is not None


@dataclass
class InstallPlan:
    method: str  # pipx, uv or pip
    command: list[str] | None  # None: nothing found to run it with
    manual: str  # the same install for a person to type
    cwd: str | None = None


def install_driver_plan() -> InstallPlan:
    """The driver install that matches this install: pipx inject for pipx,
    uv pip install into the tool's Python for uv, pip otherwise."""
    method = install_method()
    python = python_command()[0]
    quoted = f'"{DRIVER_REQUIREMENT}"'
    home = str(pathlib.Path.home())
    uv_args = ["pip", "install", "--python", python, DRIVER_REQUIREMENT]
    uv_manual = f'uv pip install --python "{python}" {quoted}'
    if method == "pipx":
        venv = pathlib.Path(sys.prefix).name
        manual = f"pipx inject {venv} {quoted}"
        pipx = _find_tool("pipx")
        # run from home: a local ofscraper folder in the working directory confuses pipx
        return InstallPlan("pipx", [pipx, "inject", venv, DRIVER_REQUIREMENT] if pipx else None, manual, home)
    if method == "uv":
        uv = _find_tool("uv")
        return InstallPlan("uv", [uv] + uv_args if uv else None, uv_manual, home)
    manual = f'"{python}" -m pip install {quoted}'
    if _pip_available():
        return InstallPlan("pip", python_command() + ["-m", "pip", "install", DRIVER_REQUIREMENT], manual)
    uv = _find_tool("uv")
    if uv:
        return InstallPlan("pip", [uv] + uv_args, uv_manual)
    return InstallPlan("pip", None, manual)


def shown_command(command: list[str]) -> str:
    """A command as the tab shows it: the program's name rather than its
    full path, and quotes around arguments a shell would split or redirect."""
    if not command:
        return ""
    program = os.path.basename(command[0])
    if program.lower().startswith("python"):
        program = "python"
    elif program.lower().endswith(".exe"):
        program = program[:-4]
    shown = [program]
    for i, arg in enumerate(command[1:]):
        if program == "python" and i == 0 and arg == "-u":
            continue
        shown.append(f'"{arg}"' if any(c in arg for c in " []<>,;&|") else arg)
    return " ".join(shown)


def import_command(folder, apply=False, skip_bad=False, staging=None) -> list[str]:
    command = python_command() + ["-m", "ofscraper.commands.postgres_import", str(folder)]
    if apply:
        command.append("--apply")
    if skip_bad:
        command.append("--skip-bad-files")
    if staging:
        command += ["--staging", str(staging)]
    return command


def export_command(folder, apply=False, site=None) -> list[str]:
    command = python_command() + ["-m", "ofscraper.commands.postgres_export", str(folder)]
    if apply:
        command.append("--apply")
    if site:
        command += ["--site", site]
    return command


def command_environment(url: str | None) -> dict:
    """The environment for upstream's commands: this one, with the address
    to use (or none), outside the GUI's tab process."""
    try:
        from ofscraper.gui import site_context

        env = site_context.standalone_environment()
    except Exception:
        env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if url:
        env[URL_KEY] = url
    else:
        env.pop(URL_KEY, None)
    return env


def default_data_folder() -> str:
    """The active profile's .data folder: where the user_data.db files are
    unless the metadata setting moves them."""
    try:
        import ofscraper.utils.paths.common as common_paths

        return str(pathlib.Path(common_paths.get_profile_path()) / ".data")
    except Exception:
        return ""
