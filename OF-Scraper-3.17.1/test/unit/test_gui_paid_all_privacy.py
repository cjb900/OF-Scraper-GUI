"""Download all purchased content: Privacy mode hides creator names.

The Exclude creators box and the Pick… list used to show real usernames
with Privacy mode on.
"""
import json

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt  # noqa: E402

from ofscraper.gui.utils import gui_settings, privacy_mode  # noqa: E402


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "gui_settings.json"
    monkeypatch.setattr(
        gui_settings, "load_gui_settings",
        lambda: json.loads(path.read_text()) if path.exists() else {},
    )
    monkeypatch.setattr(
        gui_settings, "save_gui_settings",
        lambda data, quiet=False: path.write_text(json.dumps(data)) or True,
    )
    return path


@pytest.fixture
def privacy():
    before = privacy_mode.is_privacy_mode()

    def set_(on):
        privacy_mode.set_privacy_mode(on, persist=False)

    yield set_
    privacy_mode.set_privacy_mode(before, persist=False)


@pytest.fixture
def page(qapp, settings_file, privacy):
    from ofscraper.gui.pages.action_page import ActionPage

    privacy(False)
    return ActionPage()


def test_exclude_box_is_masked_but_keeps_the_names(page, privacy):
    page._paid_all_exclude_input.setText("alice, bob")
    privacy(True)
    shown = page._paid_all_exclude_input.text()
    assert "alice" not in shown and "bob" not in shown
    assert privacy_mode.is_privacy_placeholder(shown)
    assert page.get_paid_all_options()["excluded"] == ["alice", "bob"]

    privacy(False)
    assert page._paid_all_exclude_input.text() == "alice, bob"


def test_saved_exclusions_load_masked(settings_file, privacy, qapp):
    from ofscraper.gui.pages.action_page import ActionPage

    settings_file.write_text(json.dumps({"paid_all_excluded": ["carol"]}))
    privacy(True)
    page = ActionPage()
    assert "carol" not in page._paid_all_exclude_input.text()
    assert page.get_paid_all_options()["excluded"] == ["carol"]


def _run_pick(page, monkeypatch, privacy_on, privacy, tick=(), search=""):
    """Open Pick…, record what it shows, tick names by real name, press OK."""
    from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget

    privacy(privacy_on)
    monkeypatch.setattr(type(page), "known_creator_names", staticmethod(lambda: ["alice", "bob"]))
    seen = {}

    def fake_exec(dlg):
        lst = dlg.findChild(QListWidget)
        if search:
            dlg.findChild(QLineEdit).setText(search)
        seen["shown"] = [lst.item(i).text() for i in range(lst.count())]
        seen["visible"] = [
            lst.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(lst.count()) if not lst.item(i).isHidden()
        ]
        for i in range(lst.count()):
            if lst.item(i).data(Qt.ItemDataRole.UserRole) in tick:
                lst.item(i).setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    page._on_paid_all_pick()
    return seen


def test_pick_list_hides_names_in_privacy_mode(page, monkeypatch, privacy):
    seen = _run_pick(page, monkeypatch, True, privacy, tick=("bob",), search="bo")
    assert not any(n in t for t in seen["shown"] for n in ("alice", "bob"))
    assert seen["visible"] == ["bob"]  # search still matches the real name
    assert page.get_paid_all_options()["excluded"] == ["bob"]
    assert "bob" not in page._paid_all_exclude_input.text()


def test_pick_list_shows_names_without_privacy(page, monkeypatch, privacy):
    seen = _run_pick(page, monkeypatch, False, privacy, tick=("alice",))
    assert seen["shown"] == ["alice", "bob"]
    assert page._paid_all_exclude_input.text() == "alice"
