from PyQt6.QtWidgets import QPushButton


class StyledButton(QPushButton):
    """Standard styled button matching the app theme."""

    def __init__(self, text="", parent=None, primary=False, danger=False):
        super().__init__(text, parent)
        if primary:
            self.setProperty("primary", True)
        if danger:
            self.setProperty("danger", True)


class NavButton(QPushButton):
    """Navigation sidebar button with checkable state."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setProperty("class", "nav_button")
        self.setCursor(self.cursor())
