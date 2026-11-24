"""The repo-root patch (what the GUI Docker image installs) must be the same
file as the one in this tree. rebuild_patch_zip.py --sync-root copies it; a
rebuild without --sync-root leaves Docker builds on a stale patch."""

import pathlib

import pytest

HERE = pathlib.Path(__file__).resolve().parents[2]
NAME = "patch_ofscraper_3.18.0_gui.py"


def test_root_copy_matches_this_tree():
    mine = HERE / NAME
    root = HERE.parent / NAME
    if not mine.exists() or not root.exists():
        pytest.skip("both patch copies are only present in the GUI repository")
    assert root.read_bytes() == mine.read_bytes(), (
        f"{root} differs from {mine}: rebuild with --sync-root"
    )
