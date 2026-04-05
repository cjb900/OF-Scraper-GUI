import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

ACTION_CHOICES = [
    ("Download content from a user", {"download"}),
    ("Like a selection of a user's posts", {"like"}),
    ("Unlike a selection of a user's posts", {"unlike"}),
    ("Download + Like", {"like", "download"}),
    ("Download + Unlike", {"unlike", "download"}),
    ("Scrape individual posts by URL or Post ID", {"manual_url"}),
]

_ACTION_TIPS = {
    "Download content from a user": "Scrape media from selected content areas and build the download table.\nYou can then select items to download from the table.",
    "Like a selection of a user's posts": "Automatically like posts in the selected content areas for chosen models.",
    "Unlike a selection of a user's posts": "Automatically unlike previously liked posts in the selected content areas.",
    "Download + Like": "Scrape and download content, then also like the posts.",
    "Download + Unlike": "Scrape and download content, then also unlike previously liked posts.",
    "Scrape individual posts by URL or Post ID": (
        "Download specific posts by providing OnlyFans post URLs or post IDs.\n"
        "Model and area selection are skipped — enter URLs directly on the next page.\n"
        "Equivalent to the TUI 'manual --url' command."
    ),
}

CHECK_CHOICES = [
    ("Check posts: build table of timeline/pinned/archived media", {"post_check"}),
    ("Check messages: build table of message & paid media", {"msg_check"}),
    ("Check paid content: build table of all paid/purchased media", {"paid_check"}),
    ("Check stories: build table of story & highlight media", {"story_check"}),
]

_CHECK_TIPS = {
    "Check posts: build table of timeline/pinned/archived media":
        "Fetches timeline, pinned, archived, label, and stream posts for the selected models\n"
        "and builds an interactive table showing downloaded/unlocked status.\n"
        "Select items in the table then click 'Send Downloads' to download them.",
    "Check messages: build table of message & paid media":
        "Fetches direct messages and paid content for the selected models\n"
        "and builds a browsable table. Select items to download.",
    "Check paid content: build table of all paid/purchased media":
        "Fetches all purchased/paid content for the selected models\n"
        "and builds a browsable table. Select items to download.",
    "Check stories: build table of story & highlight media":
        "Fetches stories and highlights for the selected models\n"
        "and builds a browsable table. Select items to download.",
}

ALL_CHOICES = ACTION_CHOICES + CHECK_CHOICES

# Message filter values emitted via signal
MSG_FILTER_PAID_ONLY = "paid_only"
MSG_FILTER_FREE_ONLY = "free_only"
MSG_FILTER_ALL = "all"


