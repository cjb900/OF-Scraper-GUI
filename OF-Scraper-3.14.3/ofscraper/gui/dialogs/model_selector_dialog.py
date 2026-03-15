"""Modal dialog for selecting models/creators before scraping starts."""

import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QVBoxLayout,
)

from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

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


class ModelSelectorDialog(QDialog):
    """Modal dialog for model/creator selection.
    Shows the loaded model list, allows search/filter/sort, returns selected models."""

    def __init__(self, all_models, parent=None):
        super().__init__(parent)
        self._all_models = all_models  # dict: name -> model object
        self._selected_models = []
        self.setWindowTitle("Select Models")
        self.setMinimumSize(900, 600)
        self.resize(1000, 650)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QLabel("Select Models to Scrape")
        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        layout.addWidget(header)

        subtitle = QLabel("Search and select the creators you want to process.")
        subtitle.setStyleSheet("color: #a6adc8;")
        layout.addWidget(subtitle)

        # Main content: splitter with list on left, filters on right
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # -- Left: search + model list --
        left_widget = self._build_left_panel()
        splitter.addWidget(left_widget)

        # -- Right: filter panel --
        right_widget = self._build_right_panel()
        splitter.addWidget(right_widget)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = StyledButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.ok_btn = StyledButton("Start Scraping >>", primary=True)
        self.ok_btn.setFixedWidth(180)
        self.ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

        # Populate list
        self._populate_list(sorted(self._all_models.keys()))

    def _build_left_panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search bar
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search models...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_list)
        layout.addWidget(self.search_input)

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
        self.count_label.setStyleSheet("color: #a6adc8;")
        bulk_layout.addWidget(self.count_label)

        layout.addLayout(bulk_layout)

        # Model list
        self.model_list = QListWidget()
        self.model_list.setAlternatingRowColors(True)
        self.model_list.itemChanged.connect(self._update_count)
        layout.addWidget(self.model_list)

        return widget

    def _build_right_panel(self):
        widget = QWidget()
        widget.setFixedWidth(300)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 0, 0, 0)

        filter_label = QLabel("Filters")
        filter_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(filter_label)

        # Subscription type
        sub_group = QGroupBox("Subscription Type")
        sub_grid = QGridLayout(sub_group)
        self.renewal_combo = QComboBox()
        self.renewal_combo.addItems(["All", "Renewal On", "Renewal Off"])
        sub_grid.addWidget(QLabel("Renewal:"), 0, 0)
        sub_grid.addWidget(self.renewal_combo, 0, 1)
        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Active Only", "Expired Only"])
        sub_grid.addWidget(QLabel("Status:"), 1, 0)
        sub_grid.addWidget(self.status_combo, 1, 1)
        layout.addWidget(sub_group)

        # Price range
        price_group = QGroupBox("Price Range")
        price_grid = QGridLayout(price_group)
        self.price_min = QDoubleSpinBox()
        self.price_min.setRange(0, 99999)
        self.price_min.setSpecialValueText("No min")
        price_grid.addWidget(QLabel("Min:"), 0, 0)
        price_grid.addWidget(self.price_min, 0, 1)
        self.price_max = QDoubleSpinBox()
        self.price_max.setRange(0, 99999)
        self.price_max.setSpecialValueText("No max")
        price_grid.addWidget(QLabel("Max:"), 1, 0)
        price_grid.addWidget(self.price_max, 1, 1)
        layout.addWidget(price_group)

        # Sort
        sort_group = QGroupBox("Sort")
        sort_grid = QGridLayout(sort_group)
        self.sort_combo = QComboBox()
        for label, _ in SORT_OPTIONS:
            self.sort_combo.addItem(label)
        sort_grid.addWidget(QLabel("Sort by:"), 0, 0)
        sort_grid.addWidget(self.sort_combo, 0, 1)
        self.sort_desc_check = QCheckBox("Descending")
        sort_grid.addWidget(self.sort_desc_check, 1, 0, 1, 2)
        layout.addWidget(sort_group)

        apply_btn = StyledButton("Apply Filters", primary=True)
        apply_btn.clicked.connect(self._apply_filters)
        layout.addWidget(apply_btn)

        layout.addStretch()
        return widget

    def _populate_list(self, names):
        self.model_list.blockSignals(True)
        self.model_list.clear()
        for name in names:
            model = self._all_models.get(name)
            if model:
                sub_date = getattr(model, "subscribed_string", None) or "N/A"
                price = getattr(model, "final_current_price", 0) or 0
                display = f"{name}  =>  subscribed: {sub_date} | price: {price}"
            else:
                display = name
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.model_list.addItem(item)
        self.model_list.blockSignals(False)
        self._update_count()

    def _filter_list(self, text):
        text_lower = text.lower()
        for i in range(self.model_list.count()):
            item = self.model_list.item(i)
            item.setHidden(text_lower not in item.text().lower())

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
        return [
            self.model_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.model_list.count())
            if self.model_list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def _apply_filters(self):
        if not self._all_models:
            return

        models = list(self._all_models.values())

        # Renewal filter
        renewal_idx = self.renewal_combo.currentIndex()
        if renewal_idx == 1:
            models = [m for m in models if getattr(m, "renewed", False)]
        elif renewal_idx == 2:
            models = [m for m in models if not getattr(m, "renewed", False)]

        # Status filter
        status_idx = self.status_combo.currentIndex()
        if status_idx == 1:
            models = [m for m in models if getattr(m, "active", False)]
        elif status_idx == 2:
            models = [m for m in models if not getattr(m, "active", False)]

        # Price range
        min_price = self.price_min.value()
        max_price = self.price_max.value()
        if min_price > 0:
            models = [m for m in models if getattr(m, "final_current_price", 0) >= min_price]
        if max_price > 0:
            models = [m for m in models if getattr(m, "final_current_price", 0) <= max_price]

        # Sort
        sort_idx = self.sort_combo.currentIndex()
        sort_key = SORT_OPTIONS[sort_idx][1] if sort_idx < len(SORT_OPTIONS) else "name"
        reverse = self.sort_desc_check.isChecked()
        sort_attr_map = {
            "name": "name", "last-seen": "final_last_seen",
            "expired": "final_expired", "subscribed": "final_subscribed",
            "current-price": "final_current_price", "promo-price": "final_promo_price",
            "renewal-price": "final_renewal_price", "regular-price": "final_regular_price",
        }
        attr = sort_attr_map.get(sort_key, "name")
        try:
            models.sort(key=lambda m: getattr(m, attr, "") or "", reverse=reverse)
        except TypeError:
            models.sort(key=lambda m: str(getattr(m, attr, "")), reverse=reverse)

        # Remember selections
        selected = set(self._get_selected_names())
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

    def _on_ok(self):
        selected_names = self._get_selected_names()
        if not selected_names:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "No Models Selected",
                "Please select at least one model to continue.",
            )
            return
        self._selected_models = [
            self._all_models[name]
            for name in selected_names
            if name in self._all_models
        ]
        self.accept()

    def get_selected_models(self):
        """Return the list of selected model objects after dialog is accepted."""
        return self._selected_models
