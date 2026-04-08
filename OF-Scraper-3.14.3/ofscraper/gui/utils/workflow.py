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
    transient = False  # Rich Live attribute accessed by stop_live_screen

    def start(self, refresh=True):
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
            # Map custom TRACEBACK_ level (DEBUG+1 = 11) to ERROR for display.
            # These are real exception tracebacks caught by ofscraper's log.traceback_().
            if record.levelno == logging.DEBUG + 1:
                level = "ERROR"
            # Upstream ofscraper uses log.error() for high-visibility informational
            # output (version notices, download summaries, etc.) — not actual errors.
            # Downgrade those to WARNING so they don't appear in red.
            elif record.levelno == logging.ERROR:
                level = "WARNING"
            app_signals.log_message.emit(level, msg)
        except Exception:
            pass


def _install_gui_log_handler():
    """Attach a handler to the 'shared_other' logger so its output appears in
    the GUI console widget.

    We attach ONLY to 'shared_other' (not 'shared') to avoid duplicate console
    entries. ofscraper logs every message to both loggers simultaneously:
    - 'shared'       → Rich-markup version (used by RichHandler for terminal)
    - 'shared_other' → plain-text version (Rich markup already stripped)
    Attaching to both would fire our handler twice per message.  'shared_other'
    already delivers clean text, so no additional markup stripping is needed.
    """
    global _gui_log_handler
    _gui_log_handler = _GUILogHandler()
    # Level 11 = TRACEBACK_ (DEBUG+1) — catches exceptions logged via
    # log.traceback_() which the scraper uses for all error reporting.
    _gui_log_handler.setLevel(logging.DEBUG + 1)
    _gui_log_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    )
    logger = logging.getLogger("shared_other")
    logger.addHandler(_gui_log_handler)


def _uninstall_gui_log_handler():
    """Remove the GUI log handler from the logger."""
    global _gui_log_handler
    if _gui_log_handler is None:
        return
    logger = logging.getLogger("shared_other")
    logger.removeHandler(_gui_log_handler)
    _gui_log_handler = None


# ---------------------------------------------------------------------------
# Shared state for GUI progress hooks
# ---------------------------------------------------------------------------
class _GUIDownloadState:
    """Tracks per-user download state for the GUI progress bridge."""

    def __init__(self):
        self.total_media = 0
        self.locked_total = 0  # When > 0, gui_add_download_task won't override total_media
        self.check_completed = 0  # Accumulates completed count across process_dicts calls
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
    import ofscraper.commands.scraper.actions.utils.globals as common_globals

    global _orig_update_download_task
    global _orig_add_download_task
    global _orig_remove_download_task
    global _orig_add_like_task
    global _orig_increment_like_task
    global _orig_remove_like_task
    # In ofscraper 3.14.3 these are methods on ProgressManager objects
    _orig_update_download_task = progress_updater.download.update_overall_task
    _orig_add_download_task = progress_updater.download.add_overall_task
    _orig_remove_download_task = progress_updater.download.remove_overall_task
    _orig_add_like_task = progress_updater.like.add_overall_task
    _orig_increment_like_task = progress_updater.like.update_overall_task
    _orig_remove_like_task = progress_updater.like.remove_overall_task

    def gui_add_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        total = kwargs.get("total", 0)
        if _gui_state.locked_total <= 0:
            # Normal mode: use the task total and emit an initial 0/N signal.
            _gui_state.total_media = total
            result = _orig_add_download_task(*args, **kwargs)
            try:
                app_signals.overall_progress_updated.emit(0, _gui_state.total_media)
            except Exception:
                pass
        else:
            # Check mode: total_media is pre-set; do NOT emit (0, N) here because
            # that would reset the bar back to 0 at the start of every per-item call.
            result = _orig_add_download_task(*args, **kwargs)
        return result

    def gui_update_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_update_download_task(*args, **kwargs)
        try:
            total = _gui_state.total_media
            if _gui_state.locked_total > 0:
                # Check mode: common_globals counters reset per process_dicts call so
                # they don't accumulate. Use our own counter instead.
                _gui_state.check_completed += 1
                completed = _gui_state.check_completed
            else:
                completed = (
                    common_globals.photo_count
                    + common_globals.video_count
                    + common_globals.audio_count
                    + common_globals.skipped
                    + common_globals.forced_skipped
                )
            app_signals.overall_progress_updated.emit(completed, total)
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

    progress_updater.download.update_overall_task = gui_update_download_task
    progress_updater.download.add_overall_task = gui_add_download_task
    progress_updater.download.remove_overall_task = gui_remove_download_task

    # Like progress hooks (best-effort): surface like/unlike progress in the GUI.
    # In 3.14.3, like.py uses progress_updater.like.add/update/remove_overall_task
    like_task_map = {}  # underlying task -> gui_task_id
    like_task_counter = {"n": 0}

    def gui_add_like_task(*args, **kwargs):
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
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_remove_like_task(task)
        try:
            gui_id = like_task_map.pop(task, None)
            if gui_id:
                app_signals.progress_task_removed.emit(gui_id)
        except Exception:
            pass

    progress_updater.like.add_overall_task = gui_add_like_task
    progress_updater.like.update_overall_task = gui_increment_like_task
    progress_updater.like.remove_overall_task = gui_remove_like_task


