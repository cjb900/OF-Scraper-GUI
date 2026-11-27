"""Manage DBs > PostgreSQL: how an import went, from upstream's report.

postgres_import exits 1 whenever a file can't be brought in, also when
--skip-bad-files brought the rest in, and a preview with blocked files ends
"Run again with --apply" although Import would then bring nothing in. The
reports below are the command's own text (a Windows run, 2026-11-25)."""

import pytest

from ofscraper.gui.utils.postgres_setup import import_outcome

HEAD = """Found 19 user_data.db files under C:\\Users\\me\\.data.
Copying each file and checking the copy (the files aren't opened)...
onlyfans: 1 file, 1 creator
  medias         2,476 rows
  posts            672 rows
"""
BLOCKED = """
18 files can't be brought in:
  C:\\Users\\me\\.data\\113370628\\user_data.db
    - PostgreSQL already has rows for creator 113370628
  C:\\Users\\me\\.data\\115415811\\user_data.db
    - PostgreSQL already has rows for creator 115415811
"""
PREVIEW_BLOCKED = HEAD + BLOCKED + """
Nothing was written. Run again with --apply to bring 1 file in. The files listed above stop that: fix them or move them out of the folder, or add --skip-bad-files to leave them out.
"""
APPLY_REFUSED = HEAD + BLOCKED + """
Nothing was written: the files listed above can't be brought in. Fix them or move them out of the folder, or add --skip-bad-files to bring in the rest.
"""
APPLY_SKIPPED = HEAD + BLOCKED + """
Bringing 1 file in...
onlyfans: 3,648 rows added.
Done. The files brought in are unchanged and are no longer used. The 18 files left out are still only in SQLite.
"""
PREVIEW_CLEAN = HEAD + "\nNothing was written. Run again with --apply to bring 3 files in.\n"
APPLY_CLEAN = HEAD + """
Bringing 3 files in...
onlyfans: 9,000 rows added.
Done. The user_data.db files are unchanged and are no longer used.
"""
NOTHING = "Found 2 user_data.db files under x.\n" + BLOCKED.replace("18 files", "2 files") + "\nThere is nothing to bring in.\n"


def test_a_blocked_preview_without_skipping_keeps_import_off():
    said = import_outcome(PREVIEW_BLOCKED, apply=False, skip_bad=False)
    assert not said.ready
    assert "Tick \"Skip files that can't be brought in\"" in said.message
    assert "other 1 file" in said.message
    assert "already in PostgreSQL" in said.message
    assert not said.show_exit_code


def test_a_blocked_preview_with_skipping_allows_import():
    said = import_outcome(PREVIEW_BLOCKED, apply=False, skip_bad=True)
    assert said.ready
    assert said.message.startswith("Preview done: press Import to bring 1 file in.")
    assert "18 files listed above will be left out" in said.message


def test_an_import_that_left_files_out_says_it_finished():
    said = import_outcome(APPLY_SKIPPED, apply=True, skip_bad=True)
    assert said.message.startswith("Import finished: 1 file brought in.")
    assert "18 files listed above were left out" in said.message
    assert not said.show_exit_code and not said.ready


def test_a_refused_import_says_how_to_go_on():
    said = import_outcome(APPLY_REFUSED, apply=True, skip_bad=False)
    assert said.message.startswith("Nothing was brought in")
    assert "preview again" in said.message


def test_clean_preview_and_import():
    assert import_outcome(PREVIEW_CLEAN, apply=False, skip_bad=False).ready
    said = import_outcome(APPLY_CLEAN, apply=True, skip_bad=False)
    assert said.message == "Import finished: 3 files brought in."


def test_nothing_left_to_bring_in():
    said = import_outcome(NOTHING, apply=False, skip_bad=True)
    assert not said.ready
    assert said.message == "Nothing new to bring in. Every creator in this folder is already in PostgreSQL."


@pytest.mark.parametrize("apply", [False, True])
def test_an_error_keeps_the_exit_code(apply):
    said = import_outcome("Nothing was written. Can't reach the server.", apply=apply, skip_bad=False)
    assert said.show_exit_code and not said.ready


def test_other_problems_get_no_already_there_note():
    other = PREVIEW_BLOCKED.replace("PostgreSQL already has rows for creator 115415811", "medias row 3: post_id isn't a number")
    assert "already in PostgreSQL" not in import_outcome(other, apply=False, skip_bad=False).message
