"""The GUI's "Download all purchased content" action: `--scrape-paid -eu ...`."""
import asyncio
import copy
import json
import os
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.data.posts.post as post_mod  # noqa: E402
import ofscraper.utils.args.accessors.read as read_args  # noqa: E402
import ofscraper.utils.args.mutators.write as write_args  # noqa: E402
import ofscraper.utils.settings as settings  # noqa: E402
import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402
from ofscraper.gui.utils import gui_settings, scrape_history  # noqa: E402

KEYS = ["scrape_paid", "excluded_username", "actions", "usernames", "posts"]


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


@pytest.fixture
def restore_args():
    saved = copy.deepcopy(read_args.retriveArgs())
    yield
    write_args.setArgs(saved)
    settings.update_settings()


@pytest.fixture
def workflow(qapp, restore_args):
    return workflow_mod.GUIWorkflow(None)


@pytest.fixture
def gui_settings_file(tmp_path, monkeypatch):
    path = tmp_path / "gui_settings.json"
    store = {}

    def load():
        return json.loads(path.read_text()) if path.exists() else {}

    def save(data, quiet=False):
        path.write_text(json.dumps(data))
        return True

    monkeypatch.setattr(gui_settings, "load_gui_settings", load)
    monkeypatch.setattr(gui_settings, "save_gui_settings", save)
    return path


def _set_excluded(names):
    args = read_args.retriveArgs()
    args.excluded_username = list(names)
    write_args.setArgs(args)
    settings.update_settings()


def test_args_match_the_cli(workflow, tmp_path):
    workflow._on_paid_all_options({"excluded": ["Bob", " carol "], "mediatypes": ["Videos"]})
    workflow.start_paid_all = lambda: None  # only build the args here
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    script = textwrap.dedent(
        f"""
        import json, sys
        sys.argv = ["ofscraper", "--scrape-paid", "-eu", "Bob,carol", "--action", "download"]
        import ofscraper.main.open.load
        import ofscraper.utils.args.accessors.read as r
        a = r.retriveArgs()
        print(json.dumps({{k: a.get(k) for k in {KEYS!r}}}, default=sorted))
        """
    )
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120)
    assert out.returncode == 0, out.stderr
    cli = json.loads(out.stdout.strip().splitlines()[-1])
    gui = read_args.retriveArgs()
    got = {k: gui.get(k) for k in KEYS}
    assert sorted(got.pop("excluded_username")) == sorted(cli.pop("excluded_username"))
    got["posts"] = list(got["posts"] or [])
    assert got == cli
    assert settings.get_settings().mediatypes == ["Videos"]


def test_area_page_leftovers_do_not_apply(workflow):
    # rescrape / delete / daemon / dates / models from an earlier normal run
    workflow._advanced = {"rescrape_all": True, "delete_model_db": True, "delete_downloads": True}
    workflow._daemon_enabled = True
    workflow._date_range = {"enabled": True, "from_date": "2020-01-01"}
    workflow._selected_models = [SimpleNamespace(name="bob", id=1)]
    workflow._selected_areas = ["Timeline"]
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    assert workflow._advanced == {}
    assert workflow._daemon_enabled is False
    assert workflow._date_range == {}
    assert workflow._selected_models == []
    assert workflow._scrape_paid is True
    args = read_args.retriveArgs()
    assert args.download_area == set()
    assert args.usernames == []
    assert not args.daemon
    assert args.before is None


def test_exclusions_do_not_leak_into_the_next_run(workflow):
    launch = list(read_args.retriveArgs().excluded_username or [])
    workflow._on_paid_all_options({"excluded": ["bob"]})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    assert "bob" in settings.get_settings().excluded_username

    workflow._on_action_selected({"download"})
    workflow._selected_models = [SimpleNamespace(name="carol", id=2)]
    workflow._selected_areas = ["Timeline"]
    workflow._set_args()
    assert list(read_args.retriveArgs().excluded_username) == launch
    assert "bob" not in (settings.get_settings().excluded_username or [])
    assert settings.get_settings().scrape_paid is False


