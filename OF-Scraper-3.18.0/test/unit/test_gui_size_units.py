"""The GUI shows sizes in the units ofscraper's own summary uses
(humanfriendly: 1 GB = 1000**3 bytes), so the two totals in the log match."""

import pytest
from humanfriendly import format_size

from ofscraper.gui.utils import scrape_history, workflow
from ofscraper.gui.widgets import progress_panel


@pytest.mark.parametrize("n", [0, 512, 1_536, 123_456_789, 4_580_000_000])
def test_gui_formatters_match_ofscraper(n):
    expected = format_size(n)
    assert workflow._format_bytes_short(n) == expected
    assert scrape_history.format_bytes(n) == expected
    assert progress_panel._format_bytes(n) == expected


def test_the_logged_run_total_reads_the_same():
    # the 2026-11-23 run: ofscraper said 4.58 GB, the GUI 4.26 GB
    assert workflow._format_bytes_short(4_580_000_000) == "4.58 GB"


def test_none_and_negative_are_zero():
    assert workflow._format_bytes_short(None) == "0 bytes"
    assert progress_panel._format_bytes(-5) == "0 bytes"
