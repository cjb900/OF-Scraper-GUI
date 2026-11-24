"""After a scrape, rows skipped as already downloaded still show as downloaded."""

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")

import ofscraper.db.operations_.media as media_ops  # noqa: E402
import ofscraper.gui.utils.progress_bridge as bridge  # noqa: E402
from ofscraper.gui.utils import workflow  # noqa: E402


@pytest.fixture
def sent(monkeypatch):
    updates = []
    # the database gives numbers for OnlyFans media ids
    monkeypatch.setattr(media_ops, "get_media_ids_downloaded", lambda **k: {111, 222})
    monkeypatch.setattr(bridge, "queue_cell_updates", lambda batch, force=False: updates.extend(batch))
    return updates


def _cells(updates, key):
    return {col: val for k, col, val in updates if k == key}


def test_already_downloaded_rows_stay_true(sent):
    just_downloaded = [SimpleNamespace(id=222, canview=True)]
    rows = [  # table rows hold text ids
        {"media_id": "111", "post_id": "1", "responsetype": "Paid"},  # skipped: downloaded before
        {"media_id": "333", "post_id": "1", "responsetype": "Paid"},  # never downloaded
    ]
    workflow._emit_download_status(just_downloaded, 7, "model", extra_table_rows=rows)
    assert _cells(sent, "222") == {"downloaded": "True", "download_cart": "[downloaded]"}
    assert _cells(sent, "111") == {"downloaded": "True", "download_cart": "[downloaded]"}
    assert _cells(sent, "333") == {"downloaded": "False"}


def test_text_ids_in_the_queue_match_too(sent):
    workflow._emit_download_status([SimpleNamespace(id="111", canview=True)], 7, "model")
    assert _cells(sent, "111")["downloaded"] == "True"
