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

# Cooperative cancellation flag for GUI runs.
# Progress hooks, download consumers, and the scraper loop check this first.
# A delayed KeyboardInterrupt injection is only used as a last resort if the
# thread ignores cooperative cancel past the grace period.
_gui_cancel_event = threading.Event()
_CANCEL_FORCE_GRACE_SECONDS = 5.0

# Pending summary data for normal GUI downloads.  Set by the scraping thread
# before scraping_finished is emitted; consumed by _on_scraping_finished in
# table_page.py after the date filter is applied, so the total reflects the
# filtered row count rather than all raw rows.
_pending_summary_data = None


def _snapshot_download_globals() -> dict:
    """Read current per-run download counters (reset between models by downloader)."""
    try:
        import ofscraper.commands.scraper.actions.utils.globals as cg

        return {
            "videos": int(getattr(cg, "video_count", 0) or 0),
            "photos": int(getattr(cg, "photo_count", 0) or 0),
            "audios": int(getattr(cg, "audio_count", 0) or 0),
            "forced": int(getattr(cg, "forced_skipped", 0) or 0),
            "failed": int(getattr(cg, "skipped", 0) or 0),
            "bytes": int(getattr(cg, "total_bytes_downloaded", 0) or 0),
        }
    except Exception:
        return {
            "videos": 0,
            "photos": 0,
            "audios": 0,
            "forced": 0,
            "failed": 0,
            "bytes": 0,
        }


