from PyQt6.QtCore import QObject, pyqtSignal

# Lazily created after QApplication exists (see ensure_app_signals).
# Creating QObject before QApplication leaves a dead C++ peer and causes
# "wrapped C/C++ object of type AppSignals has been deleted" from worker threads.
_app_signals_instance: "AppSignals | None" = None


class AppSignals(QObject):
    """Central signal hub for cross-component communication in the GUI."""

    # Navigation
    navigate_to_page = pyqtSignal(str)  # page name
    help_anchor_requested = pyqtSignal(str)  # anchor id within Help/README

    # Scraper workflow
    action_selected = pyqtSignal(set)  # set of action names
    models_selected = pyqtSignal(list)  # list of model objects
    areas_selected = pyqtSignal(list)  # list of area strings
    scrape_paid_toggled = pyqtSignal(bool)
    scrape_labels_toggled = pyqtSignal(bool)
    advanced_scrape_configured = pyqtSignal(object)  # dict of advanced options
    discord_configured = pyqtSignal(str)   # discord level: "OFF", "LOW", or "NORMAL"
    msg_check_include_free_toggled = pyqtSignal(str)  # "paid_only" | "free_only" | "all"

    # Data loading
    data_loading_started = pyqtSignal()
    data_loading_finished = pyqtSignal(list)  # table data rows (appended)
    data_replace = pyqtSignal(list)           # table data rows (replaces all existing rows)
    data_loading_error = pyqtSignal(str)  # error message

    # Table / Downloads
    downloads_queued = pyqtSignal(list)  # list of row data to download
    download_cart_updated = pyqtSignal(int)  # count of items in cart

    # Progress
    progress_task_added = pyqtSignal(str, int)  # task_id, total
    progress_task_updated = pyqtSignal(str, int)  # task_id, current
    progress_task_removed = pyqtSignal(str)  # task_id
    overall_progress_updated = pyqtSignal(int, int)  # completed, total
    download_speed_updated = pyqtSignal(float)  # bytes per second
    total_bytes_updated = pyqtSignal(float)  # total bytes downloaded

    # Cell updates from download process
    cell_update = pyqtSignal(str, str, str)  # row_key, column_name, new_value
    # Batched cell updates: list of (row_key, column_name, new_value) tuples
    batch_cell_update = pyqtSignal(list)

    # Log
    log_message = pyqtSignal(str, str)  # level, message

    # Scraping lifecycle
    scraping_finished = pyqtSignal()  # emitted when scraper thread completes
    scrape_started = pyqtSignal()  # emitted when scraper background thread starts
    cancel_scrape_requested = pyqtSignal()  # UI requests current scrape cancel
    # Host-callback phase for unified status strip:
    # ready | running | cancelling | daemon | complete
    scrape_phase_changed = pyqtSignal(str)
    # Per-model live badges (Select Models → scrape table)
    model_badges_reset = pyqtSignal(list)  # usernames at scrape start
    model_item_started = pyqtSignal(str)  # username now processing
    model_item_result = pyqtSignal(str, bool, str)  # username, ok, error

    # Media type filter from area selector page
    mediatypes_configured = pyqtSignal(list)  # list of media type strings e.g. ["Images", "Videos"]

    # Include post text flag from area selector page
    include_text_configured = pyqtSignal(bool)

    # Name .txt files from caption instead of File Format / post id
    text_filename_from_post_configured = pyqtSignal(bool)

    # Date range filter from area selector page
    date_range_configured = pyqtSignal(object)  # dict: {enabled, from_date, to_date} (date strings "YYYY-MM-DD")

    # Daemon mode
    daemon_configured = pyqtSignal(bool, float, bool, bool)  # enabled, interval_min, notify, sound
    daemon_next_run = pyqtSignal(str)  # countdown text like "Next run in 12:34 (≈ 9:52 PM)"
    daemon_last_run = pyqtSignal(str)  # compact last-run chip e.g. "Last run #2: 42 dl · 1 fail"
    daemon_run_starting = pyqtSignal(int)  # run number (emitted when a daemon re-run begins)
    daemon_stopped = pyqtSignal()  # emitted when daemon loop is cancelled
    stop_daemon_requested = pyqtSignal()  # UI requests daemon stop

    # Manual URL / post-ID scraping (bypasses model + area selection)
    manual_urls_confirmed = pyqtSignal(list)  # list of URL/ID strings

    # Notifications
    show_notification = pyqtSignal(str, str)  # title, message (system tray toast)

    # Like/Unlike results: dict of {post_id (int): status_str} where
    # status_str is "Liked", "Unliked", or "Failed"
    posts_liked_updated = pyqtSignal(object)

    # Status
    status_message = pyqtSignal(str)  # status bar text
    error_occurred = pyqtSignal(str, str)  # title, message

    # Theme
    theme_changed = pyqtSignal(bool)  # True = dark, False = light

    # Global GUI text size (px, design baseline 13)
    font_size_changed = pyqtSignal(int)

    # Privacy / demo mode (mask secrets & paths in UI)
    privacy_mode_changed = pyqtSignal(bool)  # True = privacy on

    # Config / auth health (status strip chips)
    config_updated = pyqtSignal()  # emitted whenever config.json is written
    auth_updated = pyqtSignal()  # emitted whenever auth.json is saved
    health_refresh_requested = pyqtSignal()  # force status-strip health chips to recheck


def _is_deleted(obj) -> bool:
    if obj is None:
        return True
    try:
        from PyQt6 import sip

        return bool(sip.isdeleted(obj))
    except Exception:
        try:
            obj.objectName()
            return False
        except RuntimeError:
            return True


def ensure_app_signals() -> AppSignals:
    """Create (or recreate) the global AppSignals parented to QApplication."""
    global _app_signals_instance
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if _app_signals_instance is not None and not _is_deleted(_app_signals_instance):
        return _app_signals_instance

    # Parent to the application so the C++ peer lives for the whole GUI session.
    _app_signals_instance = AppSignals(app) if app is not None else AppSignals()
    return _app_signals_instance


def get_app_signals() -> AppSignals:
    """Return the live AppSignals instance (creating it if needed)."""
    global _app_signals_instance
    if _app_signals_instance is None or _is_deleted(_app_signals_instance):
        return ensure_app_signals()
    return _app_signals_instance


class _AppSignalsProxy:
    """Module-level stand-in so ``from … import app_signals`` keeps working.

    Attribute access always resolves to the live AppSignals instance created
    after QApplication exists.
    """

    def __getattr__(self, name: str):
        return getattr(get_app_signals(), name)

    def __repr__(self) -> str:
        return f"<AppSignalsProxy alive={not _is_deleted(_app_signals_instance)}>"


# Import-safe proxy (does not construct a QObject at import time).
app_signals = _AppSignalsProxy()
