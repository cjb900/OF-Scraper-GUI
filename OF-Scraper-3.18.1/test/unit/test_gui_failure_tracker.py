"""The post-run "Download failures" summary lists only what is still missing.

A failed download is retried once after its links are refreshed. When the
retry worked, the summary still listed the item (seen in a check-mode test:
2 failures listed, 0 failed in the run's totals, both rows [downloaded]).
"""
from types import SimpleNamespace

import pytest

from ofscraper.gui.utils import failure_tracker as ft

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    ft.clear_failures()
    import ofscraper.gui.utils.progress_bridge as pb

    monkeypatch.setattr(pb, "update_cell_status", lambda *a, **k: None)
    yield
    ft.clear_failures()


def _item(mid, post=1):
    return SimpleNamespace(id=mid, username="melodymarksx", mediatype="videos", file_postid=post)


def test_a_failure_the_retry_fixed_leaves_the_summary():
    ft._on_item_finished(ele=_item(10), username="melodymarksx", result="failed", reason="no network")
    ft._on_item_finished(ele=_item(11), username="melodymarksx", result="failed", reason="no network")
    assert ft.failure_count() == 2
    ft._on_item_finished(ele=_item(10), username="melodymarksx", result="downloaded")
    assert [f["media_id"] for f in ft.get_failures()] == [11]
    assert ft.failure_count_for_user("melodymarksx") == 1


def test_a_deliberate_skip_also_clears_it():
    ft._on_item_finished(ele=_item(10), username="u", result="failed")
    ft._on_item_finished(ele=_item(10), username="u", result="skipped")
    assert ft.get_failures() == []


def test_a_stopped_item_keeps_its_failure():
    ft._on_item_finished(ele=_item(10), username="u", result="failed")
    ft._on_item_finished(ele=_item(10), username="u", result="stopped")
    assert ft.failure_count() == 1


def test_another_creators_success_doesnt_clear_it():
    ft._on_item_finished(ele=_item(10), username="alice", result="failed")
    assert not ft.clear_failure(10, "bob")
    assert ft.failure_count() == 1
