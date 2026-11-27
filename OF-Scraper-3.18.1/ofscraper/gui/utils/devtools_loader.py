"""The hook for the developer and testing tools (ofscraper/gui/devtools).

Only a testing install has them: the patch writes that package with
``--testing`` and removes it otherwise. A normal install has only this
module, which then does nothing.
"""

from __future__ import annotations

import importlib.util
import logging

log = logging.getLogger("shared")

PACKAGE = "ofscraper.gui.devtools"


def available() -> bool:
    """Whether this is a testing install (the devtools package is there)."""
    try:
        return importlib.util.find_spec(PACKAGE) is not None
    except Exception:
        return False


def install(window, nav_layout, style_button) -> None:
    """Add the developer tools to the main window, when installed."""
    if not available():
        return
    try:
        from ofscraper.gui import devtools

        devtools.install(window, nav_layout, style_button)
    except Exception as e:
        log.warning(f"[GUI] developer tools couldn't be loaded: {e}")


def patch_args() -> list[str]:
    """Extra patch arguments for Update now: a testing install stays one."""
    return ["--testing"] if available() else []
