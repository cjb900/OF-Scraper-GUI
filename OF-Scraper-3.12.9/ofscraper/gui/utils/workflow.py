"""
GUI workflow runner — bridges user selections from the GUI pages
to the existing scraper backend pipeline.

This module sets CLI args programmatically (as if the user had typed them)
and then invokes the same scraperManager.runner() that the TUI uses.
A GUI-specific scraper subclass emits media data to the table as each
user is processed.
"""
import logging
import threading
import traceback
import ctypes

from ofscraper.gui.signals import app_signals

log = logging.getLogger("shared")

# Best-effort cancellation flag for GUI runs.
# We cooperatively abort the pipeline from frequently-called hooks.
_gui_cancel_event = threading.Event()


def _raise_in_thread(thread_id: int, exc_type=KeyboardInterrupt) -> bool:
    """Best-effort: raise an exception asynchronously in another Python thread.

    This is not perfectly safe, but it is the most reliable way to stop long
    scraping phases that don't call our GUI progress hooks for a while.
    """
    try:
        if not thread_id:
            return False
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(thread_id), ctypes.py_object(exc_type)
        )
        if res == 0:
            return False
        if res > 1:
            # Undo if it affected multiple threads (shouldn't happen)
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(thread_id), None)
            return False
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Rich Live / Console stubs for GUI mode
# ---------------------------------------------------------------------------
class _NullLive:
    """No-op replacement for Rich Live display in GUI mode.

    The scraper pipeline uses Rich Live for terminal progress rendering.
    In GUI mode we replace it with this stub so no terminal interaction
    occurs from the background scraper thread.
    """
    is_started = False
    renderable = None

    def start(self):
        self.is_started = True

    def stop(self):
        self.is_started = False

    def update(self, *args, **kwargs):
        pass

    def refresh(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


# Saved originals for restoration
_orig_live = None
_orig_get_live = None
_orig_stop_live = None
_orig_screens_get_live = None
_orig_screens_stop_live = None
_orig_console_quiet = None
_orig_dki_enter = None
_orig_dki_exit = None


def _install_gui_live_stubs():
    """Replace Rich Live display and patch signal handlers for GUI mode.

    Three things are handled:
    1. Rich Live → _NullLive (prevents terminal drawing from bg thread)
    2. Rich Console → quiet mode (suppresses print output)
    3. DelayedKeyboardInterrupt → thread-safe (signal.signal only in main thread)

    screens.py does ``from ofscraper.utils.live.live import get_live, stop_live``
    so we must also patch the names in that module to prevent stop_live()
    from clearing our _NullLive and get_live() from recreating a real Live.
    """
    global _orig_live, _orig_get_live, _orig_stop_live
    global _orig_screens_get_live, _orig_screens_stop_live
    global _orig_console_quiet, _orig_dki_enter, _orig_dki_exit

    null_live = _NullLive()

    # 1a. Replace Rich Live with no-op in the live module
    import ofscraper.utils.live.live as live_module

    _orig_live = live_module.live
    _orig_get_live = live_module.get_live
    _orig_stop_live = live_module.stop_live

    live_module.live = null_live
    live_module.get_live = lambda recreate=False: null_live
    live_module.stop_live = lambda: None

    # 1b. Patch the imported references in screens.py
    #     (``from ... import get_live, stop_live`` binds module-level names)
    import ofscraper.utils.live.screens as screens_module

    _orig_screens_get_live = screens_module.get_live
    _orig_screens_stop_live = screens_module.stop_live

    screens_module.get_live = lambda recreate=False: null_live
    screens_module.stop_live = lambda: None

    # 2. Make Rich Console quiet to suppress terminal output
    import ofscraper.utils.console as console_module

    console = console_module.get_shared_console()
    _orig_console_quiet = console.quiet
    console.quiet = True

    # Also quiet the other console in case low_output is used
    other = console_module.get_other_console()
    other.quiet = True

    # 3. Patch DelayedKeyboardInterrupt for thread safety
    #    signal.signal() can only be called from the main thread;
    #    the scraper runs in a background thread in GUI mode.
    import ofscraper.utils.context.exit as exit_module

    _orig_dki_enter = exit_module.DelayedKeyboardInterrupt.__enter__
    _orig_dki_exit = exit_module.DelayedKeyboardInterrupt.__exit__

    def _safe_enter(self):
        if threading.current_thread() is threading.main_thread():
            return _orig_dki_enter(self)

    def _safe_exit(self, exc_type, exc_val, exc_tb):
        if threading.current_thread() is threading.main_thread():
            return _orig_dki_exit(self, exc_type, exc_val, exc_tb)

    exit_module.DelayedKeyboardInterrupt.__enter__ = _safe_enter
    exit_module.DelayedKeyboardInterrupt.__exit__ = _safe_exit


def _uninstall_gui_live_stubs():
    """Restore original Rich Live, Console, and signal handlers."""
    import ofscraper.utils.live.live as live_module
    import ofscraper.utils.live.screens as screens_module
    import ofscraper.utils.console as console_module
    import ofscraper.utils.context.exit as exit_module

    if _orig_live is not None:
        live_module.live = _orig_live
    if _orig_get_live is not None:
        live_module.get_live = _orig_get_live
    if _orig_stop_live is not None:
        live_module.stop_live = _orig_stop_live
    if _orig_screens_get_live is not None:
        screens_module.get_live = _orig_screens_get_live
    if _orig_screens_stop_live is not None:
        screens_module.stop_live = _orig_screens_stop_live
    if _orig_console_quiet is not None:
        console_module.get_shared_console().quiet = _orig_console_quiet
    if _orig_dki_enter is not None:
        exit_module.DelayedKeyboardInterrupt.__enter__ = _orig_dki_enter
    if _orig_dki_exit is not None:
        exit_module.DelayedKeyboardInterrupt.__exit__ = _orig_dki_exit


# ---------------------------------------------------------------------------
# Python logging → GUI console bridge
# ---------------------------------------------------------------------------
import re

_gui_log_handler = None


class _GUILogHandler(logging.Handler):
    """Logging handler that forwards Python log records to the GUI console
    via app_signals.log_message.  Strips Rich markup for clean display."""

    # Match Rich markup tags like [bold], [/bold], [bold yellow], [red],
    # but NOT data in brackets like [Timeline,Messages] or [downloaded]
    _RICH_TAG_RE = re.compile(
        r"\[/?"
        r"(?:bold|italic|underline|strike|dim|reverse|blink|"
        r"red|green|blue|yellow|magenta|cyan|white|black|"
        r"bright_\w+|deep_sky_blue\d*|"
        r"bold \w+|italic \w+)"
        r"\]"
    )

    def emit(self, record):
        try:
            msg = self.format(record)
            # Strip Rich markup tags
            msg = self._RICH_TAG_RE.sub("", msg)
            if not msg.strip():
                return
            level = record.levelname
            # Map custom TRACEBACK_ level to ERROR for display
            if record.levelno == logging.DEBUG + 1:  # TRACEBACK_ level
                level = "ERROR"
            app_signals.log_message.emit(level, msg)
        except Exception:
            pass


def _install_gui_log_handler():
    """Attach a handler to the 'shared' and 'shared_other' loggers so their
    output appears in the GUI console widget."""
    global _gui_log_handler
    _gui_log_handler = _GUILogHandler()
    # Level 11 = TRACEBACK_ (DEBUG+1) — catches exceptions logged via
    # log.traceback_() which the scraper uses for all error reporting.
    _gui_log_handler.setLevel(logging.DEBUG + 1)
    _gui_log_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    for name in ("shared", "shared_other"):
        logger = logging.getLogger(name)
        logger.addHandler(_gui_log_handler)


def _uninstall_gui_log_handler():
    """Remove the GUI log handler from the loggers."""
    global _gui_log_handler
    if _gui_log_handler is None:
        return
    for name in ("shared", "shared_other"):
        logger = logging.getLogger(name)
        logger.removeHandler(_gui_log_handler)
    _gui_log_handler = None


# ---------------------------------------------------------------------------
# Shared state for GUI progress hooks
# ---------------------------------------------------------------------------
class _GUIDownloadState:
    """Tracks per-user download state for the GUI progress bridge."""

    def __init__(self):
        self.total_media = 0
        self._poll_stop = None
        self._poll_thread = None

    def start_polling(self, media, model_id, username):
        """Start periodic DB polling for download status updates."""
        self._poll_stop = threading.Event()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            args=(media, model_id, username),
            daemon=True,
            name="gui-dl-poll",
        )
        self._poll_thread.start()

    def stop_polling(self):
        """Stop the periodic polling."""
        if self._poll_stop:
            self._poll_stop.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None

    def _poll_loop(self, media, model_id, username):
        """Poll DB every 3 seconds and emit cell_update signals for newly
        downloaded items."""
        # Build set of locked media IDs so we don't overwrite their status
        locked_media_ids = set()
        for ele in media:
            mid = getattr(ele, "id", None)
            if mid is not None and not getattr(ele, "canview", True):
                locked_media_ids.add(mid)

        already_downloaded = set()
        while not self._poll_stop.is_set():
            try:
                from ofscraper.db.operations_.media import (
                    get_media_ids_downloaded,
                )

                downloaded_set = get_media_ids_downloaded(
                    model_id=model_id, username=username
                )
                # Only emit signals for newly downloaded items
                new_downloads = downloaded_set - already_downloaded
                for media_id in new_downloads:
                    if media_id in locked_media_ids:
                        app_signals.cell_update.emit(
                            str(media_id), "downloaded", "N/A"
                        )
                        app_signals.cell_update.emit(
                            str(media_id), "unlocked", "Locked"
                        )
                    else:
                        app_signals.cell_update.emit(
                            str(media_id), "downloaded", "True"
                        )
                        app_signals.cell_update.emit(
                            str(media_id), "download_cart", "[downloaded]"
                        )
                already_downloaded = downloaded_set
            except Exception as e:
                log.debug(f"Download status poll error: {e}")
            self._poll_stop.wait(3)


