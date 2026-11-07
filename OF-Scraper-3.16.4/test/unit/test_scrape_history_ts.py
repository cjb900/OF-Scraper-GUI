"""Scrape history timestamps should display in the system local timezone."""
from datetime import datetime, timedelta, timezone

from ofscraper.gui.utils.scrape_history import format_short_ts


def test_format_short_ts_converts_utc_to_local():
    utc = datetime(2026, 8, 20, 2, 24, 0, tzinfo=timezone.utc)
    shown = format_short_ts(utc.isoformat())
    local = utc.astimezone()
    assert shown == local.strftime("%Y-%m-%d %H:%M")
    # Sanity: UTC evening-next-day style should not stay as UTC clock text.
    if local.utcoffset() == timedelta(hours=-4):
        assert shown == "2026-08-19 22:24"


def test_format_short_ts_local_offset_keeps_wall_clock():
    local = datetime.now().astimezone().replace(microsecond=0)
    shown = format_short_ts(local.isoformat())
    assert shown == local.strftime("%Y-%m-%d %H:%M")
