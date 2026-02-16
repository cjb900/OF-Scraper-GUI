import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
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
            self._button_group.addButton(radio, i)
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

    def _on_action_changed(self, btn_id):
        if 0 <= btn_id < len(ACTION_CHOICES):
            self._selected_actions = ACTION_CHOICES[btn_id][1]

    def _on_next(self):
        if self._selected_actions:
            log.info(f"Actions selected: {self._selected_actions}")
            app_signals.action_selected.emit(self._selected_actions)
        else:
            app_signals.error_occurred.emit(
                "No Action", "Please select an action to continue."
            )