def test_targets_name_known_creators_and_skip_excluded(restore_args, monkeypatch):
    looked_up = []

    async def resolve(mid):
        looked_up.append(mid)
        return {3: "modeldeleted_3", 4: "Expired"}[mid]

    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    _set_excluded(["carol", "modeldeleted_3"])
    paid = {1: ["p"], "2": ["p"], 3: ["p"], 4: ["p"]}
    known = {"1": "bob", "2": "Carol"}
    targets, skipped = asyncio.run(workflow_mod._paid_all_targets(paid, known=known))
    assert [(t.id, t.name) for t in targets] == [(1, "bob"), (4, "Expired")]
    assert skipped == ["Carol", "modeldeleted_3"]  # case ignored; deleted accounts too
    assert looked_up == [3, 4]  # subscriptions need no API lookup


def test_a_failed_lookup_skips_that_creator(restore_args, monkeypatch):
    async def resolve(mid):
        raise RuntimeError("timeout")

    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    _set_excluded([])
    targets, skipped = asyncio.run(workflow_mod._paid_all_targets({9: ["p"], 1: ["p"]}, known={"1": "bob"}))
    assert [t.name for t in targets] == ["bob"]
    assert skipped == []


def test_creator_names_are_remembered_for_pick(gui_settings_file):
    workflow_mod._remember_paid_all_creators(["bob", "Carol"])
    workflow_mod._remember_paid_all_creators(["carol2", "bob"])
    saved = json.loads(gui_settings_file.read_text())["paid_all_known_creators"]
    assert saved == ["bob", "Carol", "carol2"]


def test_run_processes_every_creator_and_loads_them_into_the_table(workflow, monkeypatch, gui_settings_file):
    # The real run loop with the paid API, scraper and DB stubbed: the GUI's
    # paid-scrape replacement must cover all creators, not only selected models.
    import ofscraper.data.api.paid as paid_api
    import ofscraper.data.posts.scrape_paid as spm

    async def get_all_paid_posts():
        return {1: [], 5: []}  # empty: nothing to write to the DB

    async def resolve(mid):
        return {1: "creator1", 5: "expired5"}[mid]

    seen = {}

    class Manager:
        def runner(self):
            async def drain():
                return [x async for x in spm.process_paid_dict()]

            seen["yielded"] = asyncio.run(drain())

    monkeypatch.setattr(paid_api, "get_all_paid_posts", get_all_paid_posts)
    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    monkeypatch.setattr(workflow_mod, "_make_gui_scraper_manager", lambda: Manager)
    monkeypatch.setattr(
        workflow_mod, "_load_models_from_db",
        lambda models, **kw: seen.setdefault("loads", []).append(([m.name for m in models], kw)) or {},
    )
    orig = spm.process_paid_dict
    workflow._on_paid_all_options({"excluded": []})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    workflow._run_scraper_thread()

    assert spm.process_paid_dict is orig  # replacement removed after the run
    assert seen["yielded"] == []
    assert sorted(t.name for t in workflow._paid_all_models) == ["creator1", "expired5"]
    table_loads = [names for names, kw in seen["loads"] if not kw.get("stats_only")]
    assert table_loads and sorted(table_loads[-1]) == ["creator1", "expired5"]
    remembered = json.loads(gui_settings_file.read_text())["paid_all_known_creators"]
    assert "expired5" in remembered


