import re

import arrow
from PyQt6.QtCore import Qt, QDate, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.group_layout import compact_group, tune_group_layout


def _make_help_btn(anchor: str) -> QToolButton:
    b = QToolButton()
    b.setText("?")
    b.setToolTip("Open help for this section")
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
        }
        QToolButton:hover {
            border-color: #89b4fa;
            background-color: #45475a;
        }
        """
    )
    b.clicked.connect(lambda: app_signals.help_anchor_requested.emit(anchor))
    return b


class FilterState:
    """Manages the current filter values — replaces the TUI Status singleton."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.text_search = ""
        self.full_string_match = False
        self.mediatype = None  # None = all, or set of selected types
        self.responsetype = None  # None = all, or set of selected types
        self.downloaded = None  # None = all, or set of bools
        self.unlocked = None  # None = all, or set of bools
        self.mindate = None
        self.maxdate = None
        self.min_length = None  # QTime or None
        self.max_length = None  # QTime or None
        self.min_price = None
        self.max_price = None
        self.media_id = None
        self.post_id = None
        self.post_media_count = None
        self.other_posts_with_media = None
        self.username = None

    def validate(self, name, value):
        """Check if a row value passes the current filter for the given field."""
        name = name.lower()

        if name == "text":
            return self._text_validate(value)
        elif name == "mediatype":
            return self._set_validate(self.mediatype, value)
        elif name == "responsetype":
            return self._set_validate(self.responsetype, value)
        elif name == "downloaded":
            return self._bool_validate(self.downloaded, value)
        elif name == "unlocked":
            return self._bool_validate(self.unlocked, value)
        elif name == "post_date":
            return self._date_validate(value)
        elif name == "length":
            return self._length_validate(value)
        elif name == "price":
            return self._price_validate(value)
        elif name == "media_id":
            return self._exact_validate(self.media_id, value)
        elif name == "post_id":
            return self._exact_validate(self.post_id, value)
        elif name == "post_media_count":
            return self._exact_validate(self.post_media_count, value)
        elif name == "other_posts_with_media":
            return self._list_count_validate(
                self.other_posts_with_media, value
            )
        elif name == "username":
            return self._string_validate(self.username, value)
        return True

    def _text_validate(self, value):
        if not self.text_search:
            return True
        try:
            if self.full_string_match:
                return bool(
                    re.fullmatch(self.text_search, str(value), re.IGNORECASE)
                )
            else:
                return bool(
                    re.search(self.text_search, str(value), re.IGNORECASE)
                )
        except re.error:
            return self.text_search.lower() in str(value).lower()

    def _set_validate(self, filter_set, value):
        if filter_set is None:
            return True
        return str(value).lower() in {s.lower() for s in filter_set}

    def _bool_validate(self, filter_set, value):
        if filter_set is None:
            return True
        return value in filter_set

    def _date_validate(self, value):
        if self.mindate is None and self.maxdate is None:
            return True
        try:
            test_date = arrow.get(value).floor("day")
            min_bound = arrow.get(self.mindate).floor("day") if self.mindate else None
            max_bound = arrow.get(self.maxdate).ceil("day") if self.maxdate else None
            if min_bound and max_bound:
                return test_date.is_between(min_bound, max_bound, bounds="[]")
            elif min_bound:
                return test_date >= min_bound
            elif max_bound:
                return test_date <= max_bound
        except Exception:
            return True
        return True

    def _length_validate(self, value):
        if self.min_length is None and self.max_length is None:
            return True
        try:
            if str(value) in ("N/A", "N\\A"):
                test_val = arrow.get("0:0:0", "h:m:s")
            else:
                test_val = arrow.get(str(value), "h:m:s")

            if self.min_length and self.max_length:
                return test_val.is_between(
                    self.min_length, self.max_length, bounds="[]"
                )
            elif self.min_length:
                return test_val >= self.min_length
            elif self.max_length:
                return test_val <= self.max_length
        except Exception:
            return True
        return True

    def _price_validate(self, value):
        if self.min_price is None and self.max_price is None:
            return True
        try:
            val = 0 if str(value).lower() == "free" else float(value)
            if self.min_price is not None and val < self.min_price:
                return False
            if self.max_price is not None and val > self.max_price:
                return False
        except (ValueError, TypeError):
            return True
        return True

    def _exact_validate(self, filter_val, value):
        if filter_val is None:
            return True
        return str(value).lower() == str(filter_val).lower()

    def _list_count_validate(self, filter_val, value):
        if filter_val is None:
            return True
        try:
            count = len(value) if isinstance(value, list) else int(value)
            return int(filter_val) == count
        except (ValueError, TypeError):
            return True

    def _string_validate(self, filter_val, value):
        if not filter_val:
            return True
        return str(filter_val).lower() in str(value).lower()


