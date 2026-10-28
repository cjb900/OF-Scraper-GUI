"""The GUI's "Update metadata" action runs the same job as `ofscraper metadata`."""
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

import ofscraper.commands.metadata.metadata as metadata_mod  # noqa: E402
import ofscraper.commands.utils.command as command_mod  # noqa: E402
import ofscraper.utils.args.accessors.read as read_args  # noqa: E402
import ofscraper.utils.args.mutators.write as write_args  # noqa: E402
import ofscraper.utils.config.data as config_data  # noqa: E402
import ofscraper.utils.settings as settings  # noqa: E402
import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402

# the args that decide what the metadata command does
KEYS = ["command", "metadata", "mark_stray", "anon", "actions", "posts", "scrape_paid", "usernames"]


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
    wf = workflow_mod.GUIWorkflow(None)
    wf._selected_models = [SimpleNamespace(name="bob", id=1)]
    wf._selected_areas = ["Timeline", "Messages"]
    wf._selected_mediatypes = ["Images", "Videos", "Audios"]
    return wf


def _cli_args(tmp_path, argv):
    script = textwrap.dedent(
        f"""
        import json, sys
        sys.argv = ["ofscraper"] + {argv!r}
        import ofscraper.main.open.load
        import ofscraper.utils.args.accessors.read as r
        a = r.retriveArgs()
        print(json.dumps({{k: a.get(k) for k in {KEYS!r}}}, default=sorted))
        """
    )
    env = dict(os.environ, HOME=str(tmp_path), USERPROFILE=str(tmp_path))
    out = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, timeout=120
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def _gui_args():
    a = read_args.retriveArgs()
    return {k: (sorted(a.get(k)) if k == "posts" else a.get(k)) for k in KEYS}


@pytest.mark.parametrize(
    "options, paid, cli",
    [
        ({"mode": "update"}, False, ["-md", "update"]),
        ({"mode": "check", "mark_stray": True}, False, ["-md", "check", "-msl"]),
        ({"mode": "complete"}, True, ["-md", "complete", "--scrape-paid", "complete"]),
    ],
)
def test_args_match_the_cli_metadata_command(workflow, tmp_path, options, paid, cli):
    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options(options)
    workflow._scrape_paid = paid
    workflow._set_args()
    expected = _cli_args(
        tmp_path, ["metadata", *cli, "--username", "bob", "--posts", "timeline,messages"]
    )
    expected["posts"] = sorted(expected["posts"])
    assert _gui_args() == expected


def test_a_download_after_metadata_gets_normal_args_back(workflow):
    launch_command = read_args.retriveArgs().command
    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options({"mode": "update", "mark_stray": True})
    workflow._scrape_paid = True
    workflow._set_args()
    assert settings.get_settings().command == "metadata"

    workflow._on_action_selected({"download"})
    workflow._scrape_paid = False
    workflow._set_args()
    args = read_args.retriveArgs()
    assert args.command == launch_command
    assert args.metadata is None
    assert args.mark_stray is False
    assert args.scrape_paid is False
    assert args.actions == ["download"]
    assert settings.get_settings().command == launch_command


def test_run_uses_the_hash_choice_and_cancels_between_models(workflow, monkeypatch):
    seen = {}
    loaded = []
    helped = []
    monkeypatch.setattr(command_mod.CommandManager, "_data_helper", lambda self, ele: helped.append(ele.name))
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: loaded.append(models))
    real_get_hash = config_data.get_hash

    def fake_process_selected_areas():
        settings.update_args(read_args.retriveArgs())  # the real run rebuilds settings
        seen["hash"] = settings.get_settings().hash
        mgr = metadata_mod.MetadataCommandManager()
        mgr._data_helper(SimpleNamespace(name="bob"))
        workflow_mod._gui_cancel_event.set()
        mgr._data_helper(SimpleNamespace(name="carol"))  # cancel stops here

    monkeypatch.setattr(metadata_mod, "process_selected_areas", fake_process_selected_areas)
    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options({"mode": "update", "hash": not bool(real_get_hash())})
    workflow._set_args()
    try:
        with pytest.raises(KeyboardInterrupt):
            workflow._run_metadata_mode()
    finally:
        workflow_mod._gui_cancel_event.clear()

    assert seen["hash"] is (not bool(real_get_hash()))
    assert helped == ["bob"]
    assert loaded == []  # cancelled: no table reload
    # everything put back
    assert config_data.get_hash is real_get_hash
    assert "_data_helper" not in vars(metadata_mod.MetadataCommandManager)


def test_finished_run_reloads_the_table(workflow, monkeypatch):
    loaded = []
    monkeypatch.setattr(metadata_mod, "process_selected_areas", lambda: None)
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: loaded.append([m.name for m in models]))
    workflow._on_action_selected({"metadata"})
    workflow._set_args()
    workflow._run_metadata_mode()
    assert loaded == [["bob"]]


@pytest.mark.parametrize("answer, mode, expected", [
    ("Yes", "complete", True),
    ("No", "complete", False),
    (None, "update", True),  # no dialog for other modes
])
def test_complete_mode_asks_first(workflow, monkeypatch, answer, mode, expected):
    asked = []
    QMessageBox = QtWidgets.QMessageBox

    def question(*a, **k):
        asked.append(1)
        return getattr(QMessageBox.StandardButton, answer)

    monkeypatch.setattr(QMessageBox, "question", question)
    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options({"mode": mode})
    assert workflow._confirm_metadata_complete() is expected
    assert len(asked) == (1 if answer else 0)


