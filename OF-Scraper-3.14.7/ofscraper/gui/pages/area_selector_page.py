import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c
from ofscraper.gui.utils.group_layout import compact_group, tune_group_layout
from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings
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

POST_CHECK_AREAS = [
    "Timeline",
    "Pinned",
    "Archived",
    "Labels",
    "Streams",
]

_CHECK_MODES = {"post_check", "msg_check", "paid_check", "story_check"}


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
        self._models_load_gen = 0
        self._models_worker = None
        self._models_poll_timer = None
        self._models_env_prepared = False
        self._models_finish_scheduled = False
        # True after action selected until MainWindow finishes missing-deps gate
        # and calls start_pending_model_load() — avoids overlapping that dialog
        # with the API model fetch (closing the dialog mid-fetch crashed the GUI).
        self._pending_model_load = False
        self._separators = []
        self._block_discord_prompt = False
        self._setup_ui()
        self._load_area_settings()
        self._connect_signals()
        self._sync_text_filename_option()
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
        apply_font(header, "Segoe UI", 20, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Configure what to scrape and how to filter results."
        )
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        # Areas group
        self.areas_group = compact_group(QGroupBox("Content Areas"))
        self.areas_grid = QGridLayout(self.areas_group)
        tune_group_layout(self.areas_grid)

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
            apply_font(cb, "Segoe UI", 11)
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
        bulk_layout.addWidget(_make_help_btn("sca-content-areas"))
        bulk_layout.addStretch()
        layout.addLayout(bulk_layout)

        # Media Types group
        media_sep = QFrame()
        media_sep.setFrameShape(QFrame.Shape.HLine)
        media_sep.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(media_sep)
        layout.addWidget(media_sep)

        media_group = compact_group(QGroupBox("Media Types to Download"))
        media_layout = QHBoxLayout(media_group)
        tune_group_layout(media_layout)
        media_layout.setSpacing(16)

        # Initialize checkboxes from the current config filter setting
        config_filter = config_data.get_filter() or ["Images", "Videos", "Audios"]
        config_filter_lower = {x.lower() for x in config_filter}

        self._mediatype_checks = {}
        for mt in ["Images", "Videos", "Audios"]:
            cb = QCheckBox(mt)
            apply_font(cb, "Segoe UI", 11)
            cb.setChecked(mt.lower() in config_filter_lower)
            cb.setToolTip(f"Include {mt.lower()} in this scrape session.")
            media_layout.addWidget(cb)
            self._mediatype_checks[mt] = cb

        media_layout.addWidget(_make_help_btn("sca-media-types"))
        media_layout.addStretch()
        layout.addWidget(media_group)

        # Include post text options
        text_group = compact_group(QGroupBox("Post Text"))
        text_layout = QVBoxLayout(text_group)
        tune_group_layout(text_layout)

        self.include_text_check = QCheckBox("Include Post Text")
        apply_font(self.include_text_check, "Segoe UI", 11)
        self.include_text_check.setChecked(False)
        self.include_text_check.setToolTip(
            "Download each post's caption/description as a .txt file alongside media.\n"
            "Empty captions are skipped (counted as skipped, not failed)."
        )
        text_layout.addWidget(self.include_text_check)

        self.text_filename_from_post_check = QCheckBox(
            "Name text files from post text (instead of post ID)"
        )
        apply_font(self.text_filename_from_post_check, "Segoe UI", 11)
        self.text_filename_from_post_check.setChecked(False)
        self.text_filename_from_post_check.setEnabled(False)
        self.text_filename_from_post_check.setToolTip(
            "When checked, .txt filenames use the truncated/sanitized post caption\n"
            "(Configuration → File Options → Text Length / Text Type).\n"
            "When unchecked (default), .txt files follow File Format\n"
            "(e.g. {media_id}.{ext} becomes {post_id}.txt for text posts).\n\n"
            "Keep Text Length under ~250 so name + \".txt\" stays within the\n"
            "255-character (Windows) / 255-byte (Linux) single-filename limit."
        )
        text_layout.addWidget(self.text_filename_from_post_check)

        self.text_filename_length_warning = QLabel(
            "⚠ Filename limit: Windows NTFS allows 255 Unicode characters per filename "
            "component; Linux (e.g. ext4) typically allows 255 bytes. Keep Configuration → "
            "Text Length under ~250 when naming from captions so name + \".txt\" fits."
        )
        self.text_filename_length_warning.setWordWrap(True)
        self.text_filename_length_warning.setProperty("muted", True)
        self.text_filename_length_warning.setVisible(False)
        text_layout.addWidget(self.text_filename_length_warning)

        layout.addWidget(text_group)

        # Extra options
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(sep)
        layout.addWidget(sep)

        extras_group = compact_group(QGroupBox("Additional Options"))
        extras_layout = QVBoxLayout(extras_group)
        tune_group_layout(extras_layout)

        self.scrape_paid_check = QCheckBox(
            "Scrape entire paid page (slower but more comprehensive)"
        )
        apply_font(self.scrape_paid_check, "Segoe UI", 11)
        self.scrape_paid_check.setToolTip(
            "Tries harder to enumerate all paid/purchased items.\n"
            "May be significantly slower but catches items missed by normal scraping."
        )
        row = QHBoxLayout()
        row.addWidget(self.scrape_paid_check)
        row.addWidget(_make_help_btn("sca-scrape-paid"))
        row.addStretch()
        extras_layout.addLayout(row)

        self.scrape_labels_check = QCheckBox("Scrape labels")
        apply_font(self.scrape_labels_check, "Segoe UI", 11)
        self.scrape_labels_check.setToolTip(
            "Pull content organized by the model's custom labels/categories when available."
        )
        row = QHBoxLayout()
        row.addWidget(self.scrape_labels_check)
        row.addWidget(_make_help_btn("sca-scrape-labels"))
        row.addStretch()
        extras_layout.addLayout(row)

        # Discord webhook option (enabled only if config has a webhook URL)
        self.discord_updates_check = QCheckBox(
            "Send updates to Discord (requires webhook URL in Config → General)"
        )
        apply_font(self.discord_updates_check, "Segoe UI", 11)
        self.discord_updates_check.setChecked(False)
        self.discord_updates_check.setToolTip(
            "When enabled, log updates are posted to your configured Discord webhook.\n"
            "Use the level selector to control verbosity."
        )
        self.discord_level_combo = QComboBox()
        self.discord_level_combo.addItems(["LOW", "NORMAL"])
        self.discord_level_combo.setCurrentText("LOW")
        self.discord_level_combo.setToolTip(
            "LOW: only important messages (warnings, errors, completion)\n"
            "NORMAL: standard progress updates"
        )
        self.discord_level_combo.setEnabled(False)
        self.discord_updates_check.toggled.connect(
            lambda checked: self.discord_level_combo.setEnabled(
                checked and self.discord_updates_check.isEnabled()
            )
        )
        self.discord_updates_check.toggled.connect(self._on_discord_check_toggled)
        row = QHBoxLayout()
        row.addWidget(self.discord_updates_check)
        row.addWidget(self.discord_level_combo)
        row.addWidget(_make_help_btn("sca-discord-updates"))
        row.addStretch()
        extras_layout.addLayout(row)
        layout.addWidget(extras_group)

        # Advanced options
        adv_group = compact_group(QGroupBox("Advanced Scrape Options"))
        adv_layout = QVBoxLayout(adv_group)
        tune_group_layout(adv_layout)

        self.allow_dupes_check = QCheckBox(
            "Allow duplicates (do NOT skip duplicates; treat reposts as new items)"
        )
        apply_font(self.allow_dupes_check, "Segoe UI", 11)
        self.allow_dupes_check.setToolTip(
            "When enabled, the duplicate media filter is bypassed for most cases.\n"
            "All media — including identical content reposted across multiple posts — will be included.\n"
            "Other filters (locked, types, date ranges, etc.) still apply.\n\n"
            "Use the option below to control Messages ↔ Purchased overlap."
        )
        row = QHBoxLayout()
        row.addWidget(self.allow_dupes_check)
        row.addWidget(_make_help_btn("sca-allow-dupes"))
        row.addStretch()
        adv_layout.addLayout(row)

        self.keep_msg_purchased_dupes_check = QCheckBox(
            "Also keep Messages + Purchased copies of the same media"
        )
        apply_font(self.keep_msg_purchased_dupes_check, "Segoe UI", 11)
        self.keep_msg_purchased_dupes_check.setEnabled(False)
        self.keep_msg_purchased_dupes_check.setToolTip(
            "Only applies when Allow duplicates is on.\n\n"
            "Unchecked (default): if the same media appears in both Messages and\n"
            "Purchased, keep Messages only. Other duplicates (reposts) are still kept.\n\n"
            "Checked: download both the Messages and Purchased copies."
        )
        self.allow_dupes_check.toggled.connect(self._on_allow_dupes_toggled)
        row = QHBoxLayout()
        # Indent under Allow duplicates
        row.addSpacing(24)
        row.addWidget(self.keep_msg_purchased_dupes_check)
        row.addWidget(_make_help_btn("sca-keep-msg-purchased-dupes"))
        row.addStretch()
        adv_layout.addLayout(row)

        self.rescrape_all_check = QCheckBox(
            "Rescrape everything (ignore cache / scan from the beginning)"
        )
        apply_font(self.rescrape_all_check, "Segoe UI", 11)
        self.rescrape_all_check.setToolTip(
            "Forces a full history scan, ignoring any cached 'after' timestamps.\n"
            "Useful if you suspect missed content or want a complete re-scan."
        )
        self.rescrape_all_check.toggled.connect(self._on_rescrape_toggled)
        row = QHBoxLayout()
        row.addWidget(self.rescrape_all_check)
        row.addWidget(_make_help_btn("sca-rescrape-all"))
        row.addStretch()
        adv_layout.addLayout(row)

        self.delete_db_check = QCheckBox(
            "Delete model DB before scraping (resets downloaded/unlocked history)"
        )
        apply_font(self.delete_db_check, "Segoe UI", 11)
        self.delete_db_check.setEnabled(False)
        self.delete_db_check.setToolTip(
            "Deletes the model's SQLite database before scraping starts.\n"
            "This resets all downloaded/unlocked tracking, so everything appears as new.\n"
            "Requires 'Rescrape everything' to be enabled."
        )
        row = QHBoxLayout()
        row.addWidget(self.delete_db_check)
        row.addWidget(_make_help_btn("sca-delete-db"))
        row.addStretch()
        adv_layout.addLayout(row)

        self.delete_downloads_check = QCheckBox(
            "Also delete existing downloaded files for selected models"
        )
        apply_font(self.delete_downloads_check, "Segoe UI", 11)
        self.delete_downloads_check.setEnabled(False)
        self.delete_downloads_check.setToolTip(
            "Removes previously downloaded files for the selected models.\n"
            "WARNING: This permanently deletes files from your save location.\n"
            "Requires 'Delete model DB' to be enabled."
        )
        self.delete_downloads_check.toggled.connect(self._on_delete_downloads_toggled)
        row = QHBoxLayout()
        row.addWidget(self.delete_downloads_check)
        row.addWidget(_make_help_btn("sca-delete-downloads"))
        row.addStretch()
        adv_layout.addLayout(row)

        hint = QLabel(
            "Tip: deleting files uses your model DB to locate paths, so keep the DB delete option enabled."
        )
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        adv_layout.addWidget(hint)

        # Video quality selector
        quality_row = QHBoxLayout()
        quality_label = QLabel("Video quality:")
        apply_font(quality_label, "Segoe UI", 11)
        quality_row.addWidget(quality_label)
        quality_row.addWidget(_make_help_btn("sca-quality"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Default", "240", "720", "source"])
        self.quality_combo.setFixedWidth(100)
        self.quality_combo.setToolTip(
            "Select the preferred video quality to download.\n"
            "'Default' downloads the source/highest quality available on OnlyFans (same as 'source').\n"
            "'240' / '720' request a lower rendition and fall back to source if unavailable.\n"
            "Corresponds to the -q / --quality CLI option."
        )
        quality_row.addWidget(self.quality_combo)
        quality_row.addStretch()
        adv_layout.addLayout(quality_row)

        layout.addWidget(adv_group)

        # Daemon mode
        sep_daemon = QFrame()
        sep_daemon.setFrameShape(QFrame.Shape.HLine)
        sep_daemon.setStyleSheet(f"color: {c('sep')};")
        self._separators.append(sep_daemon)
        layout.addWidget(sep_daemon)

        daemon_group = compact_group(QGroupBox("Daemon Mode (Auto-Repeat Scraping)"))
        daemon_layout = QVBoxLayout(daemon_group)
        tune_group_layout(daemon_layout)

        self.daemon_check = QCheckBox(
            "Enable daemon mode (automatically re-scrape on a schedule)"
        )
        apply_font(self.daemon_check, "Segoe UI", 11)
        self.daemon_check.setToolTip(
            "Automatically repeats the scrape at a fixed interval.\n"
            "The GUI will show a countdown timer between runs."
        )
        self.daemon_check.toggled.connect(self._on_daemon_toggled)
        row = QHBoxLayout()
        row.addWidget(self.daemon_check)
        row.addWidget(_make_help_btn("sca-daemon-enable"))
        row.addStretch()
        daemon_layout.addLayout(row)

        interval_layout = QHBoxLayout()
        interval_label = QLabel("Interval:")
        apply_font(interval_label, "Segoe UI", 11)
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(_make_help_btn("sca-daemon-interval"))

        self.daemon_interval = QDoubleSpinBox()
        self.daemon_interval.setRange(1.0, 1440.0)
        self.daemon_interval.setValue(30.0)
        self.daemon_interval.setSuffix(" minutes")
        self.daemon_interval.setDecimals(1)
        self.daemon_interval.setSingleStep(5.0)
        apply_font(self.daemon_interval, "Segoe UI", 11)
        self.daemon_interval.setEnabled(False)
        self.daemon_interval.setToolTip(
            "Minutes between each automatic scrape run (1-1440).\n"
            "1440 minutes = 24 hours."
        )
        interval_layout.addWidget(self.daemon_interval)
        interval_layout.addStretch()
        daemon_layout.addLayout(interval_layout)

        self.notify_check = QCheckBox("System notification when scraping starts")
        apply_font(self.notify_check, "Segoe UI", 11)
        self.notify_check.setToolTip(
            "Show a system tray notification when each daemon scrape run begins."
        )
        row = QHBoxLayout()
        row.addWidget(self.notify_check)
        row.addWidget(_make_help_btn("sca-daemon-notify"))
        row.addStretch()
        daemon_layout.addLayout(row)

        self.sound_check = QCheckBox("Sound alert when scraping starts")
        apply_font(self.sound_check, "Segoe UI", 11)
        self.sound_check.setToolTip(
            "Play a beep sound when each daemon scrape run begins (Windows only)."
        )
        row = QHBoxLayout()
        row.addWidget(self.sound_check)
        row.addWidget(_make_help_btn("sca-daemon-sound"))
        row.addStretch()
        daemon_layout.addLayout(row)

        self.daemon_discord_ping_check = QCheckBox(
            "@here Discord mention when new content is found"
        )
        apply_font(self.daemon_discord_ping_check, "Segoe UI", 11)
        self.daemon_discord_ping_check.setEnabled(False)
        self.daemon_discord_ping_check.setToolTip(
            "When daemon mode finds new content to download, prepend @here to the\n"
            "Discord summary so your server gets a notification.\n"
            "Requires Discord webhook to be enabled. No ping is sent if nothing new was found."
        )
        self.daemon_discord_ping_check.toggled.connect(self._on_daemon_ping_toggled)
        row = QHBoxLayout()
        row.addWidget(self.daemon_discord_ping_check)
        row.addStretch()
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
        apply_font(self.next_btn, "Segoe UI", 12, QFont.Weight.Bold)
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

        self.reload_models_btn = StyledButton("Reload Models", nav_bar)
        self.reload_models_btn.setToolTip(
            "Re-fetch models from the OnlyFans API.\n"
            "Use this if you changed the User List filter on the previous page."
        )
        self.reload_models_btn.clicked.connect(self._on_reload_models)
        self.reload_models_btn.hide()

        nav_layout.addWidget(self.model_loading_bar)
        nav_layout.addSpacing(8)
        nav_layout.addWidget(self.model_loading_label)
        nav_layout.addSpacing(4)
        nav_layout.addWidget(self.retry_models_btn)
        nav_layout.addSpacing(4)
        nav_layout.addWidget(self.reload_models_btn)
        nav_layout.addSpacing(12)
        nav_layout.addWidget(self.next_btn)

        nav_layout.addStretch()

        # Save / Reset settings buttons (right side of nav bar)
        self.save_settings_btn = StyledButton("Save Settings")
        self.save_settings_btn.setToolTip(
            "Save the current Content Areas & Filters selections to gui_settings.json\n"
            "so they are restored the next time you open the GUI."
        )
        self.save_settings_btn.clicked.connect(self._on_save_settings)
        nav_layout.addWidget(self.save_settings_btn)

        nav_layout.addSpacing(6)

        self.reset_settings_btn = StyledButton("Reset Settings")
        self.reset_settings_btn.setToolTip(
            "Clear the saved Content Areas & Filters settings from gui_settings.json\n"
            "and restore all options to their default values."
        )
        self.reset_settings_btn.clicked.connect(self._on_reset_settings)
        nav_layout.addWidget(self.reset_settings_btn)

        outer.addWidget(nav_bar)

    def _load_area_settings(self):
        """Restore persisted Select Content Areas & Filters state from gui_settings.json."""
        try:
            gs = load_gui_settings()

            # Content area checkboxes
            area_saved = gs.get("area_checks", {})
            for area, cb in self._area_checks.items():
                if area in area_saved:
                    cb.setChecked(bool(area_saved[area]))

            # Media type checkboxes
            mt_saved = gs.get("media_types", {})
            for mt, cb in self._mediatype_checks.items():
                if mt in mt_saved:
                    cb.setChecked(bool(mt_saved[mt]))

            # Additional options
            if "include_text" in gs:
                self.include_text_check.setChecked(bool(gs["include_text"]))
            if "text_filename_from_post" in gs:
                self.text_filename_from_post_check.setChecked(
                    bool(gs["text_filename_from_post"])
                )
            self._sync_text_filename_option()
            if "scrape_paid" in gs:
                self.scrape_paid_check.setChecked(bool(gs["scrape_paid"]))
            if "scrape_labels" in gs:
                self.scrape_labels_check.setChecked(bool(gs["scrape_labels"]))

            # Advanced options — rescrape_all must be set first so delete_db/delete_downloads become enabled
            if "rescrape_all" in gs:
                self.rescrape_all_check.setChecked(bool(gs["rescrape_all"]))
            if "allow_dupes" in gs:
                self.allow_dupes_check.setChecked(bool(gs["allow_dupes"]))
            # Sub-option only meaningful when allow_dupes is on
            self.keep_msg_purchased_dupes_check.setEnabled(
                self.allow_dupes_check.isChecked()
            )
            if "keep_msg_purchased_dupes" in gs:
                self.keep_msg_purchased_dupes_check.setChecked(
                    bool(gs["keep_msg_purchased_dupes"])
                    and self.allow_dupes_check.isChecked()
                )
            if "delete_db" in gs:
                self.delete_db_check.setChecked(bool(gs["delete_db"]))
            if "delete_downloads" in gs:
                self.delete_downloads_check.setChecked(bool(gs["delete_downloads"]))
            if "quality" in gs and gs["quality"] in ("Default", "240", "720", "source"):
                self.quality_combo.setCurrentText(gs["quality"])

            # Daemon options — daemon_check must be set first so interval/ping become enabled
            if "daemon_enabled" in gs:
                self.daemon_check.setChecked(bool(gs["daemon_enabled"]))
            if "daemon_interval" in gs:
                try:
                    self.daemon_interval.setValue(max(1.0, min(1440.0, float(gs["daemon_interval"]))))
                except (TypeError, ValueError):
                    pass
            if "daemon_notify" in gs:
                self.notify_check.setChecked(bool(gs["daemon_notify"]))
            if "daemon_sound" in gs:
                self.sound_check.setChecked(bool(gs["daemon_sound"]))

            # Date filter — block date signals during load so auto-enable doesn't fire
            fs = self.filter_sidebar
            _rel_units = ("hours ago", "days ago", "weeks ago", "months ago")
            try:
                from PyQt6.QtCore import QDate
                if "after_mode" in gs and gs["after_mode"] in ("Fixed date", "Relative"):
                    fs.after_mode_combo.setCurrentText(gs["after_mode"])
                if "after_date" in gs:
                    d = QDate.fromString(gs["after_date"], "yyyy-MM-dd")
                    if d.isValid():
                        fs.min_date.blockSignals(True)
                        fs.min_date.setDate(d)
                        fs.min_date.blockSignals(False)
                if "after_rel_value" in gs:
                    fs.after_rel_value.blockSignals(True)
                    fs.after_rel_value.setValue(max(1, int(gs["after_rel_value"])))
                    fs.after_rel_value.blockSignals(False)
                if "after_rel_unit" in gs and gs["after_rel_unit"] in _rel_units:
                    fs.after_rel_unit.setCurrentText(gs["after_rel_unit"])
                if "after_enabled" in gs:
                    fs.after_enabled.setChecked(bool(gs["after_enabled"]))

                if "before_mode" in gs and gs["before_mode"] in ("Fixed date", "Relative"):
                    fs.before_mode_combo.setCurrentText(gs["before_mode"])
                if "before_date" in gs:
                    d = QDate.fromString(gs["before_date"], "yyyy-MM-dd")
                    if d.isValid():
                        fs.max_date.blockSignals(True)
                        fs.max_date.setDate(d)
                        fs.max_date.blockSignals(False)
                if "before_rel_value" in gs:
                    fs.before_rel_value.blockSignals(True)
                    fs.before_rel_value.setValue(max(1, int(gs["before_rel_value"])))
                    fs.before_rel_value.blockSignals(False)
                if "before_rel_unit" in gs and gs["before_rel_unit"] in _rel_units:
                    fs.before_rel_unit.setCurrentText(gs["before_rel_unit"])
                if "before_enabled" in gs:
                    fs.before_enabled.setChecked(bool(gs["before_enabled"]))
            except Exception as _de:
                log.debug(f"[GUI] Could not restore date filter: {_de}")

        except Exception as e:
            log.debug(f"[GUI] Could not restore area settings: {e}")

    def _save_area_settings(self):
        """Persist the current Select Content Areas & Filters state to gui_settings.json."""
        try:
            gs = load_gui_settings()
            gs["area_checks"] = {area: cb.isChecked() for area, cb in self._area_checks.items()}
            gs["media_types"] = {mt: cb.isChecked() for mt, cb in self._mediatype_checks.items()}
            gs["include_text"] = self.include_text_check.isChecked()
            gs["text_filename_from_post"] = self.text_filename_from_post_check.isChecked()
            gs["scrape_paid"] = self.scrape_paid_check.isChecked()
            gs["scrape_labels"] = self.scrape_labels_check.isChecked()
            gs["allow_dupes"] = self.allow_dupes_check.isChecked()
            gs["keep_msg_purchased_dupes"] = (
                self.allow_dupes_check.isChecked()
                and self.keep_msg_purchased_dupes_check.isChecked()
            )
            gs["rescrape_all"] = self.rescrape_all_check.isChecked()
            gs["delete_db"] = self.delete_db_check.isChecked()
            gs["delete_downloads"] = self.delete_downloads_check.isChecked()
            gs["quality"] = self.quality_combo.currentText()
            gs["daemon_enabled"] = self.daemon_check.isChecked()
            gs["daemon_interval"] = self.daemon_interval.value()
            gs["daemon_notify"] = self.notify_check.isChecked()
            gs["daemon_sound"] = self.sound_check.isChecked()
            # Date filter
            fs = self.filter_sidebar
            gs["after_mode"] = fs.after_mode_combo.currentText()
            gs["after_date"] = fs.min_date.date().toString("yyyy-MM-dd")
            gs["after_rel_value"] = fs.after_rel_value.value()
            gs["after_rel_unit"] = fs.after_rel_unit.currentText()
            gs["after_enabled"] = fs.after_enabled.isChecked()
            gs["before_mode"] = fs.before_mode_combo.currentText()
            gs["before_date"] = fs.max_date.date().toString("yyyy-MM-dd")
            gs["before_rel_value"] = fs.before_rel_value.value()
            gs["before_rel_unit"] = fs.before_rel_unit.currentText()
            gs["before_enabled"] = fs.before_enabled.isChecked()
            save_gui_settings(gs)
        except Exception as e:
            log.debug(f"[GUI] Could not save area settings: {e}")

    # Area-settings keys that are owned by this page (exclude theme etc.)
    _AREA_SETTINGS_KEYS = (
        "area_checks", "media_types", "include_text", "text_filename_from_post",
        "scrape_paid", "scrape_labels",
        "allow_dupes", "keep_msg_purchased_dupes", "rescrape_all",
        "delete_db", "delete_downloads", "quality",
        "daemon_enabled", "daemon_interval", "daemon_notify", "daemon_sound",
        "after_mode", "after_date", "after_rel_value", "after_rel_unit", "after_enabled",
        "before_mode", "before_date", "before_rel_value", "before_rel_unit", "before_enabled",
    )

    def _on_save_settings(self):
        """Save current selections to gui_settings.json (explicit user action)."""
        reply = QMessageBox.question(
            self,
            "Save Settings",
            "Save the current Content Areas & Filters selections?\n\n"
            "They will be restored automatically the next time you open the GUI.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._save_area_settings()
        app_signals.status_message.emit("Settings saved to gui_settings.json")

    def _on_reset_settings(self):
        """Clear saved area settings and restore all controls to their defaults."""
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset all Content Areas & Filters options to their default values?\n\n"
            "This will also clear any saved settings from gui_settings.json.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            gs = load_gui_settings()
            for k in self._AREA_SETTINGS_KEYS:
                gs.pop(k, None)
            save_gui_settings(gs)
        except Exception as e:
            log.debug(f"[GUI] Could not clear area settings: {e}")
        # Reset all controls to defaults
        try:
            # Content areas — all checked
            for cb in self._area_checks.values():
                cb.setChecked(True)
            # Media types — all checked
            for cb in self._mediatype_checks.values():
                cb.setChecked(True)
            # Additional options
            self.include_text_check.setChecked(False)
            self.text_filename_from_post_check.setChecked(False)
            self._sync_text_filename_option()
            self.scrape_paid_check.setChecked(False)
            self.scrape_labels_check.setChecked(False)
            # Advanced options
            self.allow_dupes_check.setChecked(False)
            self.keep_msg_purchased_dupes_check.setChecked(False)
            self.keep_msg_purchased_dupes_check.setEnabled(False)
            self.rescrape_all_check.setChecked(False)
            self.delete_db_check.setChecked(False)
            self.delete_downloads_check.setChecked(False)
            self.quality_combo.setCurrentText("Default")
            # Daemon
            self.daemon_check.setChecked(False)
            self.daemon_interval.setValue(30.0)
            self.notify_check.setChecked(False)
            self.sound_check.setChecked(False)
            # Date filter
            from PyQt6.QtCore import QDate
            fs = self.filter_sidebar
            fs.after_mode_combo.setCurrentText("Fixed date")
            fs.min_date.blockSignals(True)
            fs.min_date.setDate(QDate(2000, 1, 1))
            fs.min_date.blockSignals(False)
            fs.after_rel_value.setValue(1)
            fs.after_rel_unit.setCurrentText("days ago")
            fs.after_enabled.setChecked(False)
            fs.before_mode_combo.setCurrentText("Fixed date")
            fs.max_date.blockSignals(True)
            fs.max_date.setDate(QDate.currentDate())
            fs.max_date.blockSignals(False)
            fs.before_rel_value.setValue(1)
            fs.before_rel_unit.setCurrentText("days ago")
            fs.before_enabled.setChecked(False)
        except Exception as e:
            log.debug(f"[GUI] Could not reset area controls: {e}")
        app_signals.status_message.emit("Settings reset to defaults")

    def _connect_save_signals(self):
        """Wire up save-on-change for all persistent area settings widgets."""
        for cb in self._area_checks.values():
            cb.toggled.connect(self._save_area_settings)
        for cb in self._mediatype_checks.values():
            cb.toggled.connect(self._save_area_settings)
        self.include_text_check.toggled.connect(self._on_include_text_toggled)
        self.text_filename_from_post_check.toggled.connect(
            self._on_text_filename_from_post_toggled
        )
        self.include_text_check.toggled.connect(self._save_area_settings)
        self.text_filename_from_post_check.toggled.connect(self._save_area_settings)
        self.scrape_paid_check.toggled.connect(self._save_area_settings)
        self.scrape_labels_check.toggled.connect(self._save_area_settings)
        self.allow_dupes_check.toggled.connect(self._save_area_settings)
        self.keep_msg_purchased_dupes_check.toggled.connect(self._save_area_settings)
        self.rescrape_all_check.toggled.connect(self._save_area_settings)
        self.delete_db_check.toggled.connect(self._save_area_settings)
        self.delete_downloads_check.toggled.connect(self._save_area_settings)
        self.quality_combo.currentTextChanged.connect(self._save_area_settings)
        self.daemon_check.toggled.connect(self._save_area_settings)
        self.daemon_interval.valueChanged.connect(self._save_area_settings)
        self.notify_check.toggled.connect(self._save_area_settings)
        self.sound_check.toggled.connect(self._save_area_settings)
        # Date filter
        fs = self.filter_sidebar
        fs.after_enabled.toggled.connect(self._save_area_settings)
        fs.after_mode_combo.currentTextChanged.connect(self._save_area_settings)
        fs.min_date.dateChanged.connect(self._save_area_settings)
        fs.after_rel_value.valueChanged.connect(self._save_area_settings)
        fs.after_rel_unit.currentTextChanged.connect(self._save_area_settings)
        fs.before_enabled.toggled.connect(self._save_area_settings)
        fs.before_mode_combo.currentTextChanged.connect(self._save_area_settings)
        fs.max_date.dateChanged.connect(self._save_area_settings)
        fs.before_rel_value.valueChanged.connect(self._save_area_settings)
        fs.before_rel_unit.currentTextChanged.connect(self._save_area_settings)

    def _connect_signals(self):
        app_signals.action_selected.connect(self._on_action_selected)
        app_signals.theme_changed.connect(self._apply_theme)
        self.include_text_check.toggled.connect(self._on_include_text_toggled)
        self.text_filename_from_post_check.toggled.connect(
            self._on_text_filename_from_post_toggled
        )

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

    def _get_active_userlist(self):
        """Read the current userlist from settings, stripping reserved names."""
        try:
            import ofscraper.utils.settings as _s
            import ofscraper.utils.of_env.of_env as _of_env
            reserved = {
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST") or "").lower(),
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST_ALT") or "").lower(),
            }
            ul = getattr(_s.get_settings(), "userlist", None) or []
            return [u.lower() for u in ul if u and u.lower() not in reserved]
        except Exception:
            return []

    def _on_reload_models(self):
        """Force a fresh model fetch (uses the userlist already set in args)."""
        self._cancel_models_worker()
        self._models_loaded = False
        self._models_loading = False
        self._pending_model_load = False
        self.retry_models_btn.hide()
        self.reload_models_btn.hide()
        self._start_model_load()

    def showEvent(self, event):
        super().showEvent(event)
        # If config changed, keep Discord checkbox state accurate.
        self._refresh_discord_option_state()
        # First entry is owned by MainWindow._prepare_area_page_entry (missing-deps
        # gate). Only resume loads here after that gate has run this session.
        mw = self.window()
        gate_done = bool(
            getattr(mw, "_missing_deps_notice_shown", False)
            or getattr(mw, "_missing_deps_gate_cleared", False)
        )
        if not gate_done:
            return
        if self._pending_model_load and self._current_actions:
            self.start_pending_model_load()
        elif self._current_actions and not (self._models_loaded or self._models_loading):
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
            else:
                # Apply saved "always on" preference
                gs = load_gui_settings()
                if gs.get("discord_always_on"):
                    self._block_discord_prompt = True
                    self.discord_updates_check.setChecked(True)
                    saved_level = gs.get("discord_level", "LOW")
                    if saved_level in ("LOW", "NORMAL"):
                        self.discord_level_combo.setCurrentText(saved_level)
                    self._block_discord_prompt = False
            self.discord_level_combo.setEnabled(
                has_webhook and self.discord_updates_check.isChecked()
            )
        except Exception:
            pass
        # Load saved daemon discord ping preference
        try:
            gs_ping = load_gui_settings()
            self.daemon_discord_ping_check.setChecked(
                bool(gs_ping.get("daemon_discord_ping", False))
            )
        except Exception:
            pass

    def _on_discord_check_toggled(self, checked: bool):
        """Show a one-time prompt asking whether Discord should always be enabled."""
        if not checked or self._block_discord_prompt:
            return
        gs = load_gui_settings()
        if "discord_always_on" in gs:
            return  # Already answered — don't ask again
        msg = QMessageBox(self)
        msg.setWindowTitle("Discord Notifications")
        msg.setText("Always enable Discord notifications by default?")
        msg.setInformativeText(
            "If you choose Yes, Discord updates will be pre-checked every time you "
            "open this page. This preference is saved to gui_settings.json and can "
            "be changed at any time."
        )
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton("Yes, always enable", QMessageBox.ButtonRole.YesRole)
        msg.addButton("No, ask me each time", QMessageBox.ButtonRole.NoRole)
        msg.exec()
        always_on = msg.clickedButton() is yes_btn
        gs["discord_always_on"] = always_on
        gs["discord_level"] = self.discord_level_combo.currentText()
        save_gui_settings(gs)

    def reset_to_defaults(self):
        """Reset all area selections and options to their initial defaults."""
        # Reset area checkboxes to all checked
        for cb in self._area_checks.values():
            cb.setChecked(True)
        # Reset extra options
        self.scrape_paid_check.setChecked(False)
        self.scrape_labels_check.setChecked(False)
        self.discord_updates_check.setChecked(False)
        self.discord_level_combo.setCurrentText("LOW")
        self.discord_level_combo.setEnabled(False)
        # Reset advanced options
        self.allow_dupes_check.setChecked(False)
        self.keep_msg_purchased_dupes_check.setChecked(False)
        self.keep_msg_purchased_dupes_check.setEnabled(False)
        self.rescrape_all_check.setChecked(False)
        self.delete_db_check.setChecked(False)
        self.delete_downloads_check.setChecked(False)
        self.quality_combo.setCurrentText("Default")
        # Reset daemon options
        self.daemon_check.setChecked(False)
        self.daemon_interval.setValue(30.0)
        self.daemon_interval.setEnabled(False)
        self.notify_check.setChecked(False)
        self.sound_check.setChecked(False)
        self.daemon_discord_ping_check.setChecked(False)
        self.daemon_discord_ping_check.setEnabled(False)
        # Reset media type checkboxes to match config
        config_filter = config_data.get_filter() or ["Images", "Videos", "Audios"]
        config_filter_lower = {x.lower() for x in config_filter}
        for mt, cb in self._mediatype_checks.items():
            cb.setChecked(mt.lower() in config_filter_lower)
        # Reset post text checkboxes
        self.include_text_check.setChecked(False)
        self.text_filename_from_post_check.setChecked(False)
        self._sync_text_filename_option()
        # Reset filter sidebar
        self.filter_sidebar.reset_all()
        # Reset model loading state so models reload on next visit
        self._models_loaded = False
        self._models_loading = False
        self._refresh_discord_option_state()

    def _on_action_selected(self, actions):
        """Update available areas based on selected actions.

        Model fetch is deferred until MainWindow finishes the missing-deps
        notice (or skips it). Overlapping that popup with the fetch caused
        hard GUI crashes when the popup was closed mid-load.
        """
        self._current_actions = actions
        self._update_available_areas()
        self._pending_model_load = True
        try:
            self.next_btn.setEnabled(False)
            self.model_loading_label.setText("Waiting to load models...")
            self.model_loading_label.show()
            self.model_loading_bar.hide()
        except RuntimeError:
            pass

    def start_pending_model_load(self):
        """Called by MainWindow after the missing-deps gate completes."""
        self._pending_model_load = False
        if not self._current_actions:
            return
        if self._models_loaded or self._models_loading:
            return
        self._start_model_load()

    def _on_allow_dupes_toggled(self, checked):
        """Enable the Messages+Purchased sub-option only when Allow duplicates is on."""
        on = bool(checked)
        self.keep_msg_purchased_dupes_check.setEnabled(on)
        if not on:
            self.keep_msg_purchased_dupes_check.setChecked(False)

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
        self._cancel_models_worker()
        self._models_loaded = False
        self._models_loading = False
        self.retry_models_btn.hide()
        self._start_model_load()

    def _widget_alive(self) -> bool:
        """False if this page's Qt widgets were deleted (navigate-away / shutdown)."""
        try:
            _ = self.next_btn.isEnabled()
            return True
        except RuntimeError:
            return False
        except Exception:
            return False

    def _cancel_models_worker(self):
        """Ignore any in-flight worker; stop poll timer; clean fetch environment."""
        self._models_load_gen = int(getattr(self, "_models_load_gen", 0) or 0) + 1
        self._stop_models_poll()
        self._models_worker = None
        self._models_finish_scheduled = False
        try:
            from ofscraper.gui.utils.model_fetch import clear_handoff

            clear_handoff()
        except Exception:
            pass
        self._cleanup_models_env()

    def _stop_models_poll(self):
        timer = getattr(self, "_models_poll_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass

    def _cleanup_models_env(self):
        if not getattr(self, "_models_env_prepared", False):
            return
        self._models_env_prepared = False
        try:
            from ofscraper.gui.utils.model_fetch import cleanup_model_fetch_environment

            cleanup_model_fetch_environment()
        except Exception:
            pass

    def _start_model_load(self):
        """Fetch subscription models from API in background; disable Next until ready."""
        if self._models_loading:
            return
        if self._models_loaded:
            return

        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_start_model_load", "Areas page")
        except Exception:
            pass

        self._models_loading = True
        self._models_error = None
        self._loaded_model_count = 0
        self._models_finish_scheduled = False
        self._models_load_gen = int(getattr(self, "_models_load_gen", 0) or 0) + 1
        load_gen = self._models_load_gen
        self.retry_models_btn.hide()
        self.reload_models_btn.hide()

        try:
            self.next_btn.setEnabled(False)
            self.model_loading_label.setText("Loading models from API...")
            self.model_loading_label.show()
            self.model_loading_bar.show()
        except RuntimeError:
            self._models_loading = False
            return

        if not (self.manager and getattr(self.manager, "model_manager", None)):
            self._models_loading = False
            self._models_error = "Model manager not available"
            try:
                self.model_loading_bar.hide()
                self.model_loading_label.setText("Model manager not available")
                self.next_btn.setEnabled(True)
            except RuntimeError:
                pass
            return

        # Clear profile cache on the UI thread only (not from the worker).
        try:
            import ofscraper.utils.profiles.data as profile_data

            profile_data.currentData = None
            profile_data.currentProfile = None
        except Exception:
            pass

        try:
            import ofscraper.utils.settings as _settings_mod

            _settings_mod.update_settings()
        except Exception:
            pass

        userlist = self._get_active_userlist()
        load_gen = self._models_load_gen

        def _job():
            from ofscraper.gui.utils.model_fetch import (
                fetch_subscription_models,
                publish_handoff,
                wait_for_ui_ack,
            )

            try:
                dicts = fetch_subscription_models(userlist=userlist)
                publish_handoff(gen=load_gen, payload=dicts)
                wait_for_ui_ack()
                return len(dicts or [])
            except Exception as e:
                publish_handoff(gen=load_gen, error=str(e))
                wait_for_ui_ack()
                raise

        # Prepare NullLive / quiet console on the MAIN thread (not the worker).
        try:
            from ofscraper.gui.utils.model_fetch import (
                clear_handoff,
                prepare_model_fetch_environment,
            )

            clear_handoff()
            prepare_model_fetch_environment()
            self._models_env_prepared = True
        except Exception as e:
            log.warning(f"[GUI] prepare_model_fetch_environment failed: {e}")

        self._stop_models_poll()
        # No cross-thread Qt signals — poll worker.done from a main-thread timer.
        self._models_worker = Worker(_job, emit_signals=False)
        from PyQt6.QtCore import QThreadPool, QTimer

        if self._models_poll_timer is None:
            self._models_poll_timer = QTimer(self)
            self._models_poll_timer.setInterval(50)
            self._models_poll_timer.timeout.connect(self._poll_models_worker)

        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_worker_queued", f"gen={load_gen} poll=1 handoff=1")
        except Exception:
            pass
        QThreadPool.globalInstance().start(self._models_worker)
        self._models_poll_timer.start()

    def _poll_models_worker(self):
        """Main-thread poll — takes plain dicts from the handoff box.

        Prefer ``handoff_ready`` over ``worker.done``: the worker stays blocked
        in ``wait_for_ui_ack`` until cleanup, so ``done`` flips only after ack.
        """
        worker = getattr(self, "_models_worker", None)
        load_gen = getattr(self, "_models_load_gen", None)
        ready = False
        try:
            from ofscraper.gui.utils.model_fetch import handoff_ready

            ready = handoff_ready(int(load_gen or 0))
        except Exception:
            ready = False
        if not ready and (worker is None or not getattr(worker, "done", False)):
            return
        if getattr(self, "_models_finish_scheduled", False):
            return
        self._models_finish_scheduled = True
        self._stop_models_poll()
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_poll_seen_done", f"gen={load_gen}")
        except Exception:
            pass

        from PyQt6.QtCore import QTimer

        QTimer.singleShot(150, lambda g=load_gen: self._finish_models_load(g))

    def _finish_models_load(self, load_gen=None):
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_finish_models_load", f"gen={load_gen}")
        except Exception:
            pass

        self._models_finish_scheduled = False
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            return

        from ofscraper.gui.utils.model_fetch import take_handoff

        handoff = take_handoff(int(load_gen or 0))
        worker = getattr(self, "_models_worker", None)
        self._models_worker = None
        self._cleanup_models_env()

        if handoff is None:
            err = (
                getattr(worker, "error_msg", None)
                if worker
                else "Model fetch handoff missing"
            )
            if err:
                self._on_models_error(err, load_gen)
            else:
                self._apply_models_loaded([], load_gen)
            return

        err = handoff.get("error")
        payload = handoff.get("payload")
        if err:
            self._on_models_error(err, load_gen)
            return

        from PyQt6.QtCore import QTimer
        from ofscraper.gui.utils.model_fetch import dicts_to_models

        def _build_and_apply():
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb(
                    "ui_build_models_start",
                    f"dicts={len(payload or [])}",
                )
            except Exception:
                pass
            models = dicts_to_models(payload)
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("ui_build_models_done", f"count={len(models)}")
            except Exception:
                pass
            self._apply_models_loaded(models, load_gen)

        QTimer.singleShot(0, _build_and_apply)

    def _apply_models_loaded(self, models, load_gen=None):
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            return
        if not self._widget_alive():
            return

        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_apply_models_start", f"count={len(models or [])}")
        except Exception:
            pass

        self._models_worker = None
        self._models_loading = False
        try:
            # Apply fetched models on the UI thread only.
            if self.manager and getattr(self.manager, "model_manager", None) is not None:
                self.manager.model_manager.all_subs_dict = models or []
            self._loaded_model_count = len(models or [])
            self.model_loading_bar.hide()
            if self._loaded_model_count == 0:
                self._models_loaded = False  # allow retry after fixing auth
                self._show_auth_failure_prompt()
                try:
                    from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                    breadcrumb("ui_apply_models_empty")
                except Exception:
                    pass
                return
            self._models_loaded = True
            self.retry_models_btn.hide()
            self.reload_models_btn.show()
            self.model_loading_label.setText(f"Models loaded: {self._loaded_model_count}")
            self.model_loading_label.show()
            self.next_btn.setEnabled(True)
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("ui_apply_models_done", f"count={self._loaded_model_count}")
            except Exception:
                pass
        except RuntimeError:
            log.debug("[GUI] Model-load UI update skipped (widget deleted)")
        except Exception as e:
            log.warning(f"[GUI] Model-load UI update failed: {e}")
            try:
                self._on_models_error(str(e), load_gen)
            except Exception:
                pass

    def _on_models_error(self, error_msg, load_gen=None):
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            log.debug("[GUI] Ignoring stale model-load error callback")
            return
        try:
            from ofscraper.gui.utils.crash_diagnostics import breadcrumb

            breadcrumb("ui_models_error", f"gen={load_gen} msg={error_msg}")
        except Exception:
            pass
        if not self._widget_alive():
            return

        self._models_worker = None
        self._models_loading = False
        self._models_loaded = False  # allow retry after fixing auth
        self._models_error = error_msg
        try:
            self.model_loading_bar.hide()
            self._show_auth_failure_prompt(error_msg)
        except RuntimeError:
            log.debug("[GUI] Model-load error UI update skipped (widget deleted)")
        except Exception as e:
            log.warning(f"[GUI] Model-load error UI update failed: {e}")

    def _show_auth_failure_prompt(self, detail=None):
        """Show a dialog when models can't be loaded, offering to go to auth settings or retry.

        Deferred one tick and guarded — showing a modal QMessageBox immediately
        after the model-fetch worker finishes has hard-crashed the Qt event loop
        on Windows (especially when normalize incorrectly returned 0 models).
        """
        if not self._widget_alive():
            return
        self.model_loading_label.setText("Unable to get list of models.")
        self.model_loading_label.show()
        self.retry_models_btn.show()
        self.next_btn.setEnabled(False)

        from PyQt6.QtCore import QTimer

        def _show():
            if not self._widget_alive():
                return
            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("ui_auth_prompt_open")
            except Exception:
                pass
            try:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("Unable to Load Models")
                from ofscraper.gui.utils.auth_errors import model_load_failure_dialog_text

                main_text, detail_text = model_load_failure_dialog_text(detail)
                msg.setText(main_text)
                if detail_text:
                    msg.setDetailedText(detail_text)
                retry_btn = msg.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
                auth_btn = msg.addButton(
                    "Go to Authentication", QMessageBox.ButtonRole.ActionRole
                )
                dynamic_btn = msg.addButton(
                    "Dynamic Mode (Config)", QMessageBox.ButtonRole.ActionRole
                )
                ssl_btn = msg.addButton(
                    "SSL Verify (Config)", QMessageBox.ButtonRole.ActionRole
                )
                help_btn = msg.addButton("Help / README", QMessageBox.ButtonRole.ActionRole)
                msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
                msg.exec()
            except Exception as e:
                log.warning(f"[GUI] Auth failure prompt failed: {e}")
                return

            try:
                from ofscraper.gui.utils.crash_diagnostics import breadcrumb

                breadcrumb("ui_auth_prompt_closed")
            except Exception:
                pass

            clicked = msg.clickedButton()
            if clicked == retry_btn:
                self._retry_model_load()
            elif clicked == auth_btn:
                app_signals.navigate_to_page.emit("auth")
            elif clicked == dynamic_btn:
                self._go_to_advanced_config_field("dynamic-mode-default")
            elif clicked == ssl_btn:
                self._go_to_advanced_config_field("ssl_verify")
            elif clicked == help_btn:
                self._go_to_auth_help()

        QTimer.singleShot(0, _show)

    def _go_to_advanced_config_field(self, field_key: str):
        """Navigate to Configuration → Advanced and focus a field by key."""
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
                            cfg_page.go_to_config_field("Advanced", field_key)
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
        is_check = bool(self._current_actions & _CHECK_MODES)

        if is_check:
            if "post_check" in self._current_actions:
                available = POST_CHECK_AREAS
                self.areas_group.setTitle("Check Areas")
                self.areas_group.show()
            else:
                # msg_check / paid_check / story_check don't need area selection
                self.areas_group.hide()
                for cb in self._area_checks.values():
                    cb.setChecked(False)
                    cb.setEnabled(False)
                return
        else:
            has_download = "download" in self._current_actions
            has_like = "like" in self._current_actions or "unlike" in self._current_actions
            if has_download:
                available = DOWNLOAD_AREAS
            elif has_like:
                available = LIKE_AREAS
            else:
                available = DOWNLOAD_AREAS
            self.areas_group.setTitle("Content Areas")
            self.areas_group.show()

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

    def get_selected_mediatypes(self):
        selected = [mt for mt, cb in self._mediatype_checks.items() if cb.isChecked()]
        # If nothing checked, fall back to all types so the scrape isn't broken
        return selected if selected else ["Images", "Videos", "Audios"]

    def _on_daemon_toggled(self, checked):
        self.daemon_interval.setEnabled(checked)
        self.daemon_discord_ping_check.setEnabled(checked)

    def _on_daemon_ping_toggled(self, checked: bool):
        from ofscraper.gui.utils.gui_settings import load_gui_settings, save_gui_settings
        gs = load_gui_settings()
        gs["daemon_discord_ping"] = checked
        save_gui_settings(gs)

    def is_daemon_enabled(self):
        return self.daemon_check.isChecked()

    def get_daemon_interval(self):
        return self.daemon_interval.value()

    def is_notify_enabled(self):
        return self.notify_check.isChecked()

    def is_sound_enabled(self):
        return self.sound_check.isChecked()

    def is_daemon_discord_ping_enabled(self):
        return self.daemon_discord_ping_check.isChecked()

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

        # Date — set mode/values first, dates second, enable state last so it always wins
        tgt.after_mode_combo.setCurrentText(src.after_mode_combo.currentText())
        tgt.after_rel_value.setValue(src.after_rel_value.value())
        tgt.after_rel_unit.setCurrentText(src.after_rel_unit.currentText())
        tgt.min_date.setDate(src.min_date.date())
        tgt.after_enabled.setChecked(src.after_enabled.isChecked())
        tgt.before_mode_combo.setCurrentText(src.before_mode_combo.currentText())
        tgt.before_rel_value.setValue(src.before_rel_value.value())
        tgt.before_rel_unit.setCurrentText(src.before_rel_unit.currentText())
        tgt.max_date.setDate(src.max_date.date())
        tgt.before_enabled.setChecked(src.before_enabled.isChecked())

        # Length / Price — set values first (block auto-Enable), then Enable flags.
        tgt.min_time.blockSignals(True)
        tgt.max_time.blockSignals(True)
        try:
            tgt.min_time.setTime(src.min_time.time())
            tgt.max_time.setTime(src.max_time.time())
        finally:
            tgt.min_time.blockSignals(False)
            tgt.max_time.blockSignals(False)
        tgt.length_enabled.setChecked(src.length_enabled.isChecked())

        tgt.price_min.blockSignals(True)
        tgt.price_max.blockSignals(True)
        try:
            tgt.price_min.setValue(src.price_min.value())
            tgt.price_max.setValue(src.price_max.value())
        finally:
            tgt.price_min.blockSignals(False)
            tgt.price_max.blockSignals(False)
        tgt.price_enabled.setChecked(src.price_enabled.isChecked())

        # IDs
        tgt.media_id_input.setText(src.media_id_input.text())
        tgt.post_id_input.setText(src.post_id_input.text())
        tgt.post_media_count_input.setValue(src.post_media_count_input.value())
        tgt.other_posts_input.setValue(src.other_posts_input.value())

        # Username
        tgt.username_input.setText(src.username_input.text())

    def _sync_text_filename_option(self):
        """Enable caption naming only when Include Post Text is on."""
        enabled = self.include_text_check.isChecked()
        self.text_filename_from_post_check.setEnabled(enabled)
        if not enabled:
            self.text_filename_from_post_check.setChecked(False)
        self.text_filename_length_warning.setVisible(
            enabled and self.text_filename_from_post_check.isChecked()
        )

    def _on_include_text_toggled(self, checked: bool):
        self._sync_text_filename_option()

    def _on_text_filename_from_post_toggled(self, checked: bool):
        self.text_filename_length_warning.setVisible(
            self.include_text_check.isChecked() and checked
        )

    def _on_back(self):
        parent_stack = self.parent()
        if parent_stack:
            parent_stack.setCurrentIndex(0)  # action page

    def _on_next(self):
        """Validate areas and proceed to model selection."""
        is_check = bool(self._current_actions & _CHECK_MODES)
        needs_areas = not is_check or "post_check" in self._current_actions

        selected = self.get_selected_areas()
        if needs_areas and not selected:
            app_signals.error_occurred.emit(
                "No Areas Selected",
                "Please select at least one content area.",
            )
            return

        log.info(f"Areas configured: {selected}")
        mediatypes = self.get_selected_mediatypes()
        app_signals.mediatypes_configured.emit(mediatypes)
        app_signals.include_text_configured.emit(self.include_text_check.isChecked())
        app_signals.text_filename_from_post_configured.emit(
            self.include_text_check.isChecked()
            and self.text_filename_from_post_check.isChecked()
        )
        # Emit advanced options here so check-mode auto-start (on model select)
        # sees Allow duplicates / Rescrape / quality — table Start Scraping is skipped.
        try:
            app_signals.advanced_scrape_configured.emit(
                {
                    "allow_dupe_downloads": bool(self.allow_dupes_check.isChecked()),
                    "keep_message_purchased_dupes": bool(
                        self.allow_dupes_check.isChecked()
                        and self.keep_msg_purchased_dupes_check.isChecked()
                    ),
                    "rescrape_all": bool(self.rescrape_all_check.isChecked()),
                    "delete_model_db": bool(self.delete_db_check.isChecked()),
                    "delete_downloads": bool(self.delete_downloads_check.isChecked()),
                    "quality": self.quality_combo.currentText(),
                }
            )
            app_signals.scrape_paid_toggled.emit(self.scrape_paid_check.isChecked())
            if self.scrape_labels_check.isChecked():
                app_signals.scrape_labels_toggled.emit(True)
        except Exception:
            pass

        # For check modes, emit areas immediately so the workflow stores them
        # before model selection triggers the auto-start.
        if is_check:
            app_signals.areas_selected.emit(selected)

        # Pre-filter models by username if one was entered
        username = self.get_username_filter()
        parent_stack = self.parent()
        if parent_stack:
            # Get the model selector page (index 1) and apply username filter
            model_page = parent_stack.widget(1)
            if model_page and hasattr(model_page, "pre_filter_username"):
                model_page.pre_filter_username(username)
            parent_stack.setCurrentIndex(1)  # model selector
