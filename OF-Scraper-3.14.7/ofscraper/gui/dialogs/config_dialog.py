import json
import logging

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QTabBar,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton
import ofscraper.utils.paths.common as common_paths

log = logging.getLogger("shared")

# Config QLineEdit keys that hold real filesystem paths (Windows: show `\`).
_FS_PATH_WIDGET_KEYS = frozenset(
    {
        "save_location",
        "ffmpeg",
        "client-id",
        "private-key",
        "temp_dir",
        "after_action_script",
        "post_script",
        "naming_script",
        "after_download_script",
        "skip_download_script",
    }
)

_SCRIPT_OPTION_KEYS = (
    "after_action_script",
    "post_script",
    "naming_script",
    "after_download_script",
    "skip_download_script",
)

_IMAGE_EXT_CHOICES = ("jpg", "jpeg", "png", "webp", "gif")
_VIDEO_EXT_CHOICES = ("mp4", "mov", "m4v", "mkv", "webm")
_AUDIO_EXT_CHOICES = ("mp3", "m4a", "wav", "aac", "flac")


def _sanitize_ext_text(val: str, default: str) -> str:
    s = "".join(c for c in str(val or "").strip().lstrip(".").lower() if c.isalnum())
    return s or default


def _display_fs_path(value: str) -> str:
    """Normalize Windows filesystem paths for GUI display; Linux unchanged."""
    try:
        from ofscraper.utils.config.path_norm import normalize_windows_path

        return normalize_windows_path(value) if value else value
    except Exception:
        return value


def _help_btn_qss():
    return (
        f"QToolButton {{ border: 1px solid {c('surface1')}; border-radius: 9px;"
        f" background-color: {c('surface0')}; color: {c('text')}; font-weight: bold;"
        f" margin-right: 4px; }}"
        f" QToolButton:hover {{ border-color: {c('blue')}; background-color: {c('surface1')}; }}"
    )

def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help for this config section")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(_help_btn_qss())
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b