class FilterSidebar(QWidget):
    """Collapsible filter sidebar — replaces the Textual sidebar with all filter fields."""

    filter_changed = pyqtSignal()  # emitted when any filter value changes

    def __init__(self, parent=None, embedded=False):
        super().__init__(parent)
        self.state = FilterState()
        self._embedded = embedded
        self._setup_ui()

    def _setup_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        def _control_h(w: QWidget):
            """Align control heights without a local stylesheet (avoids clobbering QGroupBox theme)."""
            try:
                # Theme QSS: padding 4px + min-height 24px (+ border) — 28px FixedHeight
                # clips QDateEdit/QTimeEdit bottom borders.
                w.setMinimumHeight(34)
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            except Exception:
                pass
            return w

        def _expanding(w: QWidget):
            """Force range widgets to consume the same available width."""
            try:
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                w.setMinimumHeight(34)
            except Exception:
                pass
            return w

        def _fit_h(w: QWidget, height: int = 34) -> QWidget:
            """Fixed row height tall enough for themed QDateEdit/QComboBox frames."""
            try:
                w.setFixedHeight(height)
            except Exception:
                pass
            return w

        def _tune_range_grid(grid: QGridLayout):
            """Standard column sizing so From/To, Min/Max, Price Min/Max align identically."""
            tune_group_layout(grid)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)
            # Columns: 0 label, 1 field, 2 label, 3 field, 4 enable, 5 help
            grid.setColumnMinimumWidth(0, 46)  # fits "From:" / "Min:"
            grid.setColumnMinimumWidth(2, 34)  # fits "To:" / "Max:"
            grid.setColumnMinimumWidth(4, 70)  # fits "Enable"
            grid.setColumnMinimumWidth(5, 22)  # fits "(?)"
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)

        if not self._embedded:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            container = QWidget()
            layout = QVBoxLayout(container)
        else:
            # Embedded mode: no scroll wrapper, widgets go directly in layout
            container = None
            layout = outer_layout

        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        title = QLabel("Filters")
        apply_font(title, "Segoe UI", 14, QFont.Weight.Bold)
        layout.addWidget(title)

        # Named presets (table sidebar only — not the embedded area-page copy)
        if not self._embedded:
            self.preset_combo = QComboBox()
            self.preset_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self.preset_combo.setMinimumHeight(28)
            self.preset_combo.setToolTip(
                "Saved filter presets — pick one to load and apply"
            )
            layout.addWidget(self.preset_combo)

            preset_btns = QHBoxLayout()
            preset_btns.setSpacing(8)
            self.preset_save_btn = QPushButton("Save")
            self.preset_save_btn.setToolTip(
                "Overwrite the selected preset with current filters "
                "(or Save as… if none selected)"
            )
            self.preset_save_btn.setMinimumWidth(64)
            self.preset_save_btn.setMinimumHeight(28)
            preset_btns.addWidget(self.preset_save_btn)

            self.preset_save_as_btn = QPushButton("Save as…")
            self.preset_save_as_btn.setToolTip(
                "Save current filters under a new preset name"
            )
            self.preset_save_as_btn.setMinimumWidth(72)
            self.preset_save_as_btn.setMinimumHeight(28)
            preset_btns.addWidget(self.preset_save_as_btn)
            layout.addLayout(preset_btns)

            preset_btns2 = QHBoxLayout()
            preset_btns2.setSpacing(8)
            self.preset_rename_btn = QPushButton("Rename")
            self.preset_rename_btn.setToolTip("Rename the selected preset")
            self.preset_rename_btn.setMinimumWidth(64)
            self.preset_rename_btn.setMinimumHeight(28)
            preset_btns2.addWidget(self.preset_rename_btn)

            self.preset_delete_btn = QPushButton("Delete")
            self.preset_delete_btn.setToolTip("Delete the selected preset")
            self.preset_delete_btn.setMinimumWidth(64)
            self.preset_delete_btn.setMinimumHeight(28)
            preset_btns2.addWidget(self.preset_delete_btn)
            preset_btns2.addStretch(1)
            layout.addLayout(preset_btns2)

            self._preset_loading = False
            self._reload_preset_combo()
            self.preset_combo.currentIndexChanged.connect(self._on_preset_selected)
            self.preset_save_btn.clicked.connect(self._on_preset_save)
            self.preset_save_as_btn.clicked.connect(self._on_preset_save_as)
            self.preset_rename_btn.clicked.connect(self._on_preset_rename)
            self.preset_delete_btn.clicked.connect(self._on_preset_delete)
            self._restore_last_used_preset()

        # -- Text search --
        text_group = compact_group(QGroupBox("Text Search"))
        text_layout = QVBoxLayout(text_group)
        tune_group_layout(text_layout)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Search text content...")
        self.text_input.setClearButtonEnabled(True)
        _control_h(self.text_input)
        text_row = QHBoxLayout()
        text_row.setContentsMargins(0, 0, 0, 0)
        text_row.setSpacing(6)
        text_row.addWidget(_make_help_btn("filters-text-search"))
        text_row.addWidget(self.text_input, stretch=1)
        text_layout.addLayout(text_row)
        self.fullstring_check = QCheckBox("Full string match")
        text_layout.addWidget(self.fullstring_check)
        layout.addWidget(text_group)

        # -- Media type (same single-row pattern as Areas → Media Types) --
        media_group = compact_group(QGroupBox("Media Type"))
        media_layout = QHBoxLayout(media_group)
        tune_group_layout(media_layout)
        media_layout.setSpacing(16)
        media_layout.addWidget(_make_help_btn("filters-media-type"))
        self.media_checks = {}
        for mt in ["audios", "images", "videos"]:
            cb = QCheckBox(mt.capitalize())
            cb.setChecked(True)
            media_layout.addWidget(cb)
            self.media_checks[mt] = cb
        media_layout.addStretch()
        layout.addWidget(media_group)

        # -- Response type (3-column grid like Content Areas) --
        resp_group = compact_group(QGroupBox("Response Type"))
        resp_outer = QVBoxLayout(resp_group)
        tune_group_layout(resp_outer)
        resp_hint = QHBoxLayout()
        resp_hint.setContentsMargins(0, 0, 0, 0)
        resp_hint.addWidget(_make_help_btn("filters-response-type"))
        resp_hint.addStretch()
        resp_outer.addLayout(resp_hint)
        resp_grid = QGridLayout()
        resp_grid.setHorizontalSpacing(16)
        resp_grid.setVerticalSpacing(6)
        self.resp_checks = {}
        for i, rt in enumerate(
            ["pinned", "archived", "timeline", "stories", "highlights", "streams"]
        ):
            cb = QCheckBox(rt.capitalize())
            cb.setChecked(True)
            resp_grid.addWidget(cb, i // 3, i % 3)
            self.resp_checks[rt] = cb
        resp_outer.addLayout(resp_grid)
        layout.addWidget(resp_group)

        # -- Downloaded / Unlocked --
        status_group = compact_group(QGroupBox("Status"))
        status_layout = QVBoxLayout(status_group)
        tune_group_layout(status_layout)

        # Use a grid so the checkbox columns align neatly.
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(16)
        status_grid.setVerticalSpacing(6)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        status_grid.setColumnStretch(2, 1)

        dl_label = QLabel("Downloaded:")
        dl_label.setProperty("muted", True)
        dl_hdr = QHBoxLayout()
        dl_hdr.setContentsMargins(0, 0, 0, 0)
        dl_hdr.setSpacing(6)
        dl_hdr.addWidget(dl_label)
        dl_hdr.addWidget(_make_help_btn("filters-status"))
        dl_hdr.addStretch()
        status_grid.addLayout(dl_hdr, 0, 0, 1, 3)

        self.dl_true = QCheckBox("True")
        self.dl_true.setChecked(True)
        self.dl_false = QCheckBox("False")
        self.dl_false.setChecked(True)
        self.dl_no = QCheckBox("No (Paid)")
        self.dl_no.setChecked(True)
        status_grid.addWidget(self.dl_true, 1, 0)
        status_grid.addWidget(self.dl_false, 1, 1)
        status_grid.addWidget(self.dl_no, 1, 2)

        ul_label = QLabel("Unlocked:")
        ul_label.setProperty("muted", True)
        status_grid.addWidget(ul_label, 2, 0, 1, 3)

        self.ul_true = QCheckBox("True")
        self.ul_true.setChecked(True)
        self.ul_false = QCheckBox("False")
        self.ul_false.setChecked(True)
        self.ul_not_paid = QCheckBox("Locked")
        self.ul_not_paid.setChecked(True)
        status_grid.addWidget(self.ul_true, 3, 0)
        status_grid.addWidget(self.ul_false, 3, 1)
        status_grid.addWidget(self.ul_not_paid, 3, 2)

        status_layout.addLayout(status_grid)
        layout.addWidget(status_group)

        # -- Date range --
        date_group = compact_group(QGroupBox("Post Date Range"))
        date_vbox = QVBoxLayout(date_group)
        tune_group_layout(date_vbox)

        _rel_units = ["hours ago", "days ago", "weeks ago", "months ago"]
        # Label column width: "After:"/"Before:" + inline ? on After only.
        _date_lbl_w = 74

        # After (--after) row
        after_row = QHBoxLayout()
        after_row.setSpacing(6)
        after_lbl_wrap = QWidget()
        after_lbl_wrap.setFixedWidth(_date_lbl_w)
        after_lbl_h = QHBoxLayout(after_lbl_wrap)
        after_lbl_h.setContentsMargins(0, 0, 0, 0)
        after_lbl_h.setSpacing(4)
        after_lbl = QLabel("After:")
        after_lbl_h.addWidget(after_lbl)
        after_lbl_h.addWidget(_make_help_btn("filters-date-range"))
        after_lbl_h.addStretch()
        after_row.addWidget(after_lbl_wrap)

        self.after_mode_combo = QComboBox()
        self.after_mode_combo.addItems(["Fixed date", "Relative"])
        self.after_mode_combo.setFixedWidth(100)
        _fit_h(self.after_mode_combo)
        self.after_mode_combo.setToolTip(
            "Fixed date: pick a specific calendar date\n"
            "Relative: computed fresh at each scrape start (e.g. '7 days ago')"
        )
        after_row.addWidget(self.after_mode_combo)

        self.min_date = QDateEdit()
        self.min_date.setCalendarPopup(True)
        self.min_date.setDisplayFormat("M/d/yyyy")
        self.min_date.setDate(QDate(2000, 1, 1))
        self.min_date.setMinimumWidth(88)
        _fit_h(self.min_date)
        self.min_date.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        _after_rel = QWidget()
        _after_rel_h = QHBoxLayout(_after_rel)
        _after_rel_h.setContentsMargins(0, 0, 0, 0)
        _after_rel_h.setSpacing(4)
        self.after_rel_value = QSpinBox()
        self.after_rel_value.setRange(1, 9999)
        self.after_rel_value.setValue(1)
        self.after_rel_value.setToolTip("Number of units ago")
        _fit_h(self.after_rel_value)
        _after_rel_h.addWidget(self.after_rel_value)
        self.after_rel_unit = QComboBox()
        self.after_rel_unit.addItems(_rel_units)
        self.after_rel_unit.setCurrentText("days ago")
        _fit_h(self.after_rel_unit)
        _after_rel_h.addWidget(self.after_rel_unit)

        self.after_date_stack = QStackedWidget()
        self.after_date_stack.setMinimumWidth(88)
        _fit_h(self.after_date_stack)
        self.after_date_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.after_date_stack.addWidget(self.min_date)   # index 0 = fixed
        self.after_date_stack.addWidget(_after_rel)       # index 1 = relative
        after_row.addWidget(self.after_date_stack, 1)

        self.after_enabled = QCheckBox("Enable")
        self.after_enabled.setToolTip(
            "Apply the After date — only show/scrape content posted on or after this date.\n"
            "Equivalent to the --after CLI flag."
        )
        after_row.addWidget(self.after_enabled)
        date_vbox.addLayout(after_row)

        # Before (--before) row
        before_row = QHBoxLayout()
        before_row.setSpacing(6)
        before_lbl = QLabel("Before:")
        before_lbl.setFixedWidth(_date_lbl_w)
        before_row.addWidget(before_lbl)

        self.before_mode_combo = QComboBox()
        self.before_mode_combo.addItems(["Fixed date", "Relative"])
        self.before_mode_combo.setFixedWidth(100)
        _fit_h(self.before_mode_combo)
        self.before_mode_combo.setToolTip(
            "Fixed date: pick a specific calendar date\n"
            "Relative: computed fresh at each scrape start (e.g. '30 days ago')"
        )
        before_row.addWidget(self.before_mode_combo)

        self.max_date = QDateEdit()
        self.max_date.setCalendarPopup(True)
        self.max_date.setDisplayFormat("M/d/yyyy")
        self.max_date.setDate(QDate.currentDate())
        self.max_date.setMinimumWidth(88)
        _fit_h(self.max_date)
        self.max_date.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )

        _before_rel = QWidget()
        _before_rel_h = QHBoxLayout(_before_rel)
        _before_rel_h.setContentsMargins(0, 0, 0, 0)
        _before_rel_h.setSpacing(4)
        self.before_rel_value = QSpinBox()
        self.before_rel_value.setRange(1, 9999)
        self.before_rel_value.setValue(1)
        self.before_rel_value.setToolTip("Number of units ago")
        _fit_h(self.before_rel_value)
        _before_rel_h.addWidget(self.before_rel_value)
        self.before_rel_unit = QComboBox()
        self.before_rel_unit.addItems(_rel_units)
        self.before_rel_unit.setCurrentText("days ago")
        _fit_h(self.before_rel_unit)
        _before_rel_h.addWidget(self.before_rel_unit)

        self.before_date_stack = QStackedWidget()
        self.before_date_stack.setMinimumWidth(88)
        _fit_h(self.before_date_stack)
        self.before_date_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.before_date_stack.addWidget(self.max_date)    # index 0 = fixed
        self.before_date_stack.addWidget(_before_rel)      # index 1 = relative
        before_row.addWidget(self.before_date_stack, 1)

        self.before_enabled = QCheckBox("Enable")
        self.before_enabled.setToolTip(
            "Apply the Before date — only show/scrape content posted on or before this date.\n"
            "Equivalent to the --before CLI flag."
        )
        before_row.addWidget(self.before_enabled)
        date_vbox.addLayout(before_row)

        layout.addWidget(date_group)

        # Switch stacks when mode changes
        self.after_mode_combo.currentIndexChanged.connect(self.after_date_stack.setCurrentIndex)
        self.before_mode_combo.currentIndexChanged.connect(self.before_date_stack.setCurrentIndex)
        # Auto-enable each side when the user changes the date/value
        self.min_date.dateChanged.connect(lambda _: self.after_enabled.setChecked(True))
        self.max_date.dateChanged.connect(lambda _: self.before_enabled.setChecked(True))
        self.after_rel_value.valueChanged.connect(lambda _: self.after_enabled.setChecked(True))
        self.before_rel_value.valueChanged.connect(lambda _: self.before_enabled.setChecked(True))

        # -- Duration / Length --
        # Match Price Range structure exactly so Min/Max fields share the same
        # horizontal slots (separate grids diverge because QTimeEdit vs
        # QDoubleSpinBox have different size hints).
        length_group = compact_group(QGroupBox("Duration (Length)"))
        length_vbox = QVBoxLayout(length_group)
        tune_group_layout(length_vbox)

        length_row = QHBoxLayout()
        length_row.setSpacing(10)
        _min_lbl_wrap = QWidget()
        _min_lbl_wrap.setFixedWidth(58)
        _min_lbl_h = QHBoxLayout(_min_lbl_wrap)
        _min_lbl_h.setContentsMargins(0, 0, 0, 0)
        _min_lbl_h.setSpacing(4)
        _min_lbl = QLabel("Min:")
        _min_lbl_h.addWidget(_min_lbl)
        length_help = _make_help_btn("filters-duration")
        length_help.setToolTip("Open help for Duration (Length)")
        _min_lbl_h.addWidget(length_help)
        _min_lbl_h.addStretch()
        length_row.addWidget(_min_lbl_wrap)
        self.min_time = QTimeEdit()
        self.min_time.setDisplayFormat("HH:mm:ss")
        self.min_time.setSpecialValueText("No min")
        self.min_time.setMinimumWidth(100)
        _fit_h(self.min_time)
        length_row.addWidget(_expanding(self.min_time), 1)
        _max_lbl = QLabel("Max:")
        _max_lbl.setFixedWidth(36)
        length_row.addWidget(_max_lbl)
        self.max_time = QTimeEdit()
        self.max_time.setDisplayFormat("HH:mm:ss")
        self.max_time.setSpecialValueText("No max")
        self.max_time.setMinimumWidth(100)
        _fit_h(self.max_time)
        length_row.addWidget(_expanding(self.max_time), 1)
        self.length_enabled = QCheckBox("Enable")
        self.length_enabled.setFixedWidth(70)
        length_row.addWidget(self.length_enabled)
        length_vbox.addLayout(length_row)
        layout.addWidget(length_group)

        # -- Price range --
        price_group = compact_group(QGroupBox("Price Range"))
        price_vbox = QVBoxLayout(price_group)
        tune_group_layout(price_vbox)

        price_row = QHBoxLayout()
        price_row.setSpacing(10)
        _pmin_lbl_wrap = QWidget()
        _pmin_lbl_wrap.setFixedWidth(58)
        _pmin_lbl_h = QHBoxLayout(_pmin_lbl_wrap)
        _pmin_lbl_h.setContentsMargins(0, 0, 0, 0)
        _pmin_lbl_h.setSpacing(4)
        _pmin_lbl = QLabel("Min:")
        _pmin_lbl_h.addWidget(_pmin_lbl)
        price_help = _make_help_btn("filters-price")
        price_help.setToolTip("Open help for Price Range")
        _pmin_lbl_h.addWidget(price_help)
        _pmin_lbl_h.addStretch()
        price_row.addWidget(_pmin_lbl_wrap)
        self.price_min = QDoubleSpinBox()
        self.price_min.setRange(0, 99999)
        self.price_min.setSpecialValueText("No min")
        self.price_min.setDecimals(2)
        self.price_min.setMinimumWidth(100)
        _fit_h(self.price_min)
        price_row.addWidget(_expanding(self.price_min), 1)
        _pmax_lbl = QLabel("Max:")
        _pmax_lbl.setFixedWidth(36)
        price_row.addWidget(_pmax_lbl)
        self.price_max = QDoubleSpinBox()
        self.price_max.setRange(0, 99999)
        self.price_max.setSpecialValueText("No max")
        self.price_max.setDecimals(2)
        self.price_max.setMinimumWidth(100)
        _fit_h(self.price_max)
        price_row.addWidget(_expanding(self.price_max), 1)
        # Same slot as Duration's Enable so the Max fields line up vertically.
        self.price_enabled = QCheckBox("Enable")
        self.price_enabled.setFixedWidth(70)
        self.price_enabled.setToolTip(
            "Apply the Min/Max price filter. Unchecked = ignore price values."
        )
        price_row.addWidget(self.price_enabled)
        price_vbox.addLayout(price_row)
        layout.addWidget(price_group)

        # Auto-enable when the user edits values (same UX as date / length)
        self.min_time.timeChanged.connect(lambda *_: self.length_enabled.setChecked(True))
        self.max_time.timeChanged.connect(lambda *_: self.length_enabled.setChecked(True))
        self.price_min.valueChanged.connect(lambda *_: self.price_enabled.setChecked(True))
        self.price_max.valueChanged.connect(lambda *_: self.price_enabled.setChecked(True))

        # -- Numeric IDs --
        ids_group = compact_group(QGroupBox("ID Filters"))
        ids_layout = QVBoxLayout(ids_group)
        tune_group_layout(ids_layout)

        # Use a QFormLayout so all fields start at the same X position.
        ids_form = QFormLayout()
        ids_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ids_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        ids_form.setHorizontalSpacing(10)
        ids_form.setVerticalSpacing(6)

        self.media_id_input = QLineEdit()
        self.media_id_input.setPlaceholderText("Exact match")
        self.media_id_input.setClearButtonEnabled(True)
        _control_h(self.media_id_input)
        media_id_label = QWidget()
        media_id_label_h = QHBoxLayout(media_id_label)
        media_id_label_h.setContentsMargins(0, 0, 0, 0)
        media_id_label_h.setSpacing(6)
        media_id_label_h.addWidget(QLabel("Media ID:"))
        media_id_label_h.addWidget(_make_help_btn("filters-id"))
        media_id_label_h.addStretch()
        ids_form.addRow(media_id_label, self.media_id_input)

        self.post_id_input = QLineEdit()
        self.post_id_input.setPlaceholderText("Exact match")
        self.post_id_input.setClearButtonEnabled(True)
        _control_h(self.post_id_input)
        ids_form.addRow("Post ID:", self.post_id_input)

        self.post_media_count_input = QSpinBox()
        self.post_media_count_input.setRange(0, 99999)
        self.post_media_count_input.setSpecialValueText("Any")
        self.post_media_count_input.setFixedHeight(28)
        ids_form.addRow("Post Media Count:", self.post_media_count_input)

        self.other_posts_input = QSpinBox()
        self.other_posts_input.setRange(0, 99999)
        self.other_posts_input.setSpecialValueText("Any")
        self.other_posts_input.setFixedHeight(28)
        ids_form.addRow("Other Posts w/ Media:", self.other_posts_input)

        ids_layout.addLayout(ids_form)

        layout.addWidget(ids_group)

        # -- Username --
        user_group = compact_group(QGroupBox("Username"))
        user_layout = QVBoxLayout(user_group)
        tune_group_layout(user_layout)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Filter by username...")
        self.username_input.setClearButtonEnabled(True)
        _control_h(self.username_input)
        user_row = QHBoxLayout()
        user_row.setContentsMargins(0, 0, 0, 0)
        user_row.setSpacing(6)
        user_row.addWidget(_make_help_btn("filters-username"))
        user_row.addWidget(self.username_input, stretch=1)
        user_layout.addLayout(user_row)
        layout.addWidget(user_group)

        if not self._embedded:
            layout.addStretch()
            scroll.setWidget(container)
            outer_layout.addWidget(scroll)

    def collect_state(self):
        """Read all widget values into the FilterState object."""
        s = self.state

        # Text
        s.text_search = self.text_input.text().strip()
        s.full_string_match = self.fullstring_check.isChecked()

        # Media type
        selected_media = {
            mt for mt, cb in self.media_checks.items() if cb.isChecked()
        }
        s.mediatype = selected_media if len(selected_media) < 3 else None

        # Response type
        selected_resp = {
            rt for rt, cb in self.resp_checks.items() if cb.isChecked()
        }
        s.responsetype = selected_resp if len(selected_resp) < 6 else None

        # Downloaded / Unlocked (mixed bool + string values)
        dl_selected = set()
        if self.dl_true.isChecked():
            dl_selected.add(True)
            dl_selected.add("True")
        if self.dl_false.isChecked():
            dl_selected.add(False)
            dl_selected.add("False")
        if self.dl_no.isChecked():
            dl_selected.add("No")
        all_dl_checked = self.dl_true.isChecked() and self.dl_false.isChecked() and self.dl_no.isChecked()
        s.downloaded = dl_selected if not all_dl_checked else None

        ul_selected = set()
        if self.ul_true.isChecked():
            ul_selected.add(True)
            ul_selected.add("True")
        if self.ul_false.isChecked():
            ul_selected.add(False)
            ul_selected.add("False")
        if self.ul_not_paid.isChecked():
            ul_selected.add("Locked")
        all_ul_checked = self.ul_true.isChecked() and self.ul_false.isChecked() and self.ul_not_paid.isChecked()
        s.unlocked = ul_selected if not all_ul_checked else None

        # Date — After and Before controlled independently; relative dates computed fresh each call
        s.mindate = self.get_after_date_str()
        s.maxdate = self.get_before_date_str()

        # Length
        if self.length_enabled.isChecked():
            min_t = self.min_time.time()
            max_t = self.max_time.time()
            if min_t.hour() > 0 or min_t.minute() > 0 or min_t.second() > 0:
                s.min_length = arrow.get(
                    f"{min_t.hour()}:{min_t.minute()}:{min_t.second()}", "h:m:s"
                )
            else:
                s.min_length = None
            if max_t.hour() > 0 or max_t.minute() > 0 or max_t.second() > 0:
                s.max_length = arrow.get(
                    f"{max_t.hour()}:{max_t.minute()}:{max_t.second()}", "h:m:s"
                )
            else:
                s.max_length = None
        else:
            s.min_length = None
            s.max_length = None

        # Price
        if self.price_enabled.isChecked():
            s.min_price = self.price_min.value() if self.price_min.value() > 0 else None
            s.max_price = self.price_max.value() if self.price_max.value() > 0 else None
        else:
            s.min_price = None
            s.max_price = None

        # IDs
        s.media_id = self.media_id_input.text().strip() or None
        s.post_id = self.post_id_input.text().strip() or None
        s.post_media_count = (
            self.post_media_count_input.value()
            if self.post_media_count_input.value() > 0
            else None
        )
        s.other_posts_with_media = (
            self.other_posts_input.value()
            if self.other_posts_input.value() > 0
            else None
        )

        # Username
        s.username = self.username_input.text().strip() or None

        return s

    def reset_all(self):
        """Reset all filter widgets to defaults."""
        self.text_input.clear()
        self.fullstring_check.setChecked(False)
        for cb in self.media_checks.values():
            cb.setChecked(True)
        for cb in self.resp_checks.values():
            cb.setChecked(True)
        self.dl_true.setChecked(True)
        self.dl_false.setChecked(True)
        self.dl_no.setChecked(True)
        self.ul_true.setChecked(True)
        self.ul_false.setChecked(True)
        self.ul_not_paid.setChecked(True)
        for w in (self.min_date, self.max_date):
            w.blockSignals(True)
            w.setDate(w.minimumDate())
            w.blockSignals(False)
        self.after_mode_combo.setCurrentIndex(0)
        self.after_rel_value.setValue(1)
        self.after_rel_unit.setCurrentText("days ago")
        self.after_enabled.setChecked(False)
        self.before_mode_combo.setCurrentIndex(0)
        self.before_rel_value.setValue(1)
        self.before_rel_unit.setCurrentText("days ago")
        self.before_enabled.setChecked(False)
        self.length_enabled.setChecked(False)
        self.price_enabled.setChecked(False)
        self.price_min.setValue(0)
        self.price_max.setValue(0)
        self.media_id_input.clear()
        self.post_id_input.clear()
        self.post_media_count_input.setValue(0)
        self.other_posts_input.setValue(0)
        self.username_input.clear()
        self.state.reset()

    # ------------------------------------------------------------------
    # Filter presets
    # ------------------------------------------------------------------

    def _reload_preset_combo(self, select_name: str | None = None):
        if self._embedded or not getattr(self, "preset_combo", None):
            return
        from ofscraper.gui.utils.filter_presets import preset_names

        self._preset_loading = True
        try:
            current = select_name
            if current is None and self.preset_combo.currentIndex() > 0:
                current = self.preset_combo.currentText()
            self.preset_combo.clear()
            self.preset_combo.addItem("(select preset)")
            for name in preset_names():
                self.preset_combo.addItem(name)
            if current:
                idx = self.preset_combo.findText(current)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)
        finally:
            self._preset_loading = False

    def _on_preset_selected(self, index: int):
        if self._embedded or self._preset_loading:
            return
        if index <= 0:
            return
        name = self.preset_combo.itemText(index)
        try:
            from ofscraper.gui.utils.filter_presets import (
                apply_sidebar_filters,
                get_preset,
                set_last_used,
            )

            entry = get_preset(name)
            if not entry:
                return
            if apply_sidebar_filters(self, entry.get("filters") or {}):
                try:
                    set_last_used(name)
                except Exception:
                    pass
                self.filter_changed.emit()
                try:
                    app_signals.status_message.emit(f"Loaded filter preset: {name}")
                except Exception:
                    pass
        except Exception as e:
            import logging

            logging.getLogger("shared").debug(f"[GUI] Load filter preset failed: {e}")

    def _restore_last_used_preset(self):
        """On sidebar create, load and apply the last-used preset if any."""
        if self._embedded:
            return
        try:
            from ofscraper.gui.utils.filter_presets import (
                apply_sidebar_filters,
                get_last_used,
                get_preset,
            )

            name = get_last_used()
            if not name:
                return
            entry = get_preset(name)
            if not entry:
                return
            self._preset_loading = True
            try:
                idx = self.preset_combo.findText(name)
                if idx >= 0:
                    self.preset_combo.setCurrentIndex(idx)
            finally:
                self._preset_loading = False
            if apply_sidebar_filters(self, entry.get("filters") or {}):
                # Defer emit so the table page can finish connecting filter_changed.
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(0, self.filter_changed.emit)
        except Exception as e:
            import logging

            logging.getLogger("shared").debug(
                f"[GUI] Restore last-used filter preset failed: {e}"
            )

    def _prompt_preset_name(self, title: str, suggested: str = "") -> str | None:
        name, ok = QInputDialog.getText(
            self,
            title,
            "Preset name:",
            text=suggested or "",
        )
        if not ok:
            return None
        name = (name or "").strip()
        if not name:
            QMessageBox.warning(self, title, "Enter a preset name.")
            return None
        return name

    def _save_preset_named(self, name: str, *, overwrite_ok: bool = False) -> bool:
        from ofscraper.gui.utils.filter_presets import (
            export_sidebar_filters,
            preset_names,
            set_last_used,
            upsert_preset,
        )

        names = preset_names()
        if name in names and not overwrite_ok:
            reply = QMessageBox.question(
                self,
                "Overwrite preset?",
                f'A preset named "{name}" already exists. Overwrite it?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        filters = export_sidebar_filters(self)
        entry = upsert_preset(name, filters)
        if not entry:
            QMessageBox.warning(self, "Save preset", "Could not save the preset.")
            return False
        try:
            set_last_used(name)
        except Exception:
            pass
        self._reload_preset_combo(select_name=name)
        try:
            app_signals.status_message.emit(f"Saved filter preset: {name}")
        except Exception:
            pass
        return True

    def _on_preset_save(self):
        """Overwrite selected preset, or fall back to Save as…."""
        if self._embedded:
            return
        if self.preset_combo.currentIndex() > 0:
            name = self.preset_combo.currentText()
            try:
                self._save_preset_named(name, overwrite_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Save preset", str(e))
            return
        self._on_preset_save_as()

    def _on_preset_save_as(self):
        if self._embedded:
            return
        suggested = ""
        if self.preset_combo.currentIndex() > 0:
            suggested = self.preset_combo.currentText()
        name = self._prompt_preset_name("Save filter preset as…", suggested)
        if not name:
            return
        try:
            self._save_preset_named(name, overwrite_ok=False)
        except Exception as e:
            QMessageBox.warning(self, "Save preset", str(e))

    def _on_preset_rename(self):
        if self._embedded:
            return
        if self.preset_combo.currentIndex() <= 0:
            QMessageBox.information(
                self, "Rename preset", "Select a saved preset to rename."
            )
            return
        old_name = self.preset_combo.currentText()
        new_name = self._prompt_preset_name("Rename filter preset", old_name)
        if not new_name:
            return
        if new_name == old_name:
            return
        try:
            from ofscraper.gui.utils.filter_presets import (
                preset_names,
                rename_preset,
                set_last_used,
            )

            if new_name in preset_names() and new_name.lower() != old_name.lower():
                QMessageBox.warning(
                    self,
                    "Rename preset",
                    f'A preset named "{new_name}" already exists.',
                )
                return
            result = rename_preset(old_name, new_name)
            if not result:
                QMessageBox.warning(
                    self, "Rename preset", "Could not rename the preset."
                )
                return
            try:
                set_last_used(result)
            except Exception:
                pass
            self._reload_preset_combo(select_name=result)
            try:
                app_signals.status_message.emit(
                    f'Renamed filter preset to "{result}"'
                )
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "Rename preset", str(e))

    def _on_preset_delete(self):
        if self._embedded:
            return
        if self.preset_combo.currentIndex() <= 0:
            QMessageBox.information(
                self, "Delete preset", "Select a saved preset to delete."
            )
            return
        name = self.preset_combo.currentText()
        reply = QMessageBox.question(
            self,
            "Delete preset",
            f'Delete filter preset "{name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from ofscraper.gui.utils.filter_presets import delete_preset

            if delete_preset(name):
                self._reload_preset_combo()
                try:
                    app_signals.status_message.emit(f"Deleted filter preset: {name}")
                except Exception:
                    pass
            else:
                QMessageBox.warning(self, "Delete preset", "Preset not found.")
        except Exception as e:
            QMessageBox.warning(self, "Delete preset", str(e))

    # ------------------------------------------------------------------
    # Date helper methods
    # ------------------------------------------------------------------

    def get_after_date_str(self):
        """Return the After date as 'YYYY-MM-DD', or None if not enabled."""
        if not self.after_enabled.isChecked():
            return None
        if self.after_mode_combo.currentText() == "Relative":
            return self._compute_relative_date(
                self.after_rel_value.value(), self.after_rel_unit.currentText()
            )
        return self.min_date.date().toString("yyyy-MM-dd")

    def get_before_date_str(self):
        """Return the Before date as 'YYYY-MM-DD', or None if not enabled."""
        if not self.before_enabled.isChecked():
            return None
        if self.before_mode_combo.currentText() == "Relative":
            return self._compute_relative_date(
                self.before_rel_value.value(), self.before_rel_unit.currentText()
            )
        return self.max_date.date().toString("yyyy-MM-dd")

    def _compute_relative_date(self, value, unit):
        """Compute 'N units ago' from now and return as 'YYYY-MM-DD'."""
        try:
            import arrow
            shift = {
                "hours ago": "hours",
                "days ago":  "days",
                "weeks ago": "weeks",
                "months ago": "months",
            }.get(unit, "days")
            return arrow.now().shift(**{shift: -value}).format("YYYY-MM-DD")
        except Exception:
            return None

    def update_field(self, field_name, value):
        """Set a specific filter field value (e.g., from right-click on table cell)."""
        field_name = field_name.lower()
        if field_name == "text":
            self.text_input.setText(str(value))
        elif field_name == "username":
            self.username_input.setText(str(value))
        elif field_name == "media_id":
            self.media_id_input.setText(str(value))
        elif field_name == "post_id":
            self.post_id_input.setText(str(value))