_gui_state = _GUIDownloadState()

# Store original functions so we can restore them
_orig_update_download_task = None
_orig_add_download_task = None
_orig_remove_download_task = None
_orig_add_like_task = None
_orig_increment_like_task = None
_orig_remove_like_task = None


def _install_gui_progress_hooks():
    """Monkey-patch progress_updater functions to also emit GUI signals.

    The consumer loop in download/normal/utils/consumer.py calls
    progress_updater.update_download_task() after EVERY media item.
    By wrapping that function, we get per-item progress updates in the GUI
    without modifying any core download code.
    """
    import ofscraper.utils.live.updater as progress_updater
    import ofscraper.actions.utils.globals as common_globals

    global _orig_update_download_task
    global _orig_add_download_task
    global _orig_remove_download_task
    global _orig_add_like_task
    global _orig_increment_like_task
    global _orig_remove_like_task
    _orig_update_download_task = progress_updater.update_download_task
    _orig_add_download_task = progress_updater.add_download_task
    _orig_remove_download_task = progress_updater.remove_download_task
    _orig_add_like_task = getattr(progress_updater, "add_like_task", None)
    _orig_increment_like_task = getattr(progress_updater, "increment_like_task", None)
    _orig_remove_like_task = getattr(progress_updater, "remove_like_task", None)

    def gui_add_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        total = kwargs.get("total", 0)
        _gui_state.total_media = total
        result = _orig_add_download_task(*args, **kwargs)
        try:
            app_signals.overall_progress_updated.emit(0, total)
        except Exception:
            pass
        return result

    def gui_update_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_update_download_task(*args, **kwargs)
        try:
            sum_count = (
                common_globals.photo_count
                + common_globals.video_count
                + common_globals.audio_count
                + common_globals.skipped
                + common_globals.forced_skipped
            )
            total = _gui_state.total_media
            app_signals.overall_progress_updated.emit(sum_count, total)
            app_signals.total_bytes_updated.emit(
                int(common_globals.total_bytes_downloaded)
            )
        except Exception:
            pass

    def gui_remove_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_remove_download_task(*args, **kwargs)
        try:
            app_signals.progress_task_removed.emit("download")
        except Exception:
            pass

    progress_updater.update_download_task = gui_update_download_task
    progress_updater.add_download_task = gui_add_download_task
    progress_updater.remove_download_task = gui_remove_download_task

    # Like progress hooks (best-effort): surface like/unlike progress in the GUI.
    # `like.py` uses like_overall_progress tasks, which we can mirror into the GUI task list.
    like_task_map = {}  # underlying task -> gui_task_id
    like_task_counter = {"n": 0}

    def gui_add_like_task(*args, **kwargs):
        if _orig_add_like_task is None:
            return None
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        total = kwargs.get("total", None)
        task = _orig_add_like_task(*args, **kwargs)
        try:
            # Only create a GUI bar when the task has a finite total.
            if total is None:
                return task
            like_task_counter["n"] += 1
            gui_id = f"like:{like_task_counter['n']}"
            like_task_map[task] = gui_id
            app_signals.progress_task_added.emit(gui_id, int(total))
        except Exception:
            pass
        return task

    def gui_increment_like_task(*args, advance=1, **kwargs):
        if _orig_increment_like_task is None:
            return None
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_increment_like_task(*args, advance=advance, **kwargs)
        try:
            task = args[0] if args else None
            gui_id = like_task_map.get(task)
            if gui_id:
                app_signals.progress_task_updated.emit(gui_id, int(advance))
        except Exception:
            pass

    def gui_remove_like_task(task):
        if _orig_remove_like_task is None:
            return None
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_remove_like_task(task)
        try:
            gui_id = like_task_map.pop(task, None)
            if gui_id:
                app_signals.progress_task_removed.emit(gui_id)
        except Exception:
            pass

    if _orig_add_like_task is not None:
        progress_updater.add_like_task = gui_add_like_task
    if _orig_increment_like_task is not None:
        progress_updater.increment_like_task = gui_increment_like_task
    if _orig_remove_like_task is not None:
        progress_updater.remove_like_task = gui_remove_like_task


