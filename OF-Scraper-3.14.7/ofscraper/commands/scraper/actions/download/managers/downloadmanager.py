r"""

 _______  _______         _______  _______  _______  _______  _______  _______  _______
(  ___  )(  ____ \       (  ____ \(  ____ \(  ____ )(  ___  )(  ____ )(  ____ \(  ____ )
| (   ) || (    \/       | (    \/| (    \/| (    )|| (   ) || (    )|| (    \/| (    )|
| |   | || (__     _____ | (_____ | |      | (____)|| (___) || (____)|| (__    | (____)|
| |   | ||  __)   (_____)(_____  )| |      |     __)|  ___  ||  _____)|  __)   |     __)
| |   | || (                   ) || |      | (\ (   | (   ) || (      | (      | (\ (
| (___) || )             /\____) || (____/\| ) \ \__| )   ( || )      | (____/\| ) \ \__
(_______)|/              \_______)(_______/|/   \__/|/     \||/       (_______/|/   \__/

"""

import asyncio
import pathlib
import os
import re
from humanfriendly import format_size
import psutil

import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.live.updater as progress_updater
from ofscraper.commands.scraper.actions.utils.progress.update import update_total
import ofscraper.utils.settings as settings
import ofscraper.commands.scraper.actions.utils.globals as common_globals
from ofscraper.commands.scraper.actions.utils.log import get_medialog
import ofscraper.utils.system.free as system
from ofscraper.db.operations_.media import mark_media_as_downloaded
from ofscraper.scripts.skip_download_script import skip_download_script
from ofscraper.scripts.after_download_script import after_download_script
from ofscraper.utils.hardening import parse_expected_file_size

# Allow tiny HTTP/filesystem slack; previously 500 bytes could hide truncated .part files.
_DEFAULT_PART_SIZE_TOLERANCE = 64


def get_part_size_tolerance() -> int:
    try:
        raw = of_env.getattr("PART_SIZE_TOLERANCE")
        if raw is not None:
            return max(0, int(raw))
    except Exception:
        pass
    try:
        val = getattr(settings.get_settings(), "part_size_tolerance", None)
        if val is not None:
            return max(0, int(val))
    except Exception:
        pass
    return _DEFAULT_PART_SIZE_TOLERANCE


# Re-export for callers/tests that imported from this module previously.
__all__ = [
    "DownloadManager",
    "get_part_size_tolerance",
    "parse_expected_file_size",
]


