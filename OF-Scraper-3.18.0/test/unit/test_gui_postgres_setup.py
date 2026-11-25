"""Merge DBs > PostgreSQL: the address is saved to the GUI's own env file
(never config.json), listed in both sites' config.json, and taken back out."""

import json
import os
import stat
import sys
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from ofscraper.gui import site_context
from ofscraper.gui.utils import postgres_setup as pg


def test_the_address_survives_special_characters():
    url = pg.build_url("db.lan", 5433, "of scraper", "me@x", "p@ss:w/rd #1")
    assert url == "postgresql://me%40x:p%40ss%3Aw%2Frd%20%231@db.lan:5433/of%20scraper"
    assert pg.parse_url(url) == {
        "host": "db.lan",
        "port": 5433,
        "database": "of scraper",
        "user": "me@x",
        "password": "p@ss:w/rd #1",
    }


def test_an_ipv6_host_is_bracketed():
    url = pg.build_url("::1", 5432, "d", "u", "")
    assert url == "postgresql://u@[::1]:5432/d"
    assert pg.parse_url(url)["host"] == "::1"


@pytest.mark.parametrize(
    "fields, message",
    [
        (("", 5432, "d", "u", "p"), "host"),
        (("h", 5432, "", "u", "p"), "database"),
        (("h", 5432, "d", "", "p"), "user"),
        (("h", "x", "d", "u", "p"), "number"),
    ],
)
def test_missing_fields_are_named(fields, message):
    with pytest.raises(ValueError, match=message):
        pg.build_url(*fields)


def test_a_keyword_address_isnt_split_into_fields():
    assert pg.parse_url("host=db user=me password=x") == {}


@pytest.fixture
def configs(tmp_path, monkeypatch):
    """An OnlyFans and a Fansly config.json, this process being OnlyFans."""
    home = tmp_path / "ofscraper"
    onlyfans = home / "config.json"
    fansly = home / site_context.FANSLY_FOLDER / "config.json"
    for path, extra in ((onlyfans, ["/keep/me.env"]), (fansly, [])):
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"config": {"main_profile": "main_profile", "advanced_options": {"env_files": extra}}}),
            encoding="utf-8",
        )
    monkeypatch.setattr(site_context, "default_config_home", lambda: home)
    monkeypatch.setattr(site_context, "is_fansly", lambda: False)
    import ofscraper.utils.paths.common as common_paths

    monkeypatch.setattr(common_paths, "get_config_path", lambda: onlyfans)
    # saving clears the scraper's cached config.json; put it back afterwards
    import ofscraper.utils.config.file as config_file

    monkeypatch.setattr(config_file, "_cached_config", config_file._cached_config)
    monkeypatch.setattr(config_file, "_cached_stamp", config_file._cached_stamp)
    return SimpleNamespace(home=home, onlyfans=onlyfans, fansly=fansly)


def _env_files(path):
    return json.loads(path.read_text(encoding="utf-8"))["config"]["advanced_options"]["env_files"]


def test_save_writes_a_private_env_file_listed_by_both_sites(configs):
    url = pg.build_url("db.lan", 5432, "ofscraper", "me", "p@ss w'rd"[:-3] + "rd")

    said = pg.save(url)

    env_file = configs.home / pg.ENV_FILE_NAME
    assert dotenv_values(env_file)[pg.URL_KEY] == url
    assert pg.saved_url() == url
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(env_file).st_mode) == 0o600
    assert _env_files(configs.onlyfans) == ["/keep/me.env", str(env_file)]
    assert _env_files(configs.fansly) == [str(env_file)]
    # the password is never in config.json
    for path in (configs.onlyfans, configs.fansly):
        assert "p%40ss" not in path.read_text(encoding="utf-8")
    assert len(said) == 3

    # saving again doesn't list it twice
    pg.save(url)
    assert _env_files(configs.onlyfans) == ["/keep/me.env", str(env_file)]


def test_remove_unlists_and_deletes_it(configs):
    pg.save(pg.build_url("db.lan", 5432, "ofscraper", "me", "secret"))

    pg.remove()

    assert not (configs.home / pg.ENV_FILE_NAME).exists()
    assert _env_files(configs.onlyfans) == ["/keep/me.env"]
    assert _env_files(configs.fansly) == []
    assert pg.saved_url() == ""


def test_a_site_without_a_config_yet_is_named(configs):
    configs.fansly.unlink()

    said = pg.save(pg.build_url("db.lan", 5432, "ofscraper", "me", "secret"))

    assert any("Fansly: no config.json yet" in line for line in said)
    assert not configs.fansly.exists()


def test_a_quote_cant_break_the_env_file(configs):
    with pytest.raises(ValueError):
        pg.save("postgresql://me:a'b@h/d")


def test_the_commands_get_the_address_and_not_the_tab_variables(monkeypatch):
    monkeypatch.setenv(site_context.ENV_CHILD, "1")
    env = pg.command_environment("postgresql://u:p@h:5432/d")
    assert env[pg.URL_KEY] == "postgresql://u:p@h:5432/d"
    assert site_context.ENV_CHILD not in env
    monkeypatch.setenv(pg.URL_KEY, "postgresql://old")
    assert pg.URL_KEY not in pg.command_environment(None)


def test_commands():
    assert pg.import_command("/d", apply=True, skip_bad=True)[-4:] == [
        "ofscraper.commands.postgres_import", "/d", "--apply", "--skip-bad-files"
    ]
    assert pg.export_command("/o", apply=False, site="fansly")[-4:] == [
        "ofscraper.commands.postgres_export", "/o", "--site", "fansly"
    ]


def test_the_password_is_hidden_in_output():
    url = pg.build_url("db.lan", 5432, "d", "me", "hunter2")
    assert "hunter2" not in pg.masked(f"failed for {url} with hunter2", url)


@pytest.fixture
def qapp():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


def test_building_merge_dbs_reads_no_settings(qapp, monkeypatch):
    """The PostgreSQL tab reads the profile folder and the address when it is
    first shown: building the page must not load the scraper's settings."""
    import ofscraper.utils.settings as settings

    def refuse():
        raise AssertionError("settings were loaded while the page was built")

    monkeypatch.setattr(settings, "get_settings", refuse)
    monkeypatch.setattr(settings, "get_args", refuse)
    from ofscraper.gui.dialogs.merge_dialog import MergePage

    page = MergePage()
    assert page.tabs.tabText(1) == "PostgreSQL"
    assert not page.postgres_panel.import_btn.isEnabled()
