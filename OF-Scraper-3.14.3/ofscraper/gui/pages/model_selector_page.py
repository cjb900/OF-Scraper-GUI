import logging

from PyQt6.QtCore import Qt, pyqtSlot
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

from PyQt6.QtCore import QThreadPool

from ofscraper.gui.signals import app_signals
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
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header = QLabel("Select Models")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
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

        # Model list
        self.model_list = QListWidget()
        self.model_list.setAlternatingRowColors(True)
        self.model_list.itemChanged.connect(self._update_count)
        left_layout.addWidget(self.model_list)

        splitter.addWidget(left_widget)

        # -- Right: filter panel --
        right_widget = QWidget()
        right_widget.setFixedWidth(320)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 0, 0)

        filter_label = QLabel("Filters")
        filter_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
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

    def _apply_theme(self, _is_dark=True):
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

    def _load_models(self):
        """Load models from the manager by triggering the API fetch in a background thread."""
        self.model_list.clear()
        self.retry_btn.hide()
        self.loading_label.setText("Loading models from API...")
        self.loading_label.show()
        self.next_btn.setEnabled(False)

        if not (self.manager and self.manager.model_manager):
            self.loading_label.setText(
                "Model manager not available. Showing empty list."
            )
            self.next_btn.setEnabled(True)
            return

        worker = Worker(self._fetch_models)
        worker.signals.finished.connect(self._on_models_loaded)
        worker.signals.error.connect(self._on_models_error)
        QThreadPool.globalInstance().start(worker)

    def _fetch_models(self):
        """Fetch models via the API (runs in background thread).
        Uses a fresh event loop directly to avoid stale loop state
        from the @run decorator on retries."""
        import asyncio
        import logging
        import ofscraper.data.models.utils.retriver as retriver
        import ofscraper.utils.paths.common as common_paths
        import ofscraper.utils.auth.utils.dict as auth_dict_mod

        _log = logging.getLogger("shared")

        # Log the auth file path and contents for debugging
        try:
            auth_path = common_paths.get_auth_file()
            _log.info(f"[GUI retry] Auth file path: {auth_path}")
            auth_data = auth_dict_mod.get_auth_dict()
            filled = {k: ("set" if v else "EMPTY") for k, v in auth_data.items()}
            _log.info(f"[GUI retry] Auth field status: {filled}")

            # Bail out early if required auth fields are empty
            required = ["sess", "auth_id", "user_agent", "x-bc"]
            missing = [k for k in required if not auth_data.get(k)]
            if missing:
                raise Exception(
                    f"Auth fields not configured: {', '.join(missing)}. "
                    "Please fill in your auth credentials first."
                )
        except Exception as e:
            _log.warning(f"[GUI retry] Auth check failed: {e}")
            raise

        # Clear cached data so we actually re-fetch from the API
        self.manager.model_manager._all_subs_dict = {}

        # Clear the profile/user info cache so stale None values from
        # a previous failed auth attempt don't poison the retry.
        import ofscraper.utils.profiles.data as profile_data
        profile_data.currentData = None
        profile_data.currentProfile = None

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(retriver.get_models())
            self.manager.model_manager.all_subs_dict = data
        finally:
            loop.close()
            asyncio.set_event_loop(None)

        return self.manager.model_manager.all_subs_obj

    def _on_models_loaded(self, models):
        """Handle successful model fetch — populate the list."""
        self.loading_label.hide()
        self.retry_btn.hide()
        self.next_btn.setEnabled(True)
        if models:
            self._all_models = {m.name: m for m in models}
            self._populate_list(sorted(self._all_models.keys()))
            app_signals.status_message.emit(
                f"Loaded {len(models)} models"
            )
        else:
            self._all_models = {}
            self._show_auth_failure_prompt()

    def _on_models_error(self, error_msg):
        """Handle model fetch failure."""
        log.error(f"Model fetch error: {error_msg}")
        self._show_auth_failure_prompt(error_msg)

    def _show_auth_failure_prompt(self, detail=None):
        """Show a dialog when models can't be loaded, offering to go to auth settings."""
        self.loading_label.setText("Unable to get list of models.")
        self.loading_label.show()
        self.retry_btn.show()
        self.next_btn.setEnabled(False)

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Unable to Load Models")
        msg.setText("Unable to get list of models.\nPlease check your auth information.")
        if detail:
            msg.setDetailedText(str(detail))
        retry_btn = msg.addButton("Retry", QMessageBox.ButtonRole.AcceptRole)
        auth_btn = msg.addButton("Go to Authentication", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Close", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        if msg.clickedButton() == retry_btn:
            self._load_models()
        elif msg.clickedButton() == auth_btn:
            app_signals.navigate_to_page.emit("auth")

    def _populate_list(self, names):
        """Populate the list widget with model names and details."""
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for name in names:
            model = self._all_models.get(name)
            if model:
                sub_date = getattr(model, "subscribed_string", None) or "N/A"
                price = getattr(model, "final_current_price", 0) or 0
                display = f"{name}  =>  subscribed date: {sub_date} | current_price: {price}"
            else:
                display = name
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        self._update_count()
        # Re-apply any active search text (e.g. pre-set by username filter from area page)
        current_text = self.search_input.text()
        if current_text:
            self._filter_list(current_text)

    def _filter_list(self, text):
        """Filter visible items based on search text.
        Supports comma-separated values (e.g. 'user1, user2')."""
        if "," in text:
            terms = [t.strip().lower() for t in text.split(",") if t.strip()]
        else:
            terms = [text.strip().lower()] if text.strip() else []

        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            if not terms:
                item.setHidden(False)
            else:
                item_text = item.text().lower()
                item.setHidden(not any(term in item_text for term in terms))

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