def _uninstall_gui_progress_hooks():
    """Restore original progress_updater functions."""
    import ofscraper.utils.live.updater as progress_updater

    if _orig_update_download_task is not None:
        progress_updater.download.update_overall_task = _orig_update_download_task
    if _orig_add_download_task is not None:
        progress_updater.download.add_overall_task = _orig_add_download_task
    if _orig_remove_download_task is not None:
        progress_updater.download.remove_overall_task = _orig_remove_download_task
    if _orig_add_like_task is not None:
        progress_updater.like.add_overall_task = _orig_add_like_task
    if _orig_increment_like_task is not None:
        progress_updater.like.update_overall_task = _orig_increment_like_task
    if _orig_remove_like_task is not None:
        progress_updater.like.remove_overall_task = _orig_remove_like_task


# ---------------------------------------------------------------------------
# Media row builder
# ---------------------------------------------------------------------------
def _format_length_display(value):
    """Format duration into DD:HH:MM:SS for GUI display."""
    if value in (None, '', 'N/A'):
        return 'N/A'
    try:
        total_seconds = int(float(value))
    except Exception:
        return str(value)
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"


def _build_media_rows(media, username):
    """Convert 3.14.x Media objects into row dicts for the GUI table.

    The 3.14.x object model stores much of the useful display metadata on the
    underlying post/raw media payload rather than as always-populated direct
    Media attributes. Derive the visible columns from those richer sources so
    the table reflects what was actually scraped.
    """
    rows = []
    for count, ele in enumerate(media):
        try:
            post = getattr(ele, "post", None)
            raw_post = getattr(post, "_post", {}) or {}
            raw_media = getattr(ele, "_media", {}) or {}

            media_id = getattr(ele, "id", "") or raw_media.get("id") or ""
            post_id = (
                getattr(ele, "post_id", None)
                or getattr(post, "id", None)
                or raw_post.get("id")
                or ""
            )

            text = (
                getattr(post, "db_sanitized_text", None)
                or getattr(post, "text", None)
                or raw_post.get("text")
                or raw_post.get("rawText")
                or getattr(ele, "text", "")
                or ""
            )

            price = (
                getattr(post, "price", None)
                if post is not None
                else raw_post.get("price")
            )
            try:
                price = float(price or 0)
            except Exception:
                price = 0.0

            responsetype = (
                getattr(ele, "responsetype", None)
                or raw_media.get("responseType")
                or raw_post.get("responseType")
                or raw_post.get("from")
                or ""
            )
            responsetype = str(responsetype or "")

            post_media = getattr(post, "media", None)
            if post_media is None:
                post_media = raw_post.get("media") or []
            try:
                post_media_count = len(post_media or [])
            except Exception:
                post_media_count = 0

            media_type = getattr(ele, "mediatype", None) or raw_media.get("type") or raw_media.get("mediaType") or ""
            media_type = str(media_type or "").strip()
            media_type_lower = media_type.lower()
            source_url = str(getattr(ele, "url", "") or raw_media.get("source") or raw_media.get("src") or "")
            mimetype = str(raw_media.get("mimetype") or raw_media.get("mimeType") or "").lower()
            if not media_type or media_type_lower == "unknown":
                if getattr(ele, "mpd", None) or "video" in mimetype or source_url.lower().endswith((".mpd", ".mp4", ".m4v", ".mov")):
                    media_type = "Videos"
                elif "audio" in mimetype or source_url.lower().endswith((".mp3", ".m4a", ".wav", ".ogg")):
                    media_type = "Audios"
                elif "image" in mimetype or source_url.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    media_type = "Images"
                else:
                    media_type = "unknown"

            duration = (
                getattr(ele, "numeric_duration", None)
                or raw_media.get("duration")
                or raw_media.get("sourceDuration")
                or "N/A"
            )

            post_date = (
                getattr(ele, "formatted_postdate", None)
                or getattr(ele, "formatted_date", None)
                or raw_post.get("postedAt")
                or raw_post.get("createdAt")
                or ""
            )

            downloaded = bool(getattr(ele, "downloaded", False))
            canview = bool(getattr(ele, "canview", True))
            unlocked = bool(getattr(ele, "unlocked", canview)) if hasattr(ele, 'unlocked') else canview
            preview = bool(getattr(post, "preview", False) if post is not None else raw_post.get("preview", False))
            post_opened = bool(getattr(post, "opened", True) if post is not None else raw_post.get("opened", True))

            if not unlocked:
                cart_status = "Locked"
                dl_display = "N/A"
                ul_display = "Locked"
            else:
                cart_status = "[downloaded]" if downloaded else "[]"
                dl_display = str(bool(downloaded))
                if price > 0 and responsetype.lower() in ("message", "messages") and not post_opened:
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
                    "mediatype": media_type,
                    "post_date": post_date,
                    "length": duration,
                    "responsetype": responsetype,
                    "price": "Free" if price == 0 else "{:.2f}".format(price),
                    "post_id": post_id,
                    "media_id": media_id,
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