def _uninstall_gui_progress_hooks():
    """Restore original progress_updater functions."""
    import ofscraper.utils.live.updater as progress_updater

    if _orig_update_download_task is not None:
        progress_updater.update_download_task = _orig_update_download_task
    if _orig_add_download_task is not None:
        progress_updater.add_download_task = _orig_add_download_task
    if _orig_remove_download_task is not None:
        progress_updater.remove_download_task = _orig_remove_download_task
    if _orig_add_like_task is not None:
        progress_updater.add_like_task = _orig_add_like_task
    if _orig_increment_like_task is not None:
        progress_updater.increment_like_task = _orig_increment_like_task
    if _orig_remove_like_task is not None:
        progress_updater.remove_like_task = _orig_remove_like_task


# ---------------------------------------------------------------------------
# Media row builder
# ---------------------------------------------------------------------------
def _build_media_rows(media, username):
    """Convert a list of Media objects into row dicts for the GUI data table."""
    import arrow

    rows = []
    try:
        sorted_media = sorted(
            media, key=lambda x: arrow.get(x.date), reverse=True
        )
    except Exception:
        sorted_media = list(media)

    for count, ele in enumerate(sorted_media):
        try:
            price = 0
            if hasattr(ele, "_post") and hasattr(ele._post, "price"):
                price = ele._post.price or 0
            preview = bool(getattr(ele, "preview", False))
            responsetype = str(getattr(ele, "responsetype", "") or "").lower()
            post_opened = False
            try:
                # For PPV messages, "opened" indicates purchase/unlock state of the message.
                # Media.canview can still be True for included/preview media even when the
                # overall message is not opened.
                post_opened = bool(getattr(getattr(ele, "post", None), "opened", 0))
            except Exception:
                post_opened = False

            post_media_count = 0
            if hasattr(ele, "_post") and hasattr(ele._post, "post_media"):
                post_media_count = len(ele._post.post_media)

            text = ""
            if hasattr(ele, "post") and hasattr(ele.post, "db_sanitized_text"):
                text = ele.post.db_sanitized_text or ""

            canview = getattr(ele, "canview", True)

            # Cart status based on viewability
            if not canview and price > 0:
                cart_status = "Locked"
            elif not canview:
                cart_status = "Locked"
            else:
                cart_status = "[]"

            # Downloaded/Unlocked display based on canview
            if not canview:
                dl_display = "N/A"
                ul_display = "Locked"
            else:
                dl_display = str(False)
                # For PPV messages, the message itself can be priced but not purchased ("opened"=False).
                # In that case, media may still be viewable as Included/Preview, and should NOT show
                # up as fully "Unlocked=True" which looks like purchased content.
                if price > 0 and responsetype in ("message", "messages") and not post_opened:
                    ul_display = "Preview" if preview else "Included"
                else:
                    ul_display = "Preview" if (preview and price > 0) else str(True)

            rows.append(
                {
                    "index": count,
                    "number": str(count + 1),
                    "download_cart": cart_status,
                    "username": username,
                    "downloaded": dl_display,
                    "unlocked": ul_display,
                    "other_posts_with_media": [],
                    "post_media_count": post_media_count,
                    "mediatype": getattr(ele, "mediatype", "unknown"),
                    "post_date": getattr(ele, "formatted_postdate", "") or "",
                    "length": getattr(ele, "numeric_duration", "N/A"),
                    "responsetype": getattr(ele, "responsetype", ""),
                    "price": "Free" if price == 0 else "{:.2f}".format(price),
                    "post_id": getattr(ele, "postid", ""),
                    "media_id": getattr(ele, "id", ""),
                    "text": text,
                }
            )
        except Exception as e:
            log.debug(f"Error building table row: {e}")
    return rows


