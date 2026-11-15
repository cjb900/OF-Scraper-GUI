"""Moving OnlyFans downloads from the bare default save location into
<save root>/OnlyFans (next to Fansly), once, on the user's say-so."""

import json
import sqlite3

import pytest

from ofscraper.gui import site_context


@pytest.fixture
def env(monkeypatch, tmp_path):
    import ofscraper.utils.config.file as config_file
    import ofscraper.utils.of_env.of_env as of_env
    import ofscraper.utils.paths.common as common_paths
    from ofscraper.gui.utils import gui_settings

    home = tmp_path / "config"
    root = tmp_path / "Data" / "ofscraper"
    config = home / "config.json"
    home.mkdir(parents=True)
    config.write_text(json.dumps({"config": {"file_options": {"save_location": str(root)}}}))
    settings = {}

    monkeypatch.setattr(site_context, "is_fansly", lambda: False)
    monkeypatch.setattr(site_context, "default_config_home", lambda: home)
    real = of_env.getattr
    monkeypatch.setattr(of_env, "getattr", lambda k: str(root) if k == "SAVE_PATH_DEFAULT" else real(k))
    monkeypatch.setattr(common_paths, "get_config_path", lambda: config)
    monkeypatch.setattr(
        common_paths, "get_save_location",
        lambda config=None: json.loads(
            (home / "config.json").read_text())["config"]["file_options"]["save_location"],
    )
    monkeypatch.setattr(gui_settings, "load_gui_settings", lambda: dict(settings))
    monkeypatch.setattr(gui_settings, "save_gui_settings", lambda s, **k: settings.update(s) or True)
    monkeypatch.setattr(config_file, "_cached_config", None, raising=False)

    class Env:
        pass

    e = Env()
    e.home, e.root, e.config, e.settings = home, root, config, settings
    return e


def _saved_location(env):
    data = json.loads(env.config.read_text())
    return (data.get("config") or data)["file_options"]["save_location"]


def _db(env, model, directory):
    db = env.home / "main_profile" / ".data" / model / "user_data.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE medias (media_id INT, directory VARCHAR)")
    conn.execute("INSERT INTO medias VALUES (1, ?)", (str(directory),))
    conn.execute("INSERT INTO medias VALUES (2, NULL)")
    conn.commit()
    conn.close()
    return db


def test_models_in_the_root_are_offered(env):
    for name in ("alice", "bob", "Fansly", ".tmp"):
        (env.root / name).mkdir(parents=True)
    root, target, folders = site_context.onlyfans_folder_plan()
    assert root == env.root and target == env.root / "OnlyFans"
    assert folders == ["alice", "bob"]  # Fansly's folder and hidden ones stay


def test_move_carries_files_database_and_setting(env):
    (env.root / "alice" / "Posts" / "Images").mkdir(parents=True)
    (env.root / "alice" / "Posts" / "Images" / "a.jpg").write_text("x")
    (env.root / "Fansly" / "carol").mkdir(parents=True)
    db = _db(env, "alice", env.root / "alice" / "Posts" / "Images")

    result = site_context.apply_onlyfans_folder(site_context.onlyfans_folder_plan(), move=True)

    target = env.root / "OnlyFans"
    assert result["moved"] == ["alice"]
    assert (target / "alice" / "Posts" / "Images" / "a.jpg").exists()
    assert not (env.root / "alice").exists()
    assert (env.root / "Fansly" / "carol").exists()
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT directory FROM medias WHERE media_id=1").fetchone()[0] == str(
        target / "alice" / "Posts" / "Images")
    conn.close()
    assert _saved_location(env) == str(target)
    assert site_context.onlyfans_folder_plan() is None  # asked once


def test_keep_changes_nothing_and_does_not_ask_again(env):
    (env.root / "alice").mkdir(parents=True)
    site_context.apply_onlyfans_folder(site_context.onlyfans_folder_plan(), move=False)
    assert (env.root / "alice").exists()
    assert _saved_location(env) == str(env.root)
    assert site_context.onlyfans_folder_plan() is None


def test_nothing_saved_yet_just_switches(env):
    plan = site_context.onlyfans_folder_plan()
    assert plan[2] == []
    site_context.apply_onlyfans_folder(plan, move=False)
    assert _saved_location(env) == str(env.root / "OnlyFans")


def test_existing_target_folder_is_left_alone(env):
    (env.root / "alice").mkdir(parents=True)
    (env.root / "OnlyFans" / "alice").mkdir(parents=True)
    result = site_context.apply_onlyfans_folder(site_context.onlyfans_folder_plan(), move=True)
    assert result["skipped"] == ["alice"] and (env.root / "alice").exists()


def test_custom_save_location_is_never_touched(env):
    env.config.write_text(json.dumps({"config": {"file_options": {"save_location": "/media/mine"}}}))
    assert site_context.onlyfans_folder_plan() is None
    assert _saved_location(env) == "/media/mine"


def test_fansly_is_never_asked(env, monkeypatch):
    monkeypatch.setattr(site_context, "is_fansly", lambda: True)
    (env.root / "alice").mkdir(parents=True)
    assert site_context.onlyfans_folder_plan() is None


@pytest.fixture(scope="module")
def qapp():
    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("click_move", [True, False])
def test_popup_moves_or_keeps(qapp, env, monkeypatch, click_move):
    from PyQt6.QtWidgets import QMessageBox, QWidget

    from ofscraper.gui import app

    (env.root / "alice").mkdir(parents=True)
    shown = []

    def fake_exec(box):
        shown.append(box.text() + box.informativeText())
        buttons = [b for b in box.buttons() if b.text()]
        if len(buttons) > 1:  # the question; the result box has only OK
            box._clicked = next(b for b in buttons if ("Move" in b.text()) == click_move)
        return 0

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: getattr(box, "_clicked", None))
    window = QWidget()
    app._offer_onlyfans_folder(window)
    assert "alice" in shown[0]
    assert (env.root / "OnlyFans" / "alice").exists() == click_move
    assert len(shown) == (2 if click_move else 1)  # the result is reported after a move
