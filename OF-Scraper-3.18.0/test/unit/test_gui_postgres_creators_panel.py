"""Merge DBs > PostgreSQL creators: the table of creators PostgreSQL holds,
their details, and deleting them. The database is stood in for here; the
live tests (test/test_gui_postgres_live.py) read a real one."""

import pytest
from PyQt6.QtWidgets import QMessageBox

from ofscraper.gui.utils import postgres_creators as data

URL = "postgresql://u:secret@db.lan:5432/ofs"


@pytest.fixture
def qapp():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


@pytest.fixture
def panel(qapp, monkeypatch):
    from ofscraper.gui.dialogs import postgres_creators_panel as module
    from ofscraper.gui.utils import privacy_mode

    monkeypatch.setattr(privacy_mode, "is_privacy_mode", lambda: False)
    monkeypatch.setattr(module, "is_privacy_mode", lambda: False)
    monkeypatch.setattr(module.pg, "active_url", lambda: URL)
    monkeypatch.setattr(module.pg, "driver_installed", lambda: True)
    db = {
        "creators": [
            data.Creator(111, "alice", media=10, downloaded=7, size=3_000_000, posts=4),
            data.Creator(222, "bob", media=2, downloaded=2, size=1000, messages=1),
        ],
        "deleted": [],
    }
    monkeypatch.setattr(module.data, "list_creators", lambda url, site: list(db["creators"]))
    monkeypatch.setattr(
        module.data,
        "creator_details",
        lambda url, site, model_id: data.Details(
            names=[("alice", "2024-01-01T00:00:00+00:00", "2024-06-01T00:00:00+00:00")],
            breakdown=[("Timeline", "Images", 10, 7, 3_000_000)],
        ),
    )

    def delete(url, site, ids, forget_names=True):
        db["deleted"].append((site, list(ids), forget_names))
        db["creators"] = [c for c in db["creators"] if c.model_id not in ids]
        return {"medias": 10}

    monkeypatch.setattr(module.data, "delete_creators", delete)
    widget = module.PostgresCreatorsPanel()

    # run the background work at once
    def run(fn, done):
        try:
            result = fn()
        except Exception as e:
            done(None, str(e))
        else:
            done(result, None)

    monkeypatch.setattr(widget, "_run", run)
    widget.db = db
    widget.refresh()
    return widget


def _texts(table, row):
    return [table.item(row, col).text() for col in range(table.columnCount())]


def test_the_table_lists_each_creator_with_counts(panel):
    assert panel.table.rowCount() == 2
    alice = next(r for r in range(2) if panel.table.item(r, 0).text() == "alice")
    row = _texts(panel.table, alice)
    assert row[1:6] == ["111", "10", "7", "3", "3 MB"]
    assert "2 creators" in panel.summary_label.text()
    assert "secret" not in panel.status_label.text()


def test_the_filter_matches_names_and_ids(panel):
    panel.filter_input.setText("22")
    shown = [panel.table.item(r, 0).text() for r in range(2) if not panel.table.isRowHidden(r)]
    assert shown == ["bob"]


def test_selecting_one_shows_its_names_and_areas(panel):
    alice = next(r for r in range(2) if panel.table.item(r, 0).text() == "alice")
    panel.table.selectRow(alice)
    assert "alice (seen 2024-01-01 to 2024-06-01)" in panel.names_label.text()
    assert _texts(panel.detail_table, 0)[:4] == ["Timeline", "Images", "10", "7"]


def test_delete_asks_then_removes_and_refreshes(panel, monkeypatch):
    alice = next(r for r in range(2) if panel.table.item(r, 0).text() == "alice")
    panel.table.selectRow(alice)
    asked = []

    def answer(*args, **kwargs):
        asked.append(args[2])
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "warning", answer)
    panel._on_delete()

    assert "alice (111)" in asked[0] and "usernames are forgotten" in asked[0]
    assert panel.db["deleted"] == [("onlyfans", [111], True)]
    assert panel.table.rowCount() == 1
    assert panel.status_label.text().startswith("Deleted 1 creator")


def test_saying_no_deletes_nothing(panel, monkeypatch):
    panel.table.selectRow(0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.No)
    panel._on_delete()
    assert panel.db["deleted"] == []


def test_no_delete_while_this_window_scrapes(panel):
    panel.table.selectRow(0)
    assert panel.delete_btn.isEnabled()
    panel._set_scraping(True)
    assert not panel.delete_btn.isEnabled()


def test_without_postgresql_it_says_how_to_turn_it_on(panel, monkeypatch):
    from ofscraper.gui.dialogs import postgres_creators_panel as module

    monkeypatch.setattr(module.pg, "active_url", lambda: "")
    monkeypatch.setattr(module.pg, "saved_url", lambda: "")
    panel.refresh()
    assert panel.table.rowCount() == 0
    assert "user_data.db files" in panel.status_label.text()
    panel.table.selectAll()
    assert not panel.delete_btn.isEnabled()


def test_a_read_error_is_shown_without_the_password(panel, monkeypatch):
    from ofscraper.gui.dialogs import postgres_creators_panel as module

    def fail(url, site):
        raise RuntimeError(f"can't reach {URL}")

    monkeypatch.setattr(module.data, "list_creators", fail)
    panel.refresh()
    assert "Couldn't read the creators" in panel.status_label.text()
    assert "secret" not in panel.status_label.text()


def test_privacy_mode_hides_names_and_ids(panel, monkeypatch):
    from ofscraper.gui.dialogs import postgres_creators_panel as module
    from ofscraper.gui.utils import privacy_mode

    monkeypatch.setattr(privacy_mode, "is_privacy_mode", lambda: True)
    monkeypatch.setattr(module, "is_privacy_mode", lambda: True)
    panel._fill_table()
    cells = {panel.table.item(r, c).text() for r in range(2) for c in (0, 1)}
    assert not cells & {"alice", "bob", "111", "222"}
    # the filter still finds them by their real name
    panel.filter_input.setText("bob")
    assert sum(not panel.table.isRowHidden(r) for r in range(2)) == 1
