"""Check mode: media you haven't bought reaches the GUI table as "Locked"
(grey, not clickable), like a normal scrape's rows, not as the TUI's
"Not Unlocked" (which the table didn't block)."""
import pytest

from ofscraper.commands import check

pytestmark = pytest.mark.unit


def _row(cart, downloaded, unlocked, n=1):
    return {"index": n - 1, "number": n, "download_cart": cart,
            "downloaded": downloaded, "unlocked": unlocked}


def test_not_unlocked_becomes_locked():
    out = check._normalize_rows_for_gui([_row("Not Unlocked", False, False)])
    assert out[0]["download_cart"] == "Locked"
    assert out[0]["downloaded"] == "N/A"
    assert out[0]["unlocked"] == "Locked"
    assert out[0]["number"] == "1"


def test_other_rows_unchanged():
    rows = [_row("[downloaded]", True, True, 1), _row("[]", False, True, 2),
            _row("Unknown", False, True, 3)]
    out = check._normalize_rows_for_gui(rows)
    assert [r["download_cart"] for r in out] == ["[downloaded]", "[]", "Unknown"]
    assert [r["downloaded"] for r in out] == [True, False, False]
    assert [r["unlocked"] for r in out] == [True, True, True]


def test_source_rows_keep_tui_label():
    rows = [_row("Not Unlocked", False, False)]
    check._normalize_rows_for_gui(rows)
    assert rows[0]["download_cart"] == "Not Unlocked"
