"""Pre-scrape / pre-download free-disk warning for the GUI.

Compares free space on the Save Location volume against a rough size
estimate (and a fixed low-space floor) so users can cancel before a
large job fills the drive.
"""
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QMessageBox, QWidget

log = logging.getLogger("shared")

# Always warn when free space is below this (download-writing jobs).
WARN_FREE_BYTES = 2 * 1024**3  # 2 GiB
# Stronger warning; still shown even if "don't ask again" is set.
CRITICAL_FREE_BYTES = 256 * 1024**2  # 256 MiB
# Require free >= estimate * headroom when we have an estimate.
HEADROOM = 1.25

# Rough per-item cart estimates when row sizes are unknown.
EST_VIDEO_BYTES = 80 * 1024**2
EST_IMAGE_BYTES = 3 * 1024**2
EST_AUDIO_BYTES = 8 * 1024**2
EST_OTHER_BYTES = 10 * 1024**2

# Rough scrape download estimates (unknown catalog size).
EST_SCRAPE_PER_MODEL = 400 * 1024**2  # 400 MiB / model baseline
EST_SCRAPE_PER_AREA_VIDEO = 150 * 1024**2
EST_SCRAPE_PER_AREA_IMAGE = 25 * 1024**2
EST_SCRAPE_MANUAL_URL = 40 * 1024**2

_session_skip = False
# One-shot: table/page already confirmed; workflow must not re-prompt.
_disk_check_ack = False


@dataclass
class DiskSpaceReport:
    save_location: str
    free_bytes: int
    total_bytes: int
    estimated_bytes: int
    reason: str  # "critical" | "low" | "estimate" | ""

    @property
    def ok(self) -> bool:
        return not self.reason


def reset_session_skip() -> None:
    global _session_skip, _disk_check_ack
    _session_skip = False
    _disk_check_ack = False


def _privacy_path(path: str) -> str:
    try:
        from ofscraper.gui.utils.privacy_mode import is_privacy_mode

        if is_privacy_mode():
            return "[Hidden for Privacy]"
    except Exception:
        pass
    return path


def format_bytes(n: int) -> str:
    n = max(0, int(n))
    for unit, div in (("GiB", 1024**3), ("MiB", 1024**2), ("KiB", 1024)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n} B"


def get_save_location_path() -> Path:
    try:
        import ofscraper.utils.paths.common as common_paths

        return Path(common_paths.get_save_location()).expanduser()
    except Exception:
        return Path.home()


def _existing_volume_path(path: Path) -> Path:
    """Walk up to an existing path so shutil.disk_usage works on Windows."""
    p = path
    try:
        p = p.resolve()
    except Exception:
        pass
    seen = set()
    while True:
        key = str(p)
        if key in seen:
            break
        seen.add(key)
        try:
            if p.exists():
                return p
        except Exception:
            pass
        parent = p.parent
        if parent == p:
            break
        p = parent
    # Fall back to drive root / path as-is.
    try:
        anchor = Path(path.anchor) if path.anchor else path
        if anchor.exists():
            return anchor
    except Exception:
        pass
    return path


def probe_free_space(save_path: Path | None = None) -> tuple[Path, int, int]:
    """Return (resolved_path, free_bytes, total_bytes). Raises on failure."""
    root = save_path or get_save_location_path()
    probe = _existing_volume_path(Path(root))
    usage = shutil.disk_usage(str(probe))
    return probe, int(usage.free), int(usage.total)


def _actions_write_media(actions: list[str], *, check_mode: bool) -> bool:
    """True when this job is likely to write downloaded media to disk."""
    if check_mode:
        # Check modes only populate the table; downloads go through Send Downloads.
        return False
    acts = {str(a).strip().lower() for a in (actions or []) if str(a).strip()}
    if not acts:
        return True  # default scrape action is download
    if acts <= {"like", "unlike"}:
        return False
    if acts & {"download", "scrape"}:
        return True
    # Unknown / mixed — be conservative if not like-only.
    return "like" not in acts or "download" in acts or len(acts - {"like", "unlike"}) > 0