def test_action_page_panel_parses_and_saves(qapp, gui_settings_file):
    from ofscraper.gui.pages.action_page import ALL_CHOICES, ActionPage

    page = ActionPage()
    idx = next(i for i, (_, a) in enumerate(ALL_CHOICES) if a == {"paid_all"})
    assert page._paid_all_widget.isHidden()
    page._button_group.button(idx).setChecked(True)
    page._on_action_changed(idx)
    assert not page._paid_all_widget.isHidden()
    assert page._metadata_widget.isHidden()

    page._paid_all_exclude_input.setText("@Bob, carol , ,bob")
    page._paid_all_type_checks["Audios"].setChecked(False)
    got = []
    opts_slot = lambda o: got.append(("options", o))
    act_slot = lambda a: got.append(("actions", a))
    app_signals.paid_all_options_changed.connect(opts_slot)
    app_signals.action_selected.connect(act_slot)
    try:
        page._on_next()
    finally:
        app_signals.paid_all_options_changed.disconnect(opts_slot)
        app_signals.action_selected.disconnect(act_slot)
    opts = {"excluded": ["bob", "carol"], "mediatypes": ["Images", "Videos"]}
    assert got == [("options", opts), ("actions", {"paid_all"})]

    saved = json.loads(gui_settings_file.read_text())
    assert saved["paid_all_excluded"] == ["bob", "carol"]
    # a new page (next GUI start) remembers them
    page2 = ActionPage()
    assert page2.get_paid_all_options() == opts


def test_history_rerun_restores_the_options(workflow):
    workflow._on_paid_all_options({"excluded": ["bob"], "mediatypes": ["Images"]})
    workflow._selected_actions = {"paid_all"}
    snap = scrape_history.snapshot_from_workflow(workflow)
    assert snap["actions"] == ["paid_all"]
    assert snap["paid_all"] == {"excluded": ["bob"], "mediatypes": ["Images"]}

    other = workflow_mod.GUIWorkflow(None)
    main = SimpleNamespace(workflow=other, area_page=object(), model_page=None)
    ok, message = scrape_history.apply_entry_to_pages(snap, main_window=main)
    assert ok, message
    assert other._selected_actions == {"paid_all"}
    assert other._paid_all_options == {"excluded": ["bob"], "mediatypes": ["Images"]}


def test_start_confirm_sees_no_area_page_leftovers(workflow, monkeypatch):
    # _start_scraping builds its confirm summary before the args are set
    from ofscraper.gui.utils import scrape_confirm

    seen = {}
    monkeypatch.setattr(workflow, "_start_scraping", lambda: seen.update(
        summary=scrape_confirm.build_summary_from_workflow(workflow)))
    workflow._advanced = {"delete_model_db": True, "delete_downloads": True, "rescrape_all": True}
    workflow._daemon_enabled = True
    workflow._on_paid_all_options({"excluded": [], "mediatypes": ["Videos"]})
    workflow.start_paid_all()
    s = seen["summary"]
    assert not (s.delete_db or s.delete_downloads or s.rescrape_all or s.daemon_enabled)
    assert s.scrape_paid and s.mediatypes == ["Videos"]


def _stub_paid_run(workflow, monkeypatch, runner):
    """Run the real scraper thread for an all-purchased job with `runner` as the
    scraping manager's runner; returns the _load_models_from_db calls."""
    import ofscraper.data.api.paid as paid_api

    async def get_all_paid_posts():
        return {1: []}

    async def resolve(mid):
        return "creator1"

    loads = []
    monkeypatch.setattr(paid_api, "get_all_paid_posts", get_all_paid_posts)
    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    monkeypatch.setattr(workflow_mod, "_make_gui_scraper_manager", lambda: type("M", (), {"runner": runner}))
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: loads.append(kw) or {})
    workflow._on_paid_all_options({"excluded": []})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    workflow._run_scraper_thread()
    return loads


def test_paid_media_ids_from_an_earlier_run_are_dropped(workflow, monkeypatch, gui_settings_file):
    # an earlier paid scrape left its media ids behind
    workflow._scrape_paid_media_ids = {"old-1", "old-2"}
    seen = {}

    def runner(self):
        seen["ids"] = set(workflow._scrape_paid_media_ids)

    loads = _stub_paid_run(workflow, monkeypatch, runner)
    assert seen["ids"] == set()
    for kw in loads:
        assert not ({"old-1", "old-2"} & set(kw.get("media_ids") or ()))