class ActionPage(QWidget):
    """Action selection page — replaces the InquirerPy action prompt."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._selected_actions = set()
        self._setup_ui()

    def _setup_ui(self):
        # Outer 0-margin layout so plugin bars can be injected at index 0
        # above the scroll area (matching area_selector_page structure).
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Header
        header = QLabel("Select Action")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel("Choose what you want to do with the selected models.")
        subtitle.setProperty("subheading", True)
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Action radio buttons
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        # Build userlist sub-widget — inserted after the Download radio
        self._userlist_widget = self._build_userlist_widget()

        for i, (label, actions) in enumerate(ACTION_CHOICES):
            radio = QRadioButton(label)
            radio.setFont(QFont("Segoe UI", 13))
            radio.setStyleSheet("QRadioButton { padding: 8px 4px; }")
            radio.setProperty("actions", actions)
            radio.setToolTip(_ACTION_TIPS.get(label, ""))
            self._button_group.addButton(radio, i)
            layout.addWidget(radio)
            if i == 0:  # "Download content from a user"
                layout.addWidget(self._userlist_widget)

        # Separator between action modes and check modes
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addSpacing(8)
        layout.addWidget(sep)

        check_label = QLabel("Check Modes  (browse & selectively download)")
        check_label.setFont(QFont("Segoe UI", 11))
        check_label.setProperty("subheading", True)
        layout.addWidget(check_label)

        # Build the message filter sub-widget (hidden until msg_check is selected)
        self._msg_filter_widget = self._build_msg_filter_widget()

        for i, (label, actions) in enumerate(CHECK_CHOICES):
            radio = QRadioButton(label)
            radio.setFont(QFont("Segoe UI", 13))
            radio.setStyleSheet("QRadioButton { padding: 8px 4px; }")
            radio.setProperty("actions", actions)
            radio.setToolTip(_CHECK_TIPS.get(label, ""))
            self._button_group.addButton(radio, len(ACTION_CHOICES) + i)
            layout.addWidget(radio)

            if "msg_check" in actions:
                layout.addWidget(self._msg_filter_widget)

        # Select first by default
        first = self._button_group.button(0)
        if first:
            first.setChecked(True)
            self._selected_actions = ACTION_CHOICES[0][1]

        self._button_group.idClicked.connect(self._on_action_changed)

        layout.addStretch()

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.next_btn = StyledButton("Next  >>", primary=True)
        self.next_btn.setFixedWidth(160)
        self.next_btn.clicked.connect(self._on_next)
        btn_layout.addWidget(self.next_btn)

        layout.addLayout(btn_layout)

    def _build_userlist_widget(self):
        """Build the User List Filter sub-widget shown under Download."""
        container = QWidget()
        container.setVisible(True)  # visible by default (Download is default)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 0, 0, 4)
        inner.setSpacing(4)

        hint = QLabel(
            "Filter which models are loaded from the OnlyFans API by your custom list(s).\n"
            "Leave blank to load all subscribed models (default)."
        )
        hint.setFont(QFont("Segoe UI", 10))
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        inner.addWidget(hint)

        row = QHBoxLayout()
        lbl = QLabel("User Lists:")
        lbl.setFont(QFont("Segoe UI", 11))
        row.addWidget(lbl)

        self._userlist_input = QLineEdit()
        self._userlist_input.setPlaceholderText("e.g.  testing, vip  (comma-separated list names)")
        self._userlist_input.setToolTip(
            "Enter one or more OnlyFans list names separated by commas.\n"
            "Only models who are members of these lists will be loaded.\n"
            "List names are case-insensitive.\n"
            "Leave blank to load all subscribed models."
        )
        # Pre-populate from CLI args (e.g. --ul testing), stripping reserved names
        try:
            import ofscraper.utils.settings as _s_init
            _ul_init = getattr(_s_init.get_settings(), "userlist", None) or []
            _ul_init = self._strip_reserved_lists([u.lower() for u in _ul_init if u])
            if _ul_init:
                self._userlist_input.setText(", ".join(_ul_init))
        except Exception:
            pass
        row.addWidget(self._userlist_input)
        inner.addLayout(row)

        return container

    @staticmethod
    def _strip_reserved_lists(names):
        """Remove ofscraper's built-in reserved list names ('main', 'ofscraper.main')."""
        try:
            import ofscraper.utils.of_env.of_env as _of_env
            reserved = {
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST") or "").lower(),
                (_of_env.getattr("OFSCRAPER_RESERVED_LIST_ALT") or "").lower(),
            }
        except Exception:
            reserved = {"ofscraper.main", "main"}
        return [n for n in names if n.lower() not in reserved]

    def get_userlist(self):
        """Return the current userlist as a list of lowercase strings (empty = no filter)."""
        text = self._userlist_input.text().strip()
        if not text:
            return []
        raw = [u.strip().lower() for u in text.split(",") if u.strip()]
        return self._strip_reserved_lists(raw)

    def _apply_userlist_to_args(self):
        """Write the current userlist into ofscraper args and refresh settings cache."""
        try:
            import ofscraper.utils.args.accessors.read as _ra
            import ofscraper.utils.settings as _settings_mod
            _ul = self.get_userlist()
            _ra.retriveArgs().userlist = _ul
            _settings_mod.update_settings()
            if _ul:
                log.info(f"[GUI] User list filter set: {_ul}")
            else:
                log.info("[GUI] No user list filter — loading all subscribed models")
        except Exception as e:
            log.warning(f"[GUI] Could not apply userlist to args: {e}")

    def _build_msg_filter_widget(self):
        """Build the three-option message filter sub-widget."""
        container = QWidget()
        container.setVisible(False)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 0, 0, 4)
        inner.setSpacing(2)

        label = QLabel("Show messages:")
        label.setFont(QFont("Segoe UI", 10))
        label.setProperty("muted", True)
        inner.addWidget(label)

        self._msg_filter_group = QButtonGroup(container)
        self._msg_filter_group.setExclusive(True)

        _options = [
            (MSG_FILTER_PAID_ONLY, "Paid / PPV only",
             "Show only paid and PPV messages — hides free messages.\nLocked (unpurchased) items are always shown."),
            (MSG_FILTER_FREE_ONLY, "Free messages only",
             "Show only free messages — hides paid and PPV content."),
            (MSG_FILTER_ALL, "All messages",
             "Show all messages: both free and paid/PPV."),
        ]

        self._msg_filter_radios = {}
        for idx, (value, text, tip) in enumerate(_options):
            rb = QRadioButton(text)
            rb.setFont(QFont("Segoe UI", 11))
            rb.setToolTip(tip)
            rb.setProperty("msg_filter_value", value)
            self._msg_filter_group.addButton(rb, idx)
            inner.addWidget(rb)
            self._msg_filter_radios[value] = rb

        # Default: paid only
        self._msg_filter_radios[MSG_FILTER_PAID_ONLY].setChecked(True)
        self._msg_filter_group.idClicked.connect(self._on_msg_filter_changed)

        return container

    def reset_to_defaults(self):
        """Reset action selection to the first option (default)."""
        first = self._button_group.button(0)
        if first:
            first.setChecked(True)
            self._selected_actions = ACTION_CHOICES[0][1]
        self._msg_filter_widget.setVisible(False)
        self._msg_filter_radios[MSG_FILTER_PAID_ONLY].setChecked(True)
        self._userlist_input.clear()
        self._userlist_widget.setVisible(True)

    def _on_action_changed(self, btn_id):
        if 0 <= btn_id < len(ALL_CHOICES):
            self._selected_actions = ALL_CHOICES[btn_id][1]
        self._msg_filter_widget.setVisible("msg_check" in self._selected_actions)
        # Show userlist widget only for "Download content from a user" (btn_id 0)
        self._userlist_widget.setVisible(btn_id == 0)

    def _on_msg_filter_changed(self, btn_id):
        checked = self._msg_filter_group.checkedButton()
        if checked:
            value = checked.property("msg_filter_value")
            app_signals.msg_check_include_free_toggled.emit(value)

    def _on_next(self):
        if self._selected_actions:
            # Apply userlist BEFORE emitting so model loading uses the correct filter
            self._apply_userlist_to_args()
            log.info(f"Actions selected: {self._selected_actions}")
            app_signals.action_selected.emit(self._selected_actions)
        else:
            app_signals.error_occurred.emit(
                "No Action", "Please select an action to continue."
            )