def _load_models_from_db(selected_models, date_range=None, stats_only=False):
    """Query the DB for all media records of each selected model and emit
    them to the GUI table.  Runs synchronously (called from the scraper
    background thread after the pipeline finishes).

    date_range: optional dict {"enabled": bool, "from_date": "YYYY-MM-DD",
                               "to_date": "YYYY-MM-DD"} — when enabled, only
    rows whose posted_at falls within the range are emitted to the table so
    the display matches what was actually scraped.

    stats_only: when True, compute and return per-model stats without emitting
    data_replace signals (used for normal GUI downloads where live rows are
    already displayed and should not be replaced).

    Returns a dict: {username: {"photos": N, "videos": N, "audios": N,
                                "dl_photos": N, "dl_videos": N, "dl_audios": N}}
    so callers can report accurate download stats.
    """
    import pathlib
    import sqlite3

    from filelock import FileLock

    import ofscraper.classes.placeholder as placeholder
    import ofscraper.utils.paths.common as common_paths

    # Pre-parse date bounds once for efficient per-row comparison
    _dr_from = None
    _dr_to = None
    if date_range and date_range.get("enabled"):
        try:
            import arrow as _arrow
            if date_range.get("from_date"):
                _dr_from = _arrow.get(date_range["from_date"], "YYYY-MM-DD")
            if date_range.get("to_date"):
                _dr_to = _arrow.get(date_range["to_date"], "YYYY-MM-DD").ceil("day")
        except Exception:
            pass

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

    per_model_stats = {}  # {username: {photos, videos, audios, dl_photos, ...}}

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
            log.warning(f"[DB Load] Checking DB path for {username}: {database_path}")
            if not database_path.exists():
                log.warning(f"[DB Load] No DB file for {username} at {database_path} — skipping")
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

            log.warning(f"[DB Load] Found {len(data)} media records in DB for {username}")

            # Apply date range filter if active — keep only rows within the
            # scraping window so the table reflects the scraped period.
            if (_dr_from or _dr_to) and data:
                try:
                    import arrow as _arrow
                    filtered = []
                    skipped = 0
                    for _r in data:
                        _posted = _r.get("posted_at") or _r.get("created_at")
                        if not _posted:
                            skipped += 1
                            continue
                        try:
                            _dt = _arrow.get(_posted)
                            if _dr_from and _dt < _dr_from:
                                skipped += 1
                                continue
                            if _dr_to and _dt > _dr_to:
                                skipped += 1
                                continue
                            filtered.append(_r)
                        except Exception:
                            filtered.append(_r)
                    log.warning(
                        f"[DB Load] Date filter: kept {len(filtered)}, "
                        f"skipped {skipped} out-of-range records for {username}"
                    )
                    data = filtered
                except Exception as _fe:
                    log.warning(f"[DB Load] Date filter failed for {username}: {_fe}")

            if data:
                # Compute per-model media counts for Discord summary
                _st = {"photos": 0, "videos": 0, "audios": 0,
                       "dl_photos": 0, "dl_videos": 0, "dl_audios": 0}
                for _row in data:
                    # DB stores "Images", "Videos", "Audios" (capitalized plural)
                    _mt = (_row.get("media_type") or "").lower()
                    _dl = bool(_row.get("downloaded"))
                    if _mt in ("image", "images"):
                        _st["photos"] += 1
                        if _dl:
                            _st["dl_photos"] += 1
                    elif _mt in ("video", "videos", "gif", "gifs"):
                        _st["videos"] += 1
                        if _dl:
                            _st["dl_videos"] += 1
                    elif _mt in ("audio", "audios"):
                        _st["audios"] += 1
                        if _dl:
                            _st["dl_audios"] += 1
                per_model_stats[username] = _st

                if not stats_only:
                    rows = _build_db_rows(data, username, post_info)
                    if rows:
                        # Use data_replace so the DB result replaces any rows
                        # emitted by the live scraper pipeline, preventing duplicates.
                        app_signals.data_replace.emit(rows)
                        log.info(
                            f"Loaded {len(rows)} items from DB for {username}"
                        )
        except Exception as e:
            log.warning(f"[DB Load] Failed to load DB data for {username}: {e}")
            import traceback as _tb
            log.warning(f"[DB Load] Traceback: {_tb.format_exc()}")
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

    return per_model_stats


def _emit_download_status(media, model_id, username, extra_table_rows=None):
    """Query the DB for downloaded media IDs and emit cell_update signals.

    extra_table_rows: optional list of all row dicts (from get_rows_for_gui_table)
    for items that may have been filtered from the download queue (already downloaded,
    profile images via the profile cache, etc.).  Each row is checked against the
    media DB; Profile-type rows also fall back to the profile key-value cache.
    """
    try:
        from ofscraper.db.operations_.media import get_media_ids_downloaded

        downloaded_set = get_media_ids_downloaded(
            model_id=model_id, username=username
        )
        handled_ids = set()
        for ele in media:
            media_id = getattr(ele, "id", None)
            if media_id is None:
                continue
            handled_ids.add(str(media_id))
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

        # Items filtered from the download queue (already downloaded, profile images
        # cached via separate cache, etc.) never appear in `media` above.
        # Check each against the media DB; Profile rows also fall back to the
        # profile key-value cache (avatar_{username}_{post_id}).
        if extra_table_rows:
            try:
                import ofscraper.utils.cache.cache as _prof_cache
            except Exception:
                _prof_cache = None
            for row in extra_table_rows:
                media_id = str(row.get('media_id', '') or '')
                if not media_id or media_id in handled_ids:
                    continue
                post_id = str(row.get('post_id', '') or '')
                responsetype = str(row.get('responsetype', '') or '').capitalize()
                # Primary: media DB (populated by mark_media_as_downloaded)
                is_downloaded = media_id in downloaded_set
                # Fallback for Profile rows: profile key-value cache
                if not is_downloaded and responsetype == 'Profile' and _prof_cache and post_id:
                    is_downloaded = bool(
                        _prof_cache.get(f"avatar_{username}_{post_id}", default=False)
                    )
                app_signals.cell_update.emit(media_id, "downloaded", str(is_downloaded))
                if is_downloaded:
                    app_signals.cell_update.emit(media_id, "download_cart", "[downloaded]")
    except Exception as e:
        log.debug(f"Failed to emit download status: {e}")


