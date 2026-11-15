"""Duplicate-download names stay within Windows' name limit, and a cancelled
scrape's summary counts what the creator in progress had downloaded."""

from types import SimpleNamespace

import ofscraper.utils.paths.paths as path_utils
from ofscraper.commands.scraper.actions.download.managers.downloadmanager import (
    find_unique_path,
)
from ofscraper.gui.utils import workflow


def _as_windows(monkeypatch):
    monkeypatch.setattr(path_utils.platform, "system", lambda: "Windows")
    monkeypatch.setattr(path_utils, "windows_long_paths_enabled", lambda: True)


def test_numbered_name_is_shortened_to_fit(tmp_path, monkeypatch):
    _as_windows(monkeypatch)
    taken = tmp_path / ("x" * 250 + ".mp4")  # 254 characters, as truncate leaves it
    taken.write_bytes(b"first")
    found = find_unique_path(taken)
    assert found.name.endswith("(1).mp4")
    assert path_utils.windows_path_length(found.name) <= 255
    assert not found.exists()


def test_emoji_count_twice_on_windows(tmp_path, monkeypatch):
    _as_windows(monkeypatch)
    # each emoji is 2 UTF-16 characters: 120 of them make a 244-character stem
    taken = tmp_path / ("a" + "🎉" * 60 + ".mp4")
    taken.write_bytes(b"first")
    monkeypatch.setattr(path_utils, "WINDOWS_MAX_NAME_CHARS", 126)
    found = find_unique_path(taken)
    assert found.name.endswith("(1).mp4")
    assert path_utils.windows_path_length(found.name) <= 126


def test_short_names_are_unchanged(tmp_path, monkeypatch):
    _as_windows(monkeypatch)
    taken = tmp_path / "clip.mp4"
    taken.write_bytes(b"first")
    (tmp_path / "clip(1).mp4").write_bytes(b"second")
    assert find_unique_path(taken).name == "clip(2).mp4"


def _workflow(**kw):
    return SimpleNamespace(
        _selected_models=[SimpleNamespace(name="model")], **kw
    )


COUNTS = {"videos": 99, "photos": 130, "audios": 2, "forced": 0, "failed": 8, "bytes": 1234}


def test_cancel_counts_the_creator_still_downloading(monkeypatch):
    monkeypatch.setattr(workflow, "_snapshot_download_globals", lambda: dict(COUNTS))
    payload = workflow.build_cancelled_summary_payload(
        _workflow(_per_model_run_stats={}, _active_download_model="model")
    )
    assert payload["run_dl"] == 231
    assert payload["failed"] == 8
    assert payload["per_model"]["model"]["photos"] == 130


def test_cancel_keeps_counts_already_saved(monkeypatch):
    monkeypatch.setattr(workflow, "_snapshot_download_globals", lambda: dict(COUNTS))
    saved = {"model": {"videos": 1, "photos": 0, "audios": 0, "forced": 0, "failed": 0, "bytes": 5}}
    payload = workflow.build_cancelled_summary_payload(
        _workflow(_per_model_run_stats=saved, _active_download_model="model")
    )
    assert payload["run_dl"] == 1


def test_cancel_before_any_download_ignores_old_counters(monkeypatch):
    monkeypatch.setattr(workflow, "_snapshot_download_globals", lambda: dict(COUNTS))
    payload = workflow.build_cancelled_summary_payload(
        _workflow(_per_model_run_stats={}, _active_download_model=None)
    )
    assert payload["run_dl"] == 0