class DownloadManager:
    def __init__(self):
        self.total = None
        self.process = psutil.Process(os.getpid())

    async def _add_download_job_task(
        self, ele, total=None, placeholderObj=None, tempholderObj=None
    ):
        pathstr = str(placeholderObj.trunicated_filepath)
        task1 = progress_updater.download.add_job_task(
            f"{(pathstr[:of_env.getattr('PATH_STR_MAX')] + '....') if len(pathstr) > of_env.getattr('PATH_STR_MAX') else pathstr}\n",
            total=total,
            file=tempholderObj.tempfilepath,
        )
        return task1

    async def _remove_download_job_task(self, task1, ele):
        if task1:
            progress_updater.download.remove_job_task(task1)

    async def _total_change_helper(self, new_total, **kwargs):
        if not self.total and not new_total:
            return
        elif not self.total:
            await update_total(new_total)
            self.total = new_total
        elif self.total and new_total - self.total != 0:
            await update_total(new_total - self.total)
            self.total = new_total

    def _get_resume_header(self, resume_size, total):
        return (
            None
            if not resume_size or not total
            else {"Range": f"bytes={resume_size}-{total}"}
        )

    def _get_resume_size(
        self,
        tempholderObj,
    ):
        if not settings.get_settings().auto_resume:
            pathlib.Path(tempholderObj.tempfilepath).unlink(missing_ok=True)
            return 0
        return (
            0
            if not pathlib.Path(tempholderObj.tempfilepath).exists()
            else pathlib.Path(tempholderObj.tempfilepath).absolute().stat().st_size
        )

    def _resume_cleaner(self, resume_size, total, path):
        """Drop a .part that is larger than the expected full size (corrupt resume)."""
        if not resume_size:
            return 0
        elif total and resume_size > total:
            pathlib.Path(path).unlink(missing_ok=True)
            return 0
        return resume_size

    def _resolve_download_totals(self, response, resume_size: int, path):
        """Map response headers → (expected_full_size, body_length, resume_size).

        Handles 206 Content-Range, 200-after-Range (restart), and missing ranges.
        """
        headers = getattr(response, "headers", {}) or {}
        try:
            body_len = int(
                headers.get("content-length") or headers.get("Content-Length") or 0
            )
        except (TypeError, ValueError):
            body_len = 0
        status = getattr(response, "status_code", None) or getattr(
            response, "status", None
        )
        try:
            status = int(status) if status is not None else None
        except (TypeError, ValueError):
            status = None

        # Server ignored Range and sent the full body — discard partial .part.
        if resume_size and status == 200:
            pathlib.Path(path).unlink(missing_ok=True)
            resume_size = 0

        expected_full = parse_expected_file_size(
            headers, resume_size=resume_size, content_length=body_len
        )
        resume_size = self._resume_cleaner(resume_size, expected_full, path)
        if resume_size == 0 and status == 200:
            expected_full = body_len or expected_full
        return expected_full, body_len, resume_size

    async def _check_forced_skip(self, ele, total):
        if total is None:
            return
        total = int(total)
        if total == 0:
            return 0
        if await skip_download_script(total, ele):
            return 0
        file_size_max = settings.get_settings().size_max
        file_size_min = settings.get_settings().size_min
        if int(file_size_max) > 0 and (int(total) > int(file_size_max)):
            ele.mediatype = "Forced_skipped"
            common_globals.log.debug(
                f"{get_medialog(ele)} {format_size(total)} over size limit"
            )
            return 0
        elif int(file_size_min) > 0 and (int(total) < int(file_size_min)):
            ele.mediatype = "Forced_skipped"
            common_globals.log.debug(
                f"{get_medialog(ele)} {format_size(total)} under size min"
            )
            return 0

    def _downloadspace(self):
        if not system.check_free_size():
            raise Exception(of_env.getattr("SPACE_DOWNLOAD_MESSAGE"))

    async def _after_download_script(self, filepath):
        await after_download_script(filepath)

    async def _size_checker(self, path, ele, total, name=None):
        """Strict .part finalize: reject missing/empty/truncated/oversized temps."""
        name = name or ele.filename
        try:
            total_i = int(total or 0)
        except (TypeError, ValueError):
            total_i = 0
        if total_i == 0:
            return True
        path_obj = pathlib.Path(path)
        if not path_obj.exists():
            raise Exception(f"{get_medialog(ele)} {path} was not created")
        actual = path_obj.absolute().stat().st_size
        if actual <= 0:
            raise Exception(
                f"{get_medialog(ele)} {name} empty .part file (0 bytes); expected {total_i}"
            )
        tolerance = get_part_size_tolerance()
        if actual < total_i - tolerance:
            raise Exception(
                f"{get_medialog(ele)} {name} size mismatch target: {total_i} vs "
                f"current file: {actual} (short by {total_i - actual})"
            )
        if actual > total_i + tolerance:
            raise Exception(
                f"{get_medialog(ele)} {path} size mismatch target item too large: "
                f"{total_i} vs current file: {actual}"
            )
        return True

    async def _force_download(self, ele, username, model_id):
        await mark_media_as_downloaded(
            ele,
            filepath=None,
            model_id=model_id,
            username=username,
            downloaded=True,
        )

    async def _next_chunk(self, chunk_iter, ele):
        """Read next chunk with an inactivity watchdog (sock_read + wait_for)."""
        from ofscraper.commands.scraper.actions.download.utils.chunk import (
            get_chunk_timeout,
        )

        timeout = get_chunk_timeout()
        try:
            return await asyncio.wait_for(chunk_iter.__anext__(), timeout=timeout)
        except StopAsyncIteration:
            raise
        except asyncio.TimeoutError as exc:
            common_globals.log.info(
                f"{get_medialog(ele)}⚠️ Download stalled "
                f"(no data for {timeout}s). Forcing retry!"
            )
            raise Exception(f"Download stalled (no data for {timeout}s)") from exc