# ---------------------------------------------------------------------------
# GUI scraper manager
# ---------------------------------------------------------------------------
def _make_gui_scraper_manager():
    """Create a scraperManager subclass that emits media data to the GUI."""
    from ofscraper.commands.scraper.scraper import scraperManager
    import ofscraper.utils.args.accessors.read as read_args
    from ofscraper.commands.scraper.actions.download.download import downloader
    import ofscraper.commands.scraper.actions.like.like as like_action

    class GUIScraperManager(scraperManager):
        """scraperManager subclass that emits media rows to the GUI table
        before executing download/like actions for each user."""

        async def _execute_user_action(self, ele, postcollection):
            import ofscraper.utils.settings as _settings
            # Use the fuller GUI table media set for display so duplicates/reposts
            # and locked/paid rows remain visible, while downloads still use the
            # normal processed queue.
            media = postcollection.get_media_for_processing()
            table_rows = postcollection.get_rows_for_gui_table()
            like_posts = postcollection.get_posts_to_like()
            posts = postcollection.get_posts_for_text_download()

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

            # Emit GUI table rows before running actions
            if table_rows and ele:
                rows = table_rows
                if rows:
                    try:
                        workflow = getattr(self, "caller", None) or getattr(self, "workflow", None)
                        emitted_via_replace = False
                        try:
                            if workflow is not None and not getattr(workflow, "_live_rows_emitted", False):
                                app_signals.data_replace.emit(rows)
                                workflow._live_rows_emitted = True
                                emitted_via_replace = True
                                log.info(f"[GUI] Emitted {len(rows)} live rows via data_replace")
                        except Exception:
                            emitted_via_replace = False

                        if not emitted_via_replace:
                            app_signals.data_loading_finished.emit(rows)
                            if workflow is not None:
                                workflow._live_rows_emitted = True
                            log.info(f"[GUI] Emitted {len(rows)} live rows via data_loading_finished")
                    except Exception as e:
                        log.debug(f"Failed to emit table data: {e}")

            # Run the actual actions (download/like/unlike)
            actions = _settings.get_settings().actions
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
                        # Still update table row statuses (e.g. profile images and
                        # already-downloaded items filtered from the queue).
                        _emit_download_status([], model_id, username, extra_table_rows=table_rows)
                        continue
                    # Start periodic DB polling for real-time Downloaded updates
                    _gui_state.start_polling(media, model_id, username)
                    try:
                        app_signals.log_message.emit(
                            "INFO",
                            f"Starting download of {len(media)} items for {username}...",
                        )
                        await downloader(
                            posts=posts,
                            media=media,
                            model_id=model_id,
                            username=username,
                        )
                        out.append([])
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
                        # Stop polling and do a final status sweep.
                        # Pass all table rows so filtered items (profile images,
                        # already-downloaded items) also get their status updated.
                        _gui_state.stop_polling()
                        _emit_download_status(media, model_id, username, extra_table_rows=table_rows)
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
        self._selected_mediatypes = []
        self._include_text = False
        self._scrape_paid = False
        self._discord_level = "OFF"
        self._advanced = {}
        self._did_purge = False
        self._manual_urls = []
        # Date range filter from area_selector_page
        self._date_range = {}
        # Snapshot specific args so GUI toggles don't permanently clobber CLI intent.
        self._baseline_args = None
        self._scraper_thread = None
        # Daemon mode settings
        self._daemon_enabled = False
        self._daemon_interval = 30.0  # minutes
        self._daemon_notify = True
        self._daemon_sound = True
        self._daemon_stop = threading.Event()
        self._msg_check_filter = "paid_only"  # "paid_only" | "free_only" | "all"
        self._live_rows_emitted = False
        self._connect_signals()
        # Mute Discord at startup — the handler is initialized from the config
        # file which may have a non-OFF level, causing every WARNING+ message
        # during model loading, API calls, etc. to be sent to Discord.
        # We re-enable it only when the user explicitly starts a scrape.
        self._mute_discord_handler()

    def _connect_signals(self):
        app_signals.action_selected.connect(self._on_action_selected)
        app_signals.models_selected.connect(self._on_models_selected)
        app_signals.areas_selected.connect(self._on_areas_selected)
        app_signals.mediatypes_configured.connect(self._on_mediatypes_configured)
        app_signals.include_text_configured.connect(self._on_include_text_configured)
        app_signals.scrape_paid_toggled.connect(self._on_scrape_paid)
        app_signals.discord_configured.connect(self._on_discord_configured)
        app_signals.daemon_configured.connect(self._on_daemon_configured)
        app_signals.stop_daemon_requested.connect(self._on_stop_daemon)
        app_signals.advanced_scrape_configured.connect(self._on_advanced)
        app_signals.date_range_configured.connect(self._on_date_range_configured)
        app_signals.cancel_scrape_requested.connect(self._on_cancel_scrape)
        app_signals.downloads_queued.connect(self._on_downloads_queued)
        app_signals.msg_check_include_free_toggled.connect(self._on_msg_check_include_free)
        app_signals.manual_urls_confirmed.connect(self._on_manual_urls_confirmed)

    def _on_action_selected(self, actions):
        self._selected_actions = actions
        log.info(f"[GUI Workflow] Actions set: {actions}")

    def _on_manual_urls_confirmed(self, urls):
        self._manual_urls = list(urls)
        self._selected_actions = {"manual_url"}
        log.info(f"[GUI Workflow] Manual URL mode: {len(urls)} URL(s)")
        self._daemon_stop.clear()
        self._start_scraping()

    def _on_models_selected(self, models):
        self._selected_models = models
        log.info(f"[GUI Workflow] Models set: {len(models)} models")
        # Check modes auto-start as soon as models are confirmed —
        # no separate "Start Scraping" click required.
        if bool(self._selected_actions & self._CHECK_MODES):
            self._daemon_stop.clear()
            self._start_scraping()

    def _on_scrape_paid(self, enabled):
        self._scrape_paid = enabled

    def _on_msg_check_include_free(self, filter_value):
        self._msg_check_filter = filter_value  # "paid_only", "free_only", or "all"

    def _on_discord_configured(self, level: str):
        self._discord_level = level if level in ("OFF", "LOW", "NORMAL") else "OFF"

    @staticmethod
    def _mute_discord_handler():
        """Set the Discord log handler to level 100 (effectively OFF)."""
        try:
            import logging as _lg
            from ofscraper.utils.logs.classes.handlers.discord import (
                DiscordHandler as _DH,
            )
            for _h in _lg.getLogger("shared").handlers:
                if isinstance(_h, _DH):
                    _h.setLevel(100)
                    break
        except Exception:
            pass

    def _on_advanced(self, config):
        try:
            self._advanced = dict(config or {})
        except Exception:
            self._advanced = {}

    def _on_date_range_configured(self, config):
        try:
            self._date_range = dict(config or {})
        except Exception:
            self._date_range = {}

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

    def _on_mediatypes_configured(self, mediatypes):
        self._selected_mediatypes = mediatypes
        log.info(f"[GUI Workflow] Media types set: {mediatypes}")

    def _on_include_text_configured(self, include: bool):
        self._include_text = include
        log.info(f"[GUI Workflow] Include post text: {include}")

    def _on_areas_selected(self, areas):
        self._selected_areas = areas
        log.info(f"[GUI Workflow] Areas set: {areas}")
        if bool(self._selected_actions & self._CHECK_MODES):
            # areas_selected is emitted early from the area selector (before model
            # selection).  If models are already known (e.g. user clicked "Start
            # Scraping" again to re-run), start immediately.  Otherwise wait —
            # _on_models_selected will fire the run once models are confirmed.
            if self._selected_models:
                self._daemon_stop.clear()
                self._start_scraping()
            return
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
        self._live_rows_emitted = False
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

    _CHECK_MODES = {"post_check", "msg_check", "paid_check", "story_check"}

    def _set_manual_url_args(self, args, write_args, _settings):
        """Set CLI args for manual URL / post-ID scraping."""
        args.command = "manual"
        args.url = list(self._manual_urls)
        args.action = ["download"]
        args.actions = ["download"]
        write_args.setArgs(args)
        try:
            _settings.update_settings()
        except Exception:
            pass
        log.info(
            f"[GUI Manual URL] Args: command=manual, {len(self._manual_urls)} URL(s)"
        )

    def _set_check_args(self, args, write_args, _settings):
        """Set CLI args for a check-mode operation."""
        check_mode = (self._selected_actions & self._CHECK_MODES).pop()
        args.command = check_mode
        usernames = [m.name for m in self._selected_models]
        if check_mode in ("post_check", "msg_check"):
            args.url = usernames
            args.check_usernames = []
        else:
            args.check_usernames = usernames
            args.url = []
        if check_mode == "post_check":
            args.check_area = list(self._selected_areas)
        args.force_all = True
        args.after = 0
        args.action = ["download"]
        args.actions = ["download"]
        write_args.setArgs(args)
        try:
            _settings.update_settings()
        except Exception:
            pass
        log.info(
            f"[GUI Check] Args: command={check_mode}, "
            f"users={usernames}, areas={getattr(args, 'check_area', [])}"
        )

    def _set_args(self):
        """Programmatically set the CLI args based on GUI selections."""
        import ofscraper.utils.args.accessors.read as read_args
        import ofscraper.utils.args.mutators.write as write_args
        import ofscraper.utils.config.data as config_data
        import ofscraper.utils.settings as _settings
        import sys

        args = read_args.retriveArgs()

        # Manual URL / post-ID mode — set command=manual and skip everything else
        if self._selected_actions == {"manual_url"}:
            self._set_manual_url_args(args, write_args, _settings)
            return

        # Check mode: configure separately and return early
        if bool(self._selected_actions & self._CHECK_MODES):
            self._set_check_args(args, write_args, _settings)
            return

        # Record baseline once (first GUI-driven run) so we can restore values when
        # GUI options (like "rescrape") are toggled off on later runs.
        if self._baseline_args is None:
            try:
                self._baseline_args = {
                    "after": getattr(args, "after", None),
                    "no_cache": bool(getattr(args, "no_cache", False)),
                    "no_api_cache": bool(getattr(args, "no_api_cache", False)),
                    "discord_level": getattr(args, "discord_level", "OFF"),
                }
            except Exception:
                self._baseline_args = {
                    "after": None,
                    "no_cache": False,
                    "no_api_cache": False,
                    "discord_level": "OFF",
                }

        # Set actions (3.14.3 scraper checks args.actions; keep args.action for compat)
        args.action = list(self._selected_actions)
        args.actions = list(self._selected_actions)

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

        # Set media types — use GUI selection so it overrides the config filter.
        # An explicit non-empty list takes precedence over config_data.get_filter()
        # in settings.py (merged.mediatypes = args.mediatypes or config_data.get_filter()).
        if self._selected_mediatypes:
            args.mediatypes = list(self._selected_mediatypes)

        # Include post text
        if self._include_text:
            args.text = True

        # Discord webhook updates: set discord_level from GUI selection.
        # The CLI arg --discord maps to args.discord_level (not args.discord).
        argv = [str(a) for a in (getattr(sys, "argv", None) or [])]
        cli_sets_discord = any(
            a in {"-dc", "--discord"} or a.startswith("--discord=") for a in argv
        )
        if not cli_sets_discord:
            args.discord_level = self._discord_level

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

            # Apply GUI date range filter (overrides baseline after/before)
            try:
                import arrow as _arrow
                dr = self._date_range or {}
                if dr.get("enabled"):
                    from_date = dr.get("from_date")
                    to_date = dr.get("to_date")
                    if from_date:
                        args.after = _arrow.get(from_date, "YYYY-MM-DD")
                    if to_date:
                        # include the full to_date day
                        args.before = _arrow.get(to_date, "YYYY-MM-DD").ceil("day")
                    else:
                        args.before = None
                else:
                    args.before = None
            except Exception:
                pass

        write_args.setArgs(args)
        # Invalidate the settings cache so settings.get_settings() picks up the new
        # actions, after, before, etc. that we just wrote.  Without this,
        # scraperManager.run_action returns False (using the stale startup cache)
        # and runner() skips all download/like work.
        try:
            _settings.update_settings()
        except Exception:
            pass
        log.info(
            f"[GUI] Args configured: actions={args.actions}, "
            f"areas={getattr(args, 'download_area', set())}, "
            f"users={args.usernames}, "
            f"after={getattr(args, 'after', None)}, "
            f"before={getattr(args, 'before', None)}"
        )
        app_signals.log_message.emit(
            "INFO",
            f"Config: actions={args.action}, "
            f"areas={list(getattr(args, 'download_area', set()))}, "
            f"users={args.usernames}",
        )

    def _send_notification(self, title, message):
        """Send a system tray notification via signal (thread-safe).
        The actual QSystemTrayIcon work happens on the main GUI thread."""
        try:
            app_signals.show_notification.emit(title, message)
        except Exception as e:
            log.debug(f"Notification signal failed: {e}")

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

    def _run_check_mode(self):
        """Run a check mode (post_check / msg_check / paid_check / story_check).

        Calls ``check.gui_checker()`` which fetches API data and emits
        ``data_replace`` with the resulting rows.  Downloads are handled later
        via the ``downloads_queued`` signal when the user sends cart items.
        """
        import ofscraper.commands.check as check_mod

        check_mode = (self._selected_actions & self._CHECK_MODES).pop()
        app_signals.status_message.emit(f"Running {check_mode}...")
        app_signals.log_message.emit("INFO", f"Starting check mode: {check_mode}")
        try:
            check_mod.gui_checker(
                check_mode,
                msg_filter=self._msg_check_filter,
            )
            app_signals.log_message.emit("INFO", f"Check mode {check_mode} complete")
            app_signals.status_message.emit(
                "Check mode complete — select items in the table and click 'Send Downloads'"
            )
        except Exception as e:
            log.error(f"Check mode error: {e}")
            log.debug(traceback.format_exc())
            app_signals.log_message.emit("ERROR", f"Check mode failed: {e}")
            app_signals.error_occurred.emit("Check Mode Error", str(e))
            app_signals.scraping_finished.emit()

    def _on_downloads_queued(self, row_data_list):
        """Handle download requests from the check-mode table.

        Only acts when the current action is a check mode; regular scrapes
        handle their own downloads via the downloader pipeline.
        """
        if not bool(self._selected_actions & self._CHECK_MODES):
            return
        if not row_data_list:
            return
        t = threading.Thread(
            target=self._run_check_downloads,
            args=(row_data_list,),
            daemon=True,
            name="gui-check-downloads",
        )
        t.start()

    def _run_check_downloads(self, row_data_list):
        """Process download requests from the check-mode cart in a background thread."""
        from collections import defaultdict
        import ofscraper.commands.check as check_mod

        app_signals.status_message.emit("Downloading selected check items...")
        app_signals.log_message.emit(
            "INFO", f"Processing {len(row_data_list)} check-mode download(s)"
        )

        _install_gui_log_handler()
        _install_gui_live_stubs()
        _install_gui_progress_hooks()

        # Pre-set the total BEFORE any add_overall_task calls so the progress bar
        # shows X/N instead of resetting to 1/1 per item (process_dicts calls
        # add_overall_task with total=1 for each individual item in check mode).
        total_items = len(row_data_list)
        _gui_state.locked_total = total_items
        _gui_state.total_media = total_items
        _gui_state.check_completed = 0
        try:
            import ofscraper.commands.scraper.actions.utils.globals as _cg
            _cg.photo_count = 0
            _cg.video_count = 0
            _cg.audio_count = 0
            _cg.skipped = 0
            _cg.forced_skipped = 0
            _cg.total_bytes_downloaded = 0
        except Exception:
            pass
        try:
            app_signals.overall_progress_updated.emit(0, total_items)
            app_signals.total_bytes_updated.emit(0)
        except Exception:
            pass

        try:
            user_cart = defaultdict(lambda: {"posts": [], "media": [], "rows": []})
            for row_data in row_data_list:
                try:
                    media_item, post_item, username, model_id = check_mod._get_data_from_row(row_data)
                    user_cart[model_id]["posts"].append(post_item)
                    user_cart[model_id]["media"].append(media_item)
                    key = str(row_data.get("media_id", ""))
                    user_cart[model_id]["rows"].append((key, row_data))
                    user_cart[model_id]["username"] = username
                except Exception as e:
                    log.error(f"Check download row error: {e}")

            for model_id, data in user_cart.items():
                username = data.get("username", "")
                try:
                    check_mod._process_user_batch(
                        username, model_id, data["media"], data["posts"], data["rows"]
                    )
                except Exception as e:
                    log.error(f"Check download batch error for {username}: {e}")
                    log.debug(traceback.format_exc())
        finally:
            _gui_state.locked_total = 0
            _uninstall_gui_progress_hooks()
            _uninstall_gui_live_stubs()
            _uninstall_gui_log_handler()

        app_signals.status_message.emit("Check mode downloads complete")
        app_signals.log_message.emit("INFO", "Check mode download processing complete")

    def _run_scraper_thread(self):
        """Run the scraper pipeline in a background thread.
        If daemon mode is enabled, loops with the configured interval."""
        run_count = 0
        try:
            _install_gui_log_handler()
            _install_gui_live_stubs()
            _install_gui_progress_hooks()

            # Check mode: one-shot run — no daemon loop
            if bool(self._selected_actions & self._CHECK_MODES):
                self._run_check_mode()
                return

            while True:
                if _gui_cancel_event.is_set():
                    raise KeyboardInterrupt()
                run_count += 1

                # Reset live-rows flag each iteration so daemon re-runs don't inherit
                # run #1's True value and incorrectly skip DB table replacement when
                # the current run produced no live rows (e.g. after a crash).
                self._live_rows_emitted = False

                # Reset GUI progress counters/state each run so the overall progress bar
                # doesn't get stuck using previous run totals (especially after purge).
                try:
                    import ofscraper.commands.scraper.actions.utils.globals as common_globals

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
                    # Reset the like tracker for this run so results from
                    # previous daemon runs don't bleed into the new one.
                    import ofscraper.commands.scraper.actions.like.like as _like_mod
                    _like_mod._GUI_LIKE_TRACKER = {}

                    GUIScraperManager = _make_gui_scraper_manager()
                    scraping_manager = GUIScraperManager()
                    scraping_manager.workflow = self
                    if self._selected_actions == {"manual_url"}:
                        app_signals.log_message.emit(
                            "INFO",
                            f"Running manual URL scrape: {len(self._manual_urls)} URL(s)",
                        )
                    else:
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

                    # Sync the Discord handler's level to the current discord_level.
                    # The handler is created at startup before the GUI sets discord_level,
                    # so it defaults to "OFF" (level 100) and must be updated here.
                    try:
                        import logging as _logging
                        import ofscraper.utils.logs.utils.level as _log_level
                        import ofscraper.utils.settings as _settings
                        from ofscraper.utils.logs.classes.handlers.discord import (
                            DiscordHandler as _DiscordHandler,
                        )
                        _level_str = (
                            getattr(_settings.get_settings(), "discord_level", None)
                            or "OFF"
                        )
                        _level = _log_level.getLevel(_level_str)
                        for _h in _logging.getLogger("shared").handlers:
                            if isinstance(_h, _DiscordHandler):
                                _h.setLevel(_level)
                                break
                    except Exception:
                        pass

                    if self._selected_actions == {"manual_url"}:
                        import ofscraper.commands.manual as _manual_cmd
                        _manual_cmd.manual_download()
                    else:
                        # Filter global paid scrape to only selected models.
                        # scrape_paid_all() uses the global /posts/paid/all endpoint
                        # which returns ALL purchased content across ALL subscriptions.
                        # By patching process_paid_dict we let process_all_paid() write
                        # metadata for every creator (unavoidable) but only DOWNLOAD
                        # content for the models the user actually selected.
                        _orig_process_paid_dict = None
                        if self._scrape_paid and self._selected_models:
                            try:
                                import ofscraper.data.posts.scrape_paid as _spm
                                import ofscraper.data.posts.post as _OF
                                _orig_process_paid_dict = _spm.process_paid_dict
                                _selected_usernames_lower = {
                                    m.name.lower() for m in self._selected_models
                                }
                                app_signals.log_message.emit(
                                    "INFO",
                                    f"Filtering paid scrape to selected models: {[m.name for m in self._selected_models]}",
                                )

                                async def _filtered_process_paid_dict():
                                    user_dict = await _OF.process_all_paid()
                                    filtered = {
                                        k: v for k, v in user_dict.items()
                                        if v.get("username", "").lower() in _selected_usernames_lower
                                    }
                                    length = len(filtered)
                                    for count, value in enumerate(filtered.values()):
                                        yield count, value, length

                                _spm.process_paid_dict = _filtered_process_paid_dict
                            except Exception as _patch_err:
                                log.warning(f"Could not patch process_paid_dict: {_patch_err}")
                                _orig_process_paid_dict = None

                        try:
                            scraping_manager.runner()
                        finally:
                            if _orig_process_paid_dict is not None:
                                try:
                                    import ofscraper.data.posts.scrape_paid as _spm
                                    _spm.process_paid_dict = _orig_process_paid_dict
                                except Exception:
                                    pass

                    # Mute Discord immediately after runner() — the handler
                    # was enabled for scrape notifications and must be silenced
                    # before the DB load to avoid spam.  The actual summary is
                    # sent AFTER _load_models_from_db (which uses FileLock and
                    # is guaranteed to see fully committed DB data).
                    self._mute_discord_handler()

                    app_signals.log_message.emit(
                        "INFO", "Scraper pipeline completed successfully"
                    )
                except Exception as e:
                    # Mute Discord first so the error/traceback doesn't get posted there.
                    self._mute_discord_handler()
                    log.error(f"Scraper error on run #{run_count}: {e}")
                    log.debug(traceback.format_exc())
                    app_signals.log_message.emit(
                        "ERROR", f"Scraper failed on run #{run_count}: {e}"
                    )
                    app_signals.log_message.emit(
                        "DEBUG", traceback.format_exc()
                    )

                if _gui_cancel_event.is_set():
                    raise KeyboardInterrupt()

                # Load previously scraped content from DB.
                # _load_models_from_db acquires FileLock so it always sees
                # fully committed data.  It returns per-model media counts
                # which we use for the Discord summary.
                _db_stats = {}
                # scrape_paid_all() bypasses _execute_user_action entirely, so
                # live rows are never emitted for content fetched via the global
                # paid endpoint. We must load from DB afterward to show those rows.
                # Using self._scrape_paid (not "Purchased" in areas) because:
                #   - scrape_paid=True  → scrape_paid_all() was called → no live rows → DB load needed
                #   - scrape_paid=False + "Purchased" in areas → per-user endpoint → live rows emitted → DB load NOT needed
                _used_global_paid = self._scrape_paid
                is_normal_gui_download = (
                    self._selected_actions == {"download"}
                    and self._selected_models
                    and self._live_rows_emitted
                    and not _used_global_paid
                    and not bool(self._selected_actions & self._CHECK_MODES)
                    and run_count == 1  # daemon re-runs always reload full DB to show complete state
                )
                if is_normal_gui_download:
                    app_signals.log_message.emit(
                        "INFO", "Skipping DB table replacement for normal GUI download scrape; keeping live rows from this run..."
                    )
                    # Still read DB stats so the Discord summary shows correct counts.
                    _db_stats = _load_models_from_db(
                        self._selected_models,
                        date_range=self._date_range or {},
                        stats_only=True,
                    )
                elif self._live_rows_emitted and not _used_global_paid and run_count == 1:
                    app_signals.log_message.emit(
                        "INFO", "Skipping DB table replacement because live rows were already emitted for this run..."
                    )
                else:
                    app_signals.log_message.emit(
                        "INFO", "Loading content from database..."
                    )
                    _db_stats = _load_models_from_db(
                        self._selected_models,
                        date_range=self._date_range or {},
                    )

                # Post per-model stats to Discord now that we have accurate
                # counts from the FileLock-protected DB read above.
                if self._discord_level != "OFF":
                    try:
                        import logging as _dlog
                        # Briefly re-enable Discord just for this summary.
                        import ofscraper.utils.logs.utils.level as _ll
                        from ofscraper.utils.logs.classes.handlers.discord import (
                            DiscordHandler as _DH,
                        )
                        _lvl = _ll.getLevel(self._discord_level)
                        for _h in _dlog.getLogger("shared").handlers:
                            if isinstance(_h, _DH):
                                _h.setLevel(_lvl)
                                break
                        # Per-run download counts from common_globals (reset each daemon iteration).
                        try:
                            import ofscraper.commands.scraper.actions.utils.globals as _cg_disc
                            _run_photos = int(_cg_disc.photo_count)
                            _run_videos = int(_cg_disc.video_count)
                            _run_audios = int(_cg_disc.audio_count)
                        except Exception:
                            _run_photos = _run_videos = _run_audios = 0
                        _run_new = _run_photos + _run_videos + _run_audios
                        # @here ping if user enabled it and new content was found
                        _daemon_ping = False
                        if self._daemon_enabled and _run_new > 0:
                            try:
                                from ofscraper.gui.utils.gui_settings import load_gui_settings as _lgs
                                _daemon_ping = bool(_lgs().get("daemon_discord_ping", False))
                            except Exception:
                                pass
                        _lines = ["@here"] if _daemon_ping else []
                        _lines.append("\n\n--- Scrape Results ---")
                        for _m in self._selected_models:
                            _un = _m.name
                            _st = _db_stats.get(_un, {})
                            _photos = _st.get("photos", 0)
                            _videos = _st.get("videos", 0)
                            _audios = _st.get("audios", 0)
                            _dl_photos = _st.get("dl_photos", 0)
                            _dl_videos = _st.get("dl_videos", 0)
                            _dl_audios = _st.get("dl_audios", 0)
                            _total = _photos + _videos + _audios
                            _dl_total = _dl_photos + _dl_videos + _dl_audios
                            # Show per-run new downloads alongside cumulative DB total.
                            # Use \[ to escape brackets so Rich's markup parser
                            # (inside DiscordFormatter) doesn't strip [username] as a style tag.
                            _lines.append(
                                f"\\[{_un}] {_run_new} new this run"
                                f" [{_run_videos} videos,"
                                f" {_run_audios} audios,"
                                f" {_run_photos} photos]"
                                f" | {_dl_total}/{_total} total in DB"
                            )
                        _dlog.getLogger("shared").warning("\n".join(_lines))
                    except Exception:
                        pass
                    finally:
                        self._mute_discord_handler()

                # Emit like/unlike status AFTER table rows are loaded from DB
                # so the signal handler can find the matching rows to update.
                try:
                    _liked = dict(_like_mod._GUI_LIKE_TRACKER or {})
                    _like_mod._GUI_LIKE_TRACKER = None
                    if _liked:
                        app_signals.posts_liked_updated.emit(_liked)
                except Exception:
                    pass

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

        import gc
        import pathlib
        import sqlite3
        import time
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
                    # Force CPython to release the file handle immediately.
                    # On Windows, sqlite3 handles can remain open until GC runs,
                    # which prevents unlink() from succeeding.
                    del cur, con
                    gc.collect()
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
                # On Windows, sqlite3 file handles can linger after close().
                # Retry up to 3 times with a short delay to let the OS release them.
                db_deleted = False
                for attempt in range(3):
                    if _safe_unlink(db_path):
                        db_deleted = True
                        break
                    if attempt < 2:
                        time.sleep(0.3)
                        gc.collect()

                if db_deleted:
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
                else:
                    app_signals.log_message.emit(
                        "ERROR",
                        f"Failed to delete DB for {username}: {db_path} "
                        "(file may be locked — close any other programs accessing it and try again)",
                    )

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
