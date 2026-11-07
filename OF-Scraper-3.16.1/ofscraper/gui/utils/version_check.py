"""Check installed OF-Scraper version against the latest on PyPI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import logging
import re

log = logging.getLogger("shared")

PYPI_JSON_URL = "https://pypi.org/pypi/ofscraper/json"
DEFAULT_PROJECT_URL = "https://pypi.org/project/ofscraper/"

UpdateKind = Literal[
    "up_to_date",
    "update_available",
    "dev",
    "unknown",
    "error",
]


@dataclass(frozen=True)
class VersionCheckResult:
    status: UpdateKind
    current: str
    latest: str | None = None
    project_url: str | None = None
    message: str = ""


def _current_version() -> str:
    try:
        from ofscraper.__version__ import __version__

        return str(__version__ or "0.0.0")
    except Exception:
        return "0.0.0"


def _parse_version(text: str):
    """Return a comparable Version if packaging is available, else None."""
    try:
        from packaging.version import Version

        return Version(str(text).strip())
    except Exception:
        return None


def _is_newer(latest: str, current: str) -> bool | None:
    """True if latest > current. None if comparison is inconclusive."""
    lv = _parse_version(latest)
    cv = _parse_version(current)
    if lv is not None and cv is not None:
        try:
            return lv > cv
        except Exception:
            pass
    # Fallback: treat exact / substring match like the CLI helper.
    if latest == current or re.search(re.escape(latest), current):
        return False
    return None


def fetch_pypi_latest(timeout: float = 8.0) -> tuple[str | None, str | None]:
    """Return ``(latest_version, project_url)`` from PyPI, or ``(None, None)``."""
    try:
        import httpx

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(PYPI_JSON_URL)
            resp.raise_for_status()
            data = resp.json() or {}
        info = data.get("info") or {}
        latest = str(info.get("version") or "").strip() or None
        url = str(info.get("project_url") or "").strip() or DEFAULT_PROJECT_URL
        return latest, url
    except Exception as e:
        log.debug(f"[GUI] PyPI version check failed: {e}")
        return None, None


def check_for_updates(
    current: str | None = None,
    *,
    timeout: float = 8.0,
) -> VersionCheckResult:
    """Compare the installed version to PyPI (network call; run off the UI thread)."""
    cur = (current or _current_version()).strip() or "0.0.0"

    if cur == "0.0.0":
        return VersionCheckResult(
            status="unknown",
            current=cur,
            message="Version check unavailable (local / unpackaged install).",
        )

    if ".dev" in cur.lower():
        return VersionCheckResult(
            status="dev",
            current=cur,
            message="Development build — treated as up to date.",
        )

    latest, url = fetch_pypi_latest(timeout=timeout)
    if not latest:
        return VersionCheckResult(
            status="error",
            current=cur,
            project_url=DEFAULT_PROJECT_URL,
            message="Could not reach PyPI to check for updates.",
        )

    newer = _is_newer(latest, cur)
    if newer is True:
        return VersionCheckResult(
            status="update_available",
            current=cur,
            latest=latest,
            project_url=url or DEFAULT_PROJECT_URL,
            message=f"Update available: {latest} (you have {cur}).",
        )
    if newer is False:
        return VersionCheckResult(
            status="up_to_date",
            current=cur,
            latest=latest,
            project_url=url or DEFAULT_PROJECT_URL,
            message=f"Up to date ({cur}).",
        )

    # Inconclusive compare but versions differ — surface as available if unequal.
    if latest != cur:
        return VersionCheckResult(
            status="update_available",
            current=cur,
            latest=latest,
            project_url=url or DEFAULT_PROJECT_URL,
            message=f"Newer version reported on PyPI: {latest} (you have {cur}).",
        )
    return VersionCheckResult(
        status="up_to_date",
        current=cur,
        latest=latest,
        project_url=url or DEFAULT_PROJECT_URL,
        message=f"Up to date ({cur}).",
    )


def should_prompt_startup(result: VersionCheckResult) -> bool:
    """Whether to show a one-shot startup prompt for this result."""
    if result.status != "update_available" or not result.latest:
        return False
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        dismissed = str(load_gui_settings().get("dismissed_update_version") or "")
        return dismissed != result.latest
    except Exception:
        return True


def dismiss_update_version(version: str) -> None:
    """Remember that the user dismissed prompts for this PyPI version."""
    ver = str(version or "").strip()
    if not ver:
        return
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

        settings = load_gui_settings()
        settings["dismissed_update_version"] = ver
        save_gui_settings(settings)
    except Exception as e:
        log.debug(f"[GUI] Could not save dismissed update version: {e}")
