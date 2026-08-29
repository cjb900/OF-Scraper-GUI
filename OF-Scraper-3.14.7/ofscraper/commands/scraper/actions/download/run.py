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
import traceback

import ofscraper.commands.scraper.actions.utils.globals as common_globals
import ofscraper.utils.live.updater as progress_updater
from ofscraper.commands.scraper.actions.utils.log import (
    log_download_progress,
)
from ofscraper.commands.scraper.actions.utils.log import get_medialog

from ofscraper.commands.scraper.actions.utils.progress.convert import convert_num_bytes
from ofscraper.commands.scraper.actions.download.utils.desc import desc
from ofscraper.commands.scraper.actions.download.managers.alt_download import (
    AltDownloadManager,
)
from ofscraper.commands.scraper.actions.download.managers.main_download import (
    MainDownloadManager,
)
from ofscraper.classes.of.media import Media


def _gui_cancel_requested() -> bool:
    """True when the Pika GUI asked to cancel the current scrape."""
    try:
        from ofscraper.gui.utils.workflow import is_gui_cancelled

        return bool(is_gui_cancelled())
    except Exception:
        return False


def _record_gui_failure(ele, username, reason: str):
    """Record a failed download for the post-run GUI summary (no-op if unused)."""
    if ele is None:
        return
    try:
        from ofscraper.gui.utils.failure_tracker import record_download_failure

        post_id = None
        try:
            post_id = getattr(ele, "file_postid", None)
        except Exception:
            post_id = None
        record_download_failure(
            media_id=getattr(ele, "id", None),
            username=username or getattr(ele, "username", "") or "",
            mediatype=str(getattr(ele, "mediatype", "") or ""),
            post_id=post_id,
            reason=reason,
        )
    except Exception:
        pass
    try:
        mid = getattr(ele, "id", None)
        if mid is None:
            return
        from ofscraper.gui.utils.progress_bridge import update_cell_status

        update_cell_status(str(mid), "download_cart", "[failed]")
    except Exception:
        pass


async def consumer(aws, task1, medialist, lock):
    while True:
        if _gui_cancel_requested():
            common_globals.log.info("Download consumer stopping — GUI cancel requested")
            break
        ele = None
        data = None
        async with lock:
            if not (bool(aws)):
                break
            data = aws.pop()
        if data is None:
            break
        else:
            if _gui_cancel_requested():
                common_globals.log.info(
                    "Download consumer stopping before next item — GUI cancel requested"
                )
                break
            username = ""
            try:
                username = data[3] if len(data) > 3 else ""
            except Exception:
                username = ""
            try:
                ele: Media = data[1]
                pack = await download(*data)
                common_globals.log.debug(f"unpack {pack} count {len(pack)}")
                media_type, num_bytes_downloaded = pack
            except Exception as e:
                common_globals.log.info(
                    f"{get_medialog(ele)} Download Failed because\n{e}"
                )
                common_globals.log.traceback_(traceback.format_exc())
                media_type = "skipped"
                num_bytes_downloaded = 0
                _record_gui_failure(ele, username, str(e))
            try:
                common_globals.total_bytes_downloaded = (
                    common_globals.total_bytes_downloaded + num_bytes_downloaded
                )
                media_type = media_type.lower()
                if media_type == "images":
                    common_globals.photo_count += 1
                    ele.mark_download_succeeded()

                elif media_type == "videos":
                    common_globals.video_count += 1
                    ele.mark_download_succeeded()
                elif media_type == "audios":
                    common_globals.audio_count += 1
                    ele.mark_download_succeeded()
                elif media_type == "skipped":
                    common_globals.skipped += 1
                    ele.mark_download_failed()
                elif media_type == "forced_skipped":
                    ele.mark_download_skipped()
                    common_globals.forced_skipped += 1
                sum_count = (
                    common_globals.photo_count
                    + common_globals.video_count
                    + common_globals.audio_count
                    + common_globals.skipped
                    + common_globals.forced_skipped
                )
                log_download_progress(media_type)
                progress_updater.download.update_overall_task(
                    task1,
                    description=desc.format(
                        p_count=common_globals.photo_count,
                        v_count=common_globals.video_count,
                        a_count=common_globals.audio_count,
                        skipped=common_globals.skipped,
                        forced_skipped=common_globals.forced_skipped,
                        mediacount=len(medialist),
                        sumcount=sum_count,
                        total_bytes=convert_num_bytes(common_globals.total_bytes),
                        total_bytes_download=convert_num_bytes(
                            common_globals.total_bytes_downloaded
                        ),
                    ),
                    refresh=True,
                    advance=1,
                )
                await asyncio.sleep(1)
            except Exception as e:
                common_globals.log.info(
                    f"{get_medialog(ele)} Download Failed because\n{e}"
                )
                common_globals.log.traceback_(traceback.format_exc())
                _record_gui_failure(ele, username, str(e))


async def download(c, ele, model_id, username):
    try:
        data = None
        if ele.url:
            data = await MainDownloadManager().main_download(
                c,
                ele,
                username,
                model_id,
            )
        elif ele.mpd:
            data = await AltDownloadManager().alt_download(c, ele, username, model_id)
        else:
            # Item has no URL and no MPD — nothing to download.
            # Force-mark as downloaded so it doesn't permanently hold the scan
            # anchor back on every subsequent run.
            await AltDownloadManager()._force_download(ele, username, model_id)
            return "forced_skipped", 0
        common_globals.log.debug(f"{get_medialog(ele)} Download finished")
        try:
            if (
                isinstance(data, (list, tuple))
                and data
                and str(data[0]).lower() == "skipped"
            ):
                _record_gui_failure(ele, username, "download returned skipped")
        except Exception:
            pass
        return data
    except Exception as E:
        common_globals.log.debug(f"{get_medialog(ele)} exception {E}")
        common_globals.log.debug(
            f"{get_medialog(ele)} exception {traceback.format_exc()}"
        )
        _record_gui_failure(ele, username, str(E))
        return "skipped", 0