def test_action_page_panel_and_signals(qapp):
    from ofscraper.gui.pages.action_page import ALL_CHOICES, ActionPage

    page = ActionPage()
    idx = next(i for i, (_, a) in enumerate(ALL_CHOICES) if a == {"metadata"})
    assert page._metadata_widget.isHidden()
    page._button_group.button(idx).setChecked(True)
    page._on_action_changed(idx)
    assert not page._metadata_widget.isHidden()

    page._metadata_mode_radios["check"].setChecked(True)
    page._metadata_mark_stray_check.setChecked(True)
    page._metadata_hash_check.setChecked(True)
    got = []
    opts_slot = lambda o: got.append(("options", o))
    act_slot = lambda a: got.append(("actions", a))
    app_signals.metadata_options_changed.connect(opts_slot)
    app_signals.action_selected.connect(act_slot)
    try:
        page._on_next()
    finally:
        app_signals.metadata_options_changed.disconnect(opts_slot)
        app_signals.action_selected.disconnect(act_slot)
    # options first, so the workflow has them before the next page
    assert got == [
        ("options", {"mode": "check", "mark_stray": True, "hash": True}),
        ("actions", {"metadata"}),
    ]

    page.reset_to_defaults()
    assert page._metadata_widget.isHidden()
    assert page.get_metadata_options()["mode"] == "update"


def test_area_page_hides_download_only_options(qapp):
    from ofscraper.gui.pages.area_selector_page import AreaSelectorPage

    page = AreaSelectorPage()
    page.daemon_check.setChecked(True)
    page._current_actions = {"metadata"}
    page._update_available_areas()
    assert page.areas_group.title() == "Metadata Areas"
    for w in (page._text_group, page._discord_row, page._adv_group, page._daemon_group, page._daemon_sep):
        assert w.isHidden()
    assert not page.daemon_check.isChecked()
    assert not page.scrape_paid_check.isHidden()  # metadata --scrape-paid is supported

    page._current_actions = {"download"}
    page._update_available_areas()
    assert page.areas_group.title() == "Content Areas"
    for w in (page._text_group, page._discord_row, page._adv_group, page._daemon_group, page._daemon_sep):
        assert not w.isHidden()


def test_history_keeps_the_metadata_options(workflow):
    from ofscraper.gui.utils import scrape_history

    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options({"mode": "complete", "mark_stray": True, "hash": True})
    snap = scrape_history.snapshot_from_workflow(workflow)
    assert snap["metadata"] == {"mode": "complete", "mark_stray": True, "hash": True}

    workflow._on_action_selected({"download"})
    assert "metadata" not in scrape_history.snapshot_from_workflow(workflow)


def test_scraper_thread_routes_to_metadata_and_finishes(workflow, monkeypatch):
    calls = []
    finished = []
    monkeypatch.setattr(metadata_mod, "process_selected_areas", lambda: calls.append("metadata"))
    monkeypatch.setattr(workflow_mod, "_load_models_from_db", lambda models, **kw: calls.append("table"))
    monkeypatch.setattr(workflow, "_run_check_mode", lambda: calls.append("check"))
    slot = lambda: finished.append(1)
    app_signals.scraping_finished.connect(slot)
    try:
        workflow._on_action_selected({"metadata"})
        workflow._set_args()
        workflow._run_scraper_thread()
    finally:
        app_signals.scraping_finished.disconnect(slot)
    assert calls == ["metadata", "table"]
    assert finished == [1]


@pytest.mark.parametrize("answer", ["Yes", "No"])
def test_start_stops_when_complete_mode_is_declined(workflow, monkeypatch, answer):
    from ofscraper.gui.utils import config_validation, key_mode_warning

    QMessageBox = QtWidgets.QMessageBox
    reached = []
    finished = []
    monkeypatch.setattr(key_mode_warning, "confirm_remote_key_mode", lambda *a, **k: True)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: getattr(QMessageBox.StandardButton, answer))
    # the next check after the Complete confirm; stop the start there
    monkeypatch.setattr(config_validation, "confirm_config_for_scrape", lambda *a, **k: reached.append(1) or False)
    slot = lambda: finished.append(1)
    app_signals.scraping_finished.connect(slot)
    try:
        workflow._on_action_selected({"metadata"})
        workflow._on_metadata_options({"mode": "complete"})
        workflow._start_scraping()
    finally:
        app_signals.scraping_finished.disconnect(slot)
    assert reached == ([1] if answer == "Yes" else [])
    assert finished == [1]  # the table leaves its "Scraping" state either way
    assert getattr(workflow, "_scraper_thread", None) is None


def test_history_rerun_restores_the_metadata_options(workflow):
    from ofscraper.gui.pages.area_selector_page import AreaSelectorPage
    from ofscraper.gui.utils import scrape_history

    workflow._on_action_selected({"metadata"})
    workflow._on_metadata_options({"mode": "check", "mark_stray": True, "hash": True})
    snap = scrape_history.snapshot_from_workflow(workflow)

    other = workflow_mod.GUIWorkflow(None)
    area_page = AreaSelectorPage()
    bob = workflow._selected_models[0]
    main = SimpleNamespace(workflow=other, area_page=area_page, model_page=SimpleNamespace(_all_models={"bob": bob}))
    ok, message = scrape_history.apply_entry_to_pages(snap, main_window=main)
    assert ok, message
    assert other._selected_actions == {"metadata"}
    assert other._metadata_options == {"mode": "check", "mark_stray": True, "hash": True}
    assert other._selected_models == [bob]
    assert area_page.areas_group.title() == "Metadata Areas"
