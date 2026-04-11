#!/usr/bin/env python
"""
uninstall_ofscraper.py — Removal tool for ofscraper and the GUI patch.

Options:
  1. Just uninstall ofscraper (pipx / uv / pip uninstall)
  2. Just remove the GUI patch (reinstall stock ofscraper from PyPI)
  3. Remove ofscraper + all config files (~/.config/ofscraper/)
  4. Purge everything (ofscraper + config + downloaded content)
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Installation detection (mirrors patch_ofscraper_3.14.5_gui.py)
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
# Config / download path helpers
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
    print("  ofscraper Removal Tool")
    print("=" * 60)


def _print_menu(method: str, save_location: str | None) -> None:
    print(f"\n  Detected install method : {method}")
    print(f"  Config directory        : {_config_dir()}")
    print(f"  Download save location  : {save_location or '(not found in config.json)'}")
    print()
    print("  What would you like to remove?\n")
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
    print("  0. Exit / cancel")
    print()


def main() -> None:
    _print_header()

    method = _detect_install_method()
    save_location = _read_save_location()

    _print_menu(method, save_location)

    choice = input("  Enter choice [0-4]: ").strip()

    if choice == "0":
        print("\n  Cancelled. Nothing was changed.\n")
        return

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

    else:
        print(f"\n  Invalid choice: '{choice}'. Nothing was changed.\n")
        return

    print()


if __name__ == "__main__":
    main()
