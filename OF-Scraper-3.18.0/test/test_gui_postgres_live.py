"""The GUI with PostgreSQL on, against a real server: files brought in with
the commands Merge DBs > PostgreSQL runs, then the GUI's table, "new since
the last run", Purge and the OnlyFans folder move work on PostgreSQL.

Skipped unless OFSC_TEST_POSTGRES_URL names a server the tests may use. Each
test makes a database of its own and drops it.
"""

import os
import pathlib
import sqlite3
import subprocess
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit, urlunsplit

import pytest

URL = os.environ.get("OFSC_TEST_POSTGRES_URL", "")
if not URL:
    pytest.skip("needs a PostgreSQL server: set OFSC_TEST_POSTGRES_URL", allow_module_level=True)

import psycopg  # noqa: E402

import ofscraper.__main__  # noqa: E402,F401  (import order)
import ofscraper.classes.placeholder as placeholder  # noqa: E402
import ofscraper.db.postgres as postgres  # noqa: E402
from ofscraper.gui import site_context  # noqa: E402
from ofscraper.gui.utils import database_reads, postgres_setup, workflow  # noqa: E402
from test.import_files import current_file  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CREATOR = SimpleNamespace(id=111, name="a_creator")


@pytest.fixture
def database():
    """A new, empty database on the server: its URL."""
    name = f"t_gui_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {name}")
    parts = urlsplit(URL)
    url = urlunsplit(parts._replace(path=f"/{name}"))
    yield url
    postgres.POSTGRES.shutdown()
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")


@pytest.fixture(autouse=True)
def settings_reloaded(monkeypatch):
    """The site is OnlyFans without reading the scraper's settings (which
    would parse the command line), and of_env keeps what it loaded while
    the test's URL was set: load it again without it afterwards, so the
    tests after these see SQLite."""
    import ofscraper.sites as sites

    monkeypatch.setattr(sites, "current_site", lambda: "onlyfans")
    yield
    import ofscraper.utils.of_env.of_env as of_env

    monkeypatch.delenv(postgres.URL_KEY, raising=False)
    of_env.get_all_configs(forced=True)


def gui_command(command, url, home):
    env = postgres_setup.command_environment(url)
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    done = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def sqlite_rows(db, query):
    with sqlite3.connect(db) as conn:
        return conn.execute(query).fetchall()


def test_files_brought_in_from_the_gui_read_the_same(tmp_path, monkeypatch, database):
    home = tmp_path / "home"
    data = home / ".config" / "ofscraper" / "main_profile" / ".data"
    db = data / "111" / "user_data.db"
    current_file(db, 111)

    class _Ph:
        def databasePathHelper(self, model_id, username):
            return str(db)

    monkeypatch.setattr(placeholder, "databasePlaceholder", _Ph)
    monkeypatch.delenv(postgres.URL_KEY, raising=False)
    before = workflow._load_models_from_db([CREATOR], stats_only=True)

    # preview, then import, as the PostgreSQL tab runs them
    code, said = gui_command(postgres_setup.import_command(data), database, home)
    assert code == 0, said
    assert "with --apply to bring" in said
    code, said = gui_command(postgres_setup.import_command(data, apply=True), database, home)
    assert code == 0, said

    monkeypatch.setenv(postgres.URL_KEY, database)
    assert postgres_setup.enabled()
    assert postgres_setup.test_connection(database).startswith("Connected to PostgreSQL")

    # the table and its counts
    assert workflow._load_models_from_db([CREATOR], stats_only=True) == before
    rows, post_info = database_reads.read_creator_media(111, "a_creator")
    assert len(rows) == len(sqlite_rows(db, "SELECT media_id FROM medias WHERE model_id = 111"))
    assert post_info and all(set(v) == {"price", "text"} for v in post_info.values())

    # new since the last run
    import arrow

    newest = sqlite_rows(db, "SELECT MAX(posted_at) FROM medias")[0][0]
    assert arrow.get(database_reads.newest_posted_at(111, "a_creator")) == arrow.get(newest)

    # Purge's file list
    expected = {
        (d, f)
        for d, f in sqlite_rows(
            db,
            "SELECT directory, filename FROM medias WHERE downloaded = 1"
            " AND directory IS NOT NULL AND filename IS NOT NULL",
        )
    }
    assert set(database_reads.downloaded_files(111, "a_creator")) == expected

    # the OnlyFans folder move
    old = pathlib.Path(sorted(d for d, _ in expected)[0])
    new = tmp_path / "moved" / old.name
    changed = database_reads.move_download_paths([(old, new)], site_context._relocated)
    assert changed >= 1
    dirs = {d for d, _ in database_reads.downloaded_files(111, "a_creator")}
    assert str(new) in dirs and str(old) not in dirs

    # Purge's "Delete model DB": the rows go, the old file stays
    assert database_reads.delete_creator_rows(111, "a_creator") > 0
    assert database_reads.read_creator_media(111, "a_creator")[0] == []
    assert db.exists()


def test_export_from_the_gui_writes_a_file_per_creator(tmp_path, monkeypatch, database):
    home = tmp_path / "home"
    data = home / ".config" / "ofscraper" / "main_profile" / ".data"
    current_file(data / "111" / "user_data.db", 111)
    code, said = gui_command(postgres_setup.import_command(data, apply=True), database, home)
    assert code == 0, said

    out = tmp_path / "out"
    code, said = gui_command(postgres_setup.export_command(out, site="onlyfans"), database, home)
    assert code == 0, said
    assert not (out / "111" / "user_data.db").exists()
    code, said = gui_command(
        postgres_setup.export_command(out, apply=True, site="onlyfans"), database, home
    )
    assert code == 0, said
    assert (out / "111" / "user_data.db").is_file()


def test_a_wrong_password_is_one_sentence_without_it(database):
    parts = urlsplit(database)
    wrong = urlunsplit(parts._replace(netloc=f"{parts.username}:not-it-zz9@{parts.hostname}:{parts.port}"))
    with pytest.raises(RuntimeError) as caught:
        postgres_setup.test_connection(wrong)
    assert "not-it-zz9" not in str(caught.value)
    assert "refused" in str(caught.value)
