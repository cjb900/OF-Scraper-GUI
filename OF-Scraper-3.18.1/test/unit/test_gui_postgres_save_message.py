"""Manage DBs > PostgreSQL > Save and use PostgreSQL: the question says what
the server already holds, not that every creator will look new, when it is
a server another computer (or an earlier setup) already filled."""

import pytest

from ofscraper.gui.utils import postgres_setup as pg
from ofscraper.gui.utils.postgres_setup import ServerOverview, save_message


def view(creators=0, other=0, files=0, missing=0, unknown=0, site="onlyfans"):
    return ServerOverview(site, creators, other, files, missing, unknown)


def test_an_empty_server_keeps_the_warning():
    said = save_message(view(files=17, missing=17))
    assert said.startswith("PostgreSQL has no OnlyFans creators yet.")
    assert "every creator will look new" in said


def test_a_server_with_every_creator_needs_nothing_brought_in():
    said = save_message(view(creators=17, other=3, files=17))
    assert said == (
        "PostgreSQL already has 17 OnlyFans creators (and 3 Fansly creators). It has all"
        " the creators of your 17 user_data.db files, so nothing needs bringing in."
    )
    assert "look new" not in said


def test_a_server_missing_some_creators_names_how_many():
    said = save_message(view(creators=17, files=19, missing=2))
    assert "2 of your 19 user_data.db files are for creators it doesn't have yet" in said
    assert "every creator" not in said


def test_one_missing_reads_in_the_singular():
    said = save_message(view(creators=17, files=18, missing=1))
    assert "1 of your 18 user_data.db files is for a creator it doesn't have yet" in said
    assert "that creator looks new" in said


def test_files_that_cant_be_matched_send_you_to_preview():
    said = save_message(view(creators=5, files=6, unknown=1))
    assert "couldn't be matched to a creator by folder name; Preview import checks them" in said


def test_no_files_in_the_folder():
    said = save_message(view(creators=4, site="fansly"))
    assert said.startswith("PostgreSQL already has 4 Fansly creators.")
    assert "No user_data.db files were found" in said


def test_only_the_other_site_has_creators():
    said = save_message(view(other=9, files=2, missing=2, site="fansly"))
    assert said.startswith("PostgreSQL has no Fansly creators yet (and 9 OnlyFans creators).")


def test_when_the_server_couldnt_be_read():
    said = save_message(None, "timeout")
    assert "couldn't be checked (timeout)" in said
    assert "doesn't have yet looks new" in said


def test_local_files_by_creator_folder(tmp_path):
    for name in ("111", "222", "alice"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "user_data.db").write_text("")
    (tmp_path / "333").mkdir()  # no file in it
    assert pg.local_creator_files(tmp_path) == ([111, 222], 1)
    assert pg.local_creator_files(tmp_path / "missing") == ([], 0)


def test_overview_compares_the_server_with_the_files(tmp_path, monkeypatch):
    from ofscraper.gui.utils import postgres_creators

    for name in ("111", "222"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "user_data.db").write_text("")
    held = {"onlyfans": [111, 999], "fansly": [5]}
    monkeypatch.setattr(
        postgres_creators,
        "list_creators",
        lambda url, site: [postgres_creators.Creator(i) for i in held[site]],
    )
    got = pg.server_overview("postgresql://x", "onlyfans", tmp_path)
    assert got == ServerOverview("onlyfans", 2, 1, 2, 1, 0)