@pytest.mark.parametrize("error", [KeyboardInterrupt, RuntimeError])
def test_stop_or_error_puts_the_paid_scrape_functions_back(workflow, monkeypatch, gui_settings_file, error):
    import ofscraper.data.posts.scrape_paid as spm

    orig_dict, orig_user = spm.process_paid_dict, spm.process_user

    def runner(self):
        assert spm.process_paid_dict is not orig_dict  # the GUI's version is in place
        raise error("stopped")

    _stub_paid_run(workflow, monkeypatch, runner)
    assert spm.process_paid_dict is orig_dict
    assert spm.process_user is orig_user


@pytest.mark.parametrize(
    "scraped, in_db, recorded, expected",
    [
        ("bob", None, None, "bob"),  # a normal creator: no DB lookup
        ("PH", True, "oldname", "oldname"),  # deleted, we know its old name
        ("PH", True, None, "PH_7"),  # deleted, in the DB but no name stored
        ("PH", False, None, "PH_7"),  # deleted, never seen before
    ],
)
def test_resolve_paid_username(monkeypatch, scraped, in_db, recorded, expected):
    ph = post_mod.of_env.getattr("DELETED_MODEL_PLACEHOLDER")
    db_calls = []

    async def table_exists(model_id, username):
        db_calls.append(("exists", model_id, username))
        return in_db

    async def profile_info(model_id, username):
        db_calls.append(("info", model_id, username))
        return recorded

    monkeypatch.setattr(post_mod.profile, "scrape_profile", lambda mid: {"username": scraped.replace("PH", ph)})
    monkeypatch.setattr(post_mod, "check_profile_table_exists", table_exists)
    monkeypatch.setattr(post_mod, "get_profile_info", profile_info)
    assert asyncio.run(post_mod.resolve_paid_username(7)) == expected.replace("PH", ph)
    if scraped == "bob":
        assert db_calls == []
    else:
        assert db_calls[0] == ("exists", 7, ph)


def test_choosing_the_action_starts_the_run():
    from ofscraper.gui.main_window import MainWindow

    calls = []
    rec = lambda name: (lambda *a: calls.append((name, *a)))
    table = SimpleNamespace(sidebar=SimpleNamespace(setVisible=rec("sidebar")), start_paid_all_run=rec("start"))
    win = SimpleNamespace(
        scraper_stack=SimpleNamespace(setCurrentWidget=rec("show")),
        table_page=table, area_page="areas", url_input_page="urls",
    )
    MainWindow._on_action_selected(win, {"paid_all"})
    assert calls == [("show", table), ("sidebar", False), ("start",)]

    calls.clear()
    MainWindow._on_action_selected(win, {"download"})
    assert calls == [("show", "areas")]  # normal actions still go to the Areas page


def _fake_table(workflow, **state):
    calls = []
    page = SimpleNamespace(
        _scrape_active=False, _cancelling=False, _live_rows_loaded=True, _check_mode_active=True,
        window=lambda: SimpleNamespace(workflow=workflow),
        data_table=SimpleNamespace(clear_all=lambda: calls.append("clear table")),
        console_widget=SimpleNamespace(clear_log=lambda: calls.append("clear log")),
        progress_summary=SimpleNamespace(clear_all=lambda: calls.append("clear progress")),
        _update_cart_toolbar_visibility=lambda: None,
        _update_row_count=lambda: None,
    )
    vars(page).update(state)
    return page, calls


