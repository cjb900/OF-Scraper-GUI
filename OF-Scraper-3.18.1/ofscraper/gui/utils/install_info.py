"""How this ofscraper was installed, and on which Python: for About, and for
installing extra packages the same way (Manage DBs > PostgreSQL > Install
driver). Only looks at this process's own Python and its folder."""

from __future__ import annotations

import os
import pathlib
import platform
import sys


def install_method() -> str:
    """How this ofscraper was installed: "pipx", "uv" (uv tool) or "pip".
    pipx and uv tool environments have no pip of their own."""
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


def standalone_build() -> bool:
    """The single-file download (.exe and the like): nothing is installed."""
    return bool(getattr(sys, "frozen", False))


def in_docker() -> bool:
    return os.path.exists("/.dockerenv")


def python_version() -> str:
    """This Python, e.g. "3.12.13 (64-bit)"."""
    bits = "64-bit" if sys.maxsize > 2**32 else "32-bit"
    name = platform.python_implementation()
    version = platform.python_version()
    return f"{version} ({bits})" if name == "CPython" else f"{name} {version} ({bits})"


def install_label() -> str:
    """What About shows under "Installed with"."""
    if standalone_build():
        return "Standalone download"
    method = install_method()
    if method == "pipx":
        label = "pipx"
    elif method == "uv":
        label = "uv (uv tool)"
    elif sys.prefix != sys.base_prefix:
        label = "pip (in a virtual environment)"
    else:
        label = "pip"
    if in_docker():
        label += ", Docker image"
    return label


def environment_path() -> str:
    """Where this ofscraper's Python environment is."""
    return str(pathlib.Path(sys.prefix))
