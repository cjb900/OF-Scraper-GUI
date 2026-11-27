"""A cancelled scrape's summary counts what the creator in progress had
downloaded."""

from types import SimpleNamespace

from ofscraper.gui.utils import workflow


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