def _build_db_rows(db_records, username, post_info=None):
    """Convert DB media records (from the medias table) into row dicts
    for the GUI data table.  This is the DB-backed equivalent of
    ``_build_media_rows`` which operates on live Media objects.

    ``post_info`` is an optional dict of post_id → {"price": int, "text": str}
    sourced from the posts/messages/stories tables.
    """
    import arrow

    if post_info is None:
        post_info = {}

    # PPV messages can contain a mix of locked and unlocked media.
    # If a priced post still has any locked media, treat the unlocked ones as "Included"
    # (i.e., visible without purchasing the full PPV payload).
    posts_with_locked_media = set()
    try:
        for r in db_records:
            if r.get("post_id") is not None and r.get("unlocked") in (0, False):
                posts_with_locked_media.add(r.get("post_id"))
    except Exception:
        posts_with_locked_media = set()

    rows = []
    try:
        sorted_records = sorted(
            db_records,
            key=lambda x: arrow.get(
                x.get("posted_at") or x.get("created_at") or 0
            ).float_timestamp,
            reverse=True,
        )
    except Exception:
        sorted_records = list(db_records)

    for count, rec in enumerate(sorted_records):
        try:
            downloaded = bool(rec.get("downloaded"))
            unlocked_raw = rec.get("unlocked")
            is_unlocked = bool(unlocked_raw) if unlocked_raw is not None else True
            preview = bool(rec.get("preview"))

            # Look up price and text from the post/message/story table
            pid = rec.get("post_id")
            pinfo = post_info.get(pid, {})
            price = pinfo.get("price", 0) or 0
            text = pinfo.get("text", "") or ""

            # Determine cart status from DB state
            # is_unlocked=False means the content is behind a paywall (locked)
            if not is_unlocked:
                cart_status = "Locked"
            elif downloaded:
                cart_status = "[downloaded]"
            else:
                cart_status = "[]"

            # Format posted_at for display
            posted_at = rec.get("posted_at") or rec.get("created_at")
            if posted_at:
                try:
                    post_date = arrow.get(posted_at).format("YYYY-MM-DD HH:mm:ss")
                except Exception:
                    post_date = str(posted_at)
            else:
                post_date = ""

            duration = rec.get("duration") or "N/A"

            # Format price display
            if price == 0:
                price_display = "Free"
            else:
                price_display = "{:.2f}".format(price)

            # Downloaded / Unlocked display
            # is_unlocked=False → content is locked behind paywall
            if not is_unlocked:
                dl_display = "N/A"
                ul_display = "Locked"
            else:
                dl_display = str(downloaded)
                api_type = str(rec.get("api_type") or "").lower()
                # Messages can be priced PPV while still exposing included/preview media.
                # If it's a priced message and the media is viewable, label as Included/Preview
                # so it doesn't look like purchased/unlocked PPV.
                if price > 0 and api_type in ("message", "messages"):
                    ul_display = "Preview" if preview else "Included"
                elif price > 0 and pid in posts_with_locked_media:
                    ul_display = "Included"
                else:
                    ul_display = "Preview" if (preview and price > 0) else str(True)

            rows.append(
                {
                    "index": count,
                    "number": str(count + 1),
                    "download_cart": cart_status,
                    "username": username,
                    "downloaded": dl_display,
                    "unlocked": ul_display,
                    "other_posts_with_media": [],
                    "post_media_count": 0,
                    "mediatype": (rec.get("media_type") or "unknown").capitalize(),
                    "post_date": post_date,
                    "length": duration,
                    "responsetype": (rec.get("api_type") or "").capitalize(),
                    "price": price_display,
                    "post_id": rec.get("post_id", ""),
                    "media_id": rec.get("media_id", ""),
                    "text": text,
                }
            )
        except Exception as e:
            log.debug(f"Error building DB table row: {e}")
    return rows


def _query_post_info(cur):
    """Build a post_id → {price, text} mapping from posts, messages, and stories tables."""
    post_info = {}  # post_id → {"price": int, "text": str}

    for table in ("posts", "messages", "stories"):
        try:
            cur.execute(
                f"SELECT post_id, price, text FROM {table}"
            )
            for row in cur.fetchall():
                r = dict(row)
                pid = r.get("post_id")
                if pid is not None and pid not in post_info:
                    post_info[pid] = {
                        "price": r.get("price") or 0,
                        "text": r.get("text") or "",
                    }
        except Exception:
            # Table may not exist in older DBs
            pass

    return post_info


