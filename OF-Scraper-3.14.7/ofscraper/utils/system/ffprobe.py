import logging
import pathlib
import re

from ofscraper.utils.system.subprocess import run
import ofscraper.utils.of_env.of_env as env

# Import both binaries!
from ofscraper.utils.system.ffmpeg import get_ffmpeg, get_ffprobe

log = logging.getLogger("shared")

# Default: actual duration must be at least 98% of API/MPD expected (SubScraper-style).
_DEFAULT_MATCH_THRESHOLD = 0.98
# Reject muxes smaller than this (empty/corrupt remux).
_MIN_BYTES = 1024
# Near-zero playback duration counts as empty.
_MIN_DURATION_SECONDS = 0.05


def _get_duration_ffprobe(file_path, ffprobe_path):
    """Primary method: Clean metadata extraction using ffprobe."""
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
        level=env.getattr("FFPROBE_SUBPROCESS_LEVEL"),
        name="ffprobe",
    )
    return float(result.stdout.strip())


def _get_duration_ffmpeg(file_path, ffmpeg_path):
    """Fallback method: Regex scraping from ffmpeg stderr output."""
    cmd = [ffmpeg_path, "-i", str(file_path)]
    result = run(
        cmd,
        capture_output=True,
        text=True,
        check=False,  # Must be False because ffmpeg exits with code 1 here
        level=env.getattr("FFMPEG_SUBPROCESS_LEVEL"),
        name="ffmpeg",
    )

    # FFmpeg prints metadata to stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", result.stderr)
    if match:
        hours, minutes, seconds = match.groups()
        return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)
    return None


def get_media_duration(file_path):
    """Gets media duration, preferring ffprobe but falling back to ffmpeg if needed."""
    try:
        # Attempt 1: The Proper Way (ffprobe)
        ffprobe_path = get_ffprobe()
        if ffprobe_path:
            try:
                return _get_duration_ffprobe(file_path, ffprobe_path)
            except Exception as e:
                log.debug(
                    f"ffprobe failed for {file_path}, trying ffmpeg fallback. Error: {e}"
                )

        # Attempt 2:  (ffmpeg Fallback)
        ffmpeg_path = get_ffmpeg()
        duration = _get_duration_ffmpeg(file_path, ffmpeg_path)
        if duration is not None:
            return duration

        log.debug(f"Both ffprobe and ffmpeg failed to read duration for {file_path}")
        return None

    except Exception as e:
        log.debug(
            f"Media duration check threw an unexpected error for {file_path}: {e}"
        )
        return None


def _resolve_match_threshold(match_threshold):
    """Clamp threshold to (0, 1]; None → default 0.98."""
    if match_threshold is None:
        try:
            from ofscraper.utils import settings as settings_mod

            match_threshold = getattr(
                settings_mod.get_settings(),
                "drm_duration_match_threshold",
                None,
            )
        except Exception:
            match_threshold = None
    try:
        value = float(match_threshold)
    except (TypeError, ValueError):
        return _DEFAULT_MATCH_THRESHOLD
    if value <= 0:
        return _DEFAULT_MATCH_THRESHOLD
    if value > 1.0:
        # Allow GUI/env mistakes like "98" meaning 98%.
        if value <= 100:
            value = value / 100.0
        else:
            return _DEFAULT_MATCH_THRESHOLD
    return min(value, 1.0)


def verify_media_integrity(
    file_path,
    expected_duration_seconds=None,
    *,
    match_threshold=None,
    min_bytes=_MIN_BYTES,
):
    """Return True if the media looks healthy.

    Checks:
    1. File exists and is larger than ``min_bytes`` (rejects empty muxes).
    2. ffprobe/ffmpeg can read a positive duration.
    3. When ``expected_duration_seconds`` is set, require
       ``actual / expected >= match_threshold`` (default 0.98), **or**
       ``expected - actual <= 1.0s`` (API whole-second rounding / remux skew).
    """
    from ofscraper.utils.hardening import check_media_integrity, resolve_match_threshold

    path = pathlib.Path(file_path)
    try:
        size = path.stat().st_size
    except OSError as e:
        log.warning(f"Integrity check: cannot stat {file_path}: {e}")
        return False

    if size < int(min_bytes):
        log.warning(
            f"Integrity check failed (empty/tiny mux): {path.name} "
            f"({size} bytes < {min_bytes})"
        )
        return False

    if match_threshold is None:
        match_threshold = _resolve_match_threshold(None)
    else:
        match_threshold = resolve_match_threshold(match_threshold)

    actual_duration = get_media_duration(file_path)
    ok = check_media_integrity(
        path,
        actual_duration,
        expected_duration_seconds,
        match_threshold=match_threshold,
        min_bytes=min_bytes,
    )
    if not ok:
        if actual_duration is None:
            log.warning(f"File is corrupted or not a valid media file: {file_path}")
        elif actual_duration <= _MIN_DURATION_SECONDS:
            log.warning(
                f"Integrity check failed (near-zero duration): {path.name} "
                f"({actual_duration:.3f}s)"
            )
        else:
            try:
                exp = float(expected_duration_seconds)
                ratio = actual_duration / exp if exp > 0 else 0.0
                log.warning(
                    f"Integrity Check Failed: {path.name} "
                    f"(expected={expected_duration_seconds}, actual={actual_duration:.3f}, "
                    f"ratio={ratio:.1%}, need ≥ {float(match_threshold):.0%} "
                    f"or within 1.0s)"
                )
            except Exception:
                log.warning(
                    f"Integrity Check Failed: {path.name} "
                    f"(expected={expected_duration_seconds}, actual={actual_duration})"
                )
        return False

    log.debug(
        f"Integrity Check Succeed: {path.name}\n"
        f"Expected: {expected_duration_seconds}s | Actual: {actual_duration:.2f}s "
        f"| need ≥ {float(match_threshold):.0%} (or ≤1.0s short)"
    )
    return True
