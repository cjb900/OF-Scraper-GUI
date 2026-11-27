"""The Developer panel: turn test control (the MCP server) on or off, and
what a connected client may do."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ofscraper.gui.devtools import settings as dev_settings


class DeveloperDialog(QDialog):
    def __init__(self, control, parent=None):
        super().__init__(parent)
        self.control = control
        self.setWindowTitle("Developer")
        self.setMinimumWidth(640)
        values = dict(control.values)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "<b>Test control (MCP)</b> lets an MCP client, such as Claude Code on this "
            "computer, see and use this window: read the controls and tables, click, type "
            "and change settings, as you would. It's for testing the GUI. It listens on "
            f"{dev_settings.HOST} (this computer only) and needs the token below."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        self.enabled = QCheckBox("Allow test control while the GUI runs")
        self.enabled.setChecked(bool(values["enabled"]))
        form.addRow(self.enabled)

        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(values["port"]))
        form.addRow("Port:", self.port)

        self.screenshots = QCheckBox("Allow screenshots of this window")
        self.screenshots.setChecked(bool(values["screenshots"]))
        self.screenshots.setToolTip(
            "A screenshot is sent to the client, and from there to its AI service, with "
            "whatever the window shows: creators' names and media, your account. "
            "Privacy mode hides names in the window, not in pictures."
        )
        form.addRow(self.screenshots)

        self.account = QCheckBox("Allow Like / Unlike (they act on your account)")
        self.account.setChecked(bool(values["account_actions"]))
        form.addRow(self.account)

        self.token = QLineEdit(values["token"])
        self.token.setObjectName("devtools_token")  # masked for test control
        self.token.setReadOnly(True)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self.token.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        renew = QPushButton("New token")
        renew.setToolTip("Clients connected with the old token have to be added again")
        renew.clicked.connect(lambda: (self.token.setText(dev_settings.new_token()), self._refresh()))
        row = QHBoxLayout()
        row.addWidget(self.token, 1)
        row.addWidget(show)
        row.addWidget(renew)
        form.addRow("Token:", row)
        layout.addLayout(form)

        layout.addWidget(QLabel("Add it to Claude Code (run once in a terminal):"))
        self.command = QLineEdit()
        self.command.setObjectName("devtools_token_command")  # holds the token
        self.command.setReadOnly(True)
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.command.text()))
        row = QHBoxLayout()
        row.addWidget(self.command, 1)
        row.addWidget(copy)
        layout.addLayout(row)

        self.state = QLabel()
        layout.addWidget(self.state)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.port.valueChanged.connect(lambda _v: self._refresh())
        control.status_changed.connect(self._refresh)
        self._refresh()

    def values(self) -> dict:
        return {
            "enabled": self.enabled.isChecked(),
            "port": self.port.value(),
            "screenshots": self.screenshots.isChecked(),
            "account_actions": self.account.isChecked(),
            "token": self.token.text(),
        }

    def _refresh(self, *_):
        try:
            self.command.setText(dev_settings.connect_command(self.values()))
            self.state.setText(self.control.state_text())
        except RuntimeError:
            pass  # closed

    def _save(self):
        self.control.apply_settings(self.values())
        self._refresh()
