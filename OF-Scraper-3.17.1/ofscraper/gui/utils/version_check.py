"""Check this GUI patch against the latest release of the GUI on GitHub.

Only the GUI's own releases count. A newer ofscraper on PyPI is not offered:
the GUI patch replaces files inside ofscraper, so an ofscraper version the
patch wasn't built and tested for can stop the GUI from starting. A release
on GitHub ships the patch script for the ofscraper version it supports, and
that script installs that version.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import logging
import re

log = logging.getLogger("shared")

GITHUB_REPO = "cjb900/OF-Scraper-GUI"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

# a patch id: 20261115_gui_3_17_1_v434 -> date 20261115, ofscraper 3.17.1, patch 434
_PATCH_ID_RE = re.compile(r"(\d{8})_gui_(\d+(?:_\d+)+)_v(\d+)")
# the patch script attached to a release: patch_ofscraper_3.17.1_gui.py
_PATCH_ASSET_RE = re.compile(r"patch_ofscraper_(\d+(?:\.\d+)+)_gui\.py$")

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


@dataclass(frozen=True)
class PatchInfo:
    patch: int | None  # the vNNN number
    date: str | None  # YYYYMMDD
    ofscraper: str | None  # the ofscraper version the patch is for

    @property
    def label(self) -> str:
        parts = []
        if self.patch is not None:
            parts.append(f"v{self.patch}")
        if self.ofscraper:
            parts.append(f"for OF-Scraper {self.ofscraper}")
        return " ".join(parts) or "unknown"


def parse_patch_id(text: str | None) -> PatchInfo:
    """The highest patch id in text, e.g. a PATCH_ID or a release's notes."""
    best = None
    for date, ver, num in _PATCH_ID_RE.findall(str(text or "")):
        if best is None or int(num) > best[2]:
            best = (date, ver.replace("_", "."), int(num))
    if best is None:
        return PatchInfo(None, None, None)
    return PatchInfo(best[2], best[0], best[1])


def installed_patch() -> PatchInfo:
    try:
        from ofscraper.gui.patch_version import PATCH_ID
    except Exception:
        return PatchInfo(None, None, None)
    return parse_patch_id(PATCH_ID)


def _version_key(text: str):
    try:
        from packaging.version import Version

        return Version(text)
    except Exception:
        return tuple(int(p) for p in re.findall(r"\d+", text))


def release_patch(release: dict) -> PatchInfo:
    """What a GitHub release ships: its patch number (from the patch id in
    its notes or title), its date, and the newest ofscraper version among
    its patch scripts."""
    found = parse_patch_id(
        " ".join(str(release.get(k) or "") for k in ("name", "body", "tag_name"))
    )
    versions = [
        m.group(1)
        for a in release.get("assets") or []
        if (m := _PATCH_ASSET_RE.search(str(a.get("name") or "")))
    ]
    ofscraper = max(versions, key=_version_key) if versions else found.ofscraper
    published = str(release.get("published_at") or "")[:10].replace("-", "")
    date = found.date or (published if len(published) == 8 else None)
    return PatchInfo(found.patch, date, ofscraper)


def fetch_latest_release(timeout: float = 8.0) -> dict | None:
    """The GUI's latest GitHub release (the API's JSON), or None."""
    try:
        import httpx

        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"Accept": "application/vnd.github+json"},
        ) as client:
            resp = client.get(LATEST_RELEASE_API)
            resp.raise_for_status()
            data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as e:
        log.debug(f"[GUI] GitHub release check failed: {e}")
        return None


def _is_newer(latest: PatchInfo, current: PatchInfo) -> bool | None:
    # patch numbers run across every ofscraper version (a 3.14.7 fix can get
    # a higher number than the 3.17.1 GUI), so the ofscraper version decides
    # first: a release for a newer one is an update, one for an older isn't
    if latest.ofscraper and current.ofscraper:
        try:
            lk, ck = _version_key(latest.ofscraper), _version_key(current.ofscraper)
            if lk != ck:
                return lk > ck
        except TypeError:
            pass
    if latest.patch is not None and current.patch is not None:
        return latest.patch > current.patch
    # notes without a patch id: a release published after this patch was built
    if latest.date and current.date:
        return latest.date > current.date
    return None


def check_for_updates(
    current: PatchInfo | None = None,
    *,
    timeout: float = 8.0,
) -> VersionCheckResult:
    """Compare this patch to the GUI's latest GitHub release (network call;
    run off the UI thread)."""
    cur = current or installed_patch()
    if cur.patch is None and cur.date is None:
        return VersionCheckResult(
            status="unknown",
            current=cur.label,
            project_url=RELEASES_URL,
            message="Update check unavailable: the GUI patch version isn't known.",
        )

    release = fetch_latest_release(timeout=timeout)
    if not release:
        return VersionCheckResult(
            status="error",
            current=cur.label,
            project_url=RELEASES_URL,
            message="Could not reach GitHub to check for GUI updates.",
        )

    latest = release_patch(release)
    url = str(release.get("html_url") or "") or RELEASES_URL
    # what a dismissal remembers: the release itself
    latest_key = str(release.get("tag_name") or "") or latest.label
    newer = _is_newer(latest, cur)
    if newer:
        return VersionCheckResult(
            status="update_available",
            current=cur.label,
            latest=latest_key,
            project_url=url,
            message=(
                f"A new GUI release is available: patch {latest.label} "
                f"(you have {cur.label})."
            ),
        )
    if newer is None:
        return VersionCheckResult(
            status="unknown",
            current=cur.label,
            latest=latest_key,
            project_url=url,
            message=f"Couldn't compare with the latest GUI release (you have {cur.label}).",
        )
    return VersionCheckResult(
        status="up_to_date",
        current=cur.label,
        latest=latest_key,
        project_url=url,
        message=f"The GUI is up to date (patch {cur.label}).",
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
    """Remember that the user dismissed prompts for this GUI release."""
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
