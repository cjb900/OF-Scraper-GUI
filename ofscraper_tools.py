#!/usr/bin/env python
"""
ofscraper_tools.py — Maintenance and removal tool for ofscraper and the GUI patch.

Uninstall options:
  1. Just uninstall ofscraper (pipx / uv / pip uninstall)
  2. Just remove the GUI patch (reinstall stock ofscraper from PyPI)
  3. Remove ofscraper + all config files (~/.config/ofscraper/)
  4. Purge everything (ofscraper + config + downloaded content)

Data management options:
  5. Delete model DB(s) only  (~/.config/ofscraper/<profile>/.data/)
  6. Delete downloaded content only  (path read from config.json)
  7. Delete SQL cache only  (~/.config/ofscraper/<profile>/cache_sql/)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Installation detection
# ---------------------------------------------------------------------------

def _get_pipx_home() -> Path | None:
    env = os.environ.get("PIPX_HOME")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    home = Path.home()
    is_win = platform.system() == "Windows"

    if is_win:
        candidates = [
            home / "pipx",
            home / "AppData" / "Local" / "pipx",
            home / ".local" / "pipx",
        ]
    else:
        candidates = [
            home / ".local" / "share" / "pipx",
            home / ".local" / "pipx",
        ]

    for c in candidates:
        if c.is_dir():
            return c
    return None


def _find_pipx_ofscraper_pkg() -> Path | None:
    candidates = []

    pipx_home = _get_pipx_home()
    if pipx_home:
        candidates.extend([
            pipx_home / "venvs" / "ofscraper",
            pipx_home / "pipx" / "venvs" / "ofscraper",
        ])

    for venv_dir in candidates:
        if not venv_dir.is_dir():
            continue
        matches = list(venv_dir.glob("**/site-packages/ofscraper/__main__.py"))
        if matches:
            return matches[0].parent
        matches = list(venv_dir.glob("**/Lib/site-packages/ofscraper/__main__.py"))
        if matches:
            return matches[0].parent
    return None


def _get_uv_tool_dir() -> Path | None:
    env = os.environ.get("UV_TOOL_DIR")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    home = Path.home()
    is_win = platform.system() == "Windows"

    if is_win:
        appdata = os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))
        candidates = [
            Path(appdata) / "uv" / "data" / "tools",
            Path(appdata) / "uv" / "tools",
        ]
    else:
        xdg = os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share"))
        candidates = [
            Path(xdg) / "uv" / "tools",
        ]

    for c in candidates:
        if c.is_dir():
            return c
    return None


def _find_uv_ofscraper_pkg() -> Path | None:
    uv_dir = _get_uv_tool_dir()
    if not uv_dir:
        return None
    venv_dir = uv_dir / "ofscraper"
    if not venv_dir.is_dir():
        return None
    matches = list(venv_dir.glob("**/site-packages/ofscraper/__main__.py"))
    if matches:
        return matches[0].parent
    return None


def _detect_install_method() -> str:
    if _find_uv_ofscraper_pkg():
        return "uv"
    if _find_pipx_ofscraper_pkg():
        return "pipx"
    exe = shutil.which("ofscraper")
    if exe:
        exe_lower = str(exe).lower()
        if "uv" in exe_lower and "tools" in exe_lower:
            return "uv"
        if "pipx" in exe_lower:
            return "pipx"
    try:
        import importlib.metadata as _meta
        _meta.version("ofscraper")
        import ofscraper  # type: ignore
        if getattr(ofscraper, "__path__", None):
            return "pip"
    except Exception:
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Config / path helpers
# ---------------------------------------------------------------------------

def _config_dir() -> Path:
    return Path.home() / ".config" / "ofscraper"


def _read_save_location() -> str | None:
    config_path = _config_dir() / "config.json"
    if not config_path.is_file():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("file_options", {}).get("save_location")
    except Exception:
        return None


def _find_profiles() -> list[Path]:
    """Return all profile directories under the config dir."""
    cfg = _config_dir()
    if not cfg.is_dir():
        return []
    profiles = []
    for item in sorted(cfg.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            # A profile dir has at least one of these markers
            if (
                (item / "auth.json").exists()
                or (item / ".data").is_dir()
                or (item / "cache_sql").is_dir()
            ):
                profiles.append(item)
    return profiles


def _find_model_db_dirs() -> list[Path]:
    """Return all .data directories (model databases) across every profile."""
    result = []
    for profile in _find_profiles():
        data_dir = profile / ".data"
        if data_dir.is_dir():
            result.append(data_dir)
    return result


def _read_username_from_db(model_dir: Path) -> str | None:
    """Query user_data.db for the username stored in the profiles table."""
    db_path = model_dir / "user_data.db"
    if not db_path.is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.execute("SELECT username FROM profiles LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            con.close()
    except Exception:
        return None


def _enumerate_model_dbs() -> list[dict]:
    """
    Return a list of dicts, one per individual model DB folder found across
    all profiles.  Each dict has:
        profile   : Path  — the profile directory
        dir       : Path  — the per-model folder  (<profile>/.data/<id>/)
        model_id  : str   — the numeric folder name
        username  : str   — username from profiles table, or the id if unreadable
    """
    entries = []
    for profile in _find_profiles():
        data_dir = profile / ".data"
        if not data_dir.is_dir():
            continue
        for model_dir in sorted(data_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            username = _read_username_from_db(model_dir) or model_dir.name
            entries.append({
                "profile": profile,
                "dir": model_dir,
                "model_id": model_dir.name,
                "username": username,
            })
    return entries


def _find_cache_dirs() -> list[Path]:
    """Return all cache_sql directories across every profile."""
    result = []
    for profile in _find_profiles():
        cache_dir = profile / "cache_sql"
        if cache_dir.is_dir():
            result.append(cache_dir)
    return result


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> int:
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def _uninstall_ofscraper(method: str) -> bool:
    """Uninstall ofscraper using the detected package manager. Returns True on success."""
    if method == "pipx":
        rc = _run(["pipx", "uninstall", "ofscraper"])
        return rc == 0
    elif method == "uv":
        rc = _run(["uv", "tool", "uninstall", "ofscraper"])
        return rc == 0
    elif method == "pip":
        rc = _run([sys.executable, "-m", "pip", "uninstall", "-y", "ofscraper"])
        return rc == 0
    else:
        print("  [!] Could not detect install method. Trying pipx, then uv, then pip...")
        for cmd in [
            ["pipx", "uninstall", "ofscraper"],
            ["uv", "tool", "uninstall", "ofscraper"],
            [sys.executable, "-m", "pip", "uninstall", "-y", "ofscraper"],
        ]:
            try:
                if _run(cmd) == 0:
                    return True
            except FileNotFoundError:
                pass
        return False


def _reinstall_stock(method: str) -> bool:
    """Reinstall stock ofscraper (no GUI patch) from PyPI."""
    print("\n  Reinstalling stock ofscraper from PyPI...")
    if method == "pipx":
        rc = _run(["pipx", "install", "ofscraper"])
        return rc == 0
    elif method == "uv":
        rc = _run(["uv", "tool", "install", "ofscraper"])
        return rc == 0
    elif method == "pip":
        rc = _run([sys.executable, "-m", "pip", "install", "ofscraper"])
        return rc == 0
    else:
        print("  [!] Could not determine install method — skipping reinstall.")
        print("      Manually run: pipx install ofscraper  (or uv tool install ofscraper)")
        return False


def _remove_config() -> None:
    cfg = _config_dir()
    if cfg.is_dir():
        print(f"  Removing config directory: {cfg}")
        shutil.rmtree(cfg)
        print("  Config directory removed.")
    else:
        print(f"  Config directory not found (already removed?): {cfg}")


def _remove_downloads(save_location: str) -> None:
    dl_path = Path(save_location)
    if dl_path.is_dir():
        print(f"  Removing downloaded content: {dl_path}")
        shutil.rmtree(dl_path)
        print("  Downloaded content removed.")
    else:
        print(f"  Download path not found (already removed?): {dl_path}")


def _remove_model_dbs() -> None:
    """Delete all .data directories (model databases) across all profiles."""
    dirs = _find_model_db_dirs()
    if not dirs:
        print("  No model DB directories found.")
        return
    for d in dirs:
        print(f"  Removing model DB folder: {d}")
        shutil.rmtree(d)
        print("  Removed.")


def _remove_caches() -> None:
    """Delete all cache_sql directories across all profiles."""
    dirs = _find_cache_dirs()
    if not dirs:
        print("  No SQL cache directories found.")
        return
    for d in dirs:
        print(f"  Removing SQL cache: {d}")
        shutil.rmtree(d)
        print("  Removed.")


def _confirm(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------

def _print_header() -> None:
    print()
    print("=" * 60)
    print("  OF-Scraper Tools")
    print("=" * 60)


def _print_menu(method: str, save_location: str | None) -> None:
    cache_dirs = _find_cache_dirs()
    model_entries = _enumerate_model_dbs()

    print(f"\n  Detected install method : {method}")
    print(f"  Config directory        : {_config_dir()}")
    print(f"  Download save location  : {save_location or '(not found in config.json)'}")
    if model_entries:
        print(f"  Model DBs found         : {len(model_entries)} model(s) across all profiles")
    else:
        print(f"  Model DBs found         : (none found)")
    if cache_dirs:
        print(f"  SQL cache folder(s)     : {', '.join(str(d) for d in cache_dirs)}")
    else:
        print(f"  SQL cache folder(s)     : (none found)")
    print()
    print("  --- Uninstall ---\n")
    print("  1. Just uninstall ofscraper")
    print("     (removes the ofscraper package; config and downloads are kept)")
    print()
    print("  2. Just remove the GUI patch")
    print("     (uninstalls patched ofscraper and reinstalls stock from PyPI)")
    print()
    print("  3. Remove ofscraper + all config files")
    print(f"     (uninstalls ofscraper and deletes {_config_dir()})")
    print()
    print("  4. Purge everything")
    print("     (uninstalls ofscraper, deletes config, AND deletes downloaded content)")
    if save_location:
        print(f"     Download path: {save_location}")
    print()
    print("  --- Data management (ofscraper stays installed) ---\n")
    print("  5. Delete model DB(s) only")
    print("     (select individual models — resets downloaded/unlocked history)")
    if model_entries:
        print(f"     {len(model_entries)} model DB(s) found across all profiles")
    print()
    print("  6. Delete downloaded content only")
    if save_location:
        dl_root_check = Path(save_location)
        if dl_root_check.is_dir():
            mf_count = sum(1 for d in dl_root_check.iterdir() if d.is_dir())
            print(f"     (select individual model folders — {mf_count} found in {save_location})")
        else:
            print(f"     ({save_location})")
    else:
        print("     (path will be read from config.json or prompted)")
    print()
    print("  7. Delete SQL cache only")
    print("     (deletes cache_sql/ folders — clears the ofscraper API response cache)")
    if cache_dirs:
        for d in cache_dirs:
            print(f"     {d}")
    print()
    print("  0. Exit / cancel")
    print()


def _prompt_continue() -> bool:
    """Ask whether to return to the menu or exit. Returns True to continue."""
    print()
    while True:
        ans = input("  Perform another action? [Y/n]: ").strip().lower()
        if ans in ("", "y", "yes"):
            return True
        if ans in ("n", "no"):
            return False


def main() -> None:
    _print_header()

    while True:
        method = _detect_install_method()
        save_location = _read_save_location()

        _print_menu(method, save_location)

        choice = input("  Enter choice [0-7]: ").strip()

        if choice == "0":
            print("\n  Cancelled. Nothing was changed.\n")
            return

        _run_action(choice, method, save_location)

        if not _prompt_continue():
            print("\n  Goodbye.\n")
            return


def _run_action(choice: str, method: str, save_location: str | None) -> None:
    if False:
        pass  # anchor for the elif chain below

    elif choice == "1":
        print("\n--- Option 1: Uninstall ofscraper only ---")
        if not _confirm("  This will uninstall the ofscraper package. Continue?"):
            print("  Cancelled.")
            return
        ok = _uninstall_ofscraper(method)
        if ok:
            print("\n  ofscraper uninstalled successfully.")
        else:
            print("\n  [!] Uninstall may have failed — check output above.")

    elif choice == "2":
        print("\n--- Option 2: Remove GUI patch (reinstall stock ofscraper) ---")
        print("  This will uninstall the patched ofscraper and reinstall the")
        print("  unmodified version from PyPI. Your config files are kept.")
        if not _confirm("  Continue?"):
            print("  Cancelled.")
            return
        print("\n  Step 1: Uninstalling current ofscraper...")
        _uninstall_ofscraper(method)
        _reinstall_stock(method)
        print("\n  Done. Stock ofscraper is now installed (no GUI patch).")

    elif choice == "3":
        print("\n--- Option 3: Remove ofscraper + config files ---")
        print(f"  This will uninstall ofscraper AND delete: {_config_dir()}")
        print("  Your downloaded content will NOT be touched.")
        if not _confirm("  Continue?"):
            print("  Cancelled.")
            return
        print("\n  Step 1: Uninstalling ofscraper...")
        _uninstall_ofscraper(method)
        print("\n  Step 2: Removing config directory...")
        _remove_config()
        print("\n  Done.")

    elif choice == "4":
        print("\n--- Option 4: Purge everything ---")
        if not save_location:
            print("  [!] Could not read save_location from config.json.")
            print(f"      Config dir: {_config_dir()}")
            manual = input("  Enter the full path to your downloads folder (or press Enter to skip): ").strip()
            if manual:
                save_location = manual
            else:
                print("  Skipping download removal (no path provided).")

        print(f"\n  This will permanently delete:")
        print(f"    - ofscraper package (method: {method})")
        print(f"    - Config directory: {_config_dir()}")
        if save_location:
            print(f"    - Downloaded content: {save_location}")
        print()
        print("  THIS CANNOT BE UNDONE.")
        if not _confirm("  Are you absolutely sure?"):
            print("  Cancelled.")
            return
        if not _confirm("  Final confirmation — delete everything?"):
            print("  Cancelled.")
            return

        print("\n  Step 1: Uninstalling ofscraper...")
        _uninstall_ofscraper(method)

        print("\n  Step 2: Removing config directory...")
        _remove_config()

        if save_location:
            print("\n  Step 3: Removing downloaded content...")
            _remove_downloads(save_location)

        print("\n  Purge complete. Everything has been removed.")

    elif choice == "5":
        print("\n--- Option 5: Delete model DB(s) only ---")
        entries = _enumerate_model_dbs()
        if not entries:
            print("  No model DB directories found. Nothing to do.")
            return

        print()
        print("  Available model databases:\n")
        for i, e in enumerate(entries, 1):
            print(f"  {i:>3}.  {e['username']:<30}  (ID: {e['model_id']})")
            print(f"        {e['dir']}")
        print()
        print("  Enter the number(s) to delete, comma-separated  (e.g. 1,3,5)")
        print("  or type 'all' to delete every model DB listed above.")
        print("  Press Enter without typing anything to cancel.")
        raw = input("\n  Selection: ").strip()

        if not raw:
            print("  Cancelled.")
            return

        if raw.lower() == "all":
            selected = entries
        else:
            selected = []
            for part in raw.split(","):
                part = part.strip()
                if not part.isdigit():
                    print(f"  [!] '{part}' is not a valid number — cancelled.")
                    return
                idx = int(part) - 1
                if idx < 0 or idx >= len(entries):
                    print(f"  [!] Number {part} is out of range — cancelled.")
                    return
                selected.append(entries[idx])
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for e in selected:
                key = str(e["dir"])
                if key not in seen:
                    seen.add(key)
                    deduped.append(e)
            selected = deduped

        print()
        print("  The following model DB folder(s) will be permanently deleted:\n")
        for e in selected:
            print(f"    {e['username']} (ID: {e['model_id']})")
            print(f"      {e['dir']}")
        print()
        print("  This resets downloaded/unlocked history for the selected model(s).")
        print("  ofscraper will treat their content as new on the next run.")
        print("  Your downloaded files and config are NOT affected.")
        if not _confirm("\n  Continue?"):
            print("  Cancelled.")
            return

        for e in selected:
            print(f"  Removing: {e['dir']}")
            shutil.rmtree(e["dir"])
            print(f"  Removed {e['username']} (ID: {e['model_id']})")
        print(f"\n  Done. Deleted {len(selected)} model DB(s).")

    elif choice == "6":
        print("\n--- Option 6: Delete downloaded content only ---")
        if not save_location:
            print("  [!] Could not read save_location from config.json.")
            manual = input("  Enter the full path to your downloads folder (or press Enter to cancel): ").strip()
            if not manual:
                print("  Cancelled.")
                return
            save_location = manual

        dl_root = Path(save_location)
        if not dl_root.is_dir():
            print(f"  [!] Download folder not found: {dl_root}")
            return

        # List immediate subdirectories — each one is a model's download folder
        model_folders = sorted(
            [d for d in dl_root.iterdir() if d.is_dir()],
            key=lambda d: d.name.lower(),
        )

        if not model_folders:
            print(f"  No model folders found inside: {dl_root}")
            return

        print()
        print(f"  Download root: {dl_root}")
        print()
        print("  Available model download folders:\n")
        for i, d in enumerate(model_folders, 1):
            try:
                size_bytes = sum(
                    f.stat().st_size for f in d.rglob("*") if f.is_file()
                )
                size_str = (
                    f"{size_bytes / 1_073_741_824:.2f} GB"
                    if size_bytes >= 1_073_741_824
                    else f"{size_bytes / 1_048_576:.1f} MB"
                )
            except Exception:
                size_str = "unknown size"
            print(f"  {i:>3}.  {d.name:<30}  ({size_str})")
        print()
        print("  Enter the number(s) to delete, comma-separated  (e.g. 1,3,5)")
        print("  or type 'all' to delete every model folder listed above.")
        print("  Press Enter without typing anything to cancel.")
        raw = input("\n  Selection: ").strip()

        if not raw:
            print("  Cancelled.")
            return

        if raw.lower() == "all":
            selected_folders = model_folders
        else:
            selected_folders = []
            for part in raw.split(","):
                part = part.strip()
                if not part.isdigit():
                    print(f"  [!] '{part}' is not a valid number — cancelled.")
                    return
                idx = int(part) - 1
                if idx < 0 or idx >= len(model_folders):
                    print(f"  [!] Number {part} is out of range — cancelled.")
                    return
                selected_folders.append(model_folders[idx])
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for d in selected_folders:
                if str(d) not in seen:
                    seen.add(str(d))
                    deduped.append(d)
            selected_folders = deduped

        print()
        print("  The following download folder(s) will be permanently deleted:\n")
        for d in selected_folders:
            print(f"    {d}")
        print()
        print("  ofscraper config and model DBs are NOT affected.")
        print("  THIS CANNOT BE UNDONE.")
        if not _confirm("  Are you absolutely sure?"):
            print("  Cancelled.")
            return
        if not _confirm("  Final confirmation — delete selected download folder(s)?"):
            print("  Cancelled.")
            return

        for d in selected_folders:
            print(f"  Removing: {d}")
            shutil.rmtree(d)
            print(f"  Removed {d.name}")
        print(f"\n  Done. Deleted {len(selected_folders)} download folder(s).")

    elif choice == "7":
        print("\n--- Option 7: Delete SQL cache only ---")
        dirs = _find_cache_dirs()
        if not dirs:
            print("  No SQL cache directories found. Nothing to do.")
            return
        print("  This will delete the following SQL cache folder(s):")
        for d in dirs:
            print(f"    {d}")
        print()
        print("  The cache holds API responses to speed up repeated runs.")
        print("  Deleting it forces ofscraper to re-fetch from the API on the next run.")
        print("  Your config, model DBs, and downloaded files are NOT affected.")
        if not _confirm("  Continue?"):
            print("  Cancelled.")
            return
        _remove_caches()
        print("\n  SQL cache deleted.")

    else:
        print(f"\n  Invalid choice: '{choice}'. Nothing was changed.")

    print()


if __name__ == "__main__":
    main()