def test_table_page_starts_and_redirects_the_run():
    from ofscraper.gui.pages.table_page import TablePage

    started = []
    wf = SimpleNamespace(_selected_actions={"paid_all"}, start_paid_all=lambda: started.append(1))
    page, calls = _fake_table(wf)
    TablePage.start_paid_all_run(page)
    assert started == [1]
    assert calls == ["clear table", "clear log", "clear progress"]
    assert page._live_rows_loaded is False and page._check_mode_active is False

    # "Start Scraping" on the table also goes to the all-purchased run
    redirected = []
    page.start_paid_all_run = lambda: redirected.append(1)
    TablePage._on_start_scraping(page)
    assert redirected == [1]

    # not while a scrape is running or still cancelling
    for busy in ({"_scrape_active": True}, {"_cancelling": True}):
        started.clear()
        page, _ = _fake_table(wf, **busy)
        TablePage.start_paid_all_run(page)
        assert started == []


@pytest.fixture
def pick(qapp, gui_settings_file, monkeypatch):
    """An ActionPage whose Pick… dialog is driven by `drive(dialog)`."""
    from PyQt6.QtWidgets import QDialog
    from ofscraper.gui.pages.action_page import ActionPage

    page = ActionPage()
    state = {"names": ["Alice", "bob", "Carol"], "drive": None}
    monkeypatch.setattr(ActionPage, "known_creator_names", staticmethod(lambda: list(state["names"])))
    monkeypatch.setattr(QDialog, "exec", lambda dlg: state["drive"](dlg))
    return page, state


def _items(dlg):
    from PyQt6.QtWidgets import QListWidget

    lst = dlg.findChild(QListWidget)
    return {lst.item(i).text(): lst.item(i) for i in range(lst.count())}


def test_pick_ticks_known_names_and_filters(pick):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QLineEdit

    page, state = pick
    page._paid_all_exclude_input.setText("carol, Zed")
    seen = {}

    def drive(dlg):
        items = _items(dlg)
        seen["names"] = list(items)
        seen["ticked"] = [n for n, it in items.items() if it.checkState() == Qt.CheckState.Checked]
        dlg.findChild(QLineEdit).setText("AL")
        seen["visible"] = [n for n, it in items.items() if not it.isHidden()]
        items["Alice"].setCheckState(Qt.CheckState.Checked)
        items["zed"].setCheckState(Qt.CheckState.Unchecked)
        return QDialog.DialogCode.Accepted

    state["drive"] = drive
    page._on_paid_all_pick()
    assert seen["names"] == ["Alice", "bob", "Carol", "zed"]  # typed names are kept
    assert seen["ticked"] == ["Carol", "zed"]
    assert seen["visible"] == ["Alice"]  # search ignores case
    assert page._paid_all_exclude_input.text() == "Alice, Carol"
    assert page.get_paid_all_options()["excluded"] == ["alice", "carol"]


def test_pick_cancel_and_no_names(pick, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialog, QMessageBox

    page, state = pick
    page._paid_all_exclude_input.setText("bob")

    def drive(dlg):
        _items(dlg)["Alice"].setCheckState(Qt.CheckState.Checked)
        return QDialog.DialogCode.Rejected

    state["drive"] = drive
    page._on_paid_all_pick()
    assert page._paid_all_exclude_input.text() == "bob"  # Cancel changes nothing

    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[1]))
    state["names"] = []
    page._paid_all_exclude_input.setText("")
    state["drive"] = lambda dlg: pytest.fail("no dialog without names")
    page._on_paid_all_pick()
    assert told == ["No creators known yet"]


def _fake_area_page(**state):
    area = SimpleNamespace(_models_loading=False, _models_loaded=False, started=[])

    def start():
        area.started.append(1)
        area._models_loading = True

    area._start_model_load = start
    vars(area).update(state)
    return area


def test_pick_offers_to_load_subscriptions(pick, monkeypatch):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QDialog, QMessageBox

    page, state = pick
    page.area_page = _fake_area_page()  # page.window() is the page itself here
    state["names"] = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: pytest.fail("should offer a load"))
    opened = []
    state["drive"] = lambda dlg: opened.append(list(_items(dlg))) or QDialog.DialogCode.Rejected

    page._on_paid_all_pick()
    assert page.area_page.started == [1]
    assert not page._paid_all_pick_btn.isEnabled()
    assert page._paid_all_pick_btn.text() == "Loading…"
    timer = page.findChildren(QTimer)[-1]

    timer.timeout.emit()  # still loading
    assert opened == []

    page.area_page._models_loading = False  # load finished
    page.area_page._models_loaded = True
    state["names"] = ["Alice", "bob"]
    timer.timeout.emit()
    assert opened == [["Alice", "bob"]]  # Pick… opened again by itself
    assert page._paid_all_pick_btn.isEnabled() and page._paid_all_pick_btn.text() == "Pick…"


