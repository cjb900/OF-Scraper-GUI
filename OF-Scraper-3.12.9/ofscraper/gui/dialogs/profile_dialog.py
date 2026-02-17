import logging
import pathlib
import shutil

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")


class ProfilePage(QWidget):
    """Profile manager page — replaces the InquirerPy profile prompts."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._setup_ui()
        self._load_profiles()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Header
        header = QLabel("Profile Manager")
        header.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Manage your profiles. Each profile has its own auth.json and data directories."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Current profile indicator
        self.current_label = QLabel("Current profile: loading...")
        self.current_label.setFont(QFont("Segoe UI", 13))
        self.current_label.setStyleSheet(f"color: {c('blue')};")
        app_signals.theme_changed.connect(
            lambda _: self.current_label.setStyleSheet(f"color: {c('blue')};")
        )
        layout.addWidget(self.current_label)

        layout.addSpacing(8)

        # Profile list + buttons
        content_layout = QHBoxLayout()

        self.profile_list = QListWidget()
        self.profile_list.setAlternatingRowColors(True)
        self.profile_list.setMinimumWidth(300)
        content_layout.addWidget(self.profile_list, stretch=2)

        # Action buttons
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(8)

        self.set_default_btn = StyledButton("Set as Default", primary=True)
        self.set_default_btn.clicked.connect(self._set_default)
        btn_layout.addWidget(self.set_default_btn)

        self.create_btn = StyledButton("Create Profile")
        self.create_btn.clicked.connect(self._create_profile)
        btn_layout.addWidget(self.create_btn)

        self.rename_btn = StyledButton("Rename")
        self.rename_btn.clicked.connect(self._rename_profile)
        btn_layout.addWidget(self.rename_btn)

        self.delete_btn = StyledButton("Delete", danger=True)
        self.delete_btn.clicked.connect(self._delete_profile)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()

        self.refresh_btn = StyledButton("Refresh")
        self.refresh_btn.clicked.connect(self._load_profiles)
        btn_layout.addWidget(self.refresh_btn)

        content_layout.addLayout(btn_layout, stretch=0)
        layout.addLayout(content_layout)
        layout.addStretch()

    def _load_profiles(self):
        """Load profile list from disk."""
        self.profile_list.clear()
        try:
            from ofscraper.utils.profiles.data import get_profile_names
            from ofscraper.utils.profiles.data import get_active_profile

            profiles = get_profile_names()
            active = get_active_profile()

            self.current_label.setText(f"Current profile: {active}")

            for name in profiles:
                item = QListWidgetItem(name)
                if name == active:
                    item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                    item.setForeground(Qt.GlobalColor.cyan)
                    item.setText(f"{name} (active)")
                else:
                    item.setFont(QFont("Segoe UI", 12))
                self.profile_list.addItem(item)

            app_signals.status_message.emit(f"Found {len(profiles)} profiles")
        except Exception as e:
            log.error(f"Failed to load profiles: {e}")
            app_signals.status_message.emit(f"Failed to load profiles: {e}")

    def _get_selected_profile(self):
        """Get the selected profile name (strip active marker)."""
        item = self.profile_list.currentItem()
        if not item:
            return None
        name = item.text().replace(" (active)", "")
        return name

    def _set_default(self):
        """Set selected profile as the default."""
        name = self._get_selected_profile()
        if not name:
            QMessageBox.warning(self, "No Selection", "Select a profile first.")
            return

        try:
            from ofscraper.utils.config.config import update_config
            clean_name = name.replace("_profile", "")
            update_config("main_profile", clean_name)
            app_signals.status_message.emit(f"Default profile set to: {name}")
            self._load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to set default: {e}")

    def _create_profile(self):
        """Create a new profile."""
        text, ok = QInputDialog.getText(
            self, "Create Profile", "Enter new profile name:"
        )
        if not ok or not text.strip():
            return

        name = text.strip()
        if not name.endswith("_profile"):
            name = f"{name}_profile"

        try:
            from ofscraper.utils.paths.common import get_config_home
            profile_path = get_config_home() / name
            if profile_path.exists():
                QMessageBox.warning(
                    self, "Exists", f"Profile '{name}' already exists."
                )
                return

            profile_path.mkdir(parents=True, exist_ok=True)
            app_signals.status_message.emit(f"Created profile: {name}")
            self._load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create profile: {e}")

    def _rename_profile(self):
        """Rename the selected profile."""
        old_name = self._get_selected_profile()
        if not old_name:
            QMessageBox.warning(self, "No Selection", "Select a profile first.")
            return

        display = old_name.replace("_profile", "")
        text, ok = QInputDialog.getText(
            self, "Rename Profile", "Enter new name:", text=display
        )
        if not ok or not text.strip():
            return

        new_name = text.strip()
        if not new_name.endswith("_profile"):
            new_name = f"{new_name}_profile"

        try:
            from ofscraper.utils.paths.common import get_config_home
            old_path = get_config_home() / old_name
            new_path = get_config_home() / new_name

            if new_path.exists():
                QMessageBox.warning(
                    self, "Exists", f"Profile '{new_name}' already exists."
                )
                return

            if old_path.exists():
                old_path.rename(new_path)
                app_signals.status_message.emit(
                    f"Renamed '{old_name}' to '{new_name}'"
                )
            self._load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to rename: {e}")

    def _delete_profile(self):
        """Delete the selected profile."""
        name = self._get_selected_profile()
        if not name:
            QMessageBox.warning(self, "No Selection", "Select a profile first.")
            return

        reply = QMessageBox.question(
            self,
            "Delete Profile",
            f"Are you sure you want to delete profile '{name}'?\n"
            "This will remove all data associated with this profile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from ofscraper.utils.paths.common import get_config_home
            profile_path = get_config_home() / name
            if profile_path.exists():
                shutil.rmtree(profile_path)
                app_signals.status_message.emit(f"Deleted profile: {name}")
            self._load_profiles()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
