from PyQt6.QtCore import QObject, pyqtSignal


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
    discord_configured = pyqtSignal(bool)  # enable discord webhook updates (uses --discord)

    # Data loading
    data_loading_started = pyqtSignal()
    data_loading_finished = pyqtSignal(list)  # table data rows
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
    total_bytes_updated = pyqtSignal(int)  # total bytes downloaded

    # Cell updates from download process
    cell_update = pyqtSignal(str, str, str)  # row_key, column_name, new_value

    # Log
    log_message = pyqtSignal(str, str)  # level, message

    # Scraping lifecycle
    scraping_finished = pyqtSignal()  # emitted when scraper thread completes
    cancel_scrape_requested = pyqtSignal()  # UI requests current scrape cancel

    # Daemon mode
    daemon_configured = pyqtSignal(bool, float, bool, bool)  # enabled, interval_min, notify, sound
    daemon_next_run = pyqtSignal(str)  # countdown text like "Next scrape in 12:34"
    daemon_run_starting = pyqtSignal(int)  # run number (emitted when a daemon re-run begins)
    daemon_stopped = pyqtSignal()  # emitted when daemon loop is cancelled
    stop_daemon_requested = pyqtSignal()  # UI requests daemon stop

    # Notifications
    show_notification = pyqtSignal(str, str)  # title, message (system tray toast)

    # Status
    status_message = pyqtSignal(str)  # status bar text
    error_occurred = pyqtSignal(str, str)  # title, message

    # Theme
    theme_changed = pyqtSignal(bool)  # True = dark, False = light


# Global signal instance
app_signals = AppSignals()