def test_pick_load_declined_or_failed(pick, monkeypatch):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QMessageBox

    page, state = pick
    state["names"] = []
    state["drive"] = lambda dlg: pytest.fail("no dialog without names")
    told = []
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: told.append(a[1]))

    # "No" at the question: nothing loads, no second message
    page.area_page = _fake_area_page()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    page._on_paid_all_pick()
    assert page.area_page.started == [] and told == []

    # load fails: the button comes back, Pick… doesn't open
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page._on_paid_all_pick()
    page.area_page._models_loading = False
    page.findChildren(QTimer)[-1].timeout.emit()
    assert page._paid_all_pick_btn.isEnabled() and told == []

    # already loaded but no subscriptions: just explain
    page.area_page = _fake_area_page(_models_loaded=True)
    page._on_paid_all_pick()
    assert page.area_page.started == [] and told == ["No creators known yet"]


def _set_counters(**counts):
    import ofscraper.commands.scraper.actions.utils.globals as cg

    for name in ("video_count", "photo_count", "audio_count", "forced_skipped", "skipped", "total_bytes_downloaded"):
        setattr(cg, name, counts.get(name, 0))


@pytest.fixture
def counters():
    import ofscraper.commands.scraper.actions.utils.globals as cg

    names = ("video_count", "photo_count", "audio_count", "forced_skipped", "skipped", "total_bytes_downloaded")
    saved = {n: getattr(cg, n, 0) for n in names}
    yield
    for n, v in saved.items():
        setattr(cg, n, v)


def test_summary_counts_every_creator(workflow, monkeypatch, gui_settings_file, counters):
    # Each creator's download resets the counters, so the summary must add up
    # per-creator stats, not show the last creator's counters for everyone.
    import ofscraper.data.api.paid as paid_api
    import ofscraper.data.posts.scrape_paid as spm

    async def get_all_paid_posts():
        return {1: [], 2: [], 3: []}

    async def resolve(mid):
        return {1: "alice", 2: "bob", 3: "carol"}[mid]

    downloads = {"alice": dict(video_count=3, photo_count=2, total_bytes_downloaded=500),
                 "bob": dict(video_count=1, skipped=1, total_bytes_downloaded=100)}

    async def fake_process_user(value, length):
        if value["medias"]:
            _set_counters(**downloads[value["username"]])  # the downloader resets, then counts

    monkeypatch.setattr(spm, "process_user", fake_process_user)

    def runner(self):
        async def run_all():
            [x async for x in spm.process_paid_dict()]  # picks the creators, as in a real run
            for name, medias in (("alice", ["m"]), ("bob", ["m"]), ("carol", [])):
                await spm.process_user({"username": name, "model_id": 0, "medias": medias, "posts": []}, 3)

        asyncio.run(run_all())

    monkeypatch.setattr(paid_api, "get_all_paid_posts", get_all_paid_posts)
    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    monkeypatch.setattr(workflow_mod, "_make_gui_scraper_manager", lambda: type("M", (), {"runner": runner}))
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: {})
    monkeypatch.setattr(workflow_mod, "_emit_download_status", lambda *a, **k: None)
    monkeypatch.setattr(workflow_mod._gui_state, "start_polling", lambda *a, **k: None)
    monkeypatch.setattr(workflow_mod._gui_state, "stop_polling", lambda *a, **k: None)
    workflow_mod._pending_summary_data = None
    workflow._on_paid_all_options({"excluded": []})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    workflow._run_scraper_thread()

    per = workflow._per_model_run_stats
    assert (per["alice"]["videos"], per["alice"]["photos"]) == (3, 2)
    assert (per["bob"]["videos"], per["bob"]["failed"]) == (1, 1)
    # carol had nothing: zeros, not bob's leftover counters
    assert all(v == 0 for v in per["carol"].values())
    s = workflow_mod._pending_summary_data
    assert s is not None
    assert (s["run_dl"], s["run_videos"], s["run_photos"], s["failed"], s["total_bytes"]) == (6, 4, 2, 1, 600)
    assert sorted(s["model_names"]) == ["alice", "bob", "carol"]
    assert set(s["per_model"]) == {"alice", "bob", "carol"}


