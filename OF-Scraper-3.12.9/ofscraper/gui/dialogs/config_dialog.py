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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton
import ofscraper.utils.paths.common as common_paths

log = logging.getLogger("shared")

def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help for this config section")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(
        """
        QToolButton {
            border: 1px solid #45475a;
            border-radius: 9px;
            background-color: #313244;
            color: #cdd6f4;
            font-weight: bold;
            margin-right: 4px;
        }
        QToolButton:hover {
            border-color: #89b4fa;
            background-color: #45475a;
        }
        """
    )
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
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header = QLabel("Configuration")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
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
        _add_tab(self._create_performance_tab(), "Performance")
        _add_tab(self._create_content_tab(), "Content")
        _add_tab(self._create_cdm_tab(), "CDM")
        _add_tab(self._create_advanced_tab(), "Advanced")
        _add_tab(self._create_response_tab(), "Response Type")
        _add_tab(self._create_overwrites_tab(), "Overwrites")
        layout.addWidget(self.tabs)

        # Add a (?) help button to each config tab.
        try:
            tab_help = {
                "General": "config-general",
                "File Options": "config-file-options",
                "Download": "config-download",
                "Performance": "config-performance",
                "Content": "config-content",
                "CDM": "config-cdm",
                "Advanced": "config-advanced",
                "Response Type": "config-response-type",
                "Overwrites": "config-overwrites",
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
            line_edit.setText(path)

    # ---- Tab Builders ----

    def _create_general_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_line(form, "main_profile", "Main Profile", "main_profile")
        self._add_line(form, "metadata", "Metadata Path", "{configpath}/{profile}/.data/{model_id}")
        self._add_line(form, "discord", "Discord Webhook URL", "https://discord.com/api/webhooks/...")
        return scroll

    def _create_file_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_path(form, "save_location", "Save Location", is_dir=True)
        self._add_line(form, "dir_format", "Directory Format",
                       "{model_username}/{responsetype}/{mediatype}/")
        self._add_line(form, "file_format", "File Format", "{filename}.{ext}")
        self._add_spin(form, "textlength", "Text Length", 0, 999, 0)
        self._add_line(form, "space_replacer", "Space Replacer", " ")
        self._add_line(form, "date", "Date Format", "YYYY-MM-DD")
        self._add_combo(form, "text_type_default", "Text Type",
                        ["letter", "word"])
        self._add_check(form, "truncation_default", "Enable Truncation", True)
        return scroll

    def _create_download_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_spin(form, "system_free_min", "Min Free Space (MB)", 0, 999999, 0,
                       "Minimum free disk space required before downloads")
        self._add_check(form, "auto_resume", "Auto Resume", True)
        self._add_spin(form, "max_post_count", "Max Post Count", 0, 999999, 0,
                       "0 = unlimited")
        # Binary options
        self._add_path(form, "ffmpeg", "FFmpeg Path", is_dir=False)
        # Script options
        self._add_line(form, "post_download_script", "Post-Download Script", "")
        self._add_line(form, "post_script", "Post Script", "")
        return scroll

    def _create_performance_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_spin(form, "thread_count", "Thread Count", 1, 3, 2)
        self._add_spin(form, "download_sems", "Download Semaphores", 1, 15, 6)
        self._add_spin(form, "download_limit", "Download Speed Limit (KB/s)", 0, 999999, 0,
                       "0 = unlimited")
        return scroll

    def _create_content_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_check(form, "block_ads", "Block Ads", False)
        self._add_line(form, "file_size_max", "Max File Size", "0",
                       "e.g., '500MB' or '2GB', 0 = no limit")
        self._add_line(form, "file_size_min", "Min File Size", "0")
        self._add_spin(form, "length_max", "Max Length (seconds)", 0, 999999, 0)
        self._add_spin(form, "length_min", "Min Length (seconds)", 0, 999999, 0)
        return scroll

    def _create_cdm_tab(self):
        scroll, form = self._create_scrollable_form()
        self._add_combo(
            form,
            "key-mode-default",
            "Key Mode",
            ["cdrm", "cdrm2", "keydb", "manual"],
            tooltip=(
                "Select how DRM keys are fetched.\n\n"
                "Note: KeyDB mode is currently not working (no ETA)."
            ),
        )
        self._add_line(
            form,
            "keydb_api",
            "KeyDB API Key",
            "",
            tooltip="KeyDB is currently not working (no ETA). This setting is currently ignored.",
        )
        self._add_path(form, "client-id", "Client ID File", is_dir=False)
        self._add_path(form, "private-key", "Private Key File", is_dir=False)
        return scroll

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
                "- 'manual' requires an embedded dynamic rule (power-user).\n"
                "- Unknown/legacy values fall back to the default rule source."
            ),
        )
        self._add_combo(
            form,
            "backend",
            "Backend",
            ["aio", "httpx"],
            tooltip=(
                "HTTP client used for network requests.\n"
                "- aio: aiohttp (async)\n"
                "- httpx: httpx (async + sync in some codepaths)\n\n"
                "If one backend has issues on your network, try the other."
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
            "code-execution",
            "Code Execution",
            False,
            tooltip=(
                "Allows evaluating certain placeholder 'custom values' using eval().\n"
                "This is a security risk if you paste untrusted content."
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
            "appendlog",
            "Append Log",
            False,
            tooltip=(
                "Append logs into a single daily log file (instead of per-run log files)."
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
            "enable_auto_after",
            "Enable Auto After",
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
        self._add_line(
            form,
            "custom_values",
            "Custom Values",
            '{"key": "value"}',
            tooltip=(
                "JSON object of custom placeholder values for file naming templates.\n"
                'Example: {"studio": "MyStudio", "tag": "favorites"}\n\n'
                "These values can be referenced in path templates.\n"
                "Leave empty or set to null to disable.\n"
                "Requires 'Code Execution' enabled for dynamic expressions."
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
            self._add_line(form, f"resp_{rt}", rt.capitalize(), rt)
        return scroll

    def _create_overwrites_tab(self):
        scroll, form = self._create_scrollable_form()
        media_types = ["audios", "videos", "images", "text"]
        for mt in media_types:
            self._add_line(
                form,
                f"ow_{mt}",
                mt.capitalize(),
                '{"dir_format": "", "file_format": "", ...}',
                tooltip=(
                    f"JSON object of per-media-type overrides for '{mt}'.\n"
                    "Supported keys: dir_format, file_format, textlength, date,\n"
                    "file_size_max, file_size_min, space_replacer, text_type_default,\n"
                    "temp_dir, truncation_default, block_ads.\n\n"
                    "Leave empty or {} for no overrides."
                ),
            )
        return scroll

    # ---- Load / Save ----

    def _load_config(self):
        """Load current config values into the widgets."""
        try:
            from ofscraper.utils.config.config import read_config
            self._config = read_config(update=False) or {}

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
                                  "text_type_default", "truncation_default"]),
                ("download_options", ["system_free_min", "auto_resume", "max_post_count"]),
                ("binary_options", ["ffmpeg"]),
                ("scripts_options", ["post_download_script", "post_script"]),
                ("performance_options", ["thread_count", "download_sems", "download_limit"]),
                ("content_filter_options", ["block_ads", "file_size_max", "file_size_min",
                                            "length_max", "length_min"]),
                ("cdm_options", ["key-mode-default", "keydb_api", "client-id", "private-key"]),
                ("advanced_options", [
                    "dynamic-mode-default", "backend", "cache-mode",
                    "code-execution", "downloadbars", "appendlog",
                    "sanitize_text", "remove_hash_match", "enable_auto_after",
                    "temp_dir", "infinite_loop_action_mode",
                    "default_user_list", "default_black_list",
                    "custom_values"
                ]),
            ]:
                section = config.get(section_key, {})
                if isinstance(section, dict):
                    for f in fields:
                        flat[f] = section.get(f, "")

            # Response type
            resp = config.get("responsetype", {})
            if isinstance(resp, dict):
                for rt in resp:
                    flat[f"resp_{rt}"] = resp.get(rt, rt)

            # Overwrites
            ow = config.get("overwrites", {})
            if isinstance(ow, dict):
                for mt in ["audios", "videos", "images", "text"]:
                    flat[f"ow_{mt}"] = ow.get(mt, {})

            # Apply to widgets
            for key, widget in self._widgets.items():
                val = flat.get(key, "")
                if isinstance(widget, QLineEdit):
                    # JSON fields: serialize dicts/lists as JSON for display
                    if (key == "custom_values" or key.startswith("ow_")) and isinstance(val, (dict, list)):
                        widget.setText(json.dumps(val) if val else "")
                    else:
                        widget.setText(str(val) if val else "")
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

            app_signals.status_message.emit("Configuration loaded")
        except Exception as e:
            log.error(f"Failed to load config: {e}")
            app_signals.status_message.emit(f"Failed to load config: {e}")

    def _save_config(self):
        """Collect widget values and save to config.json."""
        try:
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
                    config[k] = w.text()

            # File options
            for k in ["save_location", "dir_format", "file_format",
                       "space_replacer", "date"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "file_options", k, w.text())

            w = self._widgets.get("textlength")
            if w:
                set_nested(config, "file_options", "textlength", w.value())
            w = self._widgets.get("text_type_default")
            if w:
                set_nested(config, "file_options", "text_type_default", w.currentText())
            w = self._widgets.get("truncation_default")
            if w:
                set_nested(config, "file_options", "truncation_default", w.isChecked())

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

            # Binary
            w = self._widgets.get("ffmpeg")
            if w:
                set_nested(config, "binary_options", "ffmpeg", w.text())

            # Scripts
            for k in ["post_download_script", "post_script"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "scripts_options", k, w.text())

            # Performance
            for k in ["thread_count", "download_sems", "download_limit"]:
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
            for k in ["key-mode-default", "keydb_api", "client-id", "private-key"]:
                w = self._widgets.get(k)
                if w:
                    val = w.currentText() if isinstance(w, QComboBox) else w.text()
                    set_nested(config, "cdm_options", k, val)

            # Advanced
            for k in ["dynamic-mode-default", "backend", "cache-mode"]:
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
                "code-execution",
                "downloadbars",
                "appendlog",
                "sanitize_text",
                "enable_auto_after",
                "infinite_loop_action_mode",
            ]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "advanced_options", k, w.isChecked())
            for k in ["temp_dir", "default_user_list", "default_black_list"]:
                w = self._widgets.get(k)
                if w:
                    set_nested(config, "advanced_options", k, w.text())

            # custom_values: parse JSON string back to dict/null
            w = self._widgets.get("custom_values")
            if w:
                raw = w.text().strip()
                if raw:
                    try:
                        set_nested(config, "advanced_options", "custom_values", json.loads(raw))
                    except json.JSONDecodeError:
                        QMessageBox.warning(
                            self, "Invalid JSON",
                            "Custom Values must be valid JSON (e.g. {\"key\": \"value\"}).\n"
                            "The field was saved as-is (string)."
                        )
                        set_nested(config, "advanced_options", "custom_values", raw)
                else:
                    set_nested(config, "advanced_options", "custom_values", None)

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

            # Overwrites
            ow = config.get("overwrites", {})
            if not isinstance(ow, dict):
                ow = {}
            for mt in ["audios", "videos", "images", "text"]:
                w = self._widgets.get(f"ow_{mt}")
                if w:
                    raw = w.text().strip()
                    if raw:
                        try:
                            ow[mt] = json.loads(raw)
                        except json.JSONDecodeError:
                            QMessageBox.warning(
                                self, "Invalid JSON",
                                f"Overwrites '{mt}' must be valid JSON.\n"
                                "The field was saved as-is (string)."
                            )
                            ow[mt] = raw
                    else:
                        ow[mt] = {}
            config["overwrites"] = ow

            # Write config
            from ofscraper.utils.config.file import write_config
            write_config(config)

            app_signals.status_message.emit("Configuration saved")
            QMessageBox.information(self, "Saved", "Configuration saved successfully.")
        except Exception as e:
            log.error(f"Failed to save config: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")