def _format_bytes_short(n: int) -> str:
    n = float(max(0, int(n or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


def build_pending_summary_payload(
    workflow,
    *,
    is_normal_gui_download: bool,
    db_stats: dict | None,
) -> dict | None:
    """Build the scrape-summary dict consumed by table_page after finish."""
    db_stats = db_stats or {}
    models = list(getattr(workflow, "_selected_models", None) or [])
    # Manual URL runs may only have usernames in db_stats / media-id tracking.
    if not models and db_stats:
        from types import SimpleNamespace

        models = [SimpleNamespace(name=str(n), id=None) for n in db_stats.keys()]
    if not (db_stats or is_normal_gui_download or models):
        # Last resort: manual URL finished with download globals but no DB stats.
        actions = getattr(workflow, "_selected_actions", None) or set()
        if "manual_url" not in actions:
            return None
        snap = _snapshot_download_globals()
        if (
            snap["videos"]
            + snap["photos"]
            + snap["audios"]
            + snap["failed"]
            + snap["forced"]
            == 0
        ):
            return None
        return {
            "forced": snap["forced"],
            "failed": snap["failed"],
            "run_dl": snap["videos"] + snap["photos"] + snap["audios"],
            "run_videos": snap["videos"],
            "run_photos": snap["photos"],
            "run_audios": snap["audios"],
            "total_bytes": snap["bytes"],
            "model_names": list(getattr(workflow, "_manual_model_names", None) or []),
            "db_info": {},
        }

    if is_normal_gui_download:
        per_model = dict(getattr(workflow, "_per_model_run_stats", {}) or {})
        if per_model:
            sum_videos = sum(int(s.get("videos", 0) or 0) for s in per_model.values())
            sum_photos = sum(int(s.get("photos", 0) or 0) for s in per_model.values())
            sum_audios = sum(int(s.get("audios", 0) or 0) for s in per_model.values())
            sum_forced = sum(int(s.get("forced", 0) or 0) for s in per_model.values())
            sum_failed = sum(int(s.get("failed", 0) or 0) for s in per_model.values())
            sum_bytes = sum(int(s.get("bytes", 0) or 0) for s in per_model.values())
        else:
            snap = _snapshot_download_globals()
            sum_videos = snap["videos"]
            sum_photos = snap["photos"]
            sum_audios = snap["audios"]
            sum_forced = snap["forced"]
            sum_failed = snap["failed"]
            sum_bytes = snap["bytes"]
        run_dl = sum_videos + sum_photos + sum_audios
        db_info = {}
        for m in models:
            st = db_stats.get(m.name, {})
            db_total = st.get("photos", 0) + st.get("videos", 0) + st.get("audios", 0)
            db_dl = st.get("dl_photos", 0) + st.get("dl_videos", 0) + st.get("dl_audios", 0)
            db_info[m.name] = (db_total, db_dl)
        return {
            "forced": sum_forced,
            "failed": sum_failed,
            "run_dl": run_dl,
            "run_videos": sum_videos,
            "run_photos": sum_photos,
            "run_audios": sum_audios,
            "total_bytes": sum_bytes,
            "model_names": [m.name for m in models],
            "db_info": db_info,
            "dup_counts": dict(getattr(workflow, "_per_model_dup_count", {}) or {}),
            "per_model": per_model,
        }

    snap = _snapshot_download_globals()
    run_dl = snap["videos"] + snap["photos"] + snap["audios"]
    db_info = {}
    for m in models:
        st = db_stats.get(m.name, {})
        db_total = st.get("photos", 0) + st.get("videos", 0) + st.get("audios", 0)
        db_dl = st.get("dl_photos", 0) + st.get("dl_videos", 0) + st.get("dl_audios", 0)
        db_info[m.name] = (db_total, db_dl)
    return {
        "forced": snap["forced"],
        "failed": snap["failed"],
        "run_dl": run_dl,
        "run_videos": snap["videos"],
        "run_photos": snap["photos"],
        "run_audios": snap["audios"],
        "total_bytes": snap["bytes"],
        "model_names": [m.name for m in models],
        "db_info": db_info,
    }


def apply_manual_url_gui_state(workflow, url_dicts) -> None:
    """After ``manual_download``, bind models + media IDs for table/summary."""
    from types import SimpleNamespace

    models = []
    media_ids = set()
    names = []
    for value in (url_dicts or {}).values():
        collection = (value or {}).get("collection")
        if collection is None:
            continue
        username = getattr(collection, "username", None)
        model_id = getattr(collection, "model_id", None)
        if not username:
            continue
        names.append(str(username))
        for media in getattr(collection, "all_unique_media", None) or []:
            mid = getattr(media, "id", None)
            if mid is not None:
                media_ids.add(mid)
        model = None
        try:
            import ofscraper.managers.manager as manager_mod

            model = manager_mod.Manager.current_model_manager._all_subs_dict.get(
                username
            )
        except Exception:
            model = None
        if model is None:
            model = SimpleNamespace(name=username, id=model_id)
        models.append(model)
        try:
            _emit_model_badge_started(username)
        except Exception:
            pass

    workflow._selected_models = models
    workflow._manual_media_ids = media_ids or None
    workflow._manual_model_names = names
    if media_ids:
        log.info(
            f"[GUI Manual URL] Bound {len(models)} model(s), "
            f"{len(media_ids)} media id(s) for table load"
        )


def format_daemon_last_run_chip(run_number: int, payload: dict | None) -> str:
    """Compact footer/toolbar chip for the previous daemon scrape."""
    if not payload:
        return f"Last run #{run_number}"
    run_dl = int(payload.get("run_dl") or 0)
    failed = int(payload.get("failed") or 0)
    forced = int(payload.get("forced") or 0)
    total_bytes = int(payload.get("total_bytes") or 0)
    parts = [f"Last run #{run_number}: {run_dl} dl"]
    if failed:
        parts.append(f"{failed} fail")
    if forced:
        parts.append(f"{forced} skip")
    if total_bytes > 0:
        parts.append(_format_bytes_short(total_bytes))
    return " · ".join(parts) if len(parts) > 1 else parts[0]


def _record_per_model_download_stats(workflow, username: str) -> None:
    """Store this model's download stats before the next model resets globals."""
    if workflow is None or not username:
        return
    snap = _snapshot_download_globals()
    if not hasattr(workflow, "_per_model_run_stats") or workflow._per_model_run_stats is None:
        workflow._per_model_run_stats = {}
    workflow._per_model_run_stats[str(username)] = snap


def _emit_model_badge_started(username: str) -> None:
    """Notify GUI of model start (direct signal — reliable across threads)."""
    name = str(username or "").strip()
    if not name:
        return
    try:
        app_signals.model_item_started.emit(name)
    except Exception:
        pass


def _emit_model_badge_result(username: str, ok: bool, error: str = "") -> None:
    """Notify GUI of model finish (direct signal — reliable across threads)."""
    name = str(username or "").strip()
    if not name:
        return
    try:
        app_signals.model_item_result.emit(name, bool(ok), str(error or ""))
    except Exception:
        pass


def is_gui_cancelled() -> bool:
    """Return True when the GUI has requested scrape cancellation.

    Safe to call from download/API workers (including when the GUI is not
    loaded — returns False if the event is unavailable).
    """
    try:
        return _gui_cancel_event.is_set()
    except Exception:
        return False


def _raise_in_thread(thread_id: int, exc_type=KeyboardInterrupt) -> bool:
    """Last-resort: raise an exception asynchronously in another Python thread.

    Prefer cooperative checks via ``is_gui_cancelled()``. Async injection is
    not perfectly safe and is only used after the cancel grace period.
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
# Nesting depth so model-list fetch and scrape can both install safely.
_gui_live_stub_depth = 0


def _install_gui_live_stubs():
    """Replace Rich Live display and patch signal handlers for GUI mode.

    Three things are handled:
    1. Rich Live → _NullLive (prevents terminal drawing from bg thread)
    2. Rich Console → quiet mode (suppresses print output)
    3. DelayedKeyboardInterrupt → thread-safe (signal.signal only in main thread)

    screens.py does ``from ofscraper.utils.live.live import get_live, stop_live``
    so we must also patch the names in that module to prevent stop_live()
    from clearing our _NullLive and get_live() from recreating a real Live.

    Nested calls (model fetch during scrape, overlapping fetches) are counted;
    only the outermost install/uninstall mutates module state.
    """
    global _orig_live, _orig_get_live, _orig_stop_live
    global _orig_screens_get_live, _orig_screens_stop_live
    global _orig_console_quiet, _orig_dki_enter, _orig_dki_exit
    global _gui_live_stub_depth

    if _gui_live_stub_depth > 0:
        _gui_live_stub_depth += 1
        return

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
    _gui_live_stub_depth = 1


def _uninstall_gui_live_stubs():
    """Restore original Rich Live, Console, and signal handlers."""
    global _gui_live_stub_depth

    if _gui_live_stub_depth <= 0:
        return
    _gui_live_stub_depth -= 1
    if _gui_live_stub_depth > 0:
        return

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


def _strip_rich_stdout_handlers():
    """Remove RichHandler from shared loggers.

    Rich console I/O from download worker threads has caused Windows access
    violations mid-scrape (faulthandler cut off inside ``logging.flush``).
    GUI mode uses the Qt console bridge instead.
    """
    for name in ("shared", "shared_other"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            cls_name = type(h).__name__
            mod = getattr(type(h), "__module__", "") or ""
            if cls_name == "RichHandler" or mod.startswith("rich"):
                try:
                    lg.removeHandler(h)
                    h.close()
                except Exception:
                    pass


def _prepare_gui_scrape_logging():
    """Strip Rich handlers and ensure the GUI log bridge is attached.

    Call after ``resetLogger()`` (which re-adds RichHandler via stdout.py).
    """
    _strip_rich_stdout_handlers()
    # Idempotent: drop any prior GUI bridge then re-attach one.
    _uninstall_gui_log_handler()
    _install_gui_log_handler()


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

    def __init__(self):
        super().__init__()
        import time as _time
        self._last_debug_emit = 0.0
        self._time = _time

    def emit(self, record):
        try:
            try:
                from ofscraper.gui.utils import model_fetch as _mf
                import threading

                if getattr(_mf, "_suppress_worker_gui_logs", False) and (
                    threading.current_thread() is not threading.main_thread()
                ):
                    return
            except Exception:
                pass
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
            # Throttle DEBUG messages to at most one per 200ms to prevent
            # flooding the Qt event queue during high-volume scrape runs.
            if record.levelno <= logging.DEBUG:
                now = self._time.monotonic()
                if now - self._last_debug_emit < 0.2:
                    return
                self._last_debug_emit = now
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
                # Batch all updates into a single signal to avoid flooding
                # the main thread's event queue with O(n_downloads) signals.
                new_downloads = downloaded_set - already_downloaded
                if new_downloads:
                    batch = []
                    for media_id in new_downloads:
                        key = str(media_id)
                        if media_id in locked_media_ids:
                            batch.append((key, "downloaded", "N/A"))
                            batch.append((key, "unlocked", "Locked"))
                        else:
                            batch.append((key, "downloaded", "True"))
                            batch.append((key, "download_cart", "[downloaded]"))
                    app_signals.batch_cell_update.emit(batch)
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
_orig_api_add_overall = None
_orig_api_update_overall = None
_orig_api_remove_overall = None
_orig_api_add_job = None
_orig_api_update_job = None
_orig_api_remove_job = None
_orig_activity_update_task = None
_orig_activity_update_user = None
_gui_progress_hooks_installed = False


def _install_gui_progress_hooks():
    """Monkey-patch progress_updater functions to also emit GUI signals.

    The consumer loop in download/normal/utils/consumer.py calls
    progress_updater.update_download_task() after EVERY media item.
    By wrapping that function, we get per-item progress updates in the GUI
    without modifying any core download code.

    API pagination (messages/timeline/paid/labels/…) updates
    ``progress_updater.api.*`` each page — wrapping those raises
    ``KeyboardInterrupt`` on cancel so scrapes stop mid-pagination.

    Idempotent: a second install while hooks are active is a no-op so
    overlapping check-mode runs cannot wrap the wrapper (RecursionError).
    """
    import ofscraper.utils.live.updater as progress_updater
    import ofscraper.commands.scraper.actions.utils.globals as common_globals

    global _orig_update_download_task
    global _orig_add_download_task
    global _orig_remove_download_task
    global _orig_add_like_task
    global _orig_increment_like_task
    global _orig_remove_like_task
    global _orig_api_add_overall
    global _orig_api_update_overall
    global _orig_api_remove_overall
    global _orig_api_add_job
    global _orig_api_update_job
    global _orig_api_remove_job
    global _orig_activity_update_task
    global _orig_activity_update_user
    global _gui_progress_hooks_installed

    if _gui_progress_hooks_installed:
        return
    # In ofscraper 3.14.3 these are methods on ProgressManager objects
    _orig_update_download_task = progress_updater.download.update_overall_task
    _orig_add_download_task = progress_updater.download.add_overall_task
    _orig_remove_download_task = progress_updater.download.remove_overall_task
    _orig_add_like_task = progress_updater.like.add_overall_task
    _orig_increment_like_task = progress_updater.like.update_overall_task
    _orig_remove_like_task = progress_updater.like.remove_overall_task
    _orig_api_add_overall = progress_updater.api.add_overall_task
    _orig_api_update_overall = progress_updater.api.update_overall_task
    _orig_api_remove_overall = progress_updater.api.remove_overall_task
    _orig_api_add_job = progress_updater.api.add_job_task
    _orig_api_update_job = progress_updater.api.update_job_task
    _orig_api_remove_job = progress_updater.api.remove_job_task
    _orig_activity_update_task = progress_updater.activity.update_task
    _orig_activity_update_user = progress_updater.activity.update_user

    def _raise_if_cancelled():
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()

    def _get_dup_count():
        try:
            import ofscraper.managers.postcollection as _pc
            return int(_pc._gui_duplicate_count)
        except Exception:
            return 0

    # Throttle progress via progress_bridge (shared with host callbacks).
    from ofscraper.gui.utils.progress_bridge import (
        flush_pending as _flush_progress,
        reset_throttle_state as _reset_progress_throttle,
        update_overall_progress as _throttled_overall,
        update_total_bytes as _throttled_bytes,
    )

    try:
        _reset_progress_throttle()
    except Exception:
        pass

    def gui_add_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        total = kwargs.get("total", 0)
        if _gui_state.locked_total <= 0:
            # Show only actual download queue size so mid-run bar matches final count.
            _gui_state.total_media = total
            result = _orig_add_download_task(*args, **kwargs)
            try:
                _throttled_overall(0, total, force=True)
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
            _throttled_bytes(float(common_globals.total_bytes_downloaded))
            _throttled_overall(completed, total)
        except Exception:
            pass

    def gui_remove_download_task(*args, **kwargs):
        if _gui_cancel_event.is_set():
            raise KeyboardInterrupt()
        _orig_remove_download_task(*args, **kwargs)
        try:
            # Flush final progress for this download batch.
            total = _gui_state.total_media
            if _gui_state.locked_total > 0:
                completed = _gui_state.check_completed
            else:
                completed = (
                    common_globals.photo_count
                    + common_globals.video_count
                    + common_globals.audio_count
                    + common_globals.skipped
                    + common_globals.forced_skipped
                )
            _flush_progress(progress=(completed, total))
        except Exception:
            pass
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

    # API pagination progress — cancel between pages (messages/timeline/paid/labels/…).
    def gui_api_add_overall(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_add_overall(*args, **kwargs)

    def gui_api_update_overall(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_update_overall(*args, **kwargs)

    def gui_api_remove_overall(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_remove_overall(*args, **kwargs)

    def gui_api_add_job(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_add_job(*args, **kwargs)

    def gui_api_update_job(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_update_job(*args, **kwargs)

    def gui_api_remove_job(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_api_remove_job(*args, **kwargs)

    progress_updater.api.add_overall_task = gui_api_add_overall
    progress_updater.api.update_overall_task = gui_api_update_overall
    progress_updater.api.remove_overall_task = gui_api_remove_overall
    progress_updater.api.add_job_task = gui_api_add_job
    progress_updater.api.update_job_task = gui_api_update_job
    progress_updater.api.remove_job_task = gui_api_remove_job

    # Activity / per-user progress — cancel between models.
    def gui_activity_update_task(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_activity_update_task(*args, **kwargs)

    def gui_activity_update_user(*args, **kwargs):
        _raise_if_cancelled()
        return _orig_activity_update_user(*args, **kwargs)

    progress_updater.activity.update_task = gui_activity_update_task
    progress_updater.activity.update_user = gui_activity_update_user
    _gui_progress_hooks_installed = True


def _uninstall_gui_progress_hooks():
    """Restore original progress_updater functions."""
    import ofscraper.utils.live.updater as progress_updater

    global _gui_progress_hooks_installed

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
    if _orig_api_add_overall is not None:
        progress_updater.api.add_overall_task = _orig_api_add_overall
    if _orig_api_update_overall is not None:
        progress_updater.api.update_overall_task = _orig_api_update_overall
    if _orig_api_remove_overall is not None:
        progress_updater.api.remove_overall_task = _orig_api_remove_overall
    if _orig_api_add_job is not None:
        progress_updater.api.add_job_task = _orig_api_add_job
    if _orig_api_update_job is not None:
        progress_updater.api.update_job_task = _orig_api_update_job
    if _orig_api_remove_job is not None:
        progress_updater.api.remove_job_task = _orig_api_remove_job
    if _orig_activity_update_task is not None:
        progress_updater.activity.update_task = _orig_activity_update_task
    if _orig_activity_update_user is not None:
        progress_updater.activity.update_user = _orig_activity_update_user
    _gui_progress_hooks_installed = False


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
    # Pre-scan to find which media_ids appear more than once so we can flag
    # 2nd+ occurrences as duplicates (they'll be filtered by dupefiltermedia).
    from collections import Counter as _Counter
    _mid_counts = _Counter()
    for _ele in media:
        _mk = getattr(_ele, "id", None) or id(_ele)
        _mid_counts[_mk] += 1
    _mid_seen: set = set()

    # When duplicates are not allowed, duplicate rows are skipped by the pipeline
    # so their Downloaded column should stay False regardless of DB state.
    try:
        import ofscraper.utils.settings as _sett
        _allow_dupe = bool(_sett.get_settings().allow_dupe_downloads)
    except Exception:
        _allow_dupe = False

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

            # Use the POST's date (postedAt → createdAt) as the display date so
            # it matches exactly what Media.postdate returns and therefore what
            # posts_date_filter_media uses for the download decision.
            # Do NOT fall back to raw_media.createdAt/postedAt: media files can
            # have a "createdAt" that predates the post (e.g. a video uploaded
            # months ago and reused in a new post), which would cause the table
            # filter to hide items that the scraper correctly decided to download.
            # When the post has no date (postedAt=None, createdAt=None), leave
            # post_date empty; _date_validate returns True for unparseable values
            # so these items remain visible in the table (matching the download-
            # filter rule that postdate=None always passes).
            _post_date_raw = raw_post.get("postedAt") or raw_post.get("createdAt")
            if _post_date_raw:
                try:
                    import arrow as _arrow_date
                    post_date = _arrow_date.get(_post_date_raw).format("YYYY-MM-DD HH:mm:ss")
                except Exception:
                    post_date = str(_post_date_raw)
            else:
                post_date = ""

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

            # Mark 2nd+ occurrences of the same media_id as duplicates.
            _mid_key = media_id if media_id else id(ele)
            _is_dup = (_mid_counts.get(_mid_key, 1) > 1) and (_mid_key in _mid_seen)
            _mid_seen.add(_mid_key)
            duplicate_display = "Duplicate" if _is_dup else ""

            # When duplicates are skipped by the pipeline, force Downloaded=False
            # on duplicate rows so the column only reflects actual pipeline work.
            if _is_dup and not _allow_dupe:
                dl_display = "False"

            rows.append(
                {
                    "index": count,
                    "number": str(count + 1),
                    "download_cart": cart_status,
                    "username": username,
                    "downloaded": dl_display,
                    "duplicate": duplicate_display,
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

    # Pre-scan to find which media_ids appear more than once (same as _build_media_rows).
    from collections import Counter as _Counter
    _mid_counts = _Counter(
        r.get("media_id") for r in sorted_records if r.get("media_id") is not None
    )
    _mid_seen: set = set()

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

            _mid = rec.get("media_id")
            _mid_key = _mid if _mid is not None else id(rec)
            _is_dup = (_mid_counts.get(_mid_key, 1) > 1) and (_mid_key in _mid_seen)
            _mid_seen.add(_mid_key)
            duplicate_display = "Duplicate" if _is_dup else ""

            rows.append(
                {
                    "index": count,
                    "number": str(count + 1),
                    "download_cart": cart_status,
                    "username": username,
                    "downloaded": dl_display,
                    "duplicate": duplicate_display,
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


def _load_models_from_db(selected_models, date_range=None, media_ids=None, stats_only=False, per_model_from_dates=None):
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

    per_model_from_dates: optional dict {model_id: arrow_datetime} — when
    date_range is NOT enabled, use the per-model datetime as the lower-bound
    filter so the table only shows content from that date onward (e.g. since
    the DB was last touched).  Ignored when date_range is already enabled.

    Returns a dict: {username: {"photos": N, "videos": N, "audios": N,
                                "dl_photos": N, "dl_videos": N, "dl_audios": N}}
    so callers can report accurate download stats.
    """
    import pathlib
    import sqlite3

    import ofscraper.classes.placeholder as placeholder

    # Pre-parse global date bounds (active only when date_range["enabled"] is True).
    _global_dr_from = None
    _global_dr_to = None
    _date_range_enabled = bool(date_range and date_range.get("enabled"))
    if _date_range_enabled:
        try:
            import arrow as _arrow
            if date_range.get("from_date"):
                _global_dr_from = _arrow.get(date_range["from_date"], "YYYY-MM-DD")
            if date_range.get("to_date"):
                _global_dr_to = _arrow.get(date_range["to_date"], "YYYY-MM-DD").ceil("day")
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
    all_rows = []

    for model in selected_models:
        model_id = model.id
        username = model.name
        conn = None
        try:
            try:
                database_path = pathlib.Path(
                    placeholder.databasePlaceholder().databasePathHelper(
                        model_id, username
                    )
                )
            except Exception as _ph_err:
                import ofscraper.utils.paths.common as _cp_mtime
                import ofscraper.utils.profiles.data as _pd_mtime
                _cfg_home = str(_cp_mtime.get_config_home())
                _act_profile = str(_pd_mtime.get_active_profile())
                database_path = pathlib.Path(
                    _cfg_home, _act_profile, ".data",
                    str(model_id), "user_data.db"
                )
                log.debug(
                    f"[DB Load] databasePathHelper failed for {username} "
                    f"({type(_ph_err).__name__}: {_ph_err}) — using fallback path: {database_path}"
                )
            log.debug(f"[DB Load] Checking DB path for {username}: {database_path}")
            if not database_path.exists():
                log.debug(f"[DB Load] No DB file for {username} at {database_path} — skipping")
                continue

            import time
            retries = 3
            data = None
            post_info = {}
            for attempt in range(retries):
                try:
                    conn = sqlite3.connect(
                        database_path, check_same_thread=False, timeout=30
                    )
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(media_select_sql)
                    data = [dict(row) for row in cur.fetchall()]

                    # Also fetch price and text from post/message/story tables
                    post_info = _query_post_info(cur)
                    cur.close()
                    break
                except sqlite3.OperationalError as oe:
                    if "locked" in str(oe).lower() and attempt < retries - 1:
                        log.debug(f"[DB Load] Database locked for {username}, retrying in 1s... (attempt {attempt+1}/{retries})")
                        if conn:
                            try:
                                conn.close()
                            except Exception:
                                pass
                        time.sleep(1.0)
                        continue
                    raise

            log.debug(f"[DB Load] Found {len(data)} media records in DB for {username}")

            # Compute per-model media counts for Discord summary from the UNFILTERED data
            _st = {"photos": 0, "videos": 0, "audios": 0,
                   "dl_photos": 0, "dl_videos": 0, "dl_audios": 0}
            _seen_media_ids = set()
            for _row in data:
                _mid = _row.get("media_id")
                if _mid is not None:
                    if _mid in _seen_media_ids:
                        continue
                    _seen_media_ids.add(_mid)
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

            # Filter to specific media IDs when provided — ensures we only show
            # the items that were actually scraped in this session, not all
            # historical records accumulated across previous scrapes.
            if media_ids:
                _before = len(data)
                data = [r for r in data if r.get("media_id") in media_ids]
                log.debug(
                    f"[DB Load] media_id filter: kept {len(data)} of {_before} records for {username}"
                )

            # Determine per-model date bounds.
            # When date_range is enabled, use global bounds.
            # When date_range is NOT enabled but per_model_from_dates has a date for
            # this model, use it as the lower bound so only content since the last
            # DB write is shown (filters out historical pre-run duplicates).
            _dr_from = _global_dr_from
            _dr_to = _global_dr_to
            if not _date_range_enabled and per_model_from_dates:
                _model_from = per_model_from_dates.get(model_id)
                if _model_from:
                    _dr_from = _model_from  # open-ended upper bound (show up to now)

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
                            # No date on record — include it rather than silently drop it.
                            # Paid media sometimes lacks posted_at; skipping hides valid rows.
                            filtered.append(_r)
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
                    log.debug(
                        f"[DB Load] Date filter: kept {len(filtered)}, "
                        f"skipped {skipped} out-of-range records for {username}"
                    )
                    data = filtered
                except Exception as _fe:
                    log.debug(f"[DB Load] Date filter failed for {username}: {_fe}")

            if data and not stats_only:
                rows = _build_db_rows(data, username, post_info)
                if rows:
                    all_rows.extend(rows)
                    log.info(
                        f"Loaded {len(rows)} items from DB for {username}"
                    )
        except Exception as e:
            log.debug(f"[DB Load] Failed to load DB data for {username}: {e}")
            import traceback as _tb
            log.debug(f"[DB Load] Traceback: {_tb.format_exc()}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    if all_rows and not stats_only:
        # Use data_replace so the DB result replaces any rows
        # emitted by the live scraper pipeline, preventing duplicates.
        app_signals.data_replace.emit(all_rows)
        log.info(
            f"Emitted {len(all_rows)} total items from DB for all models"
        )

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
        from ofscraper.gui.utils.progress_bridge import queue_cell_updates

        downloaded_set = get_media_ids_downloaded(
            model_id=model_id, username=username
        )
        handled_ids = set()
        batch = []
        for ele in media:
            media_id = getattr(ele, "id", None)
            if media_id is None:
                continue
            handled_ids.add(str(media_id))
            canview = getattr(ele, "canview", True)
            is_downloaded = media_id in downloaded_set
            key = str(media_id)

            if not canview:
                # Locked content — don't change status
                batch.append((key, "downloaded", "N/A"))
                batch.append((key, "unlocked", "Locked"))
                batch.append((key, "download_cart", "Locked"))
            else:
                batch.append((key, "downloaded", str(is_downloaded)))
                if is_downloaded:
                    batch.append((key, "download_cart", "[downloaded]"))

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
                batch.append((media_id, "downloaded", str(is_downloaded)))
                if is_downloaded:
                    batch.append((media_id, "download_cart", "[downloaded]"))

        if batch:
            queue_cell_updates(batch, force=True)
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

        @property
        def run_action(self):
            """Skip the normal per-user action path when doing a paid-only scrape
            with no content areas selected.  Without this, runner() falls through to
            prepare() after scrape_paid_all() which shows the interactive TUI area
            selector and blocks the thread indefinitely."""
            import ofscraper.utils.settings as _s
            _cfg = _s.get_settings()
            if getattr(_cfg, "scrape_paid", False) and not getattr(_cfg, "download_area", None):
                return False
            return len(getattr(_cfg, "actions", [])) > 0

        async def _execute_user_action(self, ele, postcollection):
            import ofscraper.utils.settings as _settings
            # Use the fuller GUI table media set for display so duplicates/reposts
            # and locked/paid rows remain visible, while downloads still use the
            # normal processed queue.
            media = postcollection.get_media_for_processing()

            # Live table rows:
            # - Interactive (non-daemon): always build/emit so the GUI table fills
            #   while downloads run.
            # - Daemon + no date filter: skip (DB load at end). Building per-model
            #   API rows was the dominant GUI overhead (~30 min slower than CLI).
            try:
                import ofscraper.utils.args.accessors.read as _ra_chk
                _chk_args = _ra_chk.retriveArgs()
                _workflow_chk = getattr(self, "caller", None) or getattr(self, "workflow", None)
                _is_daemon = bool(getattr(_workflow_chk, "_daemon_enabled", False))
                _has_date_args = (
                    getattr(_chk_args, "after", None) is not None
                    or getattr(_chk_args, "before", None) is not None
                )
                _live_rows_needed = (not _is_daemon) or _has_date_args
            except Exception:
                _live_rows_needed = True  # safe default: build rows when unsure

            if _live_rows_needed:
                table_rows = postcollection.get_rows_for_gui_table()

                # Filter table_rows to the requested date range before emitting so the
                # table and progress bar only reflect in-range content during the scrape.
                # Labels don't support after/before params at the API level so their posts
                # are post-filtered here to match the user's date selection.
                try:
                    import ofscraper.utils.args.accessors.read as _ra_tbl
                    _tbl_args = _ra_tbl.retriveArgs()
                    _tbl_after = getattr(_tbl_args, 'after', None)
                    _tbl_before = getattr(_tbl_args, 'before', None)
                    if _tbl_after is not None or _tbl_before is not None:
                        import arrow as _arrow_tbl
                        _min_bound = _tbl_after.floor('day') if _tbl_after else None
                        _max_bound = _tbl_before.ceil('day') if _tbl_before else None
                        _filtered_tbl_rows = []
                        for _tbl_row in table_rows:
                            _pd = _tbl_row.get('post_date', '')
                            if not _pd:
                                _filtered_tbl_rows.append(_tbl_row)
                                continue
                            try:
                                _test_date = _arrow_tbl.get(_pd).floor('day')
                                if _min_bound and _max_bound:
                                    if not _test_date.is_between(_min_bound, _max_bound, bounds='[]'):
                                        continue
                                elif _min_bound:
                                    if _test_date < _min_bound:
                                        continue
                                elif _max_bound:
                                    if _test_date > _max_bound:
                                        continue
                            except Exception:
                                pass  # keep row on parse error
                            _filtered_tbl_rows.append(_tbl_row)
                        # Recompute _gui_duplicate_count for the date-filtered set so
                        # the progress bar total matches the filtered row count.
                        try:
                            import ofscraper.managers.postcollection as _pc_tbl
                            _seen_ids_tbl = set()
                            _dup_cnt_tbl = 0
                            for _tbl_row in _filtered_tbl_rows:
                                _mid_tbl = _tbl_row.get('media_id')
                                if _mid_tbl is not None:
                                    if _mid_tbl in _seen_ids_tbl:
                                        _dup_cnt_tbl += 1
                                    else:
                                        _seen_ids_tbl.add(_mid_tbl)
                            _pc_tbl._gui_duplicate_count = _dup_cnt_tbl
                        except Exception:
                            pass
                        table_rows = _filtered_tbl_rows
                    # When no effective GUI date filter, compute the duplicate count from
                    # only the rows on or after the DB's latest stored post_date, so the
                    # summary reflects duplicates since the last real scrape. The full live
                    # row set is still emitted to the table (no table filtering here).
                    if not (_tbl_after or _tbl_before):
                        _workflow_db = getattr(self, "caller", None) or getattr(self, "workflow", None)
                        if _workflow_db is not None and ele is not None:
                            _prerun_dates = getattr(_workflow_db, "_db_prerun_mtimes", {})
                            _model_max_date = _prerun_dates.get(getattr(ele, 'id', None))
                            log.debug(
                                f"[DIAG] DB content dup count: model={getattr(ele, 'name', None)} "
                                f"max_post_date={_model_max_date}"
                            )
                            if _model_max_date is not None:
                                import arrow as _arrow_dbf
                                _dbf_min = _model_max_date.floor('day')
                                _filtered_for_dup = []
                                for _trf in (table_rows or []):
                                    _pdf = _trf.get('post_date', '')
                                    if not _pdf:
                                        _filtered_for_dup.append(_trf)
                                        continue
                                    try:
                                        if _arrow_dbf.get(_pdf) >= _dbf_min:
                                            _filtered_for_dup.append(_trf)
                                    except Exception:
                                        _filtered_for_dup.append(_trf)
                                _seen_dbf = set()
                                _dup_dbf = 0
                                for _rdbf in _filtered_for_dup:
                                    _mid_dbf = _rdbf.get('media_id')
                                    if _mid_dbf is not None:
                                        if _mid_dbf in _seen_dbf:
                                            _dup_dbf += 1
                                        else:
                                            _seen_dbf.add(_mid_dbf)
                                log.debug(
                                    f"[DIAG] DB content dup count: {_dup_dbf} dups in "
                                    f"{len(_filtered_for_dup)} rows since {_dbf_min}"
                                )
                                # Store per-model dup count on the workflow object so the
                                # summary can use it without counting from all visible rows.
                                if not hasattr(_workflow_db, "_per_model_dup_count"):
                                    _workflow_db._per_model_dup_count = {}
                                _workflow_db._per_model_dup_count[
                                    getattr(ele, 'name', 'unknown')
                                ] = _dup_dbf
                except Exception:
                    pass
            else:
                # Daemon + no date filter — skip live row building.
                # _load_models_from_db will populate the table after the scrape completes.
                table_rows = []
                log.debug(
                    f"[GUI] Skipping live table rows for {getattr(ele, 'name', '?')} "
                    f"— daemon without date filter; DB rows used at end"
                )

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
            _fail_before = 0
            _action_error = ""
            _workflow_ref = getattr(self, "caller", None) or getattr(self, "workflow", None)
            try:
                from ofscraper.gui.utils.failure_tracker import failure_count_for_user

                _fail_before = failure_count_for_user(username)
            except Exception:
                _fail_before = 0
            _emit_model_badge_started(username)
            try:
                from ofscraper.gui.utils.host_callbacks import ensure_gui_host

                try:
                    from ofscraper.gui.utils.privacy_mode import mask_username

                    _status_user = mask_username(username) or username
                except Exception:
                    _status_user = username
                ensure_gui_host().on_status(f"Processing {_status_user}…")
            except Exception:
                try:
                    from ofscraper.gui.utils.privacy_mode import mask_username

                    _status_user = mask_username(username) or username
                    app_signals.status_message.emit(f"Processing {_status_user}…")
                except Exception:
                    pass
            try:
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
                            _record_per_model_download_stats(_workflow_ref, username)
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
                            try:
                                import ofscraper.managers.manager as _mgr

                                _mgr.Manager.stats_manager.update_and_print_stats(
                                    username, "download", media, ignore_missing=True
                                )
                            except Exception:
                                pass
                        except Exception as e:
                            _action_error = str(e)
                            log.error(f"[GUI] Download error for {username}: {e}")
                            app_signals.log_message.emit(
                                "ERROR",
                                f"Download failed for {username}: {e}",
                            )
                            out.append([])
                        finally:
                            # Snapshot BEFORE next model resets common_globals.
                            _record_per_model_download_stats(_workflow_ref, username)
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
                        try:
                            out.append(
                                like_action.process_like(
                                    ele=ele,
                                    posts=like_posts,
                                    media=media,
                                    model_id=model_id,
                                    username=username,
                                )
                            )
                        except Exception as e:
                            _action_error = str(e)
                            raise
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
                        try:
                            out.append(
                                like_action.process_unlike(
                                    ele=ele,
                                    posts=like_posts,
                                    media=media,
                                    model_id=model_id,
                                    username=username,
                                )
                            )
                        except Exception as e:
                            _action_error = str(e)
                            raise
            finally:
                try:
                    from ofscraper.gui.utils.failure_tracker import failure_count_for_user

                    _fail_after = failure_count_for_user(username)
                    _ok = (not _action_error) and (_fail_after <= _fail_before)
                    _err = _action_error
                    if not _ok and not _err and _fail_after > _fail_before:
                        _err = f"{_fail_after - _fail_before} download failure(s)"
                    _emit_model_badge_result(username, _ok, _err)
                except Exception:
                    try:
                        _emit_model_badge_result(
                            username, not bool(_action_error), _action_error
                        )
                    except Exception:
                        pass
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
        self._text_filename_from_post = False
        self._scrape_paid = False
        self._discord_level = "OFF"
        self._advanced = {}
        self._did_purge = False
        self._manual_urls = []
        self._manual_media_ids = None
        self._manual_model_names = []
        # Date range filter from area_selector_page
        self._date_range = {}
        # Snapshot specific args so GUI toggles don't permanently clobber CLI intent.
        self._baseline_args = None
        self._scraper_thread = None
        self._active_history_snapshot = None
        # Daemon mode settings
        self._daemon_enabled = False
        self._daemon_interval = 30.0  # minutes
        self._daemon_notify = True
        self._daemon_sound = True
        self._daemon_stop = threading.Event()
        self._msg_check_filter = "paid_only"  # "paid_only" | "free_only" | "all"
        self._live_rows_emitted = False
        self._db_prerun_mtimes = {}  # {model_id: arrow datetime} — DB mtime before runner() touches it
        self._db_prerun_dl_counts = {}  # {model_name: {dl_photos, dl_videos, dl_audios}} — pre-scrape baseline
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
        app_signals.text_filename_from_post_configured.connect(
            self._on_text_filename_from_post_configured
        )
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
        # Drop stale models when entering check mode so areas_selected cannot
        # auto-start a check against models left over from a prior scrape.
        if bool(set(actions or []) & self._CHECK_MODES):
            self._selected_models = []

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

    def _ensure_advanced_options(self):
        """Fill advanced scrape options if check mode skipped the table Start path.

        Check modes auto-start on model select, before table_page emits
        ``advanced_scrape_configured``. Prefer the live Areas checkbox, then
        ``gui_settings.json``, then whatever is already in ``self._advanced``.
        """
        advanced = dict(self._advanced or {})
        try:
            from ofscraper.gui.utils.gui_settings import load_gui_settings

            gs = load_gui_settings() or {}
        except Exception:
            gs = {}

        if "allow_dupe_downloads" not in advanced:
            advanced["allow_dupe_downloads"] = bool(gs.get("allow_dupes"))
        if "keep_message_purchased_dupes" not in advanced:
            advanced["keep_message_purchased_dupes"] = bool(
                gs.get("keep_msg_purchased_dupes")
            ) and bool(advanced.get("allow_dupe_downloads"))
        if "rescrape_all" not in advanced:
            advanced["rescrape_all"] = bool(gs.get("rescrape_all"))
        if "quality" not in advanced and gs.get("quality"):
            advanced["quality"] = gs.get("quality")

        # Live widget wins when available (most accurate).
        try:
            from PyQt6.QtWidgets import QApplication

            area_page = None
            win = QApplication.activeWindow()
            if win is not None:
                area_page = getattr(win, "area_page", None)
            if area_page is None:
                for w in QApplication.topLevelWidgets():
                    area_page = getattr(w, "area_page", None)
                    if area_page is not None:
                        break
            if area_page is not None:
                if getattr(area_page, "allow_dupes_check", None) is not None:
                    advanced["allow_dupe_downloads"] = bool(
                        area_page.allow_dupes_check.isChecked()
                    )
                if getattr(area_page, "keep_msg_purchased_dupes_check", None) is not None:
                    advanced["keep_message_purchased_dupes"] = bool(
                        advanced.get("allow_dupe_downloads")
                        and area_page.keep_msg_purchased_dupes_check.isChecked()
                    )
                if getattr(area_page, "rescrape_all_check", None) is not None:
                    advanced["rescrape_all"] = bool(
                        area_page.rescrape_all_check.isChecked()
                    )
                if getattr(area_page, "quality_combo", None) is not None:
                    advanced["quality"] = area_page.quality_combo.currentText()
        except Exception:
            pass

        self._advanced = advanced
        return advanced

    def _on_date_range_configured(self, config):
        try:
            self._date_range = dict(config or {})
            log.info(f"[GUI Workflow] _date_range set to: {self._date_range!r}")
        except Exception as _e:
            log.warning(f"[GUI Workflow] Exception in _on_date_range_configured: {_e}")
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
        """Request cooperative cancel; force-interrupt only after a grace period.

        UI should show a Cancelling state and keep Start disabled until
        ``scraping_finished`` fires.
        """
        already = False
        try:
            already = _gui_cancel_event.is_set()
            _gui_cancel_event.set()
        except Exception:
            pass
        try:
            self._daemon_stop.set()
        except Exception:
            pass
        try:
            from ofscraper.gui.utils.host_callbacks import ensure_gui_host

            host = ensure_gui_host()
            host.on_phase("cancelling")
            host.on_status("Cancelling… finishing current work")
            if not already:
                app_signals.log_message.emit(
                    "WARNING",
                    "Cancel requested — waiting for cooperative stop "
                    f"(force after {_CANCEL_FORCE_GRACE_SECONDS:.0f}s if needed)",
                )
        except Exception:
            try:
                app_signals.status_message.emit(
                    "Cancelling… finishing current work"
                )
                if not already:
                    app_signals.log_message.emit(
                        "WARNING",
                        "Cancel requested — waiting for cooperative stop "
                        f"(force after {_CANCEL_FORCE_GRACE_SECONDS:.0f}s if needed)",
                    )
            except Exception:
                pass

        # Avoid stacking multiple force-interrupt watchers for repeated clicks.
        if already:
            return
        try:
            t = getattr(self, "_scraper_thread", None)
        except Exception:
            t = None

        def _force_after_grace():
            import time as _time

            _time.sleep(_CANCEL_FORCE_GRACE_SECONDS)
            try:
                if not _gui_cancel_event.is_set():
                    return
                if not (t and getattr(t, "is_alive", lambda: False)()):
                    return
                tid = getattr(t, "ident", None)
                if not tid:
                    return
                ok = _raise_in_thread(int(tid), KeyboardInterrupt)
                if ok:
                    log.info(
                        "[GUI Workflow] Force-injected KeyboardInterrupt "
                        "into scraper thread after grace period"
                    )
                    try:
                        app_signals.status_message.emit(
                            "Cancelling… force-stopping stuck work"
                        )
                        app_signals.log_message.emit(
                            "WARNING",
                            "Cooperative cancel timed out; force-stopping scraper thread",
                        )
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            threading.Thread(
                target=_force_after_grace,
                daemon=True,
                name="gui-cancel-force",
            ).start()
        except Exception:
            pass

    def _on_mediatypes_configured(self, mediatypes):
        self._selected_mediatypes = mediatypes
        log.info(f"[GUI Workflow] Media types set: {mediatypes}")

    def _on_include_text_configured(self, include: bool):
        self._include_text = include
        log.info(f"[GUI Workflow] Include post text: {include}")

    def _on_text_filename_from_post_configured(self, enabled: bool):
        self._text_filename_from_post = bool(enabled)
        log.info(f"[GUI Workflow] Name text from post text: {enabled}")

    def _on_areas_selected(self, areas):
        self._selected_areas = areas
        log.info(f"[GUI Workflow] Areas set: {areas}")
        if bool(self._selected_actions & self._CHECK_MODES):
            # Check modes start only after models are confirmed
            # (_on_models_selected). Never auto-start here — leftover
            # _selected_models from a previous scrape caused overlapping
            # gui_checker runs (postcollection cleared mid-flight + hook recursion).
            return
        # Clear any previous stop request
        self._daemon_stop.clear()
        # This is the trigger to start the pipeline
        self._start_scraping()

    def _start_scraping(self):
        """Set args and launch the scraper in a background thread."""
        try:
            alive = (
                getattr(self, "_scraper_thread", None) is not None
                and self._scraper_thread.is_alive()
            )
        except Exception:
            alive = False
        if alive:
            log.warning(
                "[GUI Workflow] Scrape already running — ignoring duplicate start"
            )
            return
        # Gate check-mode / manual-URL / daemon paths that skip table Start.
        # Normal Start Scraping already confirms in table_page; session skip
        # makes a second dialog a no-op when the user opted out.
        try:
            from ofscraper.gui.utils.key_mode_warning import confirm_remote_key_mode
            from PyQt6.QtWidgets import QApplication

            parent = QApplication.activeWindow()
            if not confirm_remote_key_mode(parent, context="scrape"):
                try:
                    app_signals.status_message.emit(
                        "Scrape not started — remote key mode declined"
                    )
                    # Reset Cancelling/Scraping UI if the table already flipped active.
                    app_signals.scraping_finished.emit()
                except Exception:
                    pass
                return
        except Exception as e:
            log.debug(f"Remote key-mode start check skipped: {e}")

        try:
            from ofscraper.gui.utils.config_validation import confirm_config_for_scrape
            from PyQt6.QtWidgets import QApplication

            parent = QApplication.activeWindow()
            if not confirm_config_for_scrape(parent):
                try:
                    app_signals.status_message.emit(
                        "Scrape not started — fix configuration first"
                    )
                    app_signals.scraping_finished.emit()
                except Exception:
                    pass
                return
        except Exception as e:
            log.debug(f"Config validation start check skipped: {e}")

        summary = None
        try:
            from ofscraper.gui.utils.scrape_confirm import (
                build_summary_from_workflow,
                confirm_scrape_job,
            )
            from PyQt6.QtWidgets import QApplication

            parent = QApplication.activeWindow()
            summary = build_summary_from_workflow(self)
            if not confirm_scrape_job(parent, summary, mark_ack=True):
                try:
                    app_signals.status_message.emit(
                        "Scrape not started — cancelled at confirm"
                    )
                    app_signals.scraping_finished.emit()
                except Exception:
                    pass
                return
        except Exception as e:
            log.debug(f"Scrape confirm start check skipped: {e}")
            summary = None

        try:
            from ofscraper.gui.utils.disk_space_check import confirm_for_scrape
            from ofscraper.gui.utils.scrape_confirm import build_summary_from_workflow
            from PyQt6.QtWidgets import QApplication

            parent = QApplication.activeWindow()
            disk_summary = summary if summary is not None else build_summary_from_workflow(self)
            if not confirm_for_scrape(parent, disk_summary, mark_ack=True):
                try:
                    app_signals.status_message.emit(
                        "Scrape not started — cancelled at disk space check"
                    )
                    app_signals.scraping_finished.emit()
                except Exception:
                    pass
                return
        except Exception as e:
            log.debug(f"Disk space start check skipped: {e}")

        try:
            from ofscraper.gui.utils.failure_tracker import clear_failures

            clear_failures()
        except Exception:
            pass

        try:
            names = [getattr(m, "name", None) or str(m) for m in (self._selected_models or [])]
            names = [n for n in names if n]
            if names:
                app_signals.model_badges_reset.emit(names)
            elif self._manual_urls:
                app_signals.model_badges_reset.emit(["manual"])
        except Exception:
            pass

        try:
            _gui_cancel_event.clear()
        except Exception:
            pass
        self._live_rows_emitted = False
        self._db_prerun_mtimes = {}
        self._db_prerun_dl_counts = {}
        self._per_model_run_stats = {}
        try:
            from ofscraper.gui.utils.progress_bridge import reset_throttle_state

            reset_throttle_state()
        except Exception:
            pass
        try:
            self._set_args()
        except Exception as e:
            log.error(f"Failed to configure scraper: {e}")
            app_signals.error_occurred.emit("Configuration Error", str(e))
            return

        try:
            from ofscraper.gui.utils.scrape_history import snapshot_from_workflow

            self._active_history_snapshot = snapshot_from_workflow(self)
        except Exception as e:
            log.debug(f"[GUI] Scrape history snapshot skipped: {e}")
            self._active_history_snapshot = None

        # NullLive / quiet console on the Qt main thread before the worker starts
        # (same lesson as model-fetch: mutating Rich from a bg thread races Qt).
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("scrape_live_stubs_install_main")
        except Exception:
            pass
        try:
            _install_gui_live_stubs()
            _strip_rich_stdout_handlers()
        except Exception as e:
            log.debug(f"[GUI] live stubs install on main failed: {e}")

        # Run scraper in background thread to not block the GUI
        thread = threading.Thread(
            target=self._run_scraper_thread,
            daemon=True,
            name="gui-scraper",
        )
        self._scraper_thread = thread
        thread.start()

        try:
            from ofscraper.gui.utils.crash_diagnostics import set_scrape_active

            set_scrape_active(True)
        except Exception:
            pass
        try:
            from ofscraper.gui.utils.host_callbacks import ensure_gui_host

            ensure_gui_host().on_phase("running")
        except Exception:
            pass
        try:
            app_signals.scrape_started.emit()
        except Exception:
            pass

    _CHECK_MODES = {"post_check", "msg_check", "paid_check", "story_check"}

    def _set_manual_url_args(self, args, write_args, _settings):
        """Set CLI args for manual URL / post-ID scraping."""
        args.command = "manual"
        args.url = list(self._manual_urls)
        args.action = ["download"]
        args.actions = ["download"]
        args.gui = True
        args.no_rich = True
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
        self._ensure_advanced_options()
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
        args.gui = True
        args.no_rich = True
        # Honor advanced scrape options from the Areas page (same as normal scrapes).
        args.allow_dupe_downloads = bool(
            (self._advanced or {}).get("allow_dupe_downloads")
        )
        args.keep_message_purchased_dupes = bool(
            args.allow_dupe_downloads
            and (self._advanced or {}).get("keep_message_purchased_dupes")
        )
        if "quality" in (self._advanced or {}):
            _quality = (self._advanced.get("quality") or "").strip().lower()
            args.quality = _quality if _quality in ("240", "720", "source") else None
        write_args.setArgs(args)
        try:
            _settings.update_settings()
        except Exception:
            pass
        log.info(
            f"[GUI Check] Args: command={check_mode}, "
            f"users={usernames}, areas={getattr(args, 'check_area', [])}, "
            f"allow_dupe_downloads={bool(getattr(args, 'allow_dupe_downloads', False))}, "
            f"keep_message_purchased_dupes={bool(getattr(args, 'keep_message_purchased_dupes', False))}"
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
                    "allow_dupe_downloads": bool(getattr(args, "allow_dupe_downloads", False)),
                    "keep_message_purchased_dupes": bool(
                        getattr(args, "keep_message_purchased_dupes", False)
                    ),
                    "quality": getattr(args, "quality", None),
                }
            except Exception:
                self._baseline_args = {
                    "after": None,
                    "no_cache": False,
                    "no_api_cache": False,
                    "discord_level": "OFF",
                    "allow_dupe_downloads": False,
                    "keep_message_purchased_dupes": False,
                    "quality": None,
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
        args.text_filename_from_post = bool(
            self._include_text and self._text_filename_from_post
        )

        # Discord webhook updates: set discord_level from GUI selection.
        # The CLI arg --discord maps to args.discord_level (not args.discord).
        argv = [str(a) for a in (getattr(sys, "argv", None) or [])]
        cli_sets_discord = any(
            a in {"-dc", "--discord"} or a.startswith("--discord=") for a in argv
        )
        if not cli_sets_discord:
            args.discord_level = self._discord_level

        # Advanced flags
        if "allow_dupe_downloads" in self._advanced:
            allow_dupes = bool(self._advanced.get("allow_dupe_downloads"))
        else:
            allow_dupes = bool((self._baseline_args or {}).get("allow_dupe_downloads", False))
        rescrape_all = bool(self._advanced.get("rescrape_all"))
        args.allow_dupe_downloads = allow_dupes
        if "keep_message_purchased_dupes" in self._advanced:
            keep_msg_paid = bool(self._advanced.get("keep_message_purchased_dupes"))
        else:
            keep_msg_paid = bool(
                (self._baseline_args or {}).get("keep_message_purchased_dupes", False)
            )
        args.keep_message_purchased_dupes = bool(allow_dupes and keep_msg_paid)

        # Video quality filter (-q / --quality)
        if "quality" in self._advanced:
            _quality = (self._advanced.get("quality") or "").strip().lower()
            args.quality = _quality if _quality in ("240", "720", "source") else None
        else:
            args.quality = (self._baseline_args or {}).get("quality", None)

        # Force full scan by bypassing auto-after logic & caches
        log.info(f"[GUI] _set_args: rescrape_all={rescrape_all}, _date_range={self._date_range!r}")
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
            except Exception as _e:
                log.warning(f"[GUI] Exception restoring baseline args: {_e}")

        # Apply GUI date range filter — always runs so date range overrides rescrape_all too
        try:
            import arrow as _arrow
            dr = self._date_range or {}
            log.info(f"[GUI] Applying date range: dr={dr!r}")
            if dr.get("enabled"):
                from_date = dr.get("from_date")
                to_date = dr.get("to_date")
                if from_date:
                    args.after = _arrow.get(from_date, "YYYY-MM-DD")
                    log.info(f"[GUI] Set args.after={args.after}")
                if to_date:
                    # include the full to_date day
                    args.before = _arrow.get(to_date, "YYYY-MM-DD").ceil("day")
                    log.info(f"[GUI] Set args.before={args.before}")
                else:
                    args.before = None
            else:
                args.before = None
        except Exception as _e:
            log.warning(f"[GUI] Exception applying date range filter: {_e}")

        args.daemon = self._daemon_enabled
        args.gui = True
        # Avoid Rich Live / RichHandler console I/O from download worker threads.
        args.no_rich = True
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

        # Wait for any async post-scrape plugin work to finish before counting down.
        try:
            from ofscraper.plugins.manager import plugin_manager as _pm
            if not _pm._scrape_complete_event.is_set():
                app_signals.status_message.emit("Waiting for post-scrape plugins…")
                app_signals.log_message.emit(
                    "INFO", "Daemon: waiting for post-scrape plugins to finish…"
                )
                deadline = time.time() + 300.0
                while not _pm._scrape_complete_event.is_set():
                    if self._daemon_stop.is_set():
                        return False
                    if time.time() > deadline:
                        log.warning("Daemon: post-scrape plugin wait timed out (300 s)")
                        break
                    _pm._scrape_complete_event.wait(timeout=1.0)
        except Exception:
            pass

        total_seconds = int(self._daemon_interval * 60)
        for remaining in range(total_seconds, 0, -1):
            if self._daemon_stop.is_set():
                return False
            mins = remaining // 60
            secs = remaining % 60
            try:
                from datetime import datetime, timedelta

                eta = datetime.now() + timedelta(seconds=remaining)
                eta_str = eta.strftime("%I:%M %p").lstrip("0")
                app_signals.daemon_next_run.emit(
                    f"Next run in {mins:02d}:{secs:02d}  (≈ {eta_str})"
                )
            except Exception:
                app_signals.daemon_next_run.emit(
                    f"Next run in {mins:02d}:{secs:02d}"
                )
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
        import ofscraper.gui.utils.workflow as _wf_mod

        app_signals.status_message.emit("Downloading selected check items...")
        app_signals.log_message.emit(
            "INFO", f"Processing {len(row_data_list)} check-mode download(s)"
        )

        _install_gui_live_stubs()
        _prepare_gui_scrape_logging()
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

        total_stats = {
            "videos": 0,
            "audios": 0,
            "photos": 0,
            "forced": 0,
            "failed": 0,
            "bytes": 0,
        }
        model_names = []

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
                if username:
                    model_names.append(username)
                try:
                    batch_stats = check_mod._process_user_batch(
                        username, model_id, data["media"], data["posts"], data["rows"]
                    ) or {}
                    for k in total_stats:
                        total_stats[k] += int(batch_stats.get(k, 0) or 0)
                except Exception as e:
                    log.error(f"Check download batch error for {username}: {e}")
                    log.debug(traceback.format_exc())
        finally:
            _gui_state.locked_total = 0
            _uninstall_gui_progress_hooks()
            _uninstall_gui_live_stubs()
            _uninstall_gui_log_handler()

        run_dl = (
            total_stats["videos"] + total_stats["photos"] + total_stats["audios"]
        )
        _wf_mod._pending_summary_data = {
            "forced": total_stats["forced"],
            "failed": total_stats["failed"],
            "run_dl": run_dl,
            "run_videos": total_stats["videos"],
            "run_photos": total_stats["photos"],
            "run_audios": total_stats["audios"],
            "total_bytes": total_stats["bytes"],
            "model_names": model_names,
            "db_info": {},
            "dup_counts": {},
        }
        try:
            app_signals.total_bytes_updated.emit(float(total_stats["bytes"]))
        except Exception:
            pass

        app_signals.status_message.emit("Check mode downloads complete")
        app_signals.log_message.emit("INFO", "Check mode download processing complete")
        # Triggers table_page Final Stats Summary via _pending_summary_data
        app_signals.scraping_finished.emit()

    def _run_scraper_thread(self):
        """Run the scraper pipeline in a background thread.
        If daemon mode is enabled, loops with the configured interval."""
        run_count = 0
        try:
            # Live stubs were installed on the Qt main thread before start;
            # only prepare logging + progress hooks here.
            _prepare_gui_scrape_logging()
            _install_gui_progress_hooks()

            # Check mode: one-shot run — no daemon loop
            if bool(self._selected_actions & self._CHECK_MODES):
                self._run_check_mode()
                return

            while True:
                if _gui_cancel_event.is_set():
                    raise KeyboardInterrupt()
                run_count += 1

                # Reset the logger for the current daemon run cycle
                try:
                    import ofscraper.utils.logs.logger as logger_mod
                    logger_mod.resetLogger()
                    # resetLogger re-adds RichHandler — strip it again for GUI.
                    _prepare_gui_scrape_logging()
                except Exception as e:
                    log.debug(f"[DIAG] Failed to reset logger for daemon run: {e}")

                # Reset live-rows flag each iteration so daemon re-runs don't inherit
                # run #1's True value and incorrectly skip DB table replacement when
                # the current run produced no live rows (e.g. after a crash).
                self._live_rows_emitted = False
                self._per_model_run_stats = {}
                self._manual_media_ids = None
                self._manual_model_names = []
                try:
                    from ofscraper.gui.utils.progress_bridge import reset_throttle_state

                    reset_throttle_state()
                except Exception:
                    pass
                self._db_prerun_mtimes = {}
                self._db_prerun_dl_counts = {}

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

                try:
                    from ofscraper.__version__ import __version__ as _ofscraper_ver
                    app_signals.log_message.emit("INFO", f"OF-Scraper version: {_ofscraper_ver}")
                except Exception:
                    pass

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

                    # Reset the global sleeper singletons so they're recreated in
                    # the current event loop. Each GUI run spawns a new thread with
                    # a new asyncio event loop; the SessionSleep._alock inside each
                    # sleeper binds to the first loop that uses it. Without reset,
                    # run 2's event loop gets "bound to a different event loop" errors
                    # on all concurrent label requests, causing 15/19 labels to silently
                    # fail and return 0 posts (labels count drops from 291 to ~30).
                    try:
                        from ofscraper.managers.sessionmanager.sleepers import sleepers as _sleepers
                        _sleepers.reset()
                    except Exception:
                        pass

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

                        _url_dicts = _manual_cmd.manual_download() or {}
                        try:
                            apply_manual_url_gui_state(self, _url_dicts)
                        except Exception as _manual_gui_err:
                            log.debug(
                                f"[GUI Manual URL] Could not bind models for table: "
                                f"{_manual_gui_err}"
                            )
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
                                log.debug(
                                    f"[DIAG] Patching process_paid_dict for: {list(_selected_usernames_lower)}"
                                )
                                app_signals.log_message.emit(
                                    "INFO",
                                    f"Filtering paid scrape to selected models: {[m.name for m in self._selected_models]}",
                                )

                                # Capture selected_models and date_range for closure
                                _patch_selected_models = list(self._selected_models)
                                _patch_date_range = dict(self._date_range) if self._date_range else {}

                                async def _filtered_process_paid_dict():
                                    """
                                    Optimised replacement for process_paid_dict.
                                    Calls get_all_paid_posts() once (single API request) then
                                    processes ONLY the selected models — skipping the 60+ extra
                                    profile.scrape_profile() calls that process_all_paid() would make.
                                    """
                                    import ofscraper.data.api.paid as _paid_api
                                    import ofscraper.db.operations as _db_ops
                                    import ofscraper.classes.of.posts as _posts_cls
                                    import ofscraper.db.operations_.media as _media_ops
                                    from ofscraper.managers.postcollection import PostCollection as _PC

                                    log.debug("[DIAG] Fetching all paid posts via single API call...")
                                    try:
                                        paid_content = await _paid_api.get_all_paid_posts()
                                    except Exception as _e:
                                        import traceback as _tb
                                        log.debug(f"[DIAG] get_all_paid_posts() RAISED: {_e}\n{_tb.format_exc()}")
                                        return

                                    log.debug(
                                        f"[DIAG] get_all_paid_posts() returned {len(paid_content)} entries. "
                                        f"Processing only {len(_patch_selected_models)} selected model(s)."
                                    )

                                    output = {}
                                    for _m in _patch_selected_models:
                                        _mid = _m.id
                                        _uname = _m.name
                                        # paid_content keys may be int or str
                                        _posts_data = (
                                            paid_content.get(_mid)
                                            or paid_content.get(str(_mid))
                                            or paid_content.get(int(_mid) if isinstance(_mid, str) else _mid)
                                        )
                                        if not _posts_data:
                                            log.debug(f"[DIAG] No paid content for {_uname} (id={_mid}) — skipping")
                                            continue
                                        log.debug(f"[DIAG] {_uname}: {len(_posts_data)} paid posts found")
                                        try:
                                            await _db_ops.table_init_create(model_id=_mid, username=_uname)
                                            _pc = _PC(username=_uname, model_id=_mid)
                                            _all_posts = [
                                                _posts_cls.Post(x, _mid, _uname, responsetype="Paid")
                                                for x in _posts_data
                                            ]
                                            _pc.add_posts(_all_posts, actions="scrape_paid_download")
                                            await _db_ops.make_post_table_changes(
                                                _pc.posts, model_id=_mid, username=_uname
                                            )
                                            await _media_ops.batch_mediainsert(
                                                _pc.all_unique_media,
                                                model_id=_mid,
                                                username=_uname,
                                                downloaded=False,
                                            )
                                            _final_medias = _pc.get_media_for_processing()
                                            _text_posts = _pc.get_posts_for_text_download()
                                            output[_mid] = dict(
                                                model_id=_mid,
                                                username=_uname,
                                                posts=_text_posts,
                                                medias=_final_medias,
                                            )
                                            log.debug(
                                                f"[DIAG] {_uname}: {len(_final_medias)} media items to download"
                                            )
                                            # Track scraped media IDs so the post-scrape DB load
                                            # shows only these items (not all historical records).
                                            _final_media_ids = {
                                                getattr(_mv, "id", None) for _mv in _final_medias
                                            } - {None}
                                            if not hasattr(self, "_scrape_paid_media_ids"):
                                                self._scrape_paid_media_ids = set()
                                            self._scrape_paid_media_ids.update(_final_media_ids)
                                            # Emit rows to the GUI table immediately after DB insert
                                            # so the table populates before (or during) downloads.
                                            try:
                                                # Pass media_ids so only the 40 scraped rows are shown,
                                                # not all 206 historical records in the DB.
                                                _load_models_from_db([_m], date_range={}, media_ids=_final_media_ids)
                                                log.debug(f"[DIAG] Live table rows emitted for {_uname}")
                                            except Exception as _emit_err:
                                                log.debug(f"[DIAG] Live row emit failed: {_emit_err}")
                                        except Exception as _e2:
                                            import traceback as _tb2
                                            log.debug(f"[DIAG] Error processing {_uname}: {_e2}\n{_tb2.format_exc()}")

                                    length = len(output)
                                    log.debug(f"[DIAG] Yielding {length} model(s) to download pipeline")
                                    for count, value in enumerate(output.values()):
                                        yield count, value, length

                                _spm.process_paid_dict = _filtered_process_paid_dict
                                log.debug("[DIAG] process_paid_dict patch applied successfully")
                            except Exception as _patch_err:
                                import traceback as _tb2
                                log.debug(f"[DIAG] Could not patch process_paid_dict: {_patch_err}\n{_tb2.format_exc()}")
                                _orig_process_paid_dict = None

                        # Monkey-patch scrape_paid.process_user to start/stop DB polling
                        # so the Downloaded column updates in real time while paid content
                        # is downloading (mirrors what _execute_user_action does for normal scrapes).
                        _orig_process_user = None
                        if self._scrape_paid:
                            try:
                                import ofscraper.data.posts.scrape_paid as _spm_paid
                                _orig_process_user = _spm_paid.process_user

                                async def _polled_process_user(_pu_value, _pu_length):
                                    _pu_medias = _pu_value.get("medias", [])
                                    _pu_mid = _pu_value.get("model_id")
                                    _pu_uname = _pu_value.get("username")
                                    if _pu_medias:
                                        _gui_state.start_polling(_pu_medias, _pu_mid, _pu_uname)
                                    try:
                                        return await _orig_process_user(_pu_value, _pu_length)
                                    finally:
                                        if _pu_medias:
                                            _gui_state.stop_polling()
                                            _emit_download_status(_pu_medias, _pu_mid, _pu_uname)

                                _spm_paid.process_user = _polled_process_user
                                log.debug("[DIAG] process_user polling patch applied successfully")
                            except Exception as _pu_err:
                                log.debug(f"[DIAG] Could not patch process_user: {_pu_err}")
                                _orig_process_user = None

                        if self._scrape_paid:
                            app_signals.status_message.emit(
                                "Fetching paid content from API — this may take several minutes..."
                            )
                            app_signals.log_message.emit(
                                "INFO",
                                "Paid scrape: retrieving metadata for all subscriptions from the API. "
                                "Progress will appear at 0%% until data fetch completes. Please wait...",
                            )

                        # Wrap scrape_paid_all to diagnose where the hang is
                        try:
                            import ofscraper.data.posts.scrape_paid as _spm2
                            _orig_spa = _spm2.scrape_paid_all
                            def _diag_scrape_paid_all():
                                log.debug("[DIAG] scrape_paid_all() STARTED")
                                try:
                                    result = _orig_spa()
                                    log.debug("[DIAG] scrape_paid_all() FINISHED normally")
                                    return result
                                except Exception as _spa_err:
                                    import traceback as _tb4
                                    log.debug(f"[DIAG] scrape_paid_all() RAISED: {_spa_err}\n{_tb4.format_exc()}")
                                    raise
                            import ofscraper.commands.scraper.scraper as _scraper_mod
                            _scraper_mod.scrape_paid_all = _diag_scrape_paid_all
                        except Exception as _wrap_err:
                            log.debug(f"[DIAG] Could not wrap scrape_paid_all: {_wrap_err}")
                            _orig_spa = None
                            _scraper_mod = None

                        # Snapshot DB file mtimes before runner() touches them.
                        # Used by _load_models_from_db (no-date-filter path) to
                        # show only content since the last run, not all-time history.
                        # NOTE: databasePlaceholder().databasePathHelper() requires
                        # an active session (me.parse_user → scrape_user) which is
                        # not available before runner() starts. We therefore use a
                        # session-free fallback: {config_home}/{profile}/.data/{id}/user_data.db
                        try:
                            import pathlib as _pathlib_mtime
                            import arrow as _arrow_mtime
                            import ofscraper.utils.paths.common as _cp_mtime
                            import ofscraper.utils.profiles.data as _pd_mtime
                            _cfg_home = str(_cp_mtime.get_config_home())
                            _act_profile = str(_pd_mtime.get_active_profile())
                            for _m_mtime in self._selected_models:
                                try:
                                    # Primary: use placeholder for custom metadata paths
                                    _db_p = None
                                    try:
                                        import ofscraper.classes.placeholder as _ph_mtime
                                        _db_p = _pathlib_mtime.Path(
                                            _ph_mtime.databasePlaceholder().databasePathHelper(
                                                _m_mtime.id, _m_mtime.name
                                            )
                                        )
                                    except Exception as _ph_err:
                                        # Fallback: default metadata path format
                                        # {config_home}/{profile}/.data/{model_id}/user_data.db
                                        log.debug(
                                            f"[DIAG] mtime: placeholder failed for {_m_mtime.name}"
                                            f" ({type(_ph_err).__name__}: {_ph_err})"
                                            f" — using fallback path"
                                        )
                                        _db_p = _pathlib_mtime.Path(
                                            _cfg_home, _act_profile, ".data",
                                            str(_m_mtime.id), "user_data.db"
                                        )
                                    if _db_p is not None and _db_p.exists():
                                        try:
                                            import sqlite3 as _sq3_mtime
                                            _sq_conn = _sq3_mtime.connect(str(_db_p))
                                            try:
                                                _sq_row = _sq_conn.execute(
                                                    "SELECT MAX(posted_at) FROM medias"
                                                ).fetchone()
                                            finally:
                                                _sq_conn.close()
                                            _max_posted = _sq_row[0] if _sq_row else None
                                            if _max_posted:
                                                self._db_prerun_mtimes[_m_mtime.id] = (
                                                    _arrow_mtime.get(_max_posted)
                                                )
                                                log.debug(
                                                    f"[DIAG] DB max post date for {_m_mtime.name}:"
                                                    f" {self._db_prerun_mtimes[_m_mtime.id]}"
                                                    f" (path: {_db_p})"
                                                )
                                            else:
                                                log.debug(
                                                    f"[DIAG] DB has no records for {_m_mtime.name}"
                                                    f" — new model, no date limit"
                                                )
                                        except Exception as _sq_err:
                                            log.debug(
                                                f"[DIAG] DB content query failed for {_m_mtime.name}:"
                                                f" {_sq_err} — no date limit applied"
                                            )
                                    else:
                                        log.debug(
                                            f"[DIAG] DB not found at {_db_p}"
                                            f" for {_m_mtime.name} — new model, no date limit"
                                        )
                                except Exception as _inner_err:
                                    log.debug(
                                        f"[DIAG] mtime capture failed for"
                                        f" {getattr(_m_mtime, 'name', '?')}: {_inner_err}"
                                    )
                        except Exception as _outer_err:
                            log.debug(f"[DIAG] mtime capture outer error: {_outer_err}")

                        # Capture per-model download counts from the DB before runner()
                        # so the Discord summary can show accurate per-model "new this run"
                        # deltas rather than stamping the global total on every model.
                        try:
                            self._db_prerun_dl_counts = _load_models_from_db(
                                self._selected_models,
                                stats_only=True,
                            )
                        except Exception as _pre_dl_err:
                            log.debug(f"[DIAG] pre-scrape dl snapshot failed: {_pre_dl_err}")
                            self._db_prerun_dl_counts = {}

                        log.debug("[DIAG] About to call scraping_manager.runner()")
                        try:
                            scraping_manager.runner()
                        except Exception as _runner_err:
                            import traceback as _tb3
                            log.debug(f"[DIAG] runner() RAISED: {_runner_err}\n{_tb3.format_exc()}")
                            raise
                        finally:
                            log.debug("[DIAG] runner() exited (finally block)")
                            if _orig_process_paid_dict is not None:
                                try:
                                    import ofscraper.data.posts.scrape_paid as _spm
                                    _spm.process_paid_dict = _orig_process_paid_dict
                                except Exception:
                                    pass
                            # Restore process_user polling patch
                            if _orig_process_user is not None:
                                try:
                                    import ofscraper.data.posts.scrape_paid as _spm_paid2
                                    _spm_paid2.process_user = _orig_process_user
                                except Exception:
                                    pass
                            # Restore scrape_paid_all wrapper
                            try:
                                if _orig_spa is not None and _scraper_mod is not None:
                                    _scraper_mod.scrape_paid_all = _orig_spa
                            except Exception:
                                pass

                    # Mute Discord immediately after runner() — the handler
                    # was enabled for scrape notifications and must be silenced
                    # before the DB load to avoid spam.  The actual summary is
                    # sent AFTER _load_models_from_db completes.
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
                # _load_models_from_db reads via SQLite (no FileLock needed —
                # SQLite handles concurrent reads natively).  It returns
                # per-model media counts which we use for the Discord summary.
                _db_stats = {}
                # scrape_paid_all() bypasses _execute_user_action entirely, so
                # live rows are never emitted for content fetched via the global
                # paid endpoint. We must load from DB afterward to show those rows.
                # Using self._scrape_paid (not "Purchased" in areas) because:
                #   - scrape_paid=True  → scrape_paid_all() was called → no live rows → DB load needed
                #   - scrape_paid=False + "Purchased" in areas → per-user endpoint → live rows emitted → DB load NOT needed
                _used_global_paid = self._scrape_paid
                _has_date_filter = bool((self._date_range or {}).get("enabled", False))
                _diag_has_dl = "download" in self._selected_actions
                _diag_has_models = bool(self._selected_models)
                _diag_live = self._live_rows_emitted
                _diag_not_paid = not _used_global_paid
                _diag_not_check = not bool(self._selected_actions & self._CHECK_MODES)
                _diag_run1 = run_count == 1
                log.debug(
                    f"[DIAG] is_normal_gui_download conditions: "
                    f"has_dl={_diag_has_dl}, has_models={_diag_has_models}, "
                    f"live_rows={_diag_live}, not_paid={_diag_not_paid}, "
                    f"not_check={_diag_not_check}, run1={_diag_run1} "
                    f"| actions={self._selected_actions}"
                )
                is_normal_gui_download = (
                    _diag_has_dl
                    and _diag_has_models
                    and _diag_live
                    and _diag_not_paid
                    and _diag_not_check
                    and _diag_run1
                )
                if is_normal_gui_download:
                    app_signals.log_message.emit(
                        "INFO", "Skipping DB table replacement for normal GUI download scrape; keeping live rows from this run..."
                    )
                    # Still read DB stats so the Discord summary shows correct counts.
                    _db_stats = _load_models_from_db(
                        self._selected_models,
                        date_range={} if self._scrape_paid else (self._date_range or {}),
                        stats_only=True,
                    )
                elif self._live_rows_emitted and not _used_global_paid and run_count == 1 and _has_date_filter:
                    app_signals.log_message.emit(
                        "INFO", "Skipping DB table replacement because live rows were already emitted for this run..."
                    )
                else:
                    log.debug(f"[DIAG] Calling _load_models_from_db for {[m.name for m in self._selected_models]}, date_range={self._date_range}")
                    app_signals.log_message.emit(
                        "INFO", "Loading content from database..."
                    )
                    _db_stats = _load_models_from_db(
                        self._selected_models,
                        # Skip date filter for paid scrapes — the API already filtered
                        # to purchased content; DB posted_at may be the original creation
                        # date (not purchase date), so date filtering drops valid rows.
                        date_range={} if self._scrape_paid else (self._date_range or {}),
                        # For paid scrapes, limit to only the media IDs we actually scraped
                        # so we don't show all 200+ historical records in the DB.
                        # Manual URL scrapes similarly restrict to the URLs just processed.
                        media_ids=(
                            getattr(self, "_scrape_paid_media_ids", None)
                            if self._scrape_paid
                            else (
                                getattr(self, "_manual_media_ids", None)
                                if self._selected_actions == {"manual_url"}
                                else None
                            )
                        ),
                        # For non-paid no-date-filter runs, restrict the table to content
                        # posted since the DB was last touched — hides pre-run historical
                        # duplicates and limits the table to the current scrape window.
                        # Skip for manual URL (media_ids already scopes the table).
                        per_model_from_dates=(
                            None
                            if (
                                self._scrape_paid
                                or self._selected_actions == {"manual_url"}
                            )
                            else getattr(self, "_db_prerun_mtimes", {})
                        ),
                    )
                    log.debug(f"[DIAG] _load_models_from_db returned stats: {_db_stats}")

                # Post per-model stats to Discord now that we have accurate
                # counts from the FileLock-protected DB read above.
                # Prefer the GUI selection; fall back to settings/CLI (--discord)
                # so Docker GUI_ARGS still get scrape summaries / @here.
                _discord_for_summary = self._discord_level
                if _discord_for_summary == "OFF":
                    try:
                        import ofscraper.utils.settings as _sum_settings

                        _from_settings = str(
                            getattr(
                                _sum_settings.get_settings(), "discord_level", "OFF"
                            )
                            or "OFF"
                        ).upper()
                        if _from_settings in ("LOW", "NORMAL"):
                            _discord_for_summary = _from_settings
                    except Exception:
                        pass
                if _discord_for_summary != "OFF":
                    try:
                        import logging as _dlog
                        # Briefly re-enable Discord just for this summary.
                        import ofscraper.utils.logs.utils.level as _ll
                        from ofscraper.utils.logs.classes.handlers.discord import (
                            DiscordHandler as _DH,
                        )
                        _lvl = _ll.getLevel(_discord_for_summary)
                        for _h in _dlog.getLogger("shared").handlers:
                            if isinstance(_h, _DH):
                                _h.setLevel(_lvl)
                                break
                        # Build per-model rows first so we can sum actual new
                        # downloads before deciding whether to send @here.
                        _pre_dl = getattr(self, "_db_prerun_dl_counts", {})
                        _model_rows = []
                        _run_total_new = 0
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
                            # Compute per-model "new this run" using the actual physical
                            # downloaded counts from the StatsManager for this model.
                            _new_photos = 0
                            _new_videos = 0
                            _new_audios = 0
                            try:
                                import ofscraper.managers.manager as _manager_mod
                                from ofscraper.managers.utils.state import EActivity
                                _sm = _manager_mod.Manager.stats_manager
                                _dl_stat = _sm._stats.get(_un, {}).get(EActivity.ScrapeActivity.DOWNLOAD)
                                _paid_dl_stat = _sm._stats.get(_un, {}).get(EActivity.PaidActivity.SCRAPE_PAID_DOWNLOAD)

                                _has_stats = False
                                if _dl_stat and _dl_stat.has_changes:
                                    _new_photos += _dl_stat.photo_count
                                    _new_videos += _dl_stat.video_count
                                    _new_audios += _dl_stat.audio_count
                                    _has_stats = True

                                if _paid_dl_stat and _paid_dl_stat.has_changes:
                                    _new_photos += _paid_dl_stat.photo_count
                                    _new_videos += _paid_dl_stat.video_count
                                    _new_audios += _paid_dl_stat.audio_count
                                    _has_stats = True

                                if not _has_stats or (_new_photos + _new_videos + _new_audios == 0):
                                    # Fallback to DB delta if StatsManager has no recorded changes or reported 0 new downloads (common in GUI mode)
                                    _pre = _pre_dl.get(_un, {})
                                    _new_photos = max(0, _dl_photos - _pre.get("dl_photos", 0))
                                    _new_videos = max(0, _dl_videos - _pre.get("dl_videos", 0))
                                    _new_audios = max(0, _dl_audios - _pre.get("dl_audios", 0))
                            except Exception as _st_err:
                                log.debug(f"[DIAG] Failed to get stats from StatsManager for {_un}: {_st_err}")
                                _pre = _pre_dl.get(_un, {})
                                _new_photos = max(0, _dl_photos - _pre.get("dl_photos", 0))
                                _new_videos = max(0, _dl_videos - _pre.get("dl_videos", 0))
                                _new_audios = max(0, _dl_audios - _pre.get("dl_audios", 0))

                            _new_total = _new_photos + _new_videos + _new_audios
                            _run_total_new += _new_total
                            # Use \[ to escape brackets so Rich's markup parser
                            # (inside DiscordFormatter) doesn't strip [username] as a style tag.
                            _model_rows.append(
                                f"\\[{_un}] {_new_total} new this run"
                                f" [{_new_videos} videos,"
                                f" {_new_audios} audios,"
                                f" {_new_photos} photos]"
                                f" | {_dl_total}/{_total} total in DB"
                            )
                        _daemon_ping = False
                        if self._daemon_enabled and _run_total_new > 0:
                            try:
                                import ofscraper.utils.settings as _settings
                                if getattr(_settings.get_args(), "discord_ping", False):
                                    _daemon_ping = True
                                else:
                                    from ofscraper.gui.utils.gui_settings import load_gui_settings as _lgs
                                    _daemon_ping = bool(_lgs().get("daemon_discord_ping", False))
                            except Exception:
                                pass
                        _lines = ["@here"] if _daemon_ping else []
                        _lines.append("\n\n--- Scrape Results ---")
                        _lines.extend(_model_rows)
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

                # Prepare plugin coordination before notifying the GUI thread.
                # This clears the post-scrape event so _daemon_wait() will pause
                # if a plugin needs time to do async work after on_scrape_complete.
                try:
                    from ofscraper.plugins.manager import plugin_manager as _pm_pre
                    _pm_pre.pre_scrape_complete()
                except Exception:
                    pass

                try:
                    from ofscraper.gui.utils.progress_bridge import flush_pending

                    flush_pending()
                except Exception:
                    pass

                # Build summary before notifying the GUI so history / daemon chip
                # can consume it (QueuedConnection races are otherwise flaky).
                _run_summary = None
                try:
                    _run_summary = build_pending_summary_payload(
                        self,
                        is_normal_gui_download=is_normal_gui_download,
                        db_stats=_db_stats,
                    )
                    if _run_summary is not None:
                        import ofscraper.gui.utils.workflow as _wf_mod

                        _wf_mod._pending_summary_data = _run_summary
                except Exception:
                    _run_summary = None

                app_signals.scraping_finished.emit()

                if not self._daemon_enabled:
                    try:
                        from ofscraper.gui.utils.host_callbacks import get_host

                        get_host().on_phase("complete")
                        get_host().on_status("Scraping complete")
                    except Exception:
                        app_signals.status_message.emit("Scraping complete")
                    app_signals.log_message.emit(
                        "INFO", "Scraping pipeline finished"
                    )
                    break

                # Daemon mode: surface last-run chip, then wait for interval
                try:
                    chip = format_daemon_last_run_chip(run_count, _run_summary)
                    app_signals.daemon_last_run.emit(chip)
                except Exception:
                    pass
                try:
                    from ofscraper.gui.utils.host_callbacks import get_host

                    get_host().on_phase("daemon")
                    get_host().on_status(
                        f"Run #{run_count} complete. Next in {self._daemon_interval:.0f} min…"
                    )
                except Exception:
                    app_signals.status_message.emit(
                        f"Run #{run_count} complete. Next in {self._daemon_interval:.0f} min…"
                    )
                app_signals.log_message.emit(
                    "INFO",
                    f"Daemon run #{run_count} complete. "
                    f"Next run in {self._daemon_interval} minutes.",
                )

                if not self._daemon_wait():
                    # Stop was requested during wait
                    try:
                        from ofscraper.gui.utils.host_callbacks import get_host

                        get_host().on_phase("ready")
                        get_host().on_status("Daemon stopped")
                    except Exception:
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
            try:
                from ofscraper.gui.utils.host_callbacks import get_host

                get_host().on_phase("ready")
                get_host().on_status("Scraping cancelled")
            except Exception:
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
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("scrape_live_stubs_uninstall")
            except Exception:
                pass
            _uninstall_gui_live_stubs()
            _uninstall_gui_log_handler()
            try:
                from ofscraper.gui.utils.crash_diagnostics import set_scrape_active

                set_scrape_active(False)
            except Exception:
                pass
            try:
                from ofscraper.plugins.manager import plugin_manager as _pm_fin
                _pm_fin.pre_scrape_complete()
            except Exception:
                pass
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

            try:
                db_path = pathlib.Path(
                    placeholder.databasePlaceholder().databasePathHelper(model_id, username)
                )
            except Exception as _ph_err:
                import ofscraper.utils.paths.common as _cp_mtime
                import ofscraper.utils.profiles.data as _pd_mtime
                _cfg_home = str(_cp_mtime.get_config_home())
                _act_profile = str(_pd_mtime.get_active_profile())
                db_path = pathlib.Path(
                    _cfg_home, _act_profile, ".data",
                    str(model_id), "user_data.db"
                )
                log.debug(
                    f"[Purge] databasePathHelper failed for {username} "
                    f"({type(_ph_err).__name__}: {_ph_err}) — using fallback path: {db_path}"
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
