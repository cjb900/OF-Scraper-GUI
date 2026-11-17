"""Windows: typing reaches the embedded site window (b9).

The tab window shows each site's window from another process; Windows doesn't
always move the keyboard focus into it. A click inside it, a tab switch and
returning to the window all put the focus there."""

import pytest

from ofscraper.gui import site_context

SITE, FIELD, OTHER = 100, 101, 200  # the site window, a field in it, another window


class FakeUser32:
    def __init__(self, focused):
        self.focused, self.set_to = focused, []

    def GetFocus(self):
        return self.focused

    def IsChild(self, parent, child):
        return parent == SITE and child == FIELD

    def SetFocus(self, hwnd):
        self.set_to.append(hwnd)
        self.focused = hwnd


@pytest.mark.parametrize("focused, moved", [
    (None, True),     # nothing has the focus: the case that blocks typing
    (OTHER, True),    # the tab window or another site has it
    (SITE, False),    # already there
    (FIELD, False),   # a field inside the site window has it
])
def test_take_keyboard_focus(focused, moved):
    u = FakeUser32(focused)
    assert site_context.take_keyboard_focus(SITE, u) is moved
    assert u.set_to == ([SITE] if moved else [])


def test_no_window_does_nothing():
    u = FakeUser32(None)
    assert site_context.take_keyboard_focus(0, u) is False and u.set_to == []


def test_a_failing_call_is_harmless():
    class Broken(FakeUser32):
        def GetFocus(self):
            raise OSError("access denied")

    assert site_context.take_keyboard_focus(SITE, Broken(None)) is False


def test_off_windows_nothing_is_called(monkeypatch):
    monkeypatch.setattr(site_context.sys, "platform", "linux")
    assert site_context.take_keyboard_focus(SITE) is False


# --- the site window: a click takes the focus -----------------------------------------


@pytest.fixture(scope="module")
def qapp():
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _press(widget):
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication

    event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(1, 1), QPointF(1, 1),
                        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                        Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


def test_a_click_in_the_site_window_takes_the_focus(qapp, monkeypatch, caplog):
    from PyQt6.QtWidgets import QLineEdit, QVBoxLayout, QWidget

    calls = []

    def fake_take(win_id, user32=None):
        calls.append(win_id)
        return True

    monkeypatch.setattr(site_context, "take_keyboard_focus", fake_take)
    window = QWidget()
    field = QLineEdit(window)
    QVBoxLayout(window).addWidget(field)
    other = QWidget()  # a dialog or another top-level window
    site_context.install_focus_on_click(qapp, window)
    try:
        with caplog.at_level("INFO", logger="shared"):
            _press(field)
        assert calls == [int(window.winId())]
        assert "took it on a click" in caplog.text
        _press(other)
        assert len(calls) == 1
    finally:
        qapp.removeEventFilter(qapp._ofs_focus_on_click)


# --- the tab window: switching tabs and coming back focus the site ----------------------


def test_tab_window_hands_the_focus_on():
    import inspect

    from ofscraper.gui import site_host

    src = inspect.getsource(site_host)
    assert "QTimer.singleShot(0, tab.focus_child)" in src  # tab switch
    assert "ActivationChange" in src and "focus_child" in src  # back from Alt+Tab / a dialog
    assert "QTimer.singleShot(0, self.focus_child)" in src  # right after embedding


def test_focus_child_uses_the_embedded_window(monkeypatch):
    calls = []
    monkeypatch.setattr(site_context, "take_keyboard_focus", lambda w, u=None: calls.append(w) or True)

    class Container:
        def isVisible(self):
            return True

    from ofscraper.gui import site_host

    SiteTab, _ = site_host._define_classes()
    tab = type("T", (), {"container": Container(), "_win_id": SITE, "label": "Fansly"})()
    SiteTab.focus_child(tab)
    assert calls == [SITE]
