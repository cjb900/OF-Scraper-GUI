import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QRadioButton,
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
]

_ACTION_TIPS = {
    "Download content from a user": "Scrape media from selected content areas and build the download table.\nYou can then select items to download from the table.",
    "Like a selection of a user's posts": "Automatically like posts in the selected content areas for chosen models.",
    "Unlike a selection of a user's posts": "Automatically unlike previously liked posts in the selected content areas.",
    "Download + Like": "Scrape and download content, then also like the posts.",
    "Download + Unlike": "Scrape and download content, then also unlike previously liked posts.",
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


class ActionPage(QWidget):
    """Action selection page — replaces the InquirerPy action prompt."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._selected_actions = set()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

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

        for i, (label, actions) in enumerate(ACTION_CHOICES):
            radio = QRadioButton(label)
            radio.setFont(QFont("Segoe UI", 13))
            radio.setStyleSheet("QRadioButton { padding: 8px 4px; }")
            radio.setProperty("actions", actions)
            radio.setToolTip(_ACTION_TIPS.get(label, ""))
            self._button_group.addButton(radio, i)
            layout.addWidget(radio)

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

        for i, (label, actions) in enumerate(CHECK_CHOICES):
            radio = QRadioButton(label)
            radio.setFont(QFont("Segoe UI", 13))
            radio.setStyleSheet("QRadioButton { padding: 8px 4px; }")
            radio.setProperty("actions", actions)
            radio.setToolTip(_CHECK_TIPS.get(label, ""))
            self._button_group.addButton(radio, len(ACTION_CHOICES) + i)
            layout.addWidget(radio)

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

    def reset_to_defaults(self):
        """Reset action selection to the first option (default)."""
        first = self._button_group.button(0)
        if first:
            first.setChecked(True)
            self._selected_actions = ACTION_CHOICES[0][1]

    def _on_action_changed(self, btn_id):
        if 0 <= btn_id < len(ALL_CHOICES):
            self._selected_actions = ALL_CHOICES[btn_id][1]

    def _on_next(self):
        if self._selected_actions:
            log.info(f"Actions selected: {self._selected_actions}")
            app_signals.action_selected.emit(self._selected_actions)
        else:
            app_signals.error_occurred.emit(
                "No Action", "Please select an action to continue."
            )
