"""Developer and testing tools for the GUI.

Only a testing install has this package: the patch writes it with
``--testing``, and a normal run of the patch removes it. Without it the GUI
shows nothing of it (gui/utils/devtools_loader.py).

It adds a Developer button to the sidebar, and test control: an MCP server
(server.py) through which a client such as Claude Code can see and use the
window, off until turned on in the Developer panel.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QPushButton

log = logging.getLogger("shared")


def install(window, nav_layout, style_button) -> None:
    """Add the Developer button to the sidebar (above the version button)
    and start test control when it was left on."""
    from ofscraper.gui.devtools.dialog import DeveloperDialog
    from ofscraper.gui.devtools.server import TestControl

    control = TestControl(window)
    window._ofs_test_control = control

    button = QPushButton()
    style_button(button)
    button.setToolTip("Developer tools: test control (MCP) for this window")
    nav_layout.addWidget(button)

    def show_state(text=None):
        try:
            button.setText(text or control.state_text())
        except RuntimeError:
            pass

    control.status_changed.connect(show_state)
    # "connected" turns back into "on" when the client goes quiet
    timer = QTimer(button)
    timer.setInterval(5000)
    timer.timeout.connect(lambda: show_state())
    timer.start()

    def open_panel():
        DeveloperDialog(control, window).exec()

    button.clicked.connect(open_panel)

    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(control.stop)
    if control.values.get("enabled"):
        control.start()
    show_state()