def test_model_with_nothing_to_download_records_zeros(workflow, counters):
    _set_counters(video_count=5, total_bytes_downloaded=999)  # left from the previous model
    workflow._per_model_run_stats = {}
    workflow_mod._record_per_model_download_stats(workflow, "empty", nothing_downloaded=True)
    workflow_mod._record_per_model_download_stats(workflow, "full")
    assert all(v == 0 for v in workflow._per_model_run_stats["empty"].values())
    assert workflow._per_model_run_stats["full"]["videos"] == 5


def test_table_keeps_every_creator_while_scraping(workflow, monkeypatch, gui_settings_file):
    # Each creator's rows are shown as soon as it is scraped. Only the first
    # replaces the table; the rest are added, so earlier creators stay visible.
    import ofscraper.data.api.paid as paid_api
    import ofscraper.data.posts.scrape_paid as spm
    import ofscraper.db.operations as db_ops
    import ofscraper.db.operations_.media as media_ops
    import ofscraper.classes.of.posts as posts_cls
    import ofscraper.managers.postcollection as pc_mod

    async def get_all_paid_posts():
        return {1: [{}], 2: [{}], 3: [{}]}

    async def resolve(mid):
        return {1: "alice", 2: "bob", 3: "carol"}[mid]

    async def noop(*a, **k):
        return None

    class FakePC:
        def __init__(self, username, model_id):
            self.posts, self.all_unique_media = [], []
            self.media = [type("Media", (), {"id": model_id * 10})()]

        def add_posts(self, posts, actions=None):
            pass

        def get_media_for_processing(self):
            return self.media

        def get_posts_for_text_download(self):
            return []

    loads = []

    def runner(self):
        asyncio.run(_drain(spm.process_paid_dict()))

    async def _drain(gen):
        return [x async for x in gen]

    monkeypatch.setattr(paid_api, "get_all_paid_posts", get_all_paid_posts)
    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    monkeypatch.setattr(db_ops, "table_init_create", noop)
    monkeypatch.setattr(db_ops, "make_post_table_changes", noop)
    monkeypatch.setattr(media_ops, "batch_mediainsert", noop)
    monkeypatch.setattr(posts_cls, "Post", lambda *a, **k: object())
    monkeypatch.setattr(pc_mod, "PostCollection", FakePC)
    monkeypatch.setattr(workflow_mod, "_make_gui_scraper_manager", lambda: type("M", (), {"runner": runner}))
    monkeypatch.setattr(
        workflow_mod, "_load_models_from_db",
        lambda models, **kw: loads.append(([m.name for m in models], kw)) or {},
    )
    workflow._on_paid_all_options({"excluded": []})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    workflow._run_scraper_thread()

    # one load per creator while scraping (the final load after the run shows them all)
    live = [(names, kw.get("append", False)) for names, kw in loads if len(names) == 1]
    assert live == [(["alice"], False), (["bob"], True), (["carol"], True)]



