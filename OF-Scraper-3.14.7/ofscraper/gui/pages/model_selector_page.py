import logging

from PyQt6.QtCore import Qt, QEvent, QObject, QRunnable, QSize, QThreadPool, QTimer, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font, scale_px
from ofscraper.gui.styles import c
from ofscraper.gui.utils.thread_worker import Worker
from ofscraper.gui.widgets.styled_button import StyledButton

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
    b.setToolTip("Open help for this section")
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setAutoRaise(True)
    b.setFixedSize(18, 18)
    b.setStyleSheet(_help_btn_qss())
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b

class _AvatarSignals(QObject):
    """Signals for avatar download tasks (must be a QObject for cross-thread emit)."""
    # Emits a pre-scaled QImage so the main thread only does a lightweight
    # QPixmap.fromImage() conversion — all heavy image work stays off the UI thread.
    loaded = pyqtSignal(str, object)  # model name, scaled QImage


class _AvatarTask(QRunnable):
    """Downloads and scales a single avatar image in a thread-pool worker."""

    def __init__(self, name: str, url: str, signals: _AvatarSignals):
        super().__init__()
        self.name = name
        self.url = url
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            import urllib.request
            from PyQt6.QtGui import QImage
            req = urllib.request.Request(
                self.url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            # QImage is thread-safe; do the heavy load + scale here off the main thread
            img = QImage()
            img.loadFromData(data)
            if not img.isNull():
                img = img.scaled(
                    40, 40,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.signals.loaded.emit(self.name, img)
        except Exception:
            pass


SORT_OPTIONS = [
    ("Name", "name"),
    ("Last Seen", "last-seen"),
    ("Expired", "expired"),
    ("Subscribed", "subscribed"),
    ("Current Price", "current-price"),
    ("Promo Price", "promo-price"),
    ("Renewal Price", "renewal-price"),
    ("Regular Price", "regular-price"),
]


class ModelSelectorPage(QWidget):
    """Model/creator selection page with search and filtering.
    Replaces the InquirerPy fuzzy model selector."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._all_models = {}  # name -> model object
        self._filtered_names = []
        self._avatar_cache: dict[str, QIcon] = {}
        self._show_avatars = False
        self._models_load_gen = 0
        self._models_worker = None
        self._models_poll_timer = None
        self._models_env_prepared = False
        self._models_finish_scheduled = False
        self._avatar_signals = _AvatarSignals()
        # Dedicated thread pool for avatar downloads — isolated from Qt's global pool
        self._avatar_pool = QThreadPool()
        self._avatar_pool.setMaxThreadCount(4)
        # Batch avatar updates — collect names here, flush every 150 ms
        self._pending_avatar_names: set = set()
        self._avatar_flush_timer = QTimer()
        self._avatar_flush_timer.setSingleShot(False)
        self._avatar_flush_timer.setInterval(150)
        self._avatar_flush_timer.timeout.connect(self._flush_pending_avatars)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header = QLabel("Select Models")
        apply_font(header, "Segoe UI", 22, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Search and select the creators you want to process."
        )
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        # Main content: splitter with list on left, filters on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Left: search + model list --
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search models...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_list)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)

        # Bulk action buttons
        bulk_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        bulk_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all)
        bulk_layout.addWidget(deselect_all_btn)

        toggle_btn = QPushButton("Toggle")
        toggle_btn.clicked.connect(self._toggle_all)
        bulk_layout.addWidget(toggle_btn)

        self.avatars_check = QCheckBox("Show Avatars")
        self.avatars_check.setToolTip(
            "Download and display each creator's profile picture.\n"
            "Click an avatar to open their OnlyFans page."
        )
        self.avatars_check.toggled.connect(self._toggle_avatars)
        bulk_layout.addWidget(self.avatars_check)

        bulk_layout.addStretch()

        self.count_label = QLabel("0 / 0 selected")
        self.count_label.setProperty("muted", True)
        bulk_layout.addWidget(self.count_label)

        left_layout.addLayout(bulk_layout)

        # Inline loading indicator (must be parented + in layout; otherwise .show()
        # turns it into a stray top-level popup window).
        self.loading_label = QLabel("Loading models...", left_widget)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setProperty("subheading", True)
        self.loading_label.setWordWrap(True)
        self.loading_label.hide()
        left_layout.addWidget(self.loading_label)

        # Retry button (shown when model loading fails)
        self.retry_btn = QPushButton("Retry Loading Models")
        self.retry_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('blue')}; color: {c('base')}; "
            f"padding: 8px 16px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {c('lavender')}; }}"
        )
        self.retry_btn.clicked.connect(self._load_models)
        self.retry_btn.hide()
        left_layout.addWidget(self.retry_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Model list — monospace via stylesheet (global QSS prefers Segoe UI,
        # which breaks fixed-width column padding).
        self.model_list = QListWidget()
        self.model_list.setAlternatingRowColors(True)
        apply_font(self.model_list, "Consolas", 11)
        self.model_list.setStyleSheet(
            f'QListWidget {{ font-family: Consolas, "Courier New", monospace; font-size: {scale_px(11)}pt; }}'
        )
        self.model_list.itemChanged.connect(self._update_count)
        self.model_list.viewport().installEventFilter(self)

        self._list_name_width = 28
        self._model_list_header = QLabel("")
        apply_font(self._model_list_header, "Consolas", 11, QFont.Weight.Bold)
        self._model_list_header.setProperty("muted", True)
        left_layout.addWidget(self._model_list_header)
        left_layout.addWidget(self.model_list)
        self._sync_model_list_header()

        splitter.addWidget(left_widget)

        # -- Right: filter panel --
        right_widget = QWidget()
        right_widget.setFixedWidth(320)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        filter_label = QLabel("Filters")
        apply_font(filter_label, "Segoe UI", 14, QFont.Weight.Bold)
        right_layout.addWidget(filter_label)

        # Subscription type
        sub_group = QGroupBox("Subscription Type")
        sub_grid = QGridLayout(sub_group)
        sub_grid.addWidget(
            _make_help_btn("models-filters-subscription"),
            0,
            2,
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.renewal_combo = QComboBox()
        self.renewal_combo.addItems(["All", "Renewal On", "Renewal Off"])
        sub_grid.addWidget(QLabel("Renewal:"), 0, 0)
        sub_grid.addWidget(self.renewal_combo, 0, 1)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Active Only", "Expired Only"])
        sub_grid.addWidget(QLabel("Status:"), 1, 0)
        sub_grid.addWidget(self.status_combo, 1, 1)
        right_layout.addWidget(sub_group)

        # Promo / flags
        flags_group = QGroupBox("Flags")
        flags_grid = QGridLayout(flags_group)
        flags_grid.addWidget(
            _make_help_btn("models-filters-flags"),
            0,
            2,
            3,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.promo_combo = QComboBox()
        self.promo_combo.addItems(["All", "Has Claimable Promo", "No Promo"])
        flags_grid.addWidget(QLabel("Promo:"), 0, 0)
        flags_grid.addWidget(self.promo_combo, 0, 1)

        self.free_trial_combo = QComboBox()
        self.free_trial_combo.addItems(["All", "Free Trial Only", "No Free Trial"])
        flags_grid.addWidget(QLabel("Free Trial:"), 1, 0)
        flags_grid.addWidget(self.free_trial_combo, 1, 1)

        self.last_seen_combo = QComboBox()
        self.last_seen_combo.addItems(["All", "Visible", "Hidden"])
        flags_grid.addWidget(QLabel("Last Seen:"), 2, 0)
        flags_grid.addWidget(self.last_seen_combo, 2, 1)
        right_layout.addWidget(flags_group)

        # Price filters
        price_group = QGroupBox("Price Range")
        price_grid = QGridLayout(price_group)
        price_grid.addWidget(
            _make_help_btn("models-filters-price"),
            0,
            2,
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.price_min = QDoubleSpinBox()
        self.price_min.setRange(0, 99999)
        self.price_min.setSpecialValueText("No min")
        self.price_min.setValue(0)
        price_grid.addWidget(QLabel("Min:"), 0, 0)
        price_grid.addWidget(self.price_min, 0, 1)

        self.price_max = QDoubleSpinBox()
        self.price_max.setRange(0, 99999)
        self.price_max.setSpecialValueText("No max")
        self.price_max.setValue(0)
        price_grid.addWidget(QLabel("Max:"), 1, 0)
        price_grid.addWidget(self.price_max, 1, 1)
        right_layout.addWidget(price_group)

        # Sort
        sort_group = QGroupBox("Sort")
        sort_grid = QGridLayout(sort_group)
        sort_grid.addWidget(
            _make_help_btn("models-filters-sort"),
            0,
            2,
            2,
            1,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        self.sort_combo = QComboBox()
        for label, _ in SORT_OPTIONS:
            self.sort_combo.addItem(label)
        sort_grid.addWidget(QLabel("Sort by:"), 0, 0)
        sort_grid.addWidget(self.sort_combo, 0, 1)

        self.sort_desc_check = QCheckBox("Descending")
        sort_grid.addWidget(self.sort_desc_check, 1, 0, 1, 2)
        right_layout.addWidget(sort_group)

        # Apply filters button
        apply_btn = StyledButton("Apply Filters", primary=True)
        apply_btn.clicked.connect(self._apply_filters)
        right_layout.addWidget(apply_btn)

        reset_btn = StyledButton("Reset Filters")
        reset_btn.clicked.connect(self._reset_filters)
        right_layout.addWidget(reset_btn)

        right_layout.addStretch()
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Bottom navigation
        nav_layout = QHBoxLayout()
        back_btn = StyledButton("<< Back")
        back_btn.clicked.connect(self._on_back)
        nav_layout.addWidget(back_btn)

        nav_layout.addStretch()

        self.next_btn = StyledButton("Next  >>", primary=True)
        self.next_btn.setFixedWidth(160)
        self.next_btn.clicked.connect(self._on_next)
        nav_layout.addWidget(self.next_btn)

        layout.addLayout(nav_layout)

    def _connect_signals(self):
        # Models are loaded from the API on the Areas page so we can
        # show progress next to the "Next: Select Models" button.
        # Keep this page passive and only populate from the manager.
        app_signals.theme_changed.connect(self._apply_theme)
        app_signals.privacy_mode_changed.connect(self._on_privacy_mode_changed)
        self._avatar_signals.loaded.connect(self._on_avatar_loaded)

    def eventFilter(self, obj, event):
        """Row click zones: checkbox (native), avatar (open profile), username (toggle)."""
        if (
            obj is self.model_list.viewport()
            and event.type() == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            item = self.model_list.itemAt(event.pos())
            if item:
                item_rect = self.model_list.visualItemRect(item)
                rel_x = event.pos().x() - item_rect.left()
                # Checkbox indicator is ~0-20 px — let those clicks through so
                # the checkbox can be toggled normally.
                checkbox_w = 20
                icon_w = (
                    self.model_list.iconSize().width() if self._show_avatars else 0
                )
                icon_end = checkbox_w + icon_w + 4 if self._show_avatars else checkbox_w

                if self._show_avatars and checkbox_w < rel_x <= icon_end:
                    name = item.data(Qt.ItemDataRole.UserRole)
                    if name:
                        QDesktopServices.openUrl(QUrl(f"https://onlyfans.com/{name}"))
                        return True  # consume — open profile, don't toggle

                # Username / label area (and empty space to the right) toggles selection.
                if rel_x > icon_end:
                    new_state = (
                        Qt.CheckState.Unchecked
                        if item.checkState() == Qt.CheckState.Checked
                        else Qt.CheckState.Checked
                    )
                    item.setCheckState(new_state)
                    return True
        return super().eventFilter(obj, event)

    def _apply_theme(self, _is_dark=True):
        try:
            self.model_list.setStyleSheet(
                f'QListWidget {{ font-family: Consolas, "Courier New", monospace; font-size: {scale_px(11)}pt; }}'
            )
        except Exception:
            pass
        self.retry_btn.setStyleSheet(
            f"QPushButton {{ background-color: {c('blue')}; color: {c('base')}; "
            f"padding: 8px 16px; border-radius: 4px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: {c('lavender')}; }}"
        )
        for btn in self.findChildren(QToolButton):
            if btn.text() == "?":
                btn.setStyleSheet(_help_btn_qss())

    def showEvent(self, event):
        super().showEvent(event)
        # Populate from manager if not already populated
        if not self._all_models:
            self.populate_from_manager()

    def populate_from_manager(self):
        """Populate list from already-fetched manager state (no API calls)."""
        self.model_list.clear()
        self.loading_label.hide()
        self.next_btn.setEnabled(True)

        if not (self.manager and self.manager.model_manager):
            self.loading_label.setText(
                "Model manager not available. Showing empty list."
            )
            self.loading_label.show()
            return

        models = getattr(self.manager.model_manager, "all_subs_obj", None) or []
        if models:
            self._all_models = {m.name: m for m in models}
            self._populate_list(sorted(self._all_models.keys()))
            self.retry_btn.hide()
            app_signals.status_message.emit(f"Loaded {len(models)} models")
        else:
            self._all_models = {}
            self.loading_label.setText(
                "No models loaded. Check your auth and click Retry."
            )
            self.loading_label.show()
            self.retry_btn.show()
            self.next_btn.setEnabled(False)

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
        timer = getattr(self, "_models_poll_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._models_worker = None
        try:
            from ofscraper.gui.utils.model_fetch import clear_handoff

            clear_handoff()
        except Exception:
            pass
        if getattr(self, "_models_env_prepared", False):
            self._models_env_prepared = False
            try:
                from ofscraper.gui.utils.model_fetch import cleanup_model_fetch_environment

                cleanup_model_fetch_environment()
            except Exception:
                pass

    def _load_models(self):
        """Load models from the manager by triggering the API fetch in a background thread."""
        self._cancel_models_worker()
        try:
            self.model_list.clear()
            self.retry_btn.hide()
            self.loading_label.setText("Loading models from API...")
            self.loading_label.show()
            self.next_btn.setEnabled(False)
        except RuntimeError:
            return

        if not (self.manager and self.manager.model_manager):
            try:
                self.loading_label.setText(
                    "Model manager not available. Showing empty list."
                )
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

        self._models_load_gen = int(getattr(self, "_models_load_gen", 0) or 0) + 1
        load_gen = self._models_load_gen

        def _job():
            from ofscraper.gui.utils.model_fetch import (
                fetch_subscription_models,
                publish_handoff,
                wait_for_ui_ack,
            )

            try:
                dicts = fetch_subscription_models()
                publish_handoff(gen=load_gen, payload=dicts)
                wait_for_ui_ack()
                return len(dicts or [])
            except Exception as e:
                publish_handoff(gen=load_gen, error=str(e))
                wait_for_ui_ack()
                raise

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

        self._models_worker = Worker(_job, emit_signals=False)
        from PyQt6.QtCore import QThreadPool

        if self._models_poll_timer is None:
            self._models_poll_timer = QTimer(self)
            self._models_poll_timer.setInterval(50)
            self._models_poll_timer.timeout.connect(self._poll_models_worker)

        QThreadPool.globalInstance().start(self._models_worker)
        self._models_poll_timer.start()

    def _poll_models_worker(self):
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
        timer = getattr(self, "_models_poll_timer", None)
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(150, lambda g=load_gen: self._finish_models_load(g))

    def _finish_models_load(self, load_gen=None):
        self._models_finish_scheduled = False
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            return

        from ofscraper.gui.utils.model_fetch import dicts_to_models, take_handoff

        handoff = take_handoff(int(load_gen or 0))
        worker = getattr(self, "_models_worker", None)
        self._models_worker = None
        if getattr(self, "_models_env_prepared", False):
            self._models_env_prepared = False
            try:
                from ofscraper.gui.utils.model_fetch import cleanup_model_fetch_environment

                cleanup_model_fetch_environment()
            except Exception:
                pass

        if handoff is None:
            err = getattr(worker, "error_msg", None) if worker else "handoff missing"
            if err:
                self._on_models_error(err, load_gen)
            else:
                self._apply_models_loaded([], load_gen)
            return

        if handoff.get("error"):
            self._on_models_error(handoff["error"], load_gen)
            return

        from PyQt6.QtCore import QTimer

        payload = handoff.get("payload")

        def _build_and_apply():
            self._apply_models_loaded(dicts_to_models(payload), load_gen)

        QTimer.singleShot(0, _build_and_apply)

    def _apply_models_loaded(self, models, load_gen=None):
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            return
        if not self._widget_alive():
            return

        self._models_worker = None
        try:
            if self.manager and getattr(self.manager, "model_manager", None) is not None:
                self.manager.model_manager.all_subs_dict = models or []
            self.loading_label.hide()
            self.retry_btn.hide()
            self.next_btn.setEnabled(True)
            if models:
                self._all_models = {m.name: m for m in models}
                self._populate_list(sorted(self._all_models.keys()))
                app_signals.status_message.emit(f"Loaded {len(models)} models")
            else:
                self._all_models = {}
                self._show_auth_failure_prompt()
        except RuntimeError:
            log.debug("[GUI] Select Models load UI update skipped (widget deleted)")
        except Exception as e:
            log.warning(f"[GUI] Select Models load UI update failed: {e}")
            try:
                self._on_models_error(str(e), load_gen)
            except Exception:
                pass

    def _on_models_error(self, error_msg, load_gen=None):
        """Handle model fetch failure."""
        if load_gen is not None and load_gen != getattr(self, "_models_load_gen", None):
            log.debug("[GUI] Ignoring stale Select Models load error")
            return
        if not self._widget_alive():
            return

        self._models_worker = None
        log.error(f"Model fetch error: {error_msg}")
        try:
            self._show_auth_failure_prompt(error_msg)
        except RuntimeError:
            log.debug("[GUI] Select Models error UI update skipped (widget deleted)")

    def _show_auth_failure_prompt(self, detail=None):
        """Show a dialog when models can't be loaded, offering to go to auth settings."""
        if not self._widget_alive():
            return
        self.loading_label.setText("Unable to get list of models.")
        self.loading_label.show()
        self.retry_btn.show()
        self.next_btn.setEnabled(False)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unable to Load Models")
        from ofscraper.gui.utils.auth_errors import model_load_failure_dialog_text

        main_text, detail_text = model_load_failure_dialog_text(detail)
        msg.setText(main_text)
        if detail_text:
            msg.setDetailedText(detail_text)
        retry_btn = msg.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        auth_btn = msg.addButton("Go to Authentication", QMessageBox.ButtonRole.ActionRole)
        dynamic_btn = msg.addButton(
            "Dynamic Mode (Config)", QMessageBox.ButtonRole.ActionRole
        )
        ssl_btn = msg.addButton("SSL Verify (Config)", QMessageBox.ButtonRole.ActionRole)
        help_btn = msg.addButton("Help / README", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if not self._widget_alive():
            return
        clicked = msg.clickedButton()
        if clicked == retry_btn:
            self._load_models()
        elif clicked == auth_btn:
            app_signals.navigate_to_page.emit("auth")
        elif clicked == dynamic_btn:
            self._go_to_advanced_config_field("dynamic-mode-default")
        elif clicked == ssl_btn:
            self._go_to_advanced_config_field("ssl_verify")
        elif clicked == help_btn:
            self._go_to_auth_help()

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

    def _populate_list(self, names):
        """Populate the list widget with model names and details."""
        # Remember order for privacy-mode refresh; preserve checks across rebuild.
        self._filtered_names = list(names)
        previously_checked = set()
        try:
            previously_checked = set(self._get_selected_names())
        except Exception:
            previously_checked = set()

        self.model_list.blockSignals(True)
        self.model_list.clear()
        # Name column width from this list (capped) so short names still align.
        try:
            name_width = max((len(str(n or "")) for n in names), default=12)
            name_width = max(12, min(name_width, 32))
        except Exception:
            name_width = 28
        self._list_name_width = name_width
        self._sync_model_list_header(name_width)
        for name in names:
            model = self._all_models.get(name)
            if model:
                sub_date = getattr(model, "subscribed_string", None) or "N/A"
                price = getattr(model, "final_current_price", 0) or 0
                try:
                    from ofscraper.gui.utils.privacy_mode import format_model_list_line

                    display = format_model_list_line(
                        name,
                        sub_date=sub_date,
                        price=price,
                        style="page",
                        name_width=name_width,
                    )
                except Exception:
                    display = (
                        f"{str(name):<{name_width}}  {str(sub_date):<10}  {str(price):>8}"
                    )
            else:
                try:
                    from ofscraper.gui.utils.privacy_mode import mask_username

                    display = mask_username(name) or name
                except Exception:
                    display = name
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if name in previously_checked:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        self._update_count()
        # Re-apply avatars for any already-cached items (skip when privacy on)
        try:
            from ofscraper.gui.utils.privacy_mode import is_privacy_mode

            privacy_on = is_privacy_mode()
        except Exception:
            privacy_on = False
        if self._show_avatars and not privacy_on:
            self._apply_avatars_to_list()
            QTimer.singleShot(0, self._sync_model_list_header)
        elif privacy_on:
            self._clear_avatars()
            QTimer.singleShot(0, self._sync_model_list_header)
        # Re-apply any active search text (e.g. pre-set by username filter from area page)
        current_text = self.search_input.text()
        if current_text:
            self._filter_list(current_text)

    def _on_privacy_mode_changed(self, _enabled: bool):
        """Refresh list labels when Privacy / demo mode toggles."""
        if self._filtered_names:
            self._populate_list(self._filtered_names)
        elif self._all_models:
            self._populate_list(sorted(self._all_models.keys()))

    # ------------------------------------------------------------------
    # Avatar loading
    # ------------------------------------------------------------------

    def _measure_model_list_text_inset(self) -> int:
        """Pixels from the list widget's left edge to where row text begins.

        Uses Qt style layout (checkbox + decoration) instead of guessing widths,
        so the header lines up with Username when Show Avatars is on.
        """
        from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

        lw = self.model_list
        style = lw.style()
        option = QStyleOptionViewItem()
        try:
            lw.initViewItemOption(option)
        except Exception:
            pass
        option.decorationSize = lw.iconSize()
        option.features = QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        show_av = bool(getattr(self, "_show_avatars", False)) and lw.iconSize().width() > 0
        if show_av:
            option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration

        if lw.count() > 0:
            item = lw.item(0)
            index = lw.indexFromItem(item)
            option.rect = lw.visualRect(index)
            option.index = index
            option.checkState = item.checkState()
            option.text = item.text() or "M"
            if not item.icon().isNull():
                option.icon = item.icon()
                option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
            elif show_av:
                # Reserve decoration space before icons finish downloading.
                option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration
        else:
            option.rect = lw.viewport().rect()
            option.rect.setHeight(max(int(lw.iconSize().height() or 24), 24) + 8)
            option.checkState = Qt.CheckState.Unchecked
            option.text = "M"
            if show_av:
                option.features |= QStyleOptionViewItem.ViewItemFeature.HasDecoration

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, option, lw
        )
        # option.rect / text_rect are viewport-relative; header is above the list widget.
        try:
            inset = int(lw.viewport().mapTo(lw, text_rect.topLeft()).x())
        except Exception:
            inset = int(text_rect.left()) + int(lw.frameWidth())
        return max(0, inset)

    def _sync_model_list_header(self, name_width=None):
        """Keep column header text aligned with list text (incl. avatar offset)."""
        if name_width is None:
            name_width = getattr(self, "_list_name_width", 28)
        try:
            from ofscraper.gui.utils.privacy_mode import model_list_header_line

            hdr = model_list_header_line(name_width)
        except Exception:
            hdr = ""
        try:
            left_pad = self._measure_model_list_text_inset()
        except Exception:
            left_pad = 28
            if getattr(self, "_show_avatars", False):
                left_pad += 48
        try:
            self._model_list_header.setText(hdr)
            self._model_list_header.setStyleSheet(
                f'QLabel {{ font-family: Consolas, "Courier New", monospace; font-size: {scale_px(11)}pt;'
                f" font-weight: bold; color: {c('subtext')};"
                f" padding: 2px 4px 2px {left_pad}px; }}"
            )
            self._model_list_header.show()
        except Exception:
            pass

    def _toggle_avatars(self, checked: bool):
        self._show_avatars = checked
        try:
            from ofscraper.gui.utils.privacy_mode import is_privacy_mode

            if checked and is_privacy_mode():
                app_signals.status_message.emit(
                    "Avatars hidden while Privacy mode is on"
                )
                self._clear_avatars()
                self.model_list.setIconSize(QSize(0, 0))
                QTimer.singleShot(0, self._sync_model_list_header)
                return
        except Exception:
            pass
        if checked:
            self.model_list.setIconSize(QSize(40, 40))
            self._load_avatars()
        else:
            self._clear_avatars()
            self.model_list.setIconSize(QSize(0, 0))
        # Defer until the view applies the new decoration size.
        QTimer.singleShot(0, self._sync_model_list_header)

    def _load_avatars(self):
        """Queue background downloads for any model whose avatar isn't cached yet."""
        for name, model in self._all_models.items():
            if name in self._avatar_cache:
                continue
            url = getattr(model, "avatar", None)
            if url:
                self._avatar_pool.start(_AvatarTask(name, url, self._avatar_signals))
        # Immediately apply whatever is already cached
        self._apply_avatars_to_list()

    @pyqtSlot(str, object)
    def _on_avatar_loaded(self, name: str, image):
        """Main-thread slot: image is pre-scaled QImage; just convert to QPixmap and batch."""
        if not self._show_avatars:
            return
        try:
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                return
            self._avatar_cache[name] = QIcon(pixmap)
            self._pending_avatar_names.add(name)
            if not self._avatar_flush_timer.isActive():
                self._avatar_flush_timer.start()
        except Exception:
            pass

    def _flush_pending_avatars(self):
        """Apply all pending avatar icons to the list in one suppressed-repaint pass."""
        if not self._pending_avatar_names:
            self._avatar_flush_timer.stop()
            return
        names = self._pending_avatar_names.copy()
        self._pending_avatar_names.clear()
        self.model_list.setUpdatesEnabled(False)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name in names and name in self._avatar_cache:
                item.setIcon(self._avatar_cache[name])
        self.model_list.setUpdatesEnabled(True)
        if not self._pending_avatar_names:
            self._avatar_flush_timer.stop()
        # Icons can change row layout slightly — re-align header after paint.
        QTimer.singleShot(0, self._sync_model_list_header)

    def _apply_avatars_to_list(self):
        """Set cached icons on all current list items (single suppressed-repaint pass)."""
        self.model_list.setUpdatesEnabled(False)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            name = item.data(Qt.ItemDataRole.UserRole)
            if name in self._avatar_cache:
                item.setIcon(self._avatar_cache[name])
        self.model_list.setUpdatesEnabled(True)

    def _clear_avatars(self):
        """Remove icons from all list items (cache is kept for re-enable)."""
        self._avatar_flush_timer.stop()
        self._pending_avatar_names.clear()
        empty = QIcon()
        self.model_list.setUpdatesEnabled(False)
        for i in range(self.model_list.count()):
            self.model_list.item(i).setIcon(empty)
        self.model_list.setUpdatesEnabled(True)

    # ------------------------------------------------------------------

    def _filter_list(self, text):
        """Filter visible items based on search text.
        Supports comma-separated values (e.g. 'user1, user2').
        Matches against the real username (UserRole), so Privacy mode
        does not break search.
        """
        if "," in text:
            terms = [t.strip().lower() for t in text.split(",") if t.strip()]
        else:
            terms = [text.strip().lower()] if text.strip() else []

        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if not terms:
                item.setHidden(False)
            else:
                real = str(item.data(Qt.ItemDataRole.UserRole) or "").lower()
                shown = item.text().lower()
                haystack = f"{real} {shown}"
                item.setHidden(not any(term in haystack for term in terms))

    def _select_all(self):
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked)
        self.model_list.blockSignals(False)
        self._update_count()

    def _deselect_all(self):
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if not item.isHidden():
                item.setCheckState(Qt.CheckState.Unchecked)
        self.model_list.blockSignals(False)
        self._update_count()

    def _toggle_all(self):
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if not item.isHidden():
                new_state = (
                    Qt.CheckState.Unchecked
                    if item.checkState() == Qt.CheckState.Checked
                    else Qt.CheckState.Checked
                )
                item.setCheckState(new_state)
        self.model_list.blockSignals(False)
        self._update_count()

    def _update_count(self):
        checked = sum(
            1
            for i in range(self.model_list.count())
            if self.model_list.item(i).checkState() == Qt.CheckState.Checked
        )
        total = self.model_list.count()
        self.count_label.setText(f"{checked} / {total} selected")

    def _get_selected_names(self):
        """Return list of selected model names (using stored UserRole data)."""
        return [
            self.model_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.model_list.count())
            if self.model_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def reset_to_defaults(self):
        """Reset model selections and filters to defaults."""
        # Deselect all models
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            self.model_list.item(i).setCheckState(Qt.CheckState.Unchecked)
        self.model_list.blockSignals(False)
        self._update_count()
        # Clear search
        self.search_input.clear()
        # Reset filters
        self._reset_filters()

    def _apply_filters(self):
        """Apply filters and re-sort the model list."""
        if not self._all_models:
            return

        models = list(self._all_models.values())

        # Apply sub type filter
        renewal_idx = self.renewal_combo.currentIndex()
        if renewal_idx == 1:
            models = [m for m in models if getattr(m, "renewed", False)]
        elif renewal_idx == 2:
            models = [m for m in models if not getattr(m, "renewed", False)]

        status_idx = self.status_combo.currentIndex()
        if status_idx == 1:
            models = [m for m in models if getattr(m, "active", False)]
        elif status_idx == 2:
            models = [m for m in models if not getattr(m, "active", False)]

        # Apply promo filter
        promo_idx = self.promo_combo.currentIndex()
        if promo_idx == 1:
            models = [
                m for m in models if getattr(m, "lowest_promo_claim", None) is not None
            ]
        elif promo_idx == 2:
            models = [
                m for m in models if getattr(m, "lowest_promo_claim", None) is None
            ]

        # Free trial filter
        ft_idx = self.free_trial_combo.currentIndex()
        if ft_idx == 1:
            models = [
                m
                for m in models
                if getattr(m, "final_current_price", None) == 0
                and getattr(m, "lowest_promo_claim", None) is not None
            ]
        elif ft_idx == 2:
            models = [
                m
                for m in models
                if not (
                    getattr(m, "final_current_price", None) == 0
                    and getattr(m, "lowest_promo_claim", None) is not None
                )
            ]

        # Last seen visibility filter
        ls_idx = self.last_seen_combo.currentIndex()
        if ls_idx == 1:
            models = [m for m in models if getattr(m, "last_seen", None) is not None]
        elif ls_idx == 2:
            models = [m for m in models if getattr(m, "last_seen", None) is None]

        # Price range filter
        min_price = self.price_min.value()
        max_price = self.price_max.value()
        if min_price > 0:
            models = [
                m
                for m in models
                if getattr(m, "final_current_price", 0) >= min_price
            ]
        if max_price > 0:
            models = [
                m
                for m in models
                if getattr(m, "final_current_price", 0) <= max_price
            ]

        # Sort
        sort_idx = self.sort_combo.currentIndex()
        sort_key = SORT_OPTIONS[sort_idx][1] if sort_idx < len(SORT_OPTIONS) else "name"
        reverse = self.sort_desc_check.isChecked()

        sort_attr_map = {
            "name": "name",
            "last-seen": "final_last_seen",
            "expired": "final_expired",
            "subscribed": "final_subscribed",
            "current-price": "final_current_price",
            "promo-price": "final_promo_price",
            "renewal-price": "final_renewal_price",
            "regular-price": "final_regular_price",
        }
        attr = sort_attr_map.get(sort_key, "name")
        try:
            models.sort(
                key=lambda m: getattr(m, attr, "") or "", reverse=reverse
            )
        except TypeError:
            models.sort(key=lambda m: str(getattr(m, attr, "")), reverse=reverse)

        # Remember current selections
        selected = set(self._get_selected_names())

        # Repopulate
        names = [m.name for m in models]
        self._populate_list(names)

        # Restore selections
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) in selected:
                item.setCheckState(Qt.CheckState.Checked)
        self.model_list.blockSignals(False)
        self._update_count()

    def _reset_filters(self):
        """Reset all filters to defaults."""
        self.renewal_combo.setCurrentIndex(0)
        self.status_combo.setCurrentIndex(0)
        self.promo_combo.setCurrentIndex(0)
        self.free_trial_combo.setCurrentIndex(0)
        self.last_seen_combo.setCurrentIndex(0)
        self.price_min.setValue(0)
        self.price_max.setValue(0)
        self.sort_combo.setCurrentIndex(0)
        self.sort_desc_check.setChecked(False)
        self._apply_filters()

    def pre_filter_username(self, username_text):
        """Pre-filter and pre-select models matching the given username(s).
        Supports comma-separated values (e.g. 'user1, user2').
        Called from area_selector_page when navigating here."""
        if not username_text:
            self.search_input.clear()
            return

        # Parse comma-separated usernames
        usernames = [u.strip().lower() for u in username_text.split(",") if u.strip()]
        if not usernames:
            self.search_input.clear()
            return

        # Set search box text — _filter_list handles comma-separated values
        self.search_input.setText(username_text)

        # Auto-select exact matches
        self.model_list.blockSignals(True)
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            model_name = (item.data(Qt.ItemDataRole.UserRole) or "").lower()
            if model_name in usernames:
                item.setCheckState(Qt.CheckState.Checked)
        self.model_list.blockSignals(False)
        self._update_count()

    def _on_back(self):
        """Go back to area selector page."""
        parent_stack = self.parent()
        if parent_stack:
            parent_stack.setCurrentIndex(2)

    def _on_next(self):
        """Proceed to table page."""
        selected = self._get_selected_names()
        if not selected:
            app_signals.error_occurred.emit(
                "No Models Selected",
                "Please select at least one model to continue.",
            )
            return

        selected_models = [
            self._all_models[name] for name in selected if name in self._all_models
        ]
        log.info(f"Models selected: {len(selected_models)}")
        app_signals.models_selected.emit(selected_models)
