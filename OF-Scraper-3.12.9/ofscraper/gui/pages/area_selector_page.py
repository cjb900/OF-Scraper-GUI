import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.widgets.sidebar import FilterSidebar
from ofscraper.gui.widgets.styled_button import StyledButton
import ofscraper.utils.config.data as config_data

log = logging.getLogger("shared")

def _help_btn_qss():
    return (
        f"QToolButton {{ border: 1px solid {c('surface1')}; border-radius: 9px;"
        f" background-color: {c('surface0')}; color: {c('text')}; font-weight: bold; }}"
        f" QToolButton:hover {{ border-color: {c('blue')}; background-color: {c('surface1')}; }}"
    )

def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help for this section/option")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(_help_btn_qss())
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b

DOWNLOAD_AREAS = [
    "Profile",
    "Timeline",
    "Pinned",
    "Archived",
    "Highlights",
    "Stories",
    "Messages",
    "Purchased",
    "Streams",
    "Labels",
]

LIKE_AREAS = [
    "Timeline",
    "Pinned",
    "Archived",
    "Streams",
    "Labels",
]


class AreaSelectorPage(QWidget):
    """Content area + filter configuration page.
    Shows area checkboxes and filter options in a single scrollable layout.
    The 'Next' button proceeds to model selection."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._current_actions = set()
        self._area_checks = {}
        self._models_loading = False
        self._models_loaded = False
        self._models_error = None
        self._loaded_model_count = 0
        self._separators = []
        self._setup_ui()
        self._connect_signals()
        self._refresh_discord_option_state()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Single scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 24, 24, 8)
        layout.setSpacing(12)

        # Header
        header = QLabel("Select Content Areas & Filters")
        header.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Configure what to scrape and how to filter results."
        )
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        # Areas group
        self.areas_group = QGroupBox("Content Areas")
        self.areas_grid = QGridLayout(self.areas_group)
        self.areas_grid.setSpacing(8)

        _area_tips = {
            "Profile": "Scrape the model's profile header media (avatar, banner).",
            "Timeline": "Scrape posts from the model's main timeline feed.",
            "Pinned": "Scrape pinned posts on the model's profile.",
            "Archived": "Scrape archived/expired posts.",
            "Highlights": "Scrape story highlights (saved stories).",
            "Stories": "Scrape current (active/recent) stories.",
            "Messages": "Scrape direct messages and PPV message media.",
            "Purchased": "Scrape purchased/unlocked PPV content.",
            "Streams": "Scrape livestream recordings.",
            "Labels": "Scrape content organized under the model's labels/categories.",
        }
        for i, area in enumerate(DOWNLOAD_AREAS):
            cb = QCheckBox(area)
            cb.setFont(QFont("Segoe UI", 11))
            cb.setChecked(True)
            cb.setToolTip(_area_tips.get(area, ""))
            row = i // 3
            col = i % 3
            self.areas_grid.addWidget(cb, row, col)
            self._area_checks[area] = cb

        layout.addWidget(self.areas_group)

        # Bulk buttons
        bulk_layout = QHBoxLayout()
        select_all = StyledButton("Select All")
        select_all.clicked.connect(self._select_all)
        bulk_layout.addWidget(select_all)

        deselect_all = StyledButton("Deselect All")
        deselect_all.clicked.connect(self._deselect_all)
        bulk_layout.addWidget(deselect_all)
        bulk_layout.addStretch()
        bulk_layout.addWidget(_make_help_btn("sca-content-areas"))
        layout.addLayout(bulk_layout)

        # Extra options
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(sep)
        layout.addWidget(sep)

        extras_group = QGroupBox("Additional Options")
        extras_layout = QVBoxLayout(extras_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("sca-additional-options"))
        extras_layout.addLayout(h)

        self.scrape_paid_check = QCheckBox(
            "Scrape entire paid page (slower but more comprehensive)"
        )
        self.scrape_paid_check.setFont(QFont("Segoe UI", 11))
        self.scrape_paid_check.setToolTip(
            "Tries harder to enumerate all paid/purchased items.\n"
            "May be significantly slower but catches items missed by normal scraping."
        )
        row = QHBoxLayout()
        row.addWidget(self.scrape_paid_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-scrape-paid"))
        extras_layout.addLayout(row)

        self.scrape_labels_check = QCheckBox("Scrape labels")
        self.scrape_labels_check.setFont(QFont("Segoe UI", 11))
        self.scrape_labels_check.setToolTip(
            "Pull content organized by the model's custom labels/categories when available."
        )
        row = QHBoxLayout()
        row.addWidget(self.scrape_labels_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-scrape-labels"))
        extras_layout.addLayout(row)

        # Discord webhook option (enabled only if config has a webhook URL)
        self.discord_updates_check = QCheckBox(
            "Send updates to Discord (requires webhook URL in Config → General)"
        )
        self.discord_updates_check.setFont(QFont("Segoe UI", 11))
        self.discord_updates_check.setChecked(False)
        self.discord_updates_check.setToolTip(
            "When enabled, the GUI will run with the equivalent of --discord NORMAL\n"
            "so log updates are posted to your configured Discord webhook."
        )
        row = QHBoxLayout()
        row.addWidget(self.discord_updates_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-discord-updates"))
        extras_layout.addLayout(row)
        layout.addWidget(extras_group)

        # Advanced options
        adv_group = QGroupBox("Advanced Scrape Options")
        adv_layout = QVBoxLayout(adv_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("sca-advanced-options"))
        adv_layout.addLayout(h)

        self.allow_dupes_check = QCheckBox(
            "Allow duplicates (do NOT skip duplicates; treat reposts as new items)"
        )
        self.allow_dupes_check.setFont(QFont("Segoe UI", 11))
        self.allow_dupes_check.setToolTip(
            "Disables duplicate-skipping logic.\n"
            "When enabled, reposted media will appear as separate entries in the table."
        )
        row = QHBoxLayout()
        row.addWidget(self.allow_dupes_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-allow-dupes"))
        adv_layout.addLayout(row)

        self.rescrape_all_check = QCheckBox(
            "Rescrape everything (ignore cache / scan from the beginning)"
        )
        self.rescrape_all_check.setFont(QFont("Segoe UI", 11))
        self.rescrape_all_check.setToolTip(
            "Forces a full history scan, ignoring any cached 'after' timestamps.\n"
            "Useful if you suspect missed content or want a complete re-scan."
        )
        self.rescrape_all_check.toggled.connect(self._on_rescrape_toggled)
        row = QHBoxLayout()
        row.addWidget(self.rescrape_all_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-rescrape-all"))
        adv_layout.addLayout(row)

        self.delete_db_check = QCheckBox(
            "Delete model DB before scraping (resets downloaded/unlocked history)"
        )
        self.delete_db_check.setFont(QFont("Segoe UI", 11))
        self.delete_db_check.setEnabled(False)
        self.delete_db_check.setToolTip(
            "Deletes the model's SQLite database before scraping starts.\n"
            "This resets all downloaded/unlocked tracking, so everything appears as new.\n"
            "Requires 'Rescrape everything' to be enabled."
        )
        row = QHBoxLayout()
        row.addWidget(self.delete_db_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-delete-db"))
        adv_layout.addLayout(row)

        self.delete_downloads_check = QCheckBox(
            "Also delete existing downloaded files for selected models"
        )
        self.delete_downloads_check.setFont(QFont("Segoe UI", 11))
        self.delete_downloads_check.setEnabled(False)
        self.delete_downloads_check.setToolTip(
            "Removes previously downloaded files for the selected models.\n"
            "WARNING: This permanently deletes files from your save location.\n"
            "Requires 'Delete model DB' to be enabled."
        )
        self.delete_downloads_check.toggled.connect(self._on_delete_downloads_toggled)
        row = QHBoxLayout()
        row.addWidget(self.delete_downloads_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-delete-downloads"))
        adv_layout.addLayout(row)

        hint = QLabel(
            "Tip: deleting files uses your model DB to locate paths, so keep the DB delete option enabled."
        )
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        adv_layout.addWidget(hint)

        layout.addWidget(adv_group)

        # Daemon mode
        sep_daemon = QFrame()
        sep_daemon.setFrameShape(QFrame.Shape.HLine)
        sep_daemon.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(sep_daemon)
        layout.addWidget(sep_daemon)

        daemon_group = QGroupBox("Daemon Mode (Auto-Repeat Scraping)")
        daemon_layout = QVBoxLayout(daemon_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("sca-daemon-mode"))
        daemon_layout.addLayout(h)

        self.daemon_check = QCheckBox(
            "Enable daemon mode (automatically re-scrape on a schedule)"
        )
        self.daemon_check.setFont(QFont("Segoe UI", 11))
        self.daemon_check.setToolTip(
            "Automatically repeats the scrape at a fixed interval.\n"
            "The GUI will show a countdown timer between runs."
        )
        self.daemon_check.toggled.connect(self._on_daemon_toggled)
        row = QHBoxLayout()
        row.addWidget(self.daemon_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-daemon-enable"))
        daemon_layout.addLayout(row)

        interval_layout = QHBoxLayout()
        interval_label = QLabel("Interval:")
        interval_label.setFont(QFont("Segoe UI", 11))
        interval_layout.addWidget(interval_label)

        self.daemon_interval = QDoubleSpinBox()
        self.daemon_interval.setRange(1.0, 1440.0)
        self.daemon_interval.setValue(30.0)
        self.daemon_interval.setSuffix(" minutes")
        self.daemon_interval.setDecimals(1)
        self.daemon_interval.setSingleStep(5.0)
        self.daemon_interval.setFont(QFont("Segoe UI", 11))
        self.daemon_interval.setEnabled(False)
        self.daemon_interval.setToolTip(
            "Minutes between each automatic scrape run (1-1440).\n"
            "1440 minutes = 24 hours."
        )
        interval_layout.addWidget(self.daemon_interval)
        interval_layout.addWidget(_make_help_btn("sca-daemon-interval"))
        interval_layout.addStretch()
        daemon_layout.addLayout(interval_layout)

        self.notify_check = QCheckBox("System notification when scraping starts")
        self.notify_check.setFont(QFont("Segoe UI", 11))
        self.notify_check.setToolTip(
            "Show a system tray notification when each daemon scrape run begins."
        )
        row = QHBoxLayout()
        row.addWidget(self.notify_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-daemon-notify"))
        daemon_layout.addLayout(row)

        self.sound_check = QCheckBox("Sound alert when scraping starts")
        self.sound_check.setFont(QFont("Segoe UI", 11))
        self.sound_check.setToolTip(
            "Play a beep sound when each daemon scrape run begins (Windows only)."
        )
        row = QHBoxLayout()
        row.addWidget(self.sound_check)
        row.addStretch()
        row.addWidget(_make_help_btn("sca-daemon-sound"))
        daemon_layout.addLayout(row)

        layout.addWidget(daemon_group)

        # Separator before filters
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(sep2)
        layout.addWidget(sep2)

        # Filter widgets embedded inline (no separate scroll)
        self.filter_sidebar = FilterSidebar(embedded=True)
        layout.addWidget(self.filter_sidebar)

        layout.addSpacing(16)

        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Bottom navigation bar
        self._nav_bar = nav_bar = QWidget()
        nav_bar.setFixedHeight(56)
        nav_bar.setStyleSheet(f"background-color: {c('mantle')};")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(24, 8, 24, 8)

        back_btn = StyledButton("<< Back")
        back_btn.clicked.connect(self._on_back)
        nav_layout.addWidget(back_btn)

        nav_layout.addSpacing(24)

        self.next_btn = StyledButton("Next: Select Models  >>", primary=True)
        self.next_btn.setFixedWidth(240)
        self.next_btn.setFixedHeight(38)
        self.next_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.next_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('blue')}; color: {c('base')};"
            f" font-weight: bold; border: none; border-radius: 6px;"
            f" padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('sky')}; }}"
            f" QPushButton:disabled {{ background-color: {c('surface1')}; color: {c('muted')}; }}"
        )
        self.next_btn.clicked.connect(self._on_next)

        # Inline model-loading indicator (shown while subscriptions are fetched)
        # IMPORTANT: give these widgets an explicit parent so calling .show()
        # can never create a stray top-level popup window.
        self.model_loading_bar = QProgressBar(nav_bar)
        self.model_loading_bar.setFixedWidth(120)
        self.model_loading_bar.setFixedHeight(10)
        self.model_loading_bar.setTextVisible(False)
        self.model_loading_bar.setRange(0, 0)  # indeterminate
        self.model_loading_bar.hide()

        self.model_loading_label = QLabel("", nav_bar)
        self.model_loading_label.setProperty("muted", True)
        self.model_loading_label.hide()

        self.retry_models_btn = StyledButton("Retry Loading Models", nav_bar)
        self.retry_models_btn.clicked.connect(self._retry_model_load)
        self.retry_models_btn.hide()

        nav_layout.addWidget(self.model_loading_bar)
        nav_layout.addSpacing(8)
        nav_layout.addWidget(self.model_loading_label)
        nav_layout.addSpacing(4)
        nav_layout.addWidget(self.retry_models_btn)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()

        outer.addWidget(nav_bar)

    def _connect_signals(self):
        app_signals.action_selected.connect(self._on_action_selected)
        app_signals.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, _is_dark=True):
        """Update hardcoded styles when theme changes."""
        self._nav_bar.setStyleSheet(f"background-color: {c('mantle')};")
        self.next_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('blue')}; color: {c('base')};"
            f" font-weight: bold; border: none; border-radius: 6px;"
            f" padding: 6px 16px; }}"
            f" QPushButton:hover {{ background-color: {c('sky')}; }}"
            f" QPushButton:disabled {{ background-color: {c('surface1')}; color: {c('muted')}; }}"
        )
        for sep in self._separators:
            sep.setStyleSheet(f"color: {c('sep')};")
        # Update all help buttons
        for btn in self.findChildren(QToolButton):
            if btn.text() == "?":
                btn.setStyleSheet(_help_btn_qss())

    def showEvent(self, event):
        super().showEvent(event)
        # If config changed, keep Discord checkbox state accurate.
        self._refresh_discord_option_state()
        # If we already have actions but models haven't loaded yet, start loading.
        if self._current_actions and not (self._models_loaded or self._models_loading):
            self._start_model_load()

    def _refresh_discord_option_state(self):
        """Enable/disable the Discord option based on config webhook presence."""
        try:
            url = (config_data.get_discord() or "").strip()
        except Exception:
            url = ""
        has_webhook = bool(url)
        try:
            self.discord_updates_check.setEnabled(has_webhook)
            if not has_webhook:
                self.discord_updates_check.setChecked(False)
                self.discord_updates_check.setToolTip(
                    "Disabled because no Discord webhook URL is configured.\n\n"
                    "Set Config → General → Discord Webhook URL, then return here."
                )
        except Exception:
            pass

    def reset_to_defaults(self):
        """Reset all area selections and options to their initial defaults."""
        # Reset area checkboxes to all checked
        for cb in self._area_checks.values():
            cb.setChecked(True)
        # Reset extra options
        self.scrape_paid_check.setChecked(False)
        self.scrape_labels_check.setChecked(False)
        self.discord_updates_check.setChecked(False)
        # Reset advanced options
        self.allow_dupes_check.setChecked(False)
        self.rescrape_all_check.setChecked(False)
        self.delete_db_check.setChecked(False)
        self.delete_downloads_check.setChecked(False)
        # Reset daemon options
        self.daemon_check.setChecked(False)
        self.daemon_interval.setValue(30.0)
        self.daemon_interval.setEnabled(False)
        self.notify_check.setChecked(False)
        self.sound_check.setChecked(False)
        # Reset filter sidebar
        self.filter_sidebar.reset_all()
        # Reset model loading state so models reload on next visit
        self._models_loaded = False
        self._models_loading = False
        self._refresh_discord_option_state()

    def _on_action_selected(self, actions):
        """Update available areas based on selected actions."""
        self._current_actions = actions
        self._update_available_areas()
        # Begin loading models immediately so the user sees progress here.
        self._start_model_load()

    def _on_rescrape_toggled(self, checked):
        self.delete_db_check.setEnabled(checked)
        self.delete_downloads_check.setEnabled(checked)
        if not checked:
            self.delete_db_check.setChecked(False)
            self.delete_downloads_check.setChecked(False)

    def _on_delete_downloads_toggled(self, checked):
        # If the user deletes files, also delete the DB to avoid stale state.
        if checked:
            self.delete_db_check.setChecked(True)

    def _retry_model_load(self):
        """Reset state and re-fetch models (called from retry button)."""
        self._models_loaded = False
        self._models_loading = False
        self.retry_models_btn.hide()
        self._start_model_load()

    def _start_model_load(self):
        """Fetch subscription models from API in background; disable Next until ready."""
        if self._models_loading or self._models_loaded:
            return

        self._models_loading = True
        self._models_error = None
        self._loaded_model_count = 0
        self.retry_models_btn.hide()

        self.next_btn.setEnabled(False)
        self.model_loading_label.setText("Loading models from API...")
        self.model_loading_label.show()
        self.model_loading_bar.show()

        # Defensive: close any stray legacy top-level loading popup that might
        # still be created by older code paths or stale Qt objects.
        try:
            from PyQt6.QtWidgets import QApplication, QLabel

            for w in QApplication.topLevelWidgets():
                if w is None or w is self.window():
                    continue
                try:
                    # If a top-level window contains a QLabel with this exact text,
                    # it's almost certainly the unwanted popup.
                    lbls = w.findChildren(QLabel)
                    if any((l.text() or "").strip() == "Loading models from API..." for l in lbls):
                        w.close()
                except Exception:
                    continue
        except Exception:
            pass

        if not (self.manager and getattr(self.manager, "model_manager", None)):
            self._models_loading = False
            self._models_error = "Model manager not available"
            self.model_loading_bar.hide()
            self.model_loading_label.setText("Model manager not available")
            self.next_btn.setEnabled(True)
            return

        worker = Worker(self._fetch_models)
        worker.signals.finished.connect(self._on_models_loaded)
        worker.signals.error.connect(self._on_models_error)
        from PyQt6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(worker)

    def _fetch_models(self):
        import asyncio
        import ofscraper.data.models.utils.retriver as retriver
        import ofscraper.utils.paths.common as common_paths
        import ofscraper.utils.auth.utils.dict as auth_dict_mod

        # Log the auth file path and contents for debugging
        try:
            auth_path = common_paths.get_auth_file()
            log.info(f"[GUI retry] Auth file path: {auth_path}")
            auth_data = auth_dict_mod.get_auth_dict()
            filled = {k: ("set" if v else "EMPTY") for k, v in auth_data.items()}
            log.info(f"[GUI retry] Auth field status: {filled}")

            # Bail out early if required auth fields are empty — no point
            # hammering the API with empty credentials.
            required = ["sess", "auth_id", "user_agent", "x-bc"]
            missing = [k for k in required if not auth_data.get(k)]
            if missing:
                raise Exception(
                    f"Auth fields not configured: {', '.join(missing)}. "
                    "Please fill in your auth credentials first."
                )
        except Exception as e:
            log.warning(f"[GUI retry] Auth check failed: {e}")
            raise

        # Clear cached data so we actually re-fetch from the API
        self.manager.model_manager._all_subs_dict = {}

        # Clear the profile/user info cache so stale None values from
        # a previous failed auth attempt don't poison the retry.
        import ofscraper.utils.profiles.data as profile_data
        profile_data.currentData = None
        profile_data.currentProfile = None

        # Run the async API call directly with a fresh event loop,
        # bypassing the @run decorator which can leave stale loop state.
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(retriver.get_models())
            self.manager.model_manager.all_subs_dict = data
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        return getattr(self.manager.model_manager, "all_subs_obj", None) or []

    def _on_models_loaded(self, models):
        self._models_loading = False
        self._loaded_model_count = len(models or [])
        self.model_loading_bar.hide()
        if self._loaded_model_count == 0:
            self._models_loaded = False  # allow retry after fixing auth
            self._show_auth_failure_prompt()
            return
        self._models_loaded = True
        self.retry_models_btn.hide()
        self.model_loading_label.setText(f"Models loaded: {self._loaded_model_count}")
        self.model_loading_label.show()
        self.next_btn.setEnabled(True)

    def _on_models_error(self, error_msg):
        self._models_loading = False
        self._models_loaded = False  # allow retry after fixing auth
        self._models_error = error_msg
        self.model_loading_bar.hide()
        self._show_auth_failure_prompt(error_msg)

    def _show_auth_failure_prompt(self, detail=None):
        """Show a dialog when models can't be loaded, offering to go to auth settings or retry."""
        self.model_loading_label.setText("Unable to get list of models.")
        self.model_loading_label.show()
        self.retry_models_btn.show()
        self.next_btn.setEnabled(False)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unable to Load Models")
        msg.setText(
            "Unable to get list of models.\n"
            "Please check your auth information.\n\n"
            "If your auth is correct and the issue persists,\n"
            "try changing the Dynamic Mode in Configuration \u2192 Advanced."
        )
        if detail:
            msg.setDetailedText(str(detail))
        retry_btn = msg.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        auth_btn = msg.addButton("Go to Authentication", QMessageBox.ButtonRole.ActionRole)
        dynamic_btn = msg.addButton("Dynamic Mode (Config)", QMessageBox.ButtonRole.ActionRole)
        help_btn = msg.addButton("Help / README", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == retry_btn:
            self._retry_model_load()
        elif msg.clickedButton() == auth_btn:
            app_signals.navigate_to_page.emit("auth")
        elif msg.clickedButton() == dynamic_btn:
            self._go_to_dynamic_mode_config()
        elif msg.clickedButton() == help_btn:
            self._go_to_auth_help()

    def _go_to_dynamic_mode_config(self):
        """Navigate to Configuration → Advanced tab with Dynamic Mode focused."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        app_signals.navigate_to_page.emit("config")

        def _focus_field():
            try:
                for w in QApplication.topLevelWidgets():
                    pages = getattr(w, "_pages", None)
                    if pages and "config" in pages:
                        cfg_page = pages["config"]
                        if hasattr(cfg_page, "go_to_config_field"):
                            cfg_page.go_to_config_field("Advanced", "dynamic-mode-default")
                        break
            except Exception:
                pass

        # Defer by one event-loop tick so the page switch renders first.
        QTimer.singleShot(100, _focus_field)

    def _go_to_auth_help(self):
        """Navigate to Help / README and scroll to the Auth Issues section."""
        from PyQt6.QtCore import QTimer
        from PyQt6.QtWidgets import QApplication

        app_signals.navigate_to_page.emit("help")

        def _scroll_to_anchor():
            try:
                for w in QApplication.topLevelWidgets():
                    pages = getattr(w, "_pages", None)
                    if pages and "help" in pages:
                        help_page = pages["help"]
                        if hasattr(help_page, "scroll_to_anchor"):
                            help_page.scroll_to_anchor("auth-issues")
                        break
            except Exception:
                pass

        QTimer.singleShot(200, _scroll_to_anchor)

    def _update_available_areas(self):
        has_download = "download" in self._current_actions
        has_like = "like" in self._current_actions or "unlike" in self._current_actions

        if has_download:
            available = DOWNLOAD_AREAS
        elif has_like:
            available = LIKE_AREAS
        else:
            available = DOWNLOAD_AREAS

        for area, cb in self._area_checks.items():
            if area in available:
                cb.show()
                cb.setEnabled(True)
            else:
                cb.hide()
                cb.setEnabled(False)
                cb.setChecked(False)

    def _select_all(self):
        for cb in self._area_checks.values():
            if cb.isEnabled() and not cb.isHidden():
                cb.setChecked(True)

    def _deselect_all(self):
        for cb in self._area_checks.values():
            if cb.isEnabled() and not cb.isHidden():
                cb.setChecked(False)

    def get_selected_areas(self):
        return [
            area
            for area, cb in self._area_checks.items()
            if cb.isChecked() and cb.isEnabled() and not cb.isHidden()
        ]

    def _on_daemon_toggled(self, checked):
        self.daemon_interval.setEnabled(checked)

    def is_daemon_enabled(self):
        return self.daemon_check.isChecked()

    def get_daemon_interval(self):
        return self.daemon_interval.value()

    def is_notify_enabled(self):
        return self.notify_check.isChecked()

    def is_sound_enabled(self):
        return self.sound_check.isChecked()

    def get_username_filter(self):
        """Return the username entered in the filter, if any."""
        return self.filter_sidebar.username_input.text().strip()

    def copy_filter_state_to(self, target_sidebar):
        """Copy the filter configuration from this page's sidebar to the target sidebar."""
        src = self.filter_sidebar
        tgt = target_sidebar

        # Text search
        tgt.text_input.setText(src.text_input.text())
        tgt.fullstring_check.setChecked(src.fullstring_check.isChecked())

        # Media type
        for mt, cb in src.media_checks.items():
            if mt in tgt.media_checks:
                tgt.media_checks[mt].setChecked(cb.isChecked())

        # Response type
        for rt, cb in src.resp_checks.items():
            if rt in tgt.resp_checks:
                tgt.resp_checks[rt].setChecked(cb.isChecked())

        # Downloaded / Unlocked
        tgt.dl_true.setChecked(src.dl_true.isChecked())
        tgt.dl_false.setChecked(src.dl_false.isChecked())
        tgt.dl_no.setChecked(src.dl_no.isChecked())
        tgt.ul_true.setChecked(src.ul_true.isChecked())
        tgt.ul_false.setChecked(src.ul_false.isChecked())
        tgt.ul_not_paid.setChecked(src.ul_not_paid.isChecked())

        # Date
        tgt.date_enabled.setChecked(src.date_enabled.isChecked())
        tgt.min_date.setDate(src.min_date.date())
        tgt.max_date.setDate(src.max_date.date())

        # Length
        tgt.length_enabled.setChecked(src.length_enabled.isChecked())
        tgt.min_time.setTime(src.min_time.time())
        tgt.max_time.setTime(src.max_time.time())

        # Price
        tgt.price_min.setValue(src.price_min.value())
        tgt.price_max.setValue(src.price_max.value())

        # IDs
        tgt.media_id_input.setText(src.media_id_input.text())
        tgt.post_id_input.setText(src.post_id_input.text())
        tgt.post_media_count_input.setValue(src.post_media_count_input.value())
        tgt.other_posts_input.setValue(src.other_posts_input.value())

        # Username
        tgt.username_input.setText(src.username_input.text())

    def _on_back(self):
        parent_stack = self.parent()
        if parent_stack:
            parent_stack.setCurrentIndex(0)  # action page

    def _on_next(self):
        """Validate areas and proceed to model selection."""
        selected = self.get_selected_areas()
        if not selected:
            app_signals.error_occurred.emit(
                "No Areas Selected",
                "Please select at least one content area.",
            )
            return

        log.info(f"Areas configured: {selected}")

        # Pre-filter models by username if one was entered
        username = self.get_username_filter()
        parent_stack = self.parent()
        if parent_stack:
            # Get the model selector page (index 1) and apply username filter
            model_page = parent_stack.widget(1)
            if model_page and hasattr(model_page, "pre_filter_username"):
                model_page.pre_filter_username(username)
            parent_stack.setCurrentIndex(1)  # model selector
