"""v422: table messages, cancelled-run history, and the check action options."""

import sqlite3
import sys
from types import SimpleNamespace

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first.
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

import ofscraper.commands.check as check
import ofscraper.db.operations_.media as media_ops

pytestmark = pytest.mark.unit


# --- Check messages filter ---
ROWS = [
    {"media_id": 1, "price": "Free", "unlocked": True},
    {"media_id": 2, "price": "4.99", "unlocked": True},  # bought
    {"media_id": 3, "price": "9.99", "unlocked": False},  # locked PPV
    {"media_id": 4, "price": "Free", "unlocked": False},  # locked, no price
]


@pytest.mark.parametrize(
    "msg_filter,expected",
    [("paid_only", [2, 3, 4]), ("free_only", [1]), ("all", [1, 2, 3, 4])],
)
def test_message_filter(msg_filter, expected):
    rows = check.filter_message_rows(ROWS, msg_filter)
    assert [r["media_id"] for r in rows] == expected


# --- Compare with files on disk ---
def test_missing_downloaded_files(tmp_path):
    (tmp_path / "here.mp4").write_bytes(b"x")
    paths = {
        (1, 10): (str(tmp_path), "here.mp4"),
        (2, 20): (str(tmp_path), "gone.mp4"),
        (3, 30): ("", str(tmp_path / "here.mp4")),  # filename recorded with its path
        (4, 40): (str(tmp_path), None),  # nothing recorded: can't tell, keep
        (5, 50): ("", str(tmp_path / "gone.jpg")),
    }
    assert check.missing_downloaded_files(paths) == {(2, 20), (5, 50)}


def test_downloaded_media_paths_query():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "create table medias (media_id, post_id, directory, filename, downloaded)"
    )
    conn.executemany(
        "insert into medias values (?,?,?,?,?)",
        [(1, 10, "/d", "a.mp4", 1), (2, 20, "/d", "b.mp4", 0)],
    )
    rows = conn.execute(media_ops.downloadedMediaPaths).fetchall()
    assert rows == [(1, 10, "/d", "a.mp4")]


# --- History of a cancelled run ---
def test_cancelled_summary_adds_up_each_creator(monkeypatch):
    import ofscraper.commands.scraper.actions.utils.globals as cg
    from ofscraper.gui.utils.workflow import build_cancelled_summary_payload

    # stale counters from an earlier run must not be counted
    monkeypatch.setattr(cg, "video_count", 99, raising=False)
    wf = SimpleNamespace(
        _selected_models=[SimpleNamespace(name="a"), SimpleNamespace(name="b")],
        _per_model_run_stats={
            "a": {"videos": 2, "photos": 20, "audios": 0, "forced": 1, "failed": 0, "bytes": 100},
            "b": {"videos": 0, "photos": 0, "audios": 1, "forced": 0, "failed": 2, "bytes": 50},
        },
    )
    s = build_cancelled_summary_payload(wf)
    assert s["run_dl"] == 23
    assert (s["forced"], s["failed"], s["total_bytes"]) == (1, 2, 150)
    assert s["model_names"] == ["a", "b"]


def test_cancelled_before_any_download_counts_nothing(monkeypatch):
    import ofscraper.commands.scraper.actions.utils.globals as cg
    from ofscraper.gui.utils.workflow import build_cancelled_summary_payload

    monkeypatch.setattr(cg, "photo_count", 7, raising=False)
    s = build_cancelled_summary_payload(SimpleNamespace(_selected_models=[]))
    assert s["run_dl"] == 0


# --- GUI ---
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    return app or QtWidgets.QApplication([])


def test_clearing_the_search_box_applies_the_filter(qapp):
    from ofscraper.gui.widgets.sidebar import FilterSidebar

    sb = FilterSidebar()
    fired = []
    sb.filter_changed.connect(lambda: fired.append(1))
    sb.text_input.setText("abc")
    assert fired == []  # typing still waits for Apply Filters
    sb.text_input.clear()
    assert fired == [1]
    sb.text_input.clear()  # already empty: nothing more
    assert fired == [1]
    sb.close()


def _guide_text(page):
    page._refresh_empty_guide()
    return page._empty_guide.text()


def test_filtered_out_rows_are_explained_during_a_scrape(qapp):
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    page.data_table._raw_data = [{"media_id": 1}, {"media_id": 2}]
    page.data_table.setRowCount(0)
    page._scrape_active = True
    text = _guide_text(page)
    assert "No rows match the current filters" in text
    assert "2 rows" in text
    page.data_table._raw_data = []
    assert "Scraping in progress" in _guide_text(page)
    page.close()


def test_new_scrape_clears_scrape_cancelled(qapp):
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    page.daemon_status_label.setText("Scrape cancelled")
    page.daemon_status_label.show()
    page._on_scrape_started()
    assert page.daemon_status_label.text() == ""
    assert page.daemon_status_label.isHidden()
    page.close()


def test_new_scrape_keeps_other_status_text(qapp):
    from ofscraper.gui.pages.table_page import TablePage

    page = TablePage(manager=None)
    page.daemon_status_label.setText("Daemon mode active")
    page._on_scrape_started()
    assert page.daemon_status_label.text() == "Daemon mode active"
    page.close()


def test_check_options_shown_and_sent_for_check_actions(qapp):
    from ofscraper.gui.pages.action_page import ALL_CHOICES, ActionPage
    from ofscraper.gui.signals import app_signals

    page = ActionPage()
    sent, msg = [], []
    app_signals.check_options_changed.connect(sent.append)
    app_signals.msg_check_include_free_toggled.connect(msg.append)
    try:
        idx = next(i for i, (_, a) in enumerate(ALL_CHOICES) if a == {"msg_check"})
        page._button_group.button(idx).setChecked(True)
        page._on_action_changed(idx)
        assert not page._check_options_widget.isHidden()
        page._check_fresh_check.setChecked(True)
        page._check_disk_check.setChecked(True)
        page._on_next()
        assert sent[-1] == {"fresh": True, "disk": True}
        assert msg[-1] == "paid_only"  # sent on Next even without a click
        page._on_action_changed(0)
        assert page._check_options_widget.isHidden()
        page.reset_to_defaults()
        assert page.get_check_options() == {"fresh": False, "disk": False}
    finally:
        app_signals.check_options_changed.disconnect(sent.append)
        app_signals.msg_check_include_free_toggled.disconnect(msg.append)
        page.close()


def test_fetch_fresh_sets_force_for_the_check(monkeypatch):
    from ofscraper.gui.utils import workflow as wf_mod

    wf = wf_mod.GUIWorkflow.__new__(wf_mod.GUIWorkflow)
    wf._selected_actions = {"paid_check"}
    wf._selected_models = [SimpleNamespace(name="a")]
    wf._selected_areas = []
    wf._advanced = {}
    wf._ensure_advanced_options = lambda: None
    written = []
    args = SimpleNamespace()
    writer = SimpleNamespace(setArgs=written.append)
    settings = SimpleNamespace(update_settings=lambda: None)
    for fresh in (True, False):
        wf._check_options = {"fresh": fresh, "disk": False}
        wf._set_check_args(args, writer, settings)
        assert written[-1].force is fresh