def _load_models_from_db(selected_models):
    """Query the DB for all media records of each selected model and emit
    them to the GUI table.  Runs synchronously (called from the scraper
    background thread after the pipeline finishes)."""
    import pathlib
    import sqlite3

    from filelock import FileLock

    import ofscraper.classes.placeholder as placeholder
    import ofscraper.utils.paths.common as common_paths

    media_select_sql = """
    SELECT media_id, post_id, link, directory, filename, size, api_type,
    media_type, preview, linked, downloaded, created_at, unlocked,
    CASE WHEN EXISTS (SELECT 1 FROM pragma_table_info('medias') WHERE name = 'model_id')
        THEN model_id ELSE NULL END AS model_id,
    CASE WHEN EXISTS (SELECT 1 FROM pragma_table_info('medias') WHERE name = 'posted_at')
        THEN posted_at ELSE NULL END AS posted_at,
    CASE WHEN EXISTS (SELECT 1 FROM pragma_table_info('medias') WHERE name = 'hash')
        THEN hash ELSE NULL END AS hash,
    CASE WHEN EXISTS (SELECT 1 FROM pragma_table_info('medias') WHERE name = 'duration')
        THEN duration ELSE NULL END AS duration
    FROM medias;
    """

    for model in selected_models:
        model_id = model.id
        username = model.name
        lock = None
        conn = None
        try:
            lock = FileLock(common_paths.getDB(), timeout=-1)
            lock.acquire(timeout=-1)

            database_path = pathlib.Path(
                placeholder.databasePlaceholder().databasePathHelper(
                    model_id, username
                )
            )
            if not database_path.exists():
                log.debug(f"No DB file for {username}, skipping DB load")
                continue

            conn = sqlite3.connect(
                database_path, check_same_thread=True, timeout=10
            )
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(media_select_sql)
            data = [dict(row) for row in cur.fetchall()]

            # Also fetch price and text from post/message/story tables
            post_info = _query_post_info(cur)
            cur.close()

            if data:
                rows = _build_db_rows(data, username, post_info)
                if rows:
                    app_signals.data_loading_finished.emit(rows)
                    log.info(
                        f"Loaded {len(rows)} items from DB for {username}"
                    )
        except Exception as e:
            log.debug(f"Failed to load DB data for {username}: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            if lock:
                try:
                    lock.release(force=True)
                except Exception:
                    pass


def _emit_download_status(media, model_id, username):
    """Query the DB for downloaded media IDs and emit cell_update signals."""
    try:
        from ofscraper.db.operations_.media import get_media_ids_downloaded

        downloaded_set = get_media_ids_downloaded(
            model_id=model_id, username=username
        )
        for ele in media:
            media_id = getattr(ele, "id", None)
            if media_id is None:
                continue
            canview = getattr(ele, "canview", True)
            is_downloaded = media_id in downloaded_set

            if not canview:
                # Locked content — don't change status
                app_signals.cell_update.emit(
                    str(media_id), "downloaded", "N/A"
                )
                app_signals.cell_update.emit(
                    str(media_id), "unlocked", "Locked"
                )
                app_signals.cell_update.emit(
                    str(media_id), "download_cart", "Locked"
                )
            else:
                app_signals.cell_update.emit(
                    str(media_id), "downloaded", str(is_downloaded)
                )
                if is_downloaded:
                    app_signals.cell_update.emit(
                        str(media_id), "download_cart", "[downloaded]"
                    )
    except Exception as e:
        log.debug(f"Failed to emit download status: {e}")


# ---------------------------------------------------------------------------
# GUI scraper manager
# ---------------------------------------------------------------------------
def _make_gui_scraper_manager():
    """Create a scraperManager subclass that emits media data to the GUI."""
    from ofscraper.commands.managers.scraper import scraperManager
    import ofscraper.utils.args.accessors.read as read_args
    from ofscraper.actions.actions.download.download import downloader
    import ofscraper.actions.actions.like.like as like_action

    class GUIScraperManager(scraperManager):
        """scraperManager subclass that emits media rows to the GUI table
        before executing download/like actions for each user."""

        async def _execute_user_action(
            self, posts=None, like_posts=None, ele=None, media=None
        ):
            username = ele.name if ele else "unknown"
            media_count = len(media) if media else 0
            log.info(
                f"[GUI] Processing {username}: {media_count} media items "
                f"(posts={len(posts) if posts else 0}, "
                f"like_posts={len(like_posts) if like_posts else 0})"
            )
            app_signals.log_message.emit(
                "INFO",
                f"Processing {username}: {media_count} media items to download",
            )

            if media_count == 0:
                app_signals.log_message.emit(
                    "WARNING",
                    f"No downloadable media found for {username} — "
                    f"all items may be already downloaded or filtered out",
                )

            # Emit media data to GUI table before running actions
            if media and ele:
                rows = _build_media_rows(media, ele.name)
                if rows:
                    try:
                        app_signals.data_loading_finished.emit(rows)
                    except Exception as e:
                        log.debug(f"Failed to emit table data: {e}")

            # Run the actual actions (download/like/unlike)
            actions = read_args.retriveArgs().action
            model_id = ele.id
            out = []
            log.info(f"[GUI] Running actions {actions} for {username}")
            for action in actions:
                if action == "download":
                    if not media:
                        app_signals.log_message.emit(
                            "WARNING",
                            f"Skipping download for {username}: no media to download",
                        )
                        out.append([])
                        continue
                    # Start periodic DB polling for real-time Downloaded updates
                    _gui_state.start_polling(media, model_id, username)
                    try:
                        app_signals.log_message.emit(
                            "INFO",
                            f"Starting download of {len(media)} items for {username}...",
                        )
                        result, _ = await downloader(
                            posts=posts,
                            media=media,
                            model_id=model_id,
                            username=username,
                        )
                        out.append(result)
                        app_signals.log_message.emit(
                            "INFO",
                            f"Download complete for {username}",
                        )
                    except Exception as e:
                        log.error(f"[GUI] Download error for {username}: {e}")
                        app_signals.log_message.emit(
                            "ERROR",
                            f"Download failed for {username}: {e}",
                        )
                        out.append([])
                    finally:
                        # Stop polling and do a final status sweep
                        _gui_state.stop_polling()
                        _emit_download_status(media, model_id, username)
                elif action == "like":
                    try:
                        app_signals.log_message.emit(
                            "INFO",
                            f"Starting like action for {username}: {len(like_posts) if like_posts else 0} posts",
                        )
                        app_signals.status_message.emit(
                            f"Liking posts for {username}..."
                        )
                    except Exception:
                        pass
                    out.append(
                        like_action.process_like(
                            ele=ele,
                            posts=like_posts,
                            media=media,
                            model_id=model_id,
                            username=username,
                        )
                    )
                elif action == "unlike":
                    try:
                        app_signals.log_message.emit(
                            "INFO",
                            f"Starting unlike action for {username}: {len(like_posts) if like_posts else 0} posts",
                        )
                        app_signals.status_message.emit(
                            f"Unliking posts for {username}..."
                        )
                    except Exception:
                        pass
                    out.append(
                        like_action.process_unlike(
                            ele=ele,
                            posts=like_posts,
                            media=media,
                            model_id=model_id,
                            username=username,
                        )
                    )
            return out

    return GUIScraperManager


# ---------------------------------------------------------------------------
# Workflow orchestrator
# ---------------------------------------------------------------------------
class GUIWorkflow:
    """Orchestrates the scraper workflow driven by GUI selections."""

    def __init__(self, manager):
        self.manager = manager
        self._selected_actions = set()
        self._selected_models = []
        self._selected_areas = []
        self._scrape_paid = False
        self._discord_enabled = False
        self._advanced = {}
        self._did_purge = False
        # Snapshot specific args so GUI toggles don't permanently clobber CLI intent.
        self._baseline_args = None
        self._scraper_thread = None
        # Daemon mode settings
        self._daemon_enabled = False
        self._daemon_interval = 30.0  # minutes
        self._daemon_notify = True
        self._daemon_sound = True
        self._daemon_stop = threading.Event()
        self._connect_signals()

    def _connect_signals(self):
        app_signals.action_selected.connect(self._on_action_selected)
        app_signals.models_selected.connect(self._on_models_selected)
        app_signals.areas_selected.connect(self._on_areas_selected)
        app_signals.scrape_paid_toggled.connect(self._on_scrape_paid)
        app_signals.discord_configured.connect(self._on_discord_configured)
        app_signals.daemon_configured.connect(self._on_daemon_configured)
        app_signals.stop_daemon_requested.connect(self._on_stop_daemon)
        app_signals.advanced_scrape_configured.connect(self._on_advanced)
        app_signals.cancel_scrape_requested.connect(self._on_cancel_scrape)

    def _on_action_selected(self, actions):
        self._selected_actions = actions
        log.info(f"[GUI Workflow] Actions set: {actions}")

    def _on_models_selected(self, models):
        self._selected_models = models
        log.info(f"[GUI Workflow] Models set: {len(models)} models")

    def _on_scrape_paid(self, enabled):
        self._scrape_paid = enabled

    def _on_discord_configured(self, enabled: bool):
        self._discord_enabled = bool(enabled)

    def _on_advanced(self, config):
        try:
            self._advanced = dict(config or {})
        except Exception:
            self._advanced = {}

    def _on_daemon_configured(self, enabled, interval, notify, sound):
        self._daemon_enabled = enabled
        self._daemon_interval = interval
        self._daemon_notify = notify
        self._daemon_sound = sound
        log.info(
            f"[GUI Workflow] Daemon: enabled={enabled}, "
            f"interval={interval}min, notify={notify}, sound={sound}"
        )

    def _on_stop_daemon(self):
        self._daemon_stop.set()
        log.info("[GUI Workflow] Daemon stop requested")

    def _on_cancel_scrape(self):
        """Best-effort: request the background pipeline to cancel ASAP."""
        try:
            _gui_cancel_event.set()
        except Exception:
            pass
        try:
            self._daemon_stop.set()
        except Exception:
            pass
        # Also inject a KeyboardInterrupt into the scraper thread so we don't rely
        # on progress hooks being called (messages/API phases can be long).
        try:
            t = getattr(self, "_scraper_thread", None)
            if t and getattr(t, "is_alive", lambda: False)():
                tid = getattr(t, "ident", None)
                if tid:
                    ok = _raise_in_thread(int(tid), KeyboardInterrupt)
                    if ok:
                        log.info("[GUI Workflow] Injected KeyboardInterrupt into scraper thread")
        except Exception:
            pass
        try:
            app_signals.status_message.emit("Cancelling scrape...")
            app_signals.log_message.emit("WARNING", "Cancel requested by user")
        except Exception:
            pass

    def _on_areas_selected(self, areas):
        self._selected_areas = areas
        log.info(f"[GUI Workflow] Areas set: {areas}")
        # Clear any previous stop request
        self._daemon_stop.clear()
        # This is the trigger to start the pipeline
        self._start_scraping()

    def _start_scraping(self):
        """Set args and launch the scraper in a background thread."""
        try:
            _gui_cancel_event.clear()
        except Exception:
            pass
        try:
            self._set_args()
        except Exception as e:
            log.error(f"Failed to configure scraper: {e}")
            app_signals.error_occurred.emit("Configuration Error", str(e))
            return

        # Run scraper in background thread to not block the GUI
        thread = threading.Thread(
            target=self._run_scraper_thread,
            daemon=True,
            name="gui-scraper",
        )
        self._scraper_thread = thread
        thread.start()

    def _set_args(self):
        """Programmatically set the CLI args based on GUI selections."""
        import ofscraper.utils.args.accessors.read as read_args
        import ofscraper.utils.args.mutators.write as write_args
        import ofscraper.utils.config.data as config_data
        import sys

        args = read_args.retriveArgs()

        # Record baseline once (first GUI-driven run) so we can restore values when
        # GUI options (like "rescrape") are toggled off on later runs.
        if self._baseline_args is None:
            try:
                self._baseline_args = {
                    "after": getattr(args, "after", None),
                    "no_cache": bool(getattr(args, "no_cache", False)),
                    "no_api_cache": bool(getattr(args, "no_api_cache", False)),
                    "discord": getattr(args, "discord", "OFF"),
                }
            except Exception:
                self._baseline_args = {
                    "after": None,
                    "no_cache": False,
                    "no_api_cache": False,
                    "discord": "OFF",
                }

        # Set actions
        args.action = list(self._selected_actions)

        # Set areas — these must be set BEFORE the scraper calls select_areas()
        # so that get_download_area() / get_like_area() find them and skip prompts.
        area_list = list(self._selected_areas)
        actions = self._selected_actions
        if "download" in actions:
            args.download_area = set(area_list)
        if "like" in actions or "unlike" in actions:
            args.like_area = set(area_list)

        # Set the selected model usernames so parsed_subscriptions_helper()
        # uses them directly instead of showing the TUI model selector prompt.
        args.usernames = [m.name for m in self._selected_models]

        # Set the scrape_paid flag
        args.scrape_paid = self._scrape_paid

        # Discord webhook updates: emulate `--discord NORMAL` when enabled AND
        # a webhook URL exists in config.
        try:
            has_webhook = bool((config_data.get_discord() or "").strip())
        except Exception:
            has_webhook = False
        argv = [str(a) for a in (getattr(sys, "argv", None) or [])]
        cli_sets_discord = any(
            a in {"-dc", "--discord"} or a.startswith("--discord=") for a in argv
        )
        if not cli_sets_discord:
            args.discord = "NORMAL" if (self._discord_enabled and has_webhook) else "OFF"

        # Advanced flags
        allow_dupes = bool(self._advanced.get("allow_dupe_downloads"))
        rescrape_all = bool(self._advanced.get("rescrape_all"))
        args.allow_dupe_downloads = allow_dupes

        # Force full scan by bypassing auto-after logic & caches
        if rescrape_all:
            args.after = 0
            args.no_cache = True
            args.no_api_cache = True
        else:
            # Restore baseline values (which may include CLI-provided flags)
            try:
                args.after = (self._baseline_args or {}).get("after", None)
                args.no_cache = bool((self._baseline_args or {}).get("no_cache", False))
                args.no_api_cache = bool((self._baseline_args or {}).get("no_api_cache", False))
            except Exception:
                pass

        write_args.setArgs(args)
        log.info(
            f"[GUI] Args configured: actions={args.action}, "
            f"areas={getattr(args, 'download_area', set())}, "
            f"users={args.usernames}"
        )
        app_signals.log_message.emit(
            "INFO",
            f"Config: actions={args.action}, "
            f"areas={list(getattr(args, 'download_area', set()))}, "
            f"users={args.usernames}",
        )

    def _send_notification(self, title, message):
        """Send a system tray notification (best-effort)."""
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon, QApplication
            from PyQt6.QtGui import QIcon
            app = QApplication.instance()
            if app and QSystemTrayIcon.isSystemTrayAvailable():
                tray = QSystemTrayIcon(app)
                tray.setIcon(QIcon())
                tray.show()
                tray.showMessage(
                    title, message,
                    QSystemTrayIcon.MessageIcon.Information, 5000,
                )
        except Exception as e:
            log.debug(f"Notification failed: {e}")

    def _play_sound(self):
        """Play a short alert sound (best-effort, Windows)."""
        try:
            import winsound
            winsound.Beep(1000, 300)
            import time
            time.sleep(0.1)
            winsound.Beep(1200, 300)
        except Exception:
            pass

    def _daemon_wait(self):
        """Wait for the daemon interval, emitting countdown updates.
        Returns True if the wait completed, False if stop was requested."""
        import time
        import math

        total_seconds = int(self._daemon_interval * 60)
        for remaining in range(total_seconds, 0, -1):
            if self._daemon_stop.is_set():
                return False
            mins = remaining // 60
            secs = remaining % 60
            app_signals.daemon_next_run.emit(f"Next scrape in {mins:02d}:{secs:02d}")
            time.sleep(1)
        return True

    def _run_scraper_thread(self):
        """Run the scraper pipeline in a background thread.
        If daemon mode is enabled, loops with the configured interval."""
        run_count = 0
        try:
            _install_gui_log_handler()
            _install_gui_live_stubs()
            _install_gui_progress_hooks()

            while True:
                if _gui_cancel_event.is_set():
                    raise KeyboardInterrupt()
                run_count += 1

                # Reset GUI progress counters/state each run so the overall progress bar
                # doesn't get stuck using previous run totals (especially after purge).
                try:
                    import ofscraper.actions.utils.globals as common_globals

                    common_globals.photo_count = 0
                    common_globals.video_count = 0
                    common_globals.audio_count = 0
                    common_globals.skipped = 0
                    common_globals.forced_skipped = 0
                    common_globals.total_bytes_downloaded = 0
                except Exception:
                    pass
                try:
                    _gui_state.total_media = 0
                except Exception:
                    pass
                try:
                    app_signals.overall_progress_updated.emit(0, 0)
                    app_signals.total_bytes_updated.emit(0)
                except Exception:
                    pass

                # One-time purge (only when requested) before first run
                if run_count == 1:
                    self._maybe_purge_before_scrape()

                # Notify on daemon re-runs (not the first run)
                if run_count > 1:
                    app_signals.daemon_run_starting.emit(run_count)
                    if self._daemon_sound:
                        self._play_sound()
                    if self._daemon_notify:
                        self._send_notification(
                            "OF-Scraper",
                            f"Daemon scrape #{run_count} starting...",
                        )

                app_signals.status_message.emit(
                    f"Scraping started... (run #{run_count})"
                    if self._daemon_enabled else "Scraping started..."
                )
                app_signals.log_message.emit(
                    "INFO",
                    f"Starting scraper pipeline (run #{run_count})..."
                    if self._daemon_enabled else "Starting scraper pipeline...",
                )

                try:
                    GUIScraperManager = _make_gui_scraper_manager()
                    scraping_manager = GUIScraperManager()
                    app_signals.log_message.emit(
                        "INFO",
                        f"Running scraper for {len(self._selected_models)} model(s): "
                        f"{', '.join(m.name for m in self._selected_models)}",
                    )
                    app_signals.log_message.emit(
                        "INFO",
                        f"Actions: {list(self._selected_actions)}, "
                        f"Areas: {list(self._selected_areas)}",
                    )
                    scraping_manager.runner()
                    app_signals.log_message.emit(
                        "INFO", "Scraper pipeline completed successfully"
                    )
                except Exception as e:
                    log.error(f"Scraper error on run #{run_count}: {e}")
                    log.error(traceback.format_exc())
                    app_signals.log_message.emit(
                        "ERROR", f"Scraper failed on run #{run_count}: {e}"
                    )
                    app_signals.log_message.emit(
                        "ERROR", traceback.format_exc()
                    )

                if _gui_cancel_event.is_set():
                    raise KeyboardInterrupt()

                # Load previously scraped content from DB
                app_signals.log_message.emit(
                    "INFO", "Loading content from database..."
                )
                _load_models_from_db(self._selected_models)

                app_signals.scraping_finished.emit()

                if not self._daemon_enabled:
                    app_signals.status_message.emit("Scraping complete")
                    app_signals.log_message.emit(
                        "INFO", "Scraping pipeline finished"
                    )
                    break

                # Daemon mode: wait for interval then re-run
                app_signals.status_message.emit(
                    f"Run #{run_count} complete. Waiting {self._daemon_interval:.0f} min..."
                )
                app_signals.log_message.emit(
                    "INFO",
                    f"Daemon run #{run_count} complete. "
                    f"Next run in {self._daemon_interval} minutes.",
                )

                if not self._daemon_wait():
                    # Stop was requested during wait
                    app_signals.status_message.emit("Daemon stopped")
                    app_signals.log_message.emit(
                        "INFO", "Daemon mode stopped by user"
                    )
                    app_signals.daemon_stopped.emit()
                    break

                # Re-set args for the next run (in case usernames need refresh)
                try:
                    self._set_args()
                except Exception as e:
                    log.error(f"Failed to re-configure for daemon run: {e}")
                    break

        except KeyboardInterrupt:
            app_signals.status_message.emit("Scraping cancelled")
            app_signals.log_message.emit("WARNING", "Scraping was cancelled")
        except Exception as e:
            log.error(f"Scraper error: {e}")
            log.debug(traceback.format_exc())
            app_signals.error_occurred.emit("Scraper Error", str(e))
            app_signals.log_message.emit("ERROR", f"Scraper failed: {e}")
        finally:
            _gui_state.stop_polling()
            _uninstall_gui_progress_hooks()
            _uninstall_gui_live_stubs()
            _uninstall_gui_log_handler()
            app_signals.scraping_finished.emit()

    def _maybe_purge_before_scrape(self):
        """Delete model DB and/or downloaded files before scraping, if requested."""
        if self._did_purge:
            return
        if not self._advanced:
            return
        if not bool(self._advanced.get("rescrape_all")):
            return

        delete_db = bool(self._advanced.get("delete_model_db"))
        delete_files = bool(self._advanced.get("delete_downloads"))
        if not (delete_db or delete_files):
            return

        # NOTE: In GUI mode the download action runs immediately after purge.
        # That means files/DB can be recreated right away during scraping.
        try:
            import ofscraper.utils.args.accessors.read as read_args

            actions = set(getattr(read_args.retriveArgs(), "action", []) or [])
            if "download" in actions:
                app_signals.log_message.emit(
                    "WARNING",
                    "Purge requested: existing DB/files will be deleted now, "
                    "but the download action may recreate the DB and re-download files immediately.",
                )
        except Exception:
            pass

        import pathlib
        import sqlite3
        import os
        import shutil

        import ofscraper.utils.paths.common as common_paths
        import ofscraper.classes.placeholder as placeholder

        roots = set()
        try:
            roots.add(pathlib.Path(common_paths.get_save_location()).resolve())
        except Exception:
            pass
        for mt in ("videos", "images", "audios"):
            try:
                roots.add(pathlib.Path(common_paths.get_save_location(mediatype=mt)).resolve())
            except Exception:
                pass

        def _safe_unlink(p: pathlib.Path):
            try:
                try:
                    # Windows: if read-only, make writable first
                    if p.exists():
                        os.chmod(p, 0o666)
                except Exception:
                    pass
                p.unlink(missing_ok=True)
                return True
            except Exception:
                return False

        def _safe_rmtree(p: pathlib.Path):
            try:
                def _onerror(func, path, exc_info):
                    try:
                        os.chmod(path, 0o777)
                        func(path)
                    except Exception:
                        # Re-raise original error so we can report failure
                        raise

                shutil.rmtree(p, onerror=_onerror)
                return not p.exists()
            except Exception:
                return False

        def _is_under_root(p: pathlib.Path) -> bool:
            try:
                p = p.resolve()
                for r in roots:
                    if r in p.parents or p == r:
                        return True
                return False
            except Exception:
                return False

        app_signals.log_message.emit(
            "WARNING",
            "Advanced: purging model DB/files before scraping (requested)",
        )

        for model in list(self._selected_models or []):
            model_id = getattr(model, "id", None)
            username = getattr(model, "name", None)
            if model_id is None or not username:
                continue

            db_path = pathlib.Path(
                placeholder.databasePlaceholder().databasePathHelper(model_id, username)
            )
            # Expected default location for the model's data directory.
            # We only use this for safe deletion verification; users can customize
            # metadata paths, so we must NOT guess beyond verifying the shape.
            try:
                expected_model_dir = (
                    pathlib.Path(common_paths.get_profile_path())
                    / ".data"
                    / str(model_id)
                ).resolve()
            except Exception:
                expected_model_dir = None
            try:
                actual_model_dir = db_path.parent.resolve()
            except Exception:
                actual_model_dir = db_path.parent

            # Delete downloaded files first (uses DB to locate paths)
            if delete_files and db_path.exists():
                try:
                    con = sqlite3.connect(db_path)
                    con.row_factory = sqlite3.Row
                    cur = con.cursor()
                    cur.execute(
                        "SELECT directory, filename FROM medias WHERE downloaded=(1) AND directory IS NOT NULL AND filename IS NOT NULL"
                    )
                    rows = cur.fetchall()
                    cur.close()
                    con.close()
                except Exception as e:
                    app_signals.log_message.emit(
                        "ERROR",
                        f"Failed to read downloaded file list for {username}: {e}",
                    )
                    rows = []

                deleted = 0
                for r in rows:
                    try:
                        d = r["directory"]
                        f = r["filename"]
                        if not d or not f:
                            continue
                        fp = pathlib.Path(d) / f
                        if not _is_under_root(fp):
                            continue
                        if fp.exists() and _safe_unlink(fp):
                            deleted += 1
                            # Best-effort: prune empty parent dirs up to save roots
                            try:
                                parent = fp.parent
                                while parent and _is_under_root(parent):
                                    # Stop at configured roots themselves
                                    if any(parent == rr for rr in roots):
                                        break
                                    # Only remove if empty
                                    if any(parent.iterdir()):
                                        break
                                    parent.rmdir()
                                    parent = parent.parent
                            except Exception:
                                pass
                    except Exception:
                        continue

                app_signals.log_message.emit(
                    "INFO", f"Deleted {deleted} files for {username}"
                )

                # If DB-based deletion missed files (common when DB paths are stale,
                # downloaded flags are wrong, or the directory format changed),
                # also delete the conventional save directory: <save_root>/<username>/.
                # This matches what users expect when selecting "delete downloaded content".
                removed_any_dir = False
                for r in list(roots):
                    try:
                        candidate = (pathlib.Path(r) / username).resolve()
                        # Safety: must be under the configured root and not equal to root
                        if not _is_under_root(candidate) or candidate == pathlib.Path(r).resolve():
                            continue
                        if candidate.exists() and candidate.is_dir():
                            if _safe_rmtree(candidate):
                                removed_any_dir = True
                                app_signals.log_message.emit(
                                    "INFO",
                                    f"Deleted download directory for {username}: {candidate}",
                                )
                            else:
                                app_signals.log_message.emit(
                                    "WARNING",
                                    f"Failed to delete download directory for {username} (may be locked): {candidate}",
                                )
                    except Exception:
                        continue
                if delete_files and not removed_any_dir and deleted == 0:
                    app_signals.log_message.emit(
                        "WARNING",
                        f"No downloaded files/directories were removed for {username}. "
                        "This can happen if the DB has no saved paths yet or the save_location differs.",
                    )

            # Delete DB
            if delete_db and db_path.exists():
                if _safe_unlink(db_path):
                    app_signals.log_message.emit(
                        "INFO", f"Deleted DB for {username}"
                    )
                    # Verify (best-effort). DB may be recreated later by the scraper.
                    try:
                        if db_path.exists():
                            app_signals.log_message.emit(
                                "WARNING",
                                f"DB file still exists for {username} (may be locked or recreated): {db_path}",
                            )
                    except Exception:
                        pass

                # Also remove WAL/SHM companions if present
                _safe_unlink(db_path.with_suffix(db_path.suffix + "-wal"))
                _safe_unlink(db_path.with_suffix(db_path.suffix + "-shm"))

            # If "Delete model DB" is selected, users generally expect the model's
            # profile data folder to be reset too (Explorer "Date created" etc).
            # Remove the entire model dir only when it matches the default pattern:
            # <profile>/.data/<model_id>/...
            if delete_db:
                try:
                    if (
                        expected_model_dir
                        and actual_model_dir.exists()
                        and actual_model_dir.resolve() == expected_model_dir
                    ):
                        if _safe_rmtree(actual_model_dir):
                            app_signals.log_message.emit(
                                "INFO",
                                f"Deleted model data directory for {username}: {actual_model_dir}",
                            )
                except Exception:
                    pass
            else:
                # Optionally remove empty parent dir under profile .data/<model_id>/
                try:
                    parent = db_path.parent
                    if parent.exists() and not any(parent.iterdir()):
                        _safe_rmtree(parent)
                except Exception:
                    pass

        self._did_purge = True