def estimate_scrape_bytes(summary) -> int:
    """Rough bytes a download scrape might need (order-of-magnitude only)."""
    if not _actions_write_media(
        getattr(summary, "actions", None) or [],
        check_mode=bool(getattr(summary, "check_mode", False)),
    ):
        return 0

    models = max(int(getattr(summary, "model_count", 0) or 0), 0)
    manual = max(int(getattr(summary, "manual_url_count", 0) or 0), 0)
    if models == 0 and manual == 0:
        models = 1

    areas = max(int(getattr(summary, "area_count", 0) or 0), 1)
    mediatypes = [str(m).lower() for m in (getattr(summary, "mediatypes", None) or [])]
    if not mediatypes:
        # Unknown → assume both images and videos.
        has_video = True
        has_image = True
    else:
        has_video = any("video" in m for m in mediatypes)
        has_image = any(
            any(x in m for x in ("image", "photo", "gif", "audio")) for m in mediatypes
        ) or not has_video

    per_model = EST_SCRAPE_PER_MODEL
    if has_video:
        per_model += EST_SCRAPE_PER_AREA_VIDEO * areas
    if has_image:
        per_model += EST_SCRAPE_PER_AREA_IMAGE * areas

    total = per_model * max(models, 1)
    if manual:
        total += EST_SCRAPE_MANUAL_URL * manual
    if getattr(summary, "rescrape_all", False) or getattr(summary, "allow_dupes", False):
        total = int(total * 1.5)
    if getattr(summary, "scrape_paid", False):
        total = int(total * 1.25)
    if getattr(summary, "daemon_enabled", False):
        # Daemon reuses the same disk; don't multiply interval — small bump only.
        total = int(total * 1.1)
    return max(total, WARN_FREE_BYTES // 4)


def estimate_cart_bytes(rows: list[dict] | None, summary=None) -> int:
    """Estimate bytes for a download cart from row sizes or mediatype counts."""
    total = 0
    counted = 0
    if rows:
        for rd in rows:
            size = None
            for key in ("size", "Size", "filesize", "file_size", "length"):
                if key in rd and rd[key] is not None:
                    try:
                        size = float(rd[key])
                        break
                    except (TypeError, ValueError):
                        pass
            if size is not None and size > 0:
                # Values under 512 are almost certainly MiB labels, not raw bytes.
                if size < 512:
                    size = size * 1024**2
                total += int(size)
                counted += 1
                continue
            mt = str(
                rd.get("mediatype")
                or rd.get("Mediatype")
                or rd.get("media_type")
                or ""
            ).lower()
            if "video" in mt:
                total += EST_VIDEO_BYTES
            elif "audio" in mt:
                total += EST_AUDIO_BYTES
            elif any(x in mt for x in ("image", "photo", "gif")):
                total += EST_IMAGE_BYTES
            else:
                total += EST_OTHER_BYTES
            counted += 1
        if counted:
            return total

    if summary is not None:
        by_type = getattr(summary, "by_mediatype", None) or {}
        for key, count in by_type.items():
            mt = str(key).lower()
            n = int(count)
            if "video" in mt:
                total += EST_VIDEO_BYTES * n
            elif "audio" in mt:
                total += EST_AUDIO_BYTES * n
            elif any(x in mt for x in ("image", "photo", "gif")):
                total += EST_IMAGE_BYTES * n
            else:
                total += EST_OTHER_BYTES * n
        if total:
            return total
        n = int(getattr(summary, "total", 0) or 0)
        if n:
            return EST_OTHER_BYTES * n
    return 0


def build_report(
    *,
    estimated_bytes: int = 0,
    require_media_write: bool = True,
) -> DiskSpaceReport | None:
    """Probe disk and decide if a warning is warranted. None = skip (probe failed)."""
    try:
        save = get_save_location_path()
        probe, free, total = probe_free_space(save)
    except Exception as e:
        log.debug(f"[GUI] Disk space probe failed: {e}")
        return None

    display_path = str(save)
    estimated = max(0, int(estimated_bytes or 0))
    reason = ""

    if free < CRITICAL_FREE_BYTES:
        reason = "critical"
    elif require_media_write and estimated > 0 and free < int(estimated * HEADROOM):
        reason = "estimate"
    elif require_media_write and free < WARN_FREE_BYTES:
        reason = "low"

    return DiskSpaceReport(
        save_location=display_path,
        free_bytes=free,
        total_bytes=total,
        estimated_bytes=estimated,
        reason=reason,
    )


def should_prompt(report: DiskSpaceReport | None) -> bool:
    global _session_skip, _disk_check_ack
    if report is None or report.ok:
        return False
    if _disk_check_ack:
        return False
    if report.reason == "critical":
        return True
    try:
        from ofscraper.gui.utils.gui_settings import load_gui_settings

        if bool(load_gui_settings().get("skip_disk_space_check")):
            return False
    except Exception:
        pass
    if _session_skip:
        return False
    return True


def format_report_html(report: DiskSpaceReport) -> str:
    path_txt = _privacy_path(report.save_location)
    lines = [
        f"<p><b>Save location:</b> {path_txt}<br/>"
        f"<b>Free space:</b> {format_bytes(report.free_bytes)} "
        f"(of {format_bytes(report.total_bytes)})</p>"
    ]
    if report.estimated_bytes > 0:
        lines.append(
            f"<p><b>Rough space needed:</b> ~{format_bytes(report.estimated_bytes)} "
            f"(estimate only; includes ~{int((HEADROOM - 1) * 100)}% headroom check)</p>"
        )
    if report.reason == "critical":
        lines.append(
            "<p><b style='color:#f38ba8'>Free space is critically low.</b> "
            "Downloads may fail or corrupt mid-write.</p>"
        )
    elif report.reason == "estimate":
        lines.append(
            "<p>Free space may not be enough for this job’s rough size estimate. "
            "Consider freeing space or choosing a different Save Location.</p>"
        )
    else:
        lines.append(
            "<p>Free space is below the usual safety floor "
            f"({format_bytes(WARN_FREE_BYTES)}). Large scrapes can fill the drive quickly.</p>"
        )
    lines.append(
        "<p>Size estimates are approximate — actual usage depends on content volume, "
        "quality, and duplicates.</p>"
    )
    return "".join(lines)


def confirm_disk_space(
    parent: QWidget | None,
    report: DiskSpaceReport | None,
    *,
    mark_ack: bool = False,
) -> bool:
    """Show warning when needed. Return True to proceed."""
    global _session_skip, _disk_check_ack

    if _disk_check_ack:
        _disk_check_ack = False
        return True

    if not should_prompt(report):
        return True
    assert report is not None

    msg = QMessageBox(parent)
    msg.setIcon(
        QMessageBox.Icon.Critical
        if report.reason == "critical"
        else QMessageBox.Icon.Warning
    )
    msg.setWindowTitle("Low disk space")
    msg.setTextFormat(Qt.TextFormat.RichText)
    if report.reason == "critical":
        msg.setText("<b>Critically low disk space</b>")
    elif report.reason == "estimate":
        msg.setText("<b>Disk space may be insufficient</b>")
    else:
        msg.setText("<b>Low disk space</b>")
    msg.setInformativeText(format_report_html(report))
    msg.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    msg.setDefaultButton(
        QMessageBox.StandardButton.No
        if report.reason == "critical"
        else QMessageBox.StandardButton.Yes
    )
    yes = msg.button(QMessageBox.StandardButton.Yes)
    if yes is not None:
        yes.setText("Continue anyway")
    no = msg.button(QMessageBox.StandardButton.No)
    if no is not None:
        no.setText("Cancel")

    if report.reason != "critical":
        skip_cb = QCheckBox("Don't ask again for disk space warnings")
        msg.setCheckBox(skip_cb)
    else:
        skip_cb = None

    result = msg.exec()
    if result != QMessageBox.StandardButton.Yes:
        _disk_check_ack = False
        return False

    if skip_cb is not None and skip_cb.isChecked():
        _session_skip = True
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings

            s = load_gui_settings()
            s["skip_disk_space_check"] = True
            save_gui_settings(s)
            log.info("[GUI] Disk space check suppressed (gui_settings.skip_disk_space_check)")
        except Exception as e:
            log.debug(f"[GUI] Could not persist skip_disk_space_check: {e}")

    if mark_ack:
        _disk_check_ack = True
    return True


def confirm_for_scrape(
    parent: QWidget | None,
    summary,
    *,
    mark_ack: bool = False,
) -> bool:
    """Disk check for a scrape job summary. True = proceed."""
    writes = _actions_write_media(
        getattr(summary, "actions", None) or [],
        check_mode=bool(getattr(summary, "check_mode", False)),
    )
    estimated = estimate_scrape_bytes(summary) if writes else 0
    # Still warn on critically low space even for like-only / check-only.
    report = build_report(
        estimated_bytes=estimated,
        require_media_write=writes,
    )
    if report is None:
        return True
    if not writes and report.reason != "critical":
        return True
    return confirm_disk_space(parent, report, mark_ack=mark_ack)


def confirm_for_cart(
    parent: QWidget | None,
    rows: list[dict] | None = None,
    summary=None,
) -> bool:
    """Disk check before Send Downloads. True = proceed."""
    estimated = estimate_cart_bytes(rows, summary)
    report = build_report(estimated_bytes=estimated, require_media_write=True)
    return confirm_disk_space(parent, report, mark_ack=False)