def test_a_failed_creator_is_reported_not_hidden(workflow, monkeypatch, gui_settings_file):
    # One creator failing must not stop the others, and the user must be told.
    import ofscraper.data.api.paid as paid_api
    import ofscraper.data.posts.scrape_paid as spm
    import ofscraper.db.operations as db_ops
    import ofscraper.db.operations_.media as media_ops
    import ofscraper.classes.of.posts as posts_cls
    import ofscraper.managers.postcollection as pc_mod
    from ofscraper.gui.signals import app_signals

    async def get_all_paid_posts():
        return {1: [{}], 2: [{}]}

    async def resolve(mid):
        return {1: "alice", 2: "bob"}[mid]

    async def table_init_create(model_id=None, username=None):
        if username == "alice":
            raise RuntimeError("database is locked")

    async def noop(*a, **k):
        return None

    class FakePC:
        def __init__(self, username, model_id):
            self.posts, self.all_unique_media = [], []

        def add_posts(self, posts, actions=None):
            pass

        def get_media_for_processing(self):
            return []

        def get_posts_for_text_download(self):
            return []

    results = []

    def runner(self):
        async def drain():
            return [x async for x in spm.process_paid_dict()]

        results.extend(asyncio.run(drain()))

    shown = []

    def on_log(level, msg):
        shown.append((level, msg))

    app_signals.log_message.connect(on_log)
    monkeypatch.setattr(paid_api, "get_all_paid_posts", get_all_paid_posts)
    monkeypatch.setattr(post_mod, "resolve_paid_username", resolve)
    monkeypatch.setattr(db_ops, "table_init_create", table_init_create)
    monkeypatch.setattr(db_ops, "make_post_table_changes", noop)
    monkeypatch.setattr(media_ops, "batch_mediainsert", noop)
    monkeypatch.setattr(posts_cls, "Post", lambda *a, **k: object())
    monkeypatch.setattr(pc_mod, "PostCollection", FakePC)
    monkeypatch.setattr(workflow_mod, "_make_gui_scraper_manager", lambda: type("M", (), {"runner": runner}))
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: {})
    workflow._on_paid_all_options({"excluded": []})
    workflow._selected_actions = {"paid_all"}
    workflow._set_args()
    try:
        workflow._run_scraper_thread()
    finally:
        app_signals.log_message.disconnect(on_log)

    warnings = [msg for level, msg in shown if level == "WARNING" and "alice" in msg]
    assert len(warnings) == 1 and "database is locked" in warnings[0]
    assert not any("bob" in msg and level == "WARNING" for level, msg in shown)


@pytest.mark.parametrize("append, signal", [(False, "data_replace"), (True, "data_loading_finished")])
def test_append_adds_rows_instead_of_replacing(qapp, monkeypatch, tmp_path, append, signal):
    import sqlite3
    from types import SimpleNamespace

    from ofscraper.gui.signals import app_signals

    db = tmp_path / "user_data.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE medias (media_id, post_id, link, directory, filename, size, api_type,"
        " media_type, preview, linked, downloaded, created_at, unlocked, model_id, posted_at, hash, duration)"
    )
    conn.execute("INSERT INTO medias (media_id, media_type) VALUES (7, 'Videos')")
    conn.commit()
    conn.close()
    helper = SimpleNamespace(databasePathHelper=lambda model_id, username: db)
    import ofscraper.classes.placeholder as placeholder

    monkeypatch.setattr(placeholder, "databasePlaceholder", lambda: helper)
    monkeypatch.setattr(workflow_mod, "_build_db_rows", lambda data, username, post_info=None: [{"media_id": 7}])
    sent = {}
    handlers = {
        name: (lambda rows, name=name: sent.setdefault(name, rows))
        for name in ("data_replace", "data_loading_finished")
    }
    for name, fn in handlers.items():
        getattr(app_signals, name).connect(fn)
    try:
        workflow_mod._load_models_from_db(
            [SimpleNamespace(id=1, name="alice")], date_range={}, media_ids={7}, append=append
        )
    finally:
        for name, fn in handlers.items():
            getattr(app_signals, name).disconnect(fn)
    assert list(sent) == [signal] and sent[signal] == [{"media_id": 7}]