class ConfigPage(QWidget):
    """Configuration editor page — replaces the InquirerPy config prompt.
    Uses a QTabWidget to organize settings by category."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._config = {}
        self._widgets = {}
        self._tab_index = {}
        self._tab_scroll = {}
        self._privacy_actual = {}
        self._setup_ui()
        self._load_config()
        app_signals.theme_changed.connect(self._apply_theme)
        app_signals.config_updated.connect(self._load_config)
        app_signals.privacy_mode_changed.connect(self._on_privacy_mode_changed)

    def _apply_theme(self, _is_dark=True):
        for btn in self.findChildren(QToolButton):
            if btn.text() == "?":
                btn.setStyleSheet(_help_btn_qss())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header = QLabel("Configuration")
        apply_font(header, "Segoe UI", 22, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel("Edit application settings. Changes are saved to config.json.")
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        # Tab widget
        self.tabs = QTabWidget()
        def _add_tab(widget, label):
            idx = self.tabs.addTab(widget, label)
            self._tab_index[label] = idx
            self._tab_scroll[label] = widget
            return idx

        _add_tab(self._create_general_tab(), "General")
        _add_tab(self._create_file_tab(), "File Options")
        _add_tab(self._create_download_tab(), "Download")
        _add_tab(self._create_scripts_tab(), "Scripts")
        _add_tab(self._create_performance_tab(), "Performance")
        _add_tab(self._create_content_tab(), "Content")
        _add_tab(self._create_cdm_tab(), "CDM")
        _add_tab(self._create_advanced_tab(), "Advanced")
        _add_tab(self._create_response_tab(), "Response Type")
        layout.addWidget(self.tabs)

        # Add a (?) help button to each config tab.
        try:
            tab_help = {
                "General": "config-general",
                "File Options": "config-file-options",
                "Download": "config-download",
                "Scripts": "config-scripts",
                "Performance": "config-performance",
                "Content": "config-content",
                "CDM": "config-cdm",
                "Advanced": "config-advanced",
                "Response Type": "config-response-type",
            }
            bar = self.tabs.tabBar()
            for label, anchor in tab_help.items():
                idx = self._tab_index.get(label)
                if idx is None:
                    continue
                bar.setTabButton(
                    int(idx),
                    QTabBar.ButtonPosition.RightSide,
                    _make_help_btn(anchor),
                )
        except Exception:
            pass

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        open_config_btn = StyledButton("Open config.json")
        open_config_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(common_paths.get_config_path()))
            )
        )
        btn_layout.addWidget(open_config_btn)

        reload_btn = StyledButton("Reload")
        reload_btn.clicked.connect(self._load_config)
        btn_layout.addWidget(reload_btn)

        save_btn = StyledButton("Save", primary=True)
        save_btn.setFixedWidth(120)
        save_btn.clicked.connect(self._save_config)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def go_to_config_field(self, tab_label: str, key: str | None = None):
        """Navigate to a specific tab and optionally focus a config widget by key."""
        try:
            idx = self._tab_index.get(tab_label)
            if idx is None:
                return
            self.tabs.setCurrentIndex(idx)
            if not key:
                return
            w = self._widgets.get(key)
            if not w:
                return
            # Scroll if tab is a QScrollArea (most are)
            scroll = self._tab_scroll.get(tab_label)
            try:
                # QScrollArea.ensureWidgetVisible is available in Qt
                if hasattr(scroll, "ensureWidgetVisible"):
                    scroll.ensureWidgetVisible(w)
            except Exception:
                pass
            try:
                w.setFocus()
            except Exception:
                pass
        except Exception:
            pass

    def _create_scrollable_form(self):
        """Create a scroll area with a form layout inside."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setSpacing(10)
        scroll.setWidget(container)
        return scroll, form

    def _add_line(self, form, key, label, placeholder="", tooltip=""):
        w = QLineEdit()
        w.setPlaceholderText(placeholder)
        if tooltip:
            w.setToolTip(tooltip)
        w.setClearButtonEnabled(True)
        form.addRow(label + ":", w)
        self._widgets[key] = w
        return w

    def _add_spin(self, form, key, label, min_val=0, max_val=9999, default=0, tooltip=""):
        w = QSpinBox()
        w.setRange(min_val, max_val)
        w.setValue(default)
        if tooltip:
            w.setToolTip(tooltip)
        form.addRow(label + ":", w)
        self._widgets[key] = w
        return w

    def _add_check(self, form, key, label, default=False, tooltip=""):
        w = QCheckBox()
        w.setChecked(default)
        if tooltip:
            w.setToolTip(tooltip)
        form.addRow(label + ":", w)
        self._widgets[key] = w
        return w

    def _add_combo(self, form, key, label, items, tooltip=""):
        w = QComboBox()
        w.addItems(items)
        if tooltip:
            w.setToolTip(tooltip)
        form.addRow(label + ":", w)
        self._widgets[key] = w
        return w

    def _add_editable_combo(self, form, key, label, items, default="", tooltip=""):
        w = QComboBox()
        w.setEditable(True)
        w.addItems(list(items))
        if default:
            idx = w.findText(default)
            if idx >= 0:
                w.setCurrentIndex(idx)
            else:
                w.setCurrentText(default)
        if tooltip:
            w.setToolTip(tooltip)
        form.addRow(label + ":", w)
        self._widgets[key] = w
        return w

    def _add_manual_rules_field(self, form):
        """Compact multiline paste area + Load JSON for Dynamic Mode ``manual``."""
        from PyQt6.QtWidgets import QSizePolicy

        tip = (
            "Local OnlyFans signing-rules JSON used when Dynamic Mode is 'manual'.\n"
            "Required: static_param, checksum_indexes, checksum_constant,\n"
            "and either 'format' or both 'prefix' and 'suffix'.\n"
            "Env override: OFSC_DYNAMIC_RULE_MANUAL (takes precedence)."
        )
        row = QWidget()
        row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch()
        load_btn = StyledButton("Load JSON…")
        load_btn.setToolTip("Load signing-rules JSON from a file")
        load_btn.clicked.connect(self._load_manual_rules_json_file)
        header.addWidget(load_btn)
        row_layout.addLayout(header)
        w = QTextEdit()
        w.setAcceptRichText(False)
        w.setPlaceholderText(
            '{"static_param":"...","format":"...:{}:{:x}:...",'
            '"checksum_indexes":[0,1,2],"checksum_constant":0}'
        )
        w.setToolTip(tip)
        w.setFixedHeight(72)
        w.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        apply_font(w, "Consolas", 9)
        w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        row_layout.addWidget(w)
        form.addRow("Manual Dynamic Rules:", row)
        self._widgets["dynamic_rules_manual"] = w
        return w

    def _load_manual_rules_json_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Manual Dynamic Rules",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            from ofscraper.utils.dynamic_rules_manual import (
                normalize_manual_rules_json,
                parse_manual_rules,
                validate_manual_rules,
            )

            parsed = parse_manual_rules(raw)
            if parsed is None:
                QMessageBox.warning(
                    self, "Invalid JSON", "The selected file is not valid JSON object."
                )
                return
            err = validate_manual_rules(parsed)
            if err:
                QMessageBox.warning(self, "Invalid Rules", err)
                return
            w = self._widgets.get("dynamic_rules_manual")
            if isinstance(w, QTextEdit):
                w.setPlainText(normalize_manual_rules_json(parsed))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")

    def _add_endpoint_overrides_field(self, form):
        """Compact JSON paste area for per-endpoint API URL overrides."""
        from PyQt6.QtWidgets import QSizePolicy

        tip = (
            "JSON object of of_env endpoint keys → full URL templates.\n"
            "Example: {\"meEP\":\"https://onlyfans.com/api2/v2/users/me\"}\n"
            "Known keys include meEP, timelineEP, LICENCE_URL, messagesEP, …\n"
            "Dedicated OFSC_API_* env vars still win when set.\n"
            "Leave {} to use defaults."
        )
        row = QWidget()
        row.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.addStretch()
        load_btn = StyledButton("Load JSON…")
        load_btn.setToolTip("Load endpoint overrides JSON from a file")
        load_btn.clicked.connect(self._load_endpoint_overrides_json_file)
        header.addWidget(load_btn)
        row_layout.addLayout(header)
        w = QTextEdit()
        w.setAcceptRichText(False)
        w.setPlaceholderText('{"meEP":"https://onlyfans.com/api2/v2/users/me"}')
        w.setToolTip(tip)
        w.setFixedHeight(72)
        w.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        apply_font(w, "Consolas", 9)
        w.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        row_layout.addWidget(w)
        form.addRow("API Endpoint Overrides:", row)
        self._widgets["api_endpoint_overrides"] = w
        return w

    def _load_endpoint_overrides_json_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load API Endpoint Overrides",
            "",
            "JSON files (*.json);;All files (*.*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
            from ofscraper.utils.api_endpoint_overrides import (
                normalize_endpoint_overrides_json,
                parse_endpoint_overrides,
                validate_endpoint_overrides,
            )

            parsed = parse_endpoint_overrides(raw)
            if parsed is None:
                QMessageBox.warning(
                    self, "Invalid JSON", "The selected file is not a valid JSON object."
                )
                return
            err = validate_endpoint_overrides(parsed)
            if err:
                QMessageBox.warning(self, "Invalid Overrides", err)
                return
            w = self._widgets.get("api_endpoint_overrides")
            if isinstance(w, QTextEdit):
                w.setPlainText(normalize_endpoint_overrides_json(parsed))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file:\n{e}")

    def _add_path(self, form, key, label, is_dir=True, tooltip=""):
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        w = QLineEdit()
        w.setClearButtonEnabled(True)
        if tooltip:
            w.setToolTip(tooltip)
        row_layout.addWidget(w)
        browse = StyledButton("Browse")
        browse.clicked.connect(
            lambda: self._browse_path(w, is_dir)
        )
        row_layout.addWidget(browse)
        form.addRow(label + ":", row)
        self._widgets[key] = w
        return w

    def _browse_path(self, line_edit, is_dir):
        if is_dir:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        if path:
            # Find which privacy key this widget belongs to (if any)
            key = None
            for k, w in self._widgets.items():
                if w is line_edit:
                    key = k
                    break
            path = _display_fs_path(path)
            try:
                from ofscraper.gui.utils.privacy_mode import (
                    PRIVACY_CONFIG_KEYS,
                    PRIVACY_PLACEHOLDER,
                    is_privacy_mode,
                )

                if key in PRIVACY_CONFIG_KEYS and is_privacy_mode():
                    self._privacy_actual[key] = path
                    line_edit.setText(PRIVACY_PLACEHOLDER)
                    return
            except Exception:
                pass
            line_edit.setText(path)

    def _on_privacy_mode_changed(self, enabled: bool):
        self._apply_privacy_mask(bool(enabled))

    def _apply_privacy_mask(self, enabled=None):
        """Show/hide path & webhook fields for privacy / demo mode."""
        try:
            from ofscraper.gui.utils.privacy_mode import (
                PRIVACY_CONFIG_KEYS,
                PRIVACY_PLACEHOLDER,
                is_privacy_mode,
            )

            on = is_privacy_mode() if enabled is None else bool(enabled)
        except Exception:
            return
        for key in PRIVACY_CONFIG_KEYS:
            w = self._widgets.get(key)
            if not isinstance(w, QLineEdit):
                continue
            if on:
                current = w.text().strip()
                if current and current != PRIVACY_PLACEHOLDER:
                    self._privacy_actual[key] = (
                        _display_fs_path(current) if key in _FS_PATH_WIDGET_KEYS else current
                    )
                actual = self._privacy_actual.get(key, "")
                w.setText(PRIVACY_PLACEHOLDER if actual else "")
                w.setReadOnly(True)
                if not hasattr(w, "_privacy_tip_saved"):
                    w._privacy_tip_saved = w.toolTip() or ""
                base_tip = getattr(w, "_privacy_tip_saved", "") or ""
                w.setToolTip(
                    (base_tip + "\n\n" if base_tip else "")
                    + "Hidden by Privacy mode — turn Privacy off to view/edit."
                )
            else:
                actual = self._privacy_actual.get(key)
                if actual is not None:
                    if key in _FS_PATH_WIDGET_KEYS and actual:
                        actual = _display_fs_path(actual)
                    w.setText(actual)
                w.setReadOnly(False)
                if hasattr(w, "_privacy_tip_saved"):
                    w.setToolTip(w._privacy_tip_saved)

    # ---- Tab Builders ----

    def _create_general_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_line(form, "main_profile", "Main Profile", "main_profile",
                       tooltip="The active profile name. Each profile has its own auth.json and data directory.")
        self._add_line(form, "metadata", "Metadata Path", "{configpath}/{profile}/.data/{model_id}",
                       tooltip="Path template for metadata/database storage.\nSupports placeholders: {configpath}, {profile}, {model_id}.")
        self._add_line(form, "discord", "Discord Webhook URL", "https://discord.com/api/webhooks/...",
                       tooltip="Discord webhook URL for sending scrape notifications.\nLeave empty to disable Discord updates.")
        return scroll

    def _create_file_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_path(form, "save_location", "Save Location", is_dir=True,
                       tooltip="Root directory where downloaded files are saved.")
        self._add_line(form, "dir_format", "Directory Format",
                       "{model_username}/{responsetype}/{mediatype}/",
                       tooltip="Directory structure template under save location.\n"
                               "Must stay relative to Save Location (no absolute paths or '..').\n"
                               "Placeholders: {model_username}, {responsetype}, {mediatype}, {model_id}, {first_letter}, etc.")
        self._add_line(form, "file_format", "File Format", "{filename}.{ext}",
                       tooltip="Filename template for downloaded files.\n"
                               "Must include a uniqueness token: {filename}, {media_id}, or {original_filename}.\n"
                               "Other placeholders: {ext}, {date}, {post_id}, {text}, {number}, etc.")
        self._add_spin(form, "textlength", "Text Length", 0, 999, 0,
                       tooltip="Max characters/words from post text (see Text Type).\n"
                               "Used in File Format {text} and when naming .txt files from captions.\n"
                               "Keep under ~250 when naming text files from post text so\n"
                               "name + \".txt\" stays within the 255-character/byte OS limit.\n"
                               "0 = do not include post text in media filenames.")
        self._add_line(form, "space_replacer", "Space Replacer", " ",
                       tooltip="Character(s) to replace spaces in filenames.\nLeave empty to keep spaces as-is.")
        self._add_line(form, "date", "Date Format", "YYYY-MM-DD",
                       tooltip="Date format string for {date} placeholder in filenames.\nExamples: YYYY-MM-DD, MM-DD-YYYY, DD.MM.YYYY")
        self._add_combo(form, "text_type_default", "Text Type",
                        ["letter", "word"],
                        tooltip="How 'Text Length' is counted:\n- letter: count individual characters\n- word: count whole words")
        self._add_check(form, "truncation_default", "Enable Truncation", True,
                        tooltip="Truncate long filenames to fit OS path/name limits.\n"
                                "Windows/Linux filename components max ~255 characters/bytes.\n"
                                "Keep enabled, especially when naming .txt files from captions.")
        return scroll

    def _on_ext_override_row_toggled(self, combo_key: str, checked: bool):
        w = self._widgets.get(combo_key)
        if w is not None:
            w.setEnabled(bool(checked))

    def _add_ext_override_row(
        self,
        form,
        check_key: str,
        combo_key: str,
        label: str,
        items,
        default: str,
        tooltip: str = "",
    ):
        """Checkbox (enable this type) + editable extension combo on one row."""
        cb = QCheckBox(label)
        cb.setChecked(False)
        if tooltip:
            cb.setToolTip(tooltip)
        combo = QComboBox()
        combo.setEditable(True)
        combo.addItems(list(items))
        if default:
            idx = combo.findText(default)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentText(default)
        if tooltip:
            combo.setToolTip(tooltip)
        combo.setEnabled(False)
        form.addRow(cb, combo)
        self._widgets[check_key] = cb
        self._widgets[combo_key] = combo
        cb.toggled.connect(
            lambda checked, k=combo_key: self._on_ext_override_row_toggled(k, checked)
        )
        return cb, combo

    def _create_download_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_spin(form, "system_free_min", "Min Free Space (MB)", 0, 999999, 0,
                       "Minimum free disk space required before downloads")
        self._add_check(form, "auto_resume", "Auto Resume", True,
                        tooltip="Automatically resume partially downloaded files instead of re-downloading them.")
        self._add_spin(form, "max_post_count", "Max Post Count", 0, 999999, 0,
                       tooltip="Maximum number of posts to process per model.\n0 = unlimited (process all posts).")
        # Binary options
        self._add_path(form, "ffmpeg", "FFmpeg Path", is_dir=False,
                       tooltip="Path to ffmpeg binary for combining audio/video streams (DRM content).\nLeave empty if ffmpeg is in your system PATH.")
        self._add_check(form, "verify_all_integrity", "Verify All Integrity", False,
                        tooltip=(
                            "Also run duration integrity checks on non-DRM video/audio "
                            "downloads (DRM merges are always checked).\n"
                            "Uses ffprobe to compare playback length to the API duration; "
                            "truncated/corrupt files are deleted and marked failed."
                        ))
        self._add_spin(
            form,
            "drm_duration_match_percent",
            "DRM Duration Match %",
            50,
            100,
            98,
            tooltip=(
                "After DRM remux (and when Verify All Integrity is on), require actual "
                "playback duration ≥ this percent of the API/MPD expected length.\n"
                "Default 98. Higher = stricter (fewer half-videos, more retries); "
                "lower = looser.\n"
                "Also allows up to 1.0s shortfall (API whole-second rounding on short clips), "
                "and rejects empty/tiny muxes (< 1 KB or ~0s duration).\n"
                "See Help → Configuration → Download for the full explanation."
            ),
        )
        # Download filter
        filter_group = QGroupBox("Download Filter (media types to include)")
        filter_layout = QHBoxLayout(filter_group)
        filter_layout.setContentsMargins(8, 4, 8, 4)
        for mt in ["Images", "Audios", "Videos", "Text"]:
            cb = QCheckBox(mt)
            cb.setChecked(True)
            filter_layout.addWidget(cb)
            self._widgets[f"filter_{mt.lower()}"] = cb
        form.addRow(filter_group)
        return scroll

    def _create_scripts_tab(self):
        scroll, form = self._create_scrollable_form()
        note = QLabel(
            "Optional external scripts. Leave paths empty to disable. "
            "Paths are stored under script_options in config.json."
        )
        note.setWordWrap(True)
        note.setProperty("subheading", True)
        form.addRow(note)
        self._add_path(
            form,
            "after_action_script",
            "After Action Script",
            is_dir=False,
            tooltip=(
                "Script that runs after an action for each model has completed.\n"
                "Leave empty to disable."
            ),
        )
        self._add_path(
            form,
            "post_script",
            "Post Script",
            is_dir=False,
            tooltip=(
                "Script that runs after all actions for all models have completed.\n"
                "Leave empty to disable."
            ),
        )
        self._add_path(
            form,
            "naming_script",
            "Naming Script",
            is_dir=False,
            tooltip=(
                "External script that can rewrite the final filename/path before download.\n"
                "Disabled by default (leave empty).\n"
                "For extension-only remapping, use Preferred file extensions below."
            ),
        )

        # Preferred extensions (filename {ext} only — no convert/remux)
        ext_group = QGroupBox("Preferred file extensions")
        ext_form = QFormLayout(ext_group)
        ext_form.setSpacing(10)
        ext_note = QLabel(
            "Optional. Each type is off by default. Check Images, Videos, and/or "
            "Audios to remap only that type's file extension ({ext}) — the rest of "
            "the filename is unchanged. Does not convert or remux the file."
        )
        ext_note.setWordWrap(True)
        ext_note.setProperty("subheading", True)
        ext_form.addRow(ext_note)
        _ext_tip = (
            "When checked, replace only the {ext} part of the saved filename\n"
            "with the preferred extension for this media type.\n"
            "Does not convert or remux the file — bytes stay as downloaded.\n"
            "Off by default (use the content-type / API extension)."
        )
        self._add_ext_override_row(
            ext_form,
            "override_image_extension",
            "image_extension",
            "Images",
            _IMAGE_EXT_CHOICES,
            default="jpg",
            tooltip=_ext_tip + "\nExamples: jpg, jpeg, png, webp",
        )
        self._add_ext_override_row(
            ext_form,
            "override_video_extension",
            "video_extension",
            "Videos",
            _VIDEO_EXT_CHOICES,
            default="mp4",
            tooltip=_ext_tip + "\nExamples: mp4, mov, m4v",
        )
        self._add_ext_override_row(
            ext_form,
            "override_audio_extension",
            "audio_extension",
            "Audios",
            _AUDIO_EXT_CHOICES,
            default="mp3",
            tooltip=_ext_tip + "\nExamples: mp3, m4a, wav",
        )
        form.addRow(ext_group)

        self._add_path(
            form,
            "after_download_script",
            "After Download Script",
            is_dir=False,
            tooltip=(
                "Script that executes after each individual media download is complete.\n"
                "Leave empty to disable."
            ),
        )
        self._add_path(
            form,
            "skip_download_script",
            "Skip Download Script",
            is_dir=False,
            tooltip=(
                "Script that decides whether to skip a file download (runs before download).\n"
                "Return \"False\" or empty stdout to skip.\n"
                "Leave empty to disable."
            ),
        )
        return scroll

    def _create_performance_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_spin(form, "download_sems", "Download Semaphores", 1, 15, 6,
                       tooltip="Number of concurrent downloads per thread (1-15).\nHigher = more parallel downloads but may hit rate limits.")
        self._add_spin(form, "download_limit", "Download Speed Limit (KB/s)", 0, 999999, 0,
                       "0 = unlimited")
        return scroll

    def _create_content_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_check(form, "block_ads", "Block Ads", False,
                        tooltip="Filter out known promotional/ad posts from downloads.")
        self._add_line(form, "file_size_max", "Max File Size", "0",
                       tooltip="Maximum file size to download.\ne.g., '500MB' or '2GB'. 0 = no limit.")
        self._add_line(form, "file_size_min", "Min File Size", "0",
                       tooltip="Minimum file size to download.\ne.g., '1MB'. 0 = no minimum.")
        self._add_spin(form, "length_max", "Max Length (seconds)", 0, 999999, 0,
                       tooltip="Maximum media duration in seconds to download.\n0 = no limit.")
        self._add_spin(form, "length_min", "Min Length (seconds)", 0, 999999, 0,
                       tooltip="Minimum media duration in seconds to download.\n0 = no minimum.")
        return scroll

    def _create_cdm_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_combo(
            form,
            "key-mode-default",
            "Key Mode",
            ["manual", "cdrm", "cdrm2", "keydb"],
            tooltip=(
                "Select how DRM keys are fetched.\n\n"
                "manual — local CDM files (default / recommended; most reliable)\n"
                "cdrm / cdrm2 / keydb — remote helpers (pssh + license URL only; "
                "no session cookies; may fail for OnlyFans DRM)\n\n"
                "Note: KeyDB mode is currently not working (no ETA)."
            ),
        )
        self._key_mode_warning = QLabel()
        self._key_mode_warning.setWordWrap(True)
        self._key_mode_warning.setTextFormat(Qt.TextFormat.RichText)
        self._key_mode_warning.setStyleSheet(
            f"color: {c('peach')}; background-color: {c('surface0')};"
            f" border: 1px solid {c('surface2')}; border-radius: 6px; padding: 8px;"
        )
        self._key_mode_warning.hide()
        form.addRow(self._key_mode_warning)
        combo = self._widgets.get("key-mode-default")
        if isinstance(combo, QComboBox):
            combo.currentTextChanged.connect(self._on_key_mode_changed)
            self._on_key_mode_changed(combo.currentText())
        self._add_path(form, "client-id", "Client ID File", is_dir=False,
                       tooltip="Path to Widevine CDM client_id.bin file.\nRequired for 'manual' key mode to decrypt DRM content.")
        self._add_path(form, "private-key", "Private Key File", is_dir=False,
                       tooltip="Path to Widevine CDM private_key.pem file.\nRequired for 'manual' key mode to decrypt DRM content.")
        return scroll

    def _on_key_mode_changed(self, mode: str):
        """Show inline warning when a remote key helper is selected."""
        try:
            from ofscraper.gui.utils.key_mode_warning import is_remote_key_mode

            if is_remote_key_mode(mode):
                self._key_mode_warning.setText(
                    f"<b>Note:</b> <code>{mode}</code> posts only pssh + license URL "
                    "to a third-party helper (session cookies stay local). "
                    "OnlyFans DRM often still fails without auth on the license "
                    "request — prefer <code>manual</code> with local CDM files "
                    "(see DRM Key Creation)."
                )
                self._key_mode_warning.show()
            else:
                self._key_mode_warning.hide()
        except Exception:
            try:
                self._key_mode_warning.hide()
            except Exception:
                pass

    def _create_advanced_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_combo(
            form,
            "dynamic-mode-default",
            "Dynamic Mode",
            ["datawhores", "digitalcriminals", "xagler", "rafa", "generic", "manual"],
            tooltip=(
                "Controls where OF request-signing rules are fetched from.\n"
                "If scraping breaks due to auth/signature issues, try switching this.\n\n"
                "Notes:\n"
                "- 'manual' uses Manual Dynamic Rules below (or OFSC_DYNAMIC_RULE_MANUAL).\n"
                "- 'generic' uses Dynamic Rules URL below (or OF_DYNAMIC_GENERIC_URL).\n"
                "- Unknown/legacy values fall back to the default rule source."
            ),
        )
        self._add_line(
            form,
            "api_path",
            "API Path",
            placeholder="/api2/v2",
            tooltip=(
                "OnlyFans API path prefix (default /api2/v2).\n"
                "Change only if OnlyFans renames the API path.\n"
                "Env override: OFSC_API_PATH.\n"
                "Restart or re-open the app after changing if needed."
            ),
        )
        self._add_manual_rules_field(form)
        self._add_line(
            form,
            "dynamic_rules_url",
            "Dynamic Rules URL",
            placeholder="https://example.com/rules.json",
            tooltip=(
                "Remote signing-rules JSON URL used when Dynamic Mode is 'generic'.\n"
                "Env overrides: OF_DYNAMIC_GENERIC_URL or OFSC_DYNAMIC_GENERIC_URL."
            ),
        )
        self._add_endpoint_overrides_field(form)
        self._add_line(
            form,
            "media_host_suffixes",
            "Media Host Suffixes",
            placeholder="examplecdn.net,othercdn.com",
            tooltip=(
                "Extra allowed media/DRM CDN host suffixes (comma-separated).\n"
                "Built-in: onlyfans.com, cloudfront.net.\n"
                "Add hosts here if OF moves media to a new CDN and downloads are blocked.\n"
                "Env: OFSC_MEDIA_HOST_SUFFIXES (merged with this field)."
            ),
        )
        self._add_combo(
            form,
            "cache-mode",
            "Cache Mode",
            ["sqlite", "json", "disabled"],
            tooltip=(
                "Storage backend for OF-Scraper's local cache.\n"
                "- sqlite: faster + more robust for larger caches\n"
                "- json: simpler, sometimes slower\n"
                "- disabled: attempt to disable caching (may reduce performance)\n\n"
                "Tip: For a one-off rescrape, use the GUI 'ignore cache' options."
            ),
        )
        self._add_check(
            form,
            "downloadbars",
            "Download Bars",
            True,
            tooltip=(
                "Show per-download progress bars in console output.\n"
                "May reduce performance at higher thread counts."
            ),
        )
        self._add_check(
            form,
            "sanitize_text",
            "Sanitize Text",
            False,
            tooltip=(
                "Cleans post/message text before inserting into the database.\n"
                "Helps avoid DB issues caused by unusual characters."
            ),
        )
        self._add_combo(
            form,
            "remove_hash_match",
            "Hash / duplicate handling",
            [
                "Don't hash files (fastest)",
                "Hash files only (no deletion)",
                "Hash + remove duplicates (deletes extra copies)",
            ],
            tooltip=(
                "Controls optional file hashing and duplicate removal.\n"
                "- 'Hash files only' stores hashes/metadata but does not delete files.\n"
                "- 'Hash + remove duplicates' can delete extra copies of identical files.\n\n"
                "Warning: Deleting is permanent—use with care."
            ),
        )
        self._add_check(
            form,
            "incremental_downloads",
            "Incremental Downloads",
            False,
            tooltip=(
                "Speeds up future scrapes by automatically setting an 'after' cutoff\n"
                "based on previous scans (DB/cache). Disabling forces full-history scans."
            ),
        )
        self._add_path(
            form,
            "temp_dir",
            "Temp Directory",
            is_dir=True,
            tooltip="Optional directory for temporary download files. Leave empty for default.",
        )
        self._add_check(
            form,
            "infinite_loop_action_mode",
            "Infinite Loop (Action Mode)",
            False,
            tooltip=(
                "When enabled, Action Mode can loop and re-run actions until you choose to stop.\n"
                "Mostly affects CLI 'action mode' flows."
            ),
        )
        self._add_line(
            form,
            "default_user_list",
            "Default User List",
            "main",
            tooltip=(
                "Comma-separated list(s) of user lists used when retrieving models.\n"
                "Built-ins: main / active / expired (also supports ofscraper.main, etc.)"
            ),
        )
        self._add_line(
            form,
            "default_black_list",
            "Default Black List",
            "",
            tooltip="Comma-separated list(s) of user lists to exclude by default.",
        )
        self._add_check(
            form,
            "skip_unavailable_content",
            "Skip Unavailable Content",
            False,
            tooltip=(
                "Skip posts/media that are unavailable (e.g. expired or restricted).\n"
                "When enabled, unavailable items are silently ignored instead of logged as errors."
            ),
        )
        self._add_combo(
            form,
            "ssl_verify",
            "SSL Verify",
            ["custom", "true", "false"],
            tooltip=(
                "Controls SSL certificate verification for API requests.\n"
                "- custom: use ofscraper's built-in certificate bundle\n"
                "- true: use system certificates (strict)\n"
                "- false: disable SSL verification (not recommended)"
            ),
        )
        self._add_line(
            form,
            "env_files",
            "Env Files",
            "",
            tooltip=(
                "Comma-separated list of .env file paths to load before running.\n"
                "Leave empty to disable."
            ),
        )
        return scroll

    def _create_response_tab(self):
        scroll, form = self._create_scrollable_form()
        resp_types = [
            "timeline", "message", "archived", "paid",
            "stories", "highlights", "profile", "pinned", "streams"
        ]
        for rt in resp_types:
            self._add_line(form, f"resp_{rt}", rt.capitalize(), rt,
                           tooltip=f"Custom label for '{rt}' content in the {{responsetype}} filename placeholder.\nChange this to rename the folder/label used for {rt} content.")
        return scroll

    # ---- Load / Save ----

    def _load_config(self):
        """Load current config values into the widgets.

        Always re-reads config.json from disk (both config caches cleared) so
        Reload picks up external edits such as CDM key paths pasted into the file.
        """
        try:
            from ofscraper.utils.config.config import read_config, reset_config_cache
            reset_config_cache()
            self._config = read_config(update=False) or {}
            # Drop stale privacy-mode cached paths so Reload does not restore
            # empty values after the user edited config.json outside the GUI.
            self._privacy_actual = {}

            # Flatten nested config into widget values
            config = self._config
            flat = {}

            # Top-level
            for k in ["main_profile", "metadata", "discord"]:
                flat[k] = config.get(k, "")

            # Nested sections
            for section_key, fields in [
                ("file_options", ["save_location", "dir_format", "file_format",
                                  "textlength", "space_replacer", "date",
                                  "text_type_default", "truncation_default",
                                  "override_image_extension",
                                  "override_video_extension",
                                  "override_audio_extension",
                                  "image_extension",
                                  "video_extension", "audio_extension"]),
                ("download_options", ["system_free_min", "auto_resume", "max_post_count", "verify_all_integrity"]),
                ("binary_options", ["ffmpeg"]),
                ("script_options", list(_SCRIPT_OPTION_KEYS)),
                ("performance_options", ["download_sems", "download_limit"]),
                ("content_filter_options", ["block_ads", "file_size_max", "file_size_min",
                                            "length_max", "length_min"]),
                ("cdm_options", ["key-mode-default", "client-id", "private-key"]),
                ("advanced_options", [
                    "dynamic-mode-default", "api_path", "dynamic_rules_manual",
                    "dynamic_rules_url", "api_endpoint_overrides",
                    "media_host_suffixes", "cache-mode",
                    "downloadbars", "sanitize_text", "remove_hash_match",
                    "incremental_downloads", "temp_dir", "infinite_loop_action_mode",
                    "default_user_list", "default_black_list",
                    "skip_unavailable_content", "ssl_verify", "env_files",
                ]),
            ]:
                section = config.get(section_key, {})
                if isinstance(section, dict):
                    for f in fields:
                        flat[f] = section.get(f, "")

            # Legacy global override_file_extensions → enable all three types
            fo = config.get("file_options") if isinstance(config.get("file_options"), dict) else {}
            has_per_type = any(
                k in fo
                for k in (
                    "override_image_extension",
                    "override_video_extension",
                    "override_audio_extension",
                )
            )
            if fo.get("override_file_extensions") and not has_per_type:
                flat["override_image_extension"] = True
                flat["override_video_extension"] = True
                flat["override_audio_extension"] = True

            # Legacy typo key scripts_options → fill any missing script fields
            legacy_scripts = config.get("scripts_options")
            if isinstance(legacy_scripts, dict):
                for f in _SCRIPT_OPTION_KEYS:
                    if not flat.get(f) and legacy_scripts.get(f):
                        flat[f] = legacy_scripts.get(f)

            # Response type
            resp = config.get("responsetype", {})
            if isinstance(resp, dict):
                for rt in resp:
                    flat[f"resp_{rt}"] = resp.get(rt, rt)

            # Apply to widgets
            for key, widget in self._widgets.items():
                val = flat.get(key, "")
                if isinstance(widget, QLineEdit):
                    # JSON fields: serialize dicts/lists as JSON for display
                    if (key == "custom_values" or key.startswith("ow_")) and isinstance(val, (dict, list)):
                        widget.setText(json.dumps(val) if val else "")
                    else:
                        text = str(val).strip() if val else ""
                        if key in _FS_PATH_WIDGET_KEYS and text:
                            text = _display_fs_path(text)
                        widget.setText(text)
                elif isinstance(widget, QTextEdit):
                    if key == "dynamic_rules_manual":
                        try:
                            from ofscraper.utils.dynamic_rules_manual import (
                                normalize_manual_rules_json,
                            )

                            widget.setPlainText(normalize_manual_rules_json(val))
                        except Exception:
                            if isinstance(val, (dict, list)):
                                widget.setPlainText(json.dumps(val, indent=2) if val else "")
                            else:
                                widget.setPlainText(str(val).strip() if val else "")
                    elif key == "api_endpoint_overrides":
                        try:
                            from ofscraper.utils.api_endpoint_overrides import (
                                normalize_endpoint_overrides_json,
                            )

                            widget.setPlainText(normalize_endpoint_overrides_json(val))
                        except Exception:
                            if isinstance(val, (dict, list)):
                                widget.setPlainText(
                                    json.dumps(val, indent=2) if val else "{}"
                                )
                            else:
                                widget.setPlainText(str(val).strip() if val else "{}")
                    elif isinstance(val, (dict, list)):
                        widget.setPlainText(json.dumps(val, indent=2) if val else "")
                    else:
                        widget.setPlainText(str(val).strip() if val else "")
                elif isinstance(widget, QSpinBox):
                    try:
                        widget.setValue(int(val) if val else 0)
                    except (ValueError, TypeError):
                        widget.setValue(0)
                elif isinstance(widget, QCheckBox):
                    # Some legacy configs stored strings; normalize a few known cases.
                    if key == "infinite_loop_action_mode" and isinstance(val, str):
                        v = val.strip().lower()
                        if v in {"disabled", "false", "0", "no", "off", ""}:
                            widget.setChecked(False)
                        elif v in {"after", "true", "1", "yes", "on"}:
                            widget.setChecked(True)
                        else:
                            widget.setChecked(bool(val))
                    else:
                        widget.setChecked(bool(val))
                elif isinstance(widget, QComboBox):
                    idx = widget.findText(str(val))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        widget.setCurrentText(str(val) if val else "")

            # Extension override: enable each combo only when its type checkbox is on
            try:
                for check_key, combo_key, default in (
                    ("override_image_extension", "image_extension", "jpg"),
                    ("override_video_extension", "video_extension", "mp4"),
                    ("override_audio_extension", "audio_extension", "mp3"),
                ):
                    cb = self._widgets.get(check_key)
                    combo = self._widgets.get(combo_key)
                    if isinstance(cb, QCheckBox) and combo is not None:
                        self._on_ext_override_row_toggled(combo_key, cb.isChecked())
                    if isinstance(combo, QComboBox) and not (combo.currentText() or "").strip():
                        idx = combo.findText(default)
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                        else:
                            combo.setCurrentText(default)
            except Exception:
                pass

            # DRM duration match is stored as 0–1 ratio; GUI spin is percent.
            w = self._widgets.get("drm_duration_match_percent")
            if w is not None:
                dl = config.get("download_options") if isinstance(config.get("download_options"), dict) else {}
                raw = (dl or {}).get("drm_duration_match_threshold", config.get("drm_duration_match_threshold"))
                try:
                    ratio = float(raw) if raw is not None else 0.98
                    if ratio > 1.0 and ratio <= 100:
                        pct = int(round(ratio))
                    else:
                        pct = int(round(max(0.0, min(1.0, ratio)) * 100))
                except (TypeError, ValueError):
                    pct = 98
                w.setValue(max(50, min(100, pct)))

            # Download filter checkboxes
            try:
                dl_filter = config.get("download_options", {}).get("filter", None)
                if dl_filter is None:
                    # Default: all checked
                    for mt in ["images", "audios", "videos", "text"]:
                        w = self._widgets.get(f"filter_{mt}")
                        if w:
                            w.setChecked(True)
                else:
                    active = {s.lower() for s in dl_filter}
                    for mt in ["images", "audios", "videos", "text"]:
                        w = self._widgets.get(f"filter_{mt}")
                        if w:
                            w.setChecked(mt in active)
            except Exception:
                pass

            # Normalize remove_hash_match tri-state into the UI choices.
            try:
                w = self._widgets.get("remove_hash_match")
                if isinstance(w, QComboBox):
                    val = flat.get("remove_hash_match", "")
                    if val is None:
                        choice = "Don't hash files (fastest)"
                    elif bool(val) is True:
                        choice = "Hash + remove duplicates (deletes extra copies)"
                    else:
                        choice = "Hash files only (no deletion)"
                    idx = w.findText(choice)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
            except Exception:
                pass

            try:
                from ofscraper.gui.utils.privacy_mode import PRIVACY_CONFIG_KEYS

                for key in PRIVACY_CONFIG_KEYS:
                    w = self._widgets.get(key)
                    if isinstance(w, QLineEdit):
                        self._privacy_actual[key] = w.text()
                self._apply_privacy_mask()
            except Exception:
                pass

            app_signals.status_message.emit("Configuration loaded")
        except Exception as e:
            log.error(f"Failed to load config: {e}")
            app_signals.status_message.emit(f"Failed to load config: {e}")

    def _save_config(self):
        """Collect widget values and save to config.json."""
        try:
            # Warn before persisting a remote key mode that may exfiltrate cookies.
            try:
                from ofscraper.gui.utils.key_mode_warning import (
                    confirm_remote_key_mode,
                    is_remote_key_mode,
                    reset_session_skip,
                )

                key_w = self._widgets.get("key-mode-default")
                if isinstance(key_w, QComboBox) and is_remote_key_mode(key_w.currentText()):
                    if not confirm_remote_key_mode(
                        self,
                        key_w.currentText(),
                        context="config",
                        allow_session_skip=False,
                    ):
                        app_signals.status_message.emit(
                            "Configuration not saved — remote key mode declined"
                        )
                        return
                    # Re-prompt on next scrape after explicitly saving remote mode.
                    reset_session_skip()
            except Exception as e:
                log.debug(f"Remote key-mode save check skipped: {e}")

            config = dict(self._config) if self._config else {}

            # Helper to set nested dict values
            def set_nested(d, section, key, val):
                if section not in d:
                    d[section] = {}
                d[section][key] = val

            # Top-level
            for k in ["main_profile", "metadata", "discord"]:
                w = self._widgets.get(k)
                if w:
                    val = w.text()
                    if k == "discord":
                        try:
                            from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                            val = resolve_saved_value(val, self._privacy_actual.get(k))
                        except Exception:
                            pass
                    config[k] = val

            # File options
            for k in ["save_location", "dir_format", "file_format",
                       "space_replacer", "date"]:
                w = self._widgets.get(k)
                if w:
                    val = w.text()
                    if k == "save_location":
                        try:
                            from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                            val = resolve_saved_value(val, self._privacy_actual.get(k))
                        except Exception:
                            pass
                        val = _display_fs_path(val)
                    set_nested(config, "file_options", k, val)

            w = self._widgets.get("textlength")
            if w:
                set_nested(config, "file_options", "textlength", w.value())
            w = self._widgets.get("text_type_default")
            if w:
                set_nested(config, "file_options", "text_type_default", w.currentText())
            w = self._widgets.get("truncation_default")
            if w:
                set_nested(config, "file_options", "truncation_default", w.isChecked())

            for check_key in (
                "override_image_extension",
                "override_video_extension",
                "override_audio_extension",
            ):
                w = self._widgets.get(check_key)
                if w:
                    set_nested(config, "file_options", check_key, w.isChecked())
            for k, default in (
                ("image_extension", "jpg"),
                ("video_extension", "mp4"),
                ("audio_extension", "mp3"),
            ):
                w = self._widgets.get(k)
                if w:
                    raw = w.currentText() if isinstance(w, QComboBox) else w.text()
                    set_nested(
                        config, "file_options", k, _sanitize_ext_text(raw, default)
                    )
            # Drop legacy all-or-nothing flag once per-type keys are written
            fo = config.get("file_options")
            if isinstance(fo, dict) and "override_file_extensions" in fo:
                try:
                    del fo["override_file_extensions"]
                except Exception:
                    pass

            # Download
            w = self._widgets.get("system_free_min")
            if w:
                set_nested(config, "download_options", "system_free_min", w.value())
            w = self._widgets.get("auto_resume")
            if w:
                set_nested(config, "download_options", "auto_resume", w.isChecked())
            w = self._widgets.get("max_post_count")
            if w:
                set_nested(config, "download_options", "max_post_count", w.value())
            w = self._widgets.get("verify_all_integrity")
            if w:
                set_nested(config, "download_options", "verify_all_integrity", w.isChecked())
            w = self._widgets.get("drm_duration_match_percent")
            if w:
                set_nested(
                    config,
                    "download_options",
                    "drm_duration_match_threshold",
                    round(float(w.value()) / 100.0, 2),
                )

            # Download filter
            active_filter = []
            for mt in ["Images", "Audios", "Videos", "Text"]:
                w = self._widgets.get(f"filter_{mt.lower()}")
                if w and w.isChecked():
                    active_filter.append(mt)
            set_nested(config, "download_options", "filter", active_filter)

            # Binary
            w = self._widgets.get("ffmpeg")
            if w:
                val = w.text().strip()
                try:
                    from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                    val = resolve_saved_value(val, self._privacy_actual.get("ffmpeg"))
                except Exception:
                    pass
                set_nested(config, "binary_options", "ffmpeg", _display_fs_path(val))

            # Scripts (canonical key: script_options; migrate legacy scripts_options)
            legacy_scripts = config.get("scripts_options")
            if not isinstance(legacy_scripts, dict):
                legacy_scripts = {}
            for k in _SCRIPT_OPTION_KEYS:
                w = self._widgets.get(k)
                val = ""
                if w:
                    val = w.text().strip()
                    try:
                        from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                        val = resolve_saved_value(val, self._privacy_actual.get(k))
                    except Exception:
                        pass
                    val = _display_fs_path(val) if val else ""
                if not val and legacy_scripts.get(k):
                    val = str(legacy_scripts.get(k) or "").strip()
                # Empty path → null so scripts stay disabled by default
                set_nested(config, "script_options", k, val if val else None)
            if "scripts_options" in config:
                try:
                    del config["scripts_options"]
                except Exception:
                    pass

            # Performance
            for k in ["download_sems", "download_limit"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "performance_options", k, w.value())

            # Content
            w = self._widgets.get("block_ads")
            if w:
                set_nested(config, "content_filter_options", "block_ads", w.isChecked())
            for k in ["file_size_max", "file_size_min"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "content_filter_options", k, w.text())
            for k in ["length_max", "length_min"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "content_filter_options", k, w.value())

            # CDM
            for k in ["key-mode-default", "client-id", "private-key"]:
                w = self._widgets.get(k)
                if w:
                    val = w.currentText() if isinstance(w, QComboBox) else w.text()
                    if k in ("client-id", "private-key") and isinstance(w, QLineEdit):
                        try:
                            from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                            val = resolve_saved_value(val, self._privacy_actual.get(k))
                        except Exception:
                            pass
                        val = _display_fs_path(val)
                    set_nested(config, "cdm_options", k, val)

            # Advanced
            for k in ["dynamic-mode-default", "cache-mode", "ssl_verify"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "advanced_options", k, w.currentText())
            # Tri-state-ish handling for remove_hash_match (None/False/True)
            w = self._widgets.get("remove_hash_match")
            if w and isinstance(w, QComboBox):
                txt = w.currentText()
                if txt.startswith("Don't hash"):
                    set_nested(config, "advanced_options", "remove_hash_match", None)
                elif txt.startswith("Hash + remove"):
                    set_nested(config, "advanced_options", "remove_hash_match", True)
                else:
                    set_nested(config, "advanced_options", "remove_hash_match", False)

            for k in [
                "downloadbars",
                "sanitize_text",
                "incremental_downloads",
                "infinite_loop_action_mode",
                "skip_unavailable_content",
            ]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "advanced_options", k, w.isChecked())
            for k in [
                "api_path",
                "dynamic_rules_url",
                "media_host_suffixes",
                "temp_dir",
                "default_user_list",
                "default_black_list",
            ]:
                w = self._widgets.get(k)
                if w:
                    val = w.text()
                    if k == "api_path":
                        from ofscraper.utils.api_path import normalize_api_path

                        val = normalize_api_path(val)
                    elif k == "dynamic_rules_url":
                        from ofscraper.utils.dynamic_rules_url import (
                            normalize_dynamic_rules_url,
                            validate_dynamic_rules_url,
                        )

                        val = normalize_dynamic_rules_url(val)
                        err = validate_dynamic_rules_url(val)
                        if val and err:
                            QMessageBox.warning(
                                self, "Invalid Dynamic Rules URL", err
                            )
                            return
                    elif k == "media_host_suffixes":
                        from ofscraper.utils.media_host_suffixes import (
                            normalize_media_host_suffixes,
                            validate_media_host_suffixes,
                        )

                        err = validate_media_host_suffixes(val)
                        if err:
                            QMessageBox.warning(
                                self, "Invalid Media Host Suffixes", err
                            )
                            return
                        val = normalize_media_host_suffixes(val)
                    elif k == "temp_dir":
                        try:
                            from ofscraper.gui.utils.privacy_mode import resolve_saved_value

                            val = resolve_saved_value(val, self._privacy_actual.get(k))
                        except Exception:
                            pass
                        val = _display_fs_path(val)
                    set_nested(config, "advanced_options", k, val)

            # Manual dynamic rules JSON (Dynamic Mode = manual)
            w = self._widgets.get("dynamic_rules_manual")
            mode_w = self._widgets.get("dynamic-mode-default")
            mode_txt = mode_w.currentText() if isinstance(mode_w, QComboBox) else ""
            if isinstance(w, QTextEdit):
                raw_rules = w.toPlainText().strip()
                if raw_rules:
                    from ofscraper.utils.dynamic_rules_manual import (
                        normalize_manual_rules_json,
                        parse_manual_rules,
                        validate_manual_rules,
                    )

                    parsed = parse_manual_rules(raw_rules)
                    if parsed is None:
                        if mode_txt == "manual":
                            QMessageBox.warning(
                                self,
                                "Invalid Manual Rules",
                                "Manual Dynamic Rules must be valid JSON when "
                                "Dynamic Mode is 'manual'.",
                            )
                            return
                        set_nested(config, "advanced_options", "dynamic_rules_manual", raw_rules)
                    else:
                        err = validate_manual_rules(parsed)
                        if err and mode_txt == "manual":
                            QMessageBox.warning(self, "Invalid Manual Rules", err)
                            return
                        pretty = normalize_manual_rules_json(parsed)
                        w.setPlainText(pretty)
                        set_nested(
                            config, "advanced_options", "dynamic_rules_manual", pretty
                        )
                else:
                    set_nested(config, "advanced_options", "dynamic_rules_manual", "")

            # API endpoint overrides JSON object
            w = self._widgets.get("api_endpoint_overrides")
            if isinstance(w, QTextEdit):
                raw_ov = w.toPlainText().strip() or "{}"
                from ofscraper.utils.api_endpoint_overrides import (
                    normalize_endpoint_overrides_dict,
                    normalize_endpoint_overrides_json,
                    parse_endpoint_overrides,
                    validate_endpoint_overrides,
                )

                parsed = parse_endpoint_overrides(raw_ov)
                if parsed is None:
                    QMessageBox.warning(
                        self,
                        "Invalid Endpoint Overrides",
                        "API Endpoint Overrides must be a JSON object.",
                    )
                    return
                err = validate_endpoint_overrides(parsed)
                if err:
                    QMessageBox.warning(self, "Invalid Endpoint Overrides", err)
                    return
                cleaned = normalize_endpoint_overrides_dict(parsed)
                pretty = normalize_endpoint_overrides_json(cleaned)
                w.setPlainText(pretty)
                set_nested(
                    config, "advanced_options", "api_endpoint_overrides", cleaned
                )

            # env_files: comma-separated string → list
            w = self._widgets.get("env_files")
            if w:
                raw = w.text().strip()
                env_list = [
                    _display_fs_path(s.strip()) for s in raw.split(",") if s.strip()
                ] if raw else []
                set_nested(config, "advanced_options", "env_files", env_list)

            # Response type
            resp = {}
            resp_types = [
                "timeline", "message", "archived", "paid",
                "stories", "highlights", "profile", "pinned", "streams"
            ]
            for rt in resp_types:
                w = self._widgets.get(f"resp_{rt}")
                if w:
                    resp[rt] = w.text() or rt
            config["responsetype"] = resp

            # Validate before write (uniqueness tokens, path confinement, etc.)
            try:
                from ofscraper.gui.utils.config_validation import (
                    show_config_validation_dialog,
                    validate_config,
                )

                _vr = validate_config(config)
                if not show_config_validation_dialog(self, _vr, context="save"):
                    return
            except Exception as e:
                log.debug(f"Config validation skipped: {e}")

            # Write config
            from ofscraper.utils.config.file import write_config
            write_config(config)

            # Invalidate the in-memory auth cache so a changed dynamic-mode-default
            # takes effect immediately without requiring a GUI restart.
            try:
                from ofscraper.utils.auth.request import invalidate_auth_cache
                invalidate_auth_cache()
            except Exception:
                pass
            try:
                from ofscraper.utils.of_env.of_env import (
                    clear_api_endpoint_overrides_cache,
                    clear_api_path_cache,
                )

                clear_api_path_cache()
                clear_api_endpoint_overrides_cache()
            except Exception:
                pass

            app_signals.status_message.emit("Configuration saved")
            try:
                app_signals.config_updated.emit()
            except Exception:
                pass
            QMessageBox.information(self, "Saved", "Configuration saved successfully.")
        except Exception as e:
            log.error(f"Failed to save config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")
