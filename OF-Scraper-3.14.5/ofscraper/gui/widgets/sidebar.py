import re

import arrow
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from ofscraper.gui.signals import app_signals


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
            if self.mindate and self.maxdate:
                return test_date.is_between(
                    arrow.get(self.mindate), arrow.get(self.maxdate), bounds="[]"
                )
            elif self.mindate:
                return test_date >= arrow.get(self.mindate)
            elif self.maxdate:
                return test_date <= arrow.get(self.maxdate)
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

        # Keep input controls visually aligned across different widgets.
        # (QLineEdit/QSpinBox/QDateEdit/etc have slightly different native heights otherwise.)
        self.setStyleSheet(
            """
            QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QComboBox {
                min-height: 28px;
            }
            """
        )

        def _expanding(w: QWidget):
            """Force range widgets to consume the same available width."""
            try:
                w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            except Exception:
                pass
            return w

        def _tune_range_grid(grid: QGridLayout):
            """Standard column sizing so From/To, Min/Max, Price Min/Max align identically."""
            try:
                grid.setContentsMargins(8, 6, 8, 6)
            except Exception:
                pass
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
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
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # -- Text search --
        text_group = QGroupBox("Text Search")
        text_layout = QVBoxLayout(text_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-text-search"))
        text_layout.addLayout(h)
        self.text_input = QLineEdit()
        self.text_input.setPlaceholderText("Search text content...")
        self.text_input.setClearButtonEnabled(True)
        text_layout.addWidget(self.text_input)
        self.fullstring_check = QCheckBox("Full string match")
        text_layout.addWidget(self.fullstring_check)
        layout.addWidget(text_group)

        # -- Media type --
        media_group = QGroupBox("Media Type")
        media_layout = QVBoxLayout(media_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-media-type"))
        media_layout.addLayout(h)
        self.media_checks = {}
        for mt in ["audios", "images", "videos"]:
            cb = QCheckBox(mt.capitalize())
            cb.setChecked(True)
            media_layout.addWidget(cb)
            self.media_checks[mt] = cb
        layout.addWidget(media_group)

        # -- Response type --
        resp_group = QGroupBox("Response Type")
        resp_layout = QVBoxLayout(resp_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-response-type"))
        resp_layout.addLayout(h)
        self.resp_checks = {}
        for rt in ["pinned", "archived", "timeline", "stories", "highlights", "streams"]:
            cb = QCheckBox(rt.capitalize())
            cb.setChecked(True)
            resp_layout.addWidget(cb)
            self.resp_checks[rt] = cb
        layout.addWidget(resp_group)

        # -- Downloaded / Unlocked --
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-status"))
        status_layout.addLayout(h)

        # Use a grid so the checkbox columns align neatly.
        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(16)
        status_grid.setVerticalSpacing(8)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        status_grid.setColumnStretch(2, 1)

        dl_label = QLabel("Downloaded:")
        dl_label.setProperty("muted", True)
        status_grid.addWidget(dl_label, 0, 0, 1, 3)

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
        date_group = QGroupBox("Post Date Range")
        date_layout = QGridLayout(date_group)
        _tune_range_grid(date_layout)
        date_help = _make_help_btn("filters-date-range")
        date_help.setToolTip("Open help for Post Date Range")
        self.min_date = QDateEdit()
        self.min_date.setCalendarPopup(True)
        self.min_date.setSpecialValueText("No min")
        self.min_date.setMinimumDate(self.min_date.minimumDate())
        date_layout.addWidget(QLabel("From:"), 0, 0)
        date_layout.addWidget(_expanding(self.min_date), 0, 1)
        self.max_date = QDateEdit()
        self.max_date.setCalendarPopup(True)
        self.max_date.setSpecialValueText("No max")
        date_layout.addWidget(QLabel("To:"), 0, 2)
        date_layout.addWidget(_expanding(self.max_date), 0, 3)
        self.date_enabled = QCheckBox("Enable")
        date_layout.addWidget(self.date_enabled, 0, 4)
        date_layout.addWidget(date_help, 0, 5)
        layout.addWidget(date_group)

        # -- Duration / Length --
        length_group = QGroupBox("Duration (Length)")
        length_layout = QGridLayout(length_group)
        _tune_range_grid(length_layout)
        length_help = _make_help_btn("filters-duration")
        length_help.setToolTip("Open help for Duration (Length)")
        self.min_time = QTimeEdit()
        self.min_time.setDisplayFormat("HH:mm:ss")
        self.min_time.setSpecialValueText("No min")
        length_layout.addWidget(QLabel("Min:"), 0, 0)
        length_layout.addWidget(_expanding(self.min_time), 0, 1)
        self.max_time = QTimeEdit()
        self.max_time.setDisplayFormat("HH:mm:ss")
        self.max_time.setSpecialValueText("No max")
        length_layout.addWidget(QLabel("Max:"), 0, 2)
        length_layout.addWidget(_expanding(self.max_time), 0, 3)
        self.length_enabled = QCheckBox("Enable")
        length_layout.addWidget(self.length_enabled, 0, 4)
        length_layout.addWidget(length_help, 0, 5)
        layout.addWidget(length_group)

        # -- Price range --
        price_group = QGroupBox("Price Range")
        price_layout = QGridLayout(price_group)
        _tune_range_grid(price_layout)
        price_help = _make_help_btn("filters-price")
        price_help.setToolTip("Open help for Price Range")
        self.price_min = QDoubleSpinBox()
        self.price_min.setRange(0, 99999)
        self.price_min.setSpecialValueText("No min")
        self.price_min.setDecimals(2)
        price_layout.addWidget(QLabel("Min:"), 0, 0)
        price_layout.addWidget(_expanding(self.price_min), 0, 1)
        self.price_max = QDoubleSpinBox()
        self.price_max.setRange(0, 99999)
        self.price_max.setSpecialValueText("No max")
        self.price_max.setDecimals(2)
        price_layout.addWidget(QLabel("Max:"), 0, 2)
        price_layout.addWidget(_expanding(self.price_max), 0, 3)
        price_layout.addWidget(price_help, 0, 5)
        layout.addWidget(price_group)

        # -- Numeric IDs --
        ids_group = QGroupBox("ID Filters")
        ids_layout = QVBoxLayout(ids_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-id"))
        ids_layout.addLayout(h)

        # Use a QFormLayout so all fields start at the same X position.
        ids_form = QFormLayout()
        ids_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ids_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        ids_form.setHorizontalSpacing(10)
        ids_form.setVerticalSpacing(10)

        self.media_id_input = QLineEdit()
        self.media_id_input.setPlaceholderText("Exact match")
        self.media_id_input.setClearButtonEnabled(True)
        ids_form.addRow("Media ID:", self.media_id_input)

        self.post_id_input = QLineEdit()
        self.post_id_input.setPlaceholderText("Exact match")
        self.post_id_input.setClearButtonEnabled(True)
        ids_form.addRow("Post ID:", self.post_id_input)

        self.post_media_count_input = QSpinBox()
        self.post_media_count_input.setRange(0, 99999)
        self.post_media_count_input.setSpecialValueText("Any")
        ids_form.addRow("Post Media Count:", self.post_media_count_input)

        self.other_posts_input = QSpinBox()
        self.other_posts_input.setRange(0, 99999)
        self.other_posts_input.setSpecialValueText("Any")
        ids_form.addRow("Other Posts w/ Media:", self.other_posts_input)

        ids_layout.addLayout(ids_form)

        layout.addWidget(ids_group)

        # -- Username --
        user_group = QGroupBox("Username")
        user_layout = QVBoxLayout(user_group)
        h = QHBoxLayout()
        h.addStretch()
        h.addWidget(_make_help_btn("filters-username"))
        user_layout.addLayout(h)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Filter by username...")
        self.username_input.setClearButtonEnabled(True)
        user_layout.addWidget(self.username_input)
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

        # Date
        if self.date_enabled.isChecked():
            s.mindate = self.min_date.date().toString("yyyy-MM-dd")
            s.maxdate = self.max_date.date().toString("yyyy-MM-dd")
        else:
            s.mindate = None
            s.maxdate = None

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
        s.min_price = self.price_min.value() if self.price_min.value() > 0 else None
        s.max_price = self.price_max.value() if self.price_max.value() > 0 else None

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
        self.date_enabled.setChecked(False)
        self.length_enabled.setChecked(False)
        self.price_min.setValue(0)
        self.price_max.setValue(0)
        self.media_id_input.clear()
        self.post_id_input.clear()
        self.post_media_count_input.setValue(0)
        self.other_posts_input.setValue(0)
        self.username_input.clear()
        self.state.reset()

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

