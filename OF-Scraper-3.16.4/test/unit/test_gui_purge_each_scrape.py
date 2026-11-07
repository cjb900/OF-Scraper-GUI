"""Delete model DB / downloaded files must work on every scrape of a GUI session.

The workflow object lives for the whole session; its "already purged" flag was
only reset when it was created, so the second purge of a session was skipped
silently and the scrape found nothing new.
"""
import inspect
import sqlite3
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.classes.placeholder as placeholder  # noqa: E402
import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
import ofscraper.utils.args.accessors.read as read_args  # noqa: E402
import ofscraper.utils.paths.common as common_paths  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402

pytestmark = pytest.mark.unit

MODEL = SimpleNamespace(id=1234, name="creator")


@pytest.fixture
def env(tmp_path, monkeypatch):
    profile = tmp_path / "profile"
    save = tmp_path / "save"
    db_path = profile / ".data" / str(MODEL.id) / "user_data.db"

    class _Placeholder:
        def databasePathHelper(self, model_id, username):
            return str(db_path)

    monkeypatch.setattr(placeholder, "databasePlaceholder", _Placeholder)
    monkeypatch.setattr(common_paths, "get_profile_path", lambda *a, **k: str(profile))
    monkeypatch.setattr(common_paths, "get_save_location", lambda *a, **k: str(save))
    monkeypatch.setattr(read_args, "retriveArgs", lambda: SimpleNamespace(action=["download"]))

    messages = []
    slot = lambda level, msg: messages.append((level, msg))  # noqa: E731
    app_signals.log_message.connect(slot)
    yield SimpleNamespace(db_path=db_path, save=save, messages=messages)
    app_signals.log_message.disconnect(slot)


def _make_db(env, with_file=False):
    env.db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(env.db_path)
    con.execute("CREATE TABLE medias (directory TEXT, filename TEXT, downloaded INTEGER)")
    if with_file:
        folder = env.save / MODEL.name / "Posts" / "Images"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a.jpg").write_bytes(b"x")
        con.execute("INSERT INTO medias VALUES (?, ?, 1)", (str(folder), "a.jpg"))
    con.commit()
    con.close()


def _workflow(delete_files=False):
    wf = workflow_mod.GUIWorkflow(None)
    wf._selected_models = [MODEL]
    wf._advanced = {
        "rescrape_all": True,
        "delete_model_db": True,
        "delete_downloads": delete_files,
    }
    return wf


def test_every_scrape_of_a_session_purges(env):
    wf = _workflow()
    _make_db(env)
    wf._reset_purge_for_new_scrape()
    wf._maybe_purge_before_scrape()
    assert not env.db_path.exists()

    # second scrape in the same GUI session (the DB was rebuilt by scraping)
    _make_db(env)
    wf._reset_purge_for_new_scrape()
    wf._maybe_purge_before_scrape()
    assert not env.db_path.exists()


def test_a_second_purge_in_one_scrape_is_skipped_but_said(env):
    wf = _workflow()
    _make_db(env)
    wf._maybe_purge_before_scrape()
    _make_db(env)
    env.messages.clear()
    wf._maybe_purge_before_scrape()  # same scrape (e.g. a daemon re-run)
    assert env.db_path.exists()
    assert any(level == "WARNING" and "not deleting again" in msg for level, msg in env.messages)


def test_downloaded_files_are_deleted_on_a_later_scrape_too(env):
    wf = _workflow(delete_files=True)
    for _ in range(2):
        _make_db(env, with_file=True)
        wf._reset_purge_for_new_scrape()
        wf._maybe_purge_before_scrape()
        assert not (env.save / MODEL.name).exists()
        assert not env.db_path.exists()


def test_start_scraping_resets_before_the_thread_starts():
    src = inspect.getsource(workflow_mod.GUIWorkflow._start_scraping)
    assert src.index("self._reset_purge_for_new_scrape()") < src.index("thread.start()")
