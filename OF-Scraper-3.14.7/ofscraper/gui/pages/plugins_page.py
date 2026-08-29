"""Plugins manager page — list installed plugins, enable/disable, open folders."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ofscraper.gui.signals import app_signals
from ofscraper.gui.utils.ui_scale import apply_font
from ofscraper.gui.styles import c
from ofscraper.gui.widgets.styled_button import StyledButton

log = logging.getLogger("shared")

_COLS = ["Name", "Version", "Status", "Description"]


class PluginsPage(QWidget):
    """Manage plugins in the user plugins folder."""

    def __init__(self, manager=None, parent=None):
        super().__init__(parent)
        self.manager = manager
        self._rows: list[dict] = []
        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        header = QLabel("Plugins")
        apply_font(header, "Segoe UI", 22, QFont.Weight.Bold)
        header.setProperty("heading", True)
        layout.addWidget(header)

        subtitle = QLabel(
            "Install plugins by copying a folder into your plugins directory. "
            "Use <b>Load now</b> / <b>Unload now</b> to activate or deactivate "
            "without restarting."
        )
        subtitle.setProperty("subheading", True)
        subtitle.setWordWrap(True)
        subtitle.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(subtitle)

        self.path_label = QLabel("Plugins folder: …")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet(f"color: {c('subtext')};")
        app_signals.theme_changed.connect(self._apply_theme)
        layout.addWidget(self.path_label)

        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.refresh_btn = StyledButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        btn_row.addWidget(self.refresh_btn)

        self.open_folder_btn = StyledButton("Open plugins folder")
        self.open_folder_btn.clicked.connect(self._open_plugins_folder)
        btn_row.addWidget(self.open_folder_btn)

        self.open_plugin_btn = StyledButton("Open selected folder")
        self.open_plugin_btn.clicked.connect(self._open_selected_folder)
        btn_row.addWidget(self.open_plugin_btn)

        self.load_now_btn = StyledButton("Load now", primary=True)
        self.load_now_btn.setToolTip(
            "Import and activate the selected enabled plugin without restarting"
        )
        self.load_now_btn.clicked.connect(self._load_selected_now)
        btn_row.addWidget(self.load_now_btn)

        self.unload_now_btn = StyledButton("Unload now")
        self.unload_now_btn.setToolTip(
            "Deactivate the selected loaded plugin and remove its UI without restarting"
        )
        self.unload_now_btn.clicked.connect(self._unload_selected_now)
        btn_row.addWidget(self.unload_now_btn)

        self.toggle_btn = StyledButton("Disable")
        self.toggle_btn.clicked.connect(self._toggle_selected)
        btn_row.addWidget(self.toggle_btn)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"color: {c('subtext')};")
        layout.addWidget(self.hint_label)

        self._update_buttons()

    def _apply_theme(self, *_args):
        self.path_label.setStyleSheet(f"color: {c('subtext')};")
        self.hint_label.setStyleSheet(f"color: {c('subtext')};")

    def _plugins_dir(self) -> Path | None:
        try:
            from ofscraper.plugins.manager import plugin_manager

            return plugin_manager.plugins_dir
        except Exception:
            return None

    def refresh(self):
        try:
            from ofscraper.plugins.manager import plugin_manager

            plugins_dir = plugin_manager.plugins_dir
            if plugins_dir is None:
                self.path_label.setText("Plugins folder: (unavailable)")
                self._rows = []
            else:
                try:
                    plugins_dir.mkdir(parents=True, exist_ok=True)
                except Exception:
                    pass
                display = str(plugins_dir)
                try:
                    from ofscraper.gui.utils.privacy_mode import is_privacy_mode

                    if is_privacy_mode():
                        display = "[Hidden for Privacy]"
                except Exception:
                    pass
                self.path_label.setText(f"Plugins folder: {display}")
                self._rows = plugin_manager.list_installed_plugins()
        except Exception as e:
            log.debug(f"[GUI] Plugin list refresh failed: {e}")
            self._rows = []
            self.path_label.setText("Plugins folder: (error reading list)")

        self.table.setRowCount(0)
        for info in self._rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            if info.get("loaded"):
                status = "Loaded"
            elif not info.get("enabled", True):
                status = "Disabled"
            else:
                status = "Not loaded"
            values = [
                str(info.get("name") or info.get("id") or ""),
                str(info.get("version") or "—"),
                status,
                str(info.get("description") or ""),
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, info.get("id"))
                if col == 2:
                    if status == "Loaded":
                        item.setForeground(self._status_color("green"))
                    elif status == "Disabled":
                        item.setForeground(self._status_color("yellow"))
                    else:
                        item.setForeground(self._status_color("subtext"))
                self.table.setItem(row, col, item)

        if not self._rows:
            self.hint_label.setText(
                "No plugins installed yet. Copy a plugin folder into the plugins "
                "directory, then click Refresh (or restart the GUI)."
            )
        else:
            self.hint_label.setText(
                f"{len(self._rows)} plugin(s) found. "
                "Load now / Unload now change the current session; "
                "Disable marks a plugin off on disk."
            )
        self._update_buttons()

    def _status_color(self, name: str):
        from PyQt6.QtGui import QColor

        try:
            return QColor(c(name))
        except Exception:
            return QColor("#cdd6f4")

    def _selected_info(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        idx = rows[0].row()
        if idx < 0 or idx >= len(self._rows):
            return None
        return self._rows[idx]

    def _update_buttons(self):
        info = self._selected_info()
        has = info is not None
        self.open_plugin_btn.setEnabled(has)
        self.toggle_btn.setEnabled(has)
        can_load = bool(
            has
            and info.get("enabled", True)
            and not info.get("loaded")
        )
        can_unload = bool(has and info.get("loaded"))
        self.load_now_btn.setEnabled(can_load)
        self.unload_now_btn.setEnabled(can_unload)
        if not has:
            self.toggle_btn.setText("Enable / Disable")
            return
        if info.get("enabled", True):
            self.toggle_btn.setText("Disable")
        else:
            self.toggle_btn.setText("Enable")

    def _open_path(self, path: Path):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            log.debug(f"[GUI] Could not create path {path}: {e}")
        try:
            if sys.platform == "win32":
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            QMessageBox.warning(self, "Open folder", f"Could not open:\n{path}\n\n{e}")

    def _open_plugins_folder(self):
        path = self._plugins_dir()
        if path is None:
            QMessageBox.warning(self, "Plugins", "Plugins folder path is unavailable.")
            return
        self._open_path(path)

    def _open_selected_folder(self):
        info = self._selected_info()
        if not info:
            return
        self._open_path(Path(info["path"]))

    def _main_window(self):
        win = self.window()
        return win if win is not None else None

    def _reselect_plugin(self, plugin_id: str):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == plugin_id:
                self.table.selectRow(row)
                break

    def _load_selected_now(self):
        info = self._selected_info()
        if not info:
            return
        if info.get("loaded"):
            QMessageBox.information(self, "Load now", "That plugin is already loaded.")
            return
        if not info.get("enabled", True):
            QMessageBox.information(
                self,
                "Load now",
                "Enable the plugin first, then use Load now.",
            )
            return
        plugin_id = info["id"]
        try:
            from ofscraper.plugins.manager import plugin_manager

            ok, message = plugin_manager.load_plugin_now(
                plugin_id, main_window=self._main_window()
            )
        except Exception as e:
            QMessageBox.warning(self, "Load now", str(e))
            return

        if ok:
            app_signals.status_message.emit(message)
            QMessageBox.information(self, "Load now", message)
        else:
            QMessageBox.warning(self, "Load now", message)
        self.refresh()
        self._reselect_plugin(plugin_id)

    def _unload_selected_now(self):
        info = self._selected_info()
        if not info:
            return
        if not info.get("loaded"):
            QMessageBox.information(self, "Unload now", "That plugin is not loaded.")
            return
        plugin_id = info["id"]
        reply = QMessageBox.question(
            self,
            "Unload now",
            f'Unload plugin "{info.get("name") or plugin_id}" from this session?\n\n'
            "Its sidebar page (if any) will be removed. You can Load now again later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from ofscraper.plugins.manager import plugin_manager

            ok, message = plugin_manager.unload_plugin_now(
                plugin_id, main_window=self._main_window()
            )
        except Exception as e:
            QMessageBox.warning(self, "Unload now", str(e))
            return

        if ok:
            app_signals.status_message.emit(message)
            QMessageBox.information(self, "Unload now", message)
        else:
            QMessageBox.warning(self, "Unload now", message)
        self.refresh()
        self._reselect_plugin(plugin_id)

    def _toggle_selected(self):
        info = self._selected_info()
        if not info:
            return
        plugin_id = info["id"]
        currently_enabled = bool(info.get("enabled", True))
        new_enabled = not currently_enabled
        action = "enable" if new_enabled else "disable"
        was_loaded = bool(info.get("loaded"))
        if new_enabled:
            detail = (
                f'Enable plugin "{info.get("name") or plugin_id}"?\n\n'
                "After enabling, click Load now to activate it without restarting."
            )
        else:
            detail = (
                f'Disable plugin "{info.get("name") or plugin_id}"?\n\n'
                + (
                    "It is currently loaded — you can unload it from this session next."
                    if was_loaded
                    else "It will stay off on disk until you Enable it again."
                )
            )
        reply = QMessageBox.question(
            self,
            f"{action.capitalize()} plugin",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from ofscraper.plugins.manager import plugin_manager

            ok = plugin_manager.set_enabled_flag(plugin_id, new_enabled)
        except Exception as e:
            QMessageBox.warning(self, "Plugins", str(e))
            return
        if not ok:
            QMessageBox.warning(
                self,
                "Plugins",
                "Could not update plugin_enabled in main.py.",
            )
            return

        if new_enabled:
            # Offer immediate load.
            load_reply = QMessageBox.question(
                self,
                "Load now?",
                "Plugin enabled on disk. Load it into this session now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if load_reply == QMessageBox.StandardButton.Yes:
                try:
                    lok, lmsg = plugin_manager.load_plugin_now(
                        plugin_id, main_window=self._main_window()
                    )
                    app_signals.status_message.emit(lmsg)
                    if not lok:
                        QMessageBox.warning(self, "Load now", lmsg)
                except Exception as e:
                    QMessageBox.warning(self, "Load now", str(e))
            else:
                app_signals.status_message.emit(
                    f"Plugin '{plugin_id}' enabled — use Load now or restart"
                )
        else:
            if was_loaded:
                unload_reply = QMessageBox.question(
                    self,
                    "Unload now?",
                    "Plugin disabled on disk. Unload it from this session now?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if unload_reply == QMessageBox.StandardButton.Yes:
                    try:
                        uok, umsg = plugin_manager.unload_plugin_now(
                            plugin_id, main_window=self._main_window()
                        )
                        app_signals.status_message.emit(umsg)
                        if not uok:
                            QMessageBox.warning(self, "Unload now", umsg)
                    except Exception as e:
                        QMessageBox.warning(self, "Unload now", str(e))
                else:
                    app_signals.status_message.emit(
                        f"Plugin '{plugin_id}' disabled on disk — still loaded until Unload now"
                    )
            else:
                app_signals.status_message.emit(
                    f"Plugin '{plugin_id}' disabled on disk"
                )

        self.refresh()
        self._reselect_plugin(plugin_id)
