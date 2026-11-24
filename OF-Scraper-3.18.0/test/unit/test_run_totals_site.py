"""The run totals name the site the run was for.

OnlyFans and Fansly runs can share a log folder and a Discord channel, so
"GLOBAL RUN TOTALS (ALL MODELS)" now ends with the site, both in the
command-line summary (managers/stats.py) and in the GUI's (table_page.py).
"""

import logging

import pytest

import ofscraper.managers.stats as stats
import ofscraper.sites as sites


@pytest.mark.parametrize("site, label", [("onlyfans", "OnlyFans"), ("fansly", "Fansly")])
def test_title_names_the_site(monkeypatch, site, label):
    monkeypatch.setattr(sites, "current_site", lambda: site)
    assert stats.totals_title() == f"📊 GLOBAL RUN TOTALS (ALL MODELS) · {label}"


def test_unknown_site_reads_as_onlyfans(monkeypatch):
    def broken():
        raise RuntimeError("no settings yet")

    monkeypatch.setattr(sites, "current_site", broken)
    assert stats.totals_title().endswith("· OnlyFans")


def test_global_summary_uses_the_title(monkeypatch, caplog):
    monkeypatch.setattr(sites, "current_site", lambda: "fansly")
    manager = stats.StatsManager()
    manager._stats = {"someone": {}}
    with caplog.at_level(logging.WARNING, logger="shared"):
        manager.print_global_summary()
    assert "GLOBAL RUN TOTALS (ALL MODELS) · Fansly" in caplog.text


def test_gui_summary_uses_the_shared_title():
    import pathlib

    source = pathlib.Path(__file__).parents[2] / "ofscraper/gui/pages/table_page.py"
    text = source.read_text(encoding="utf-8")
    assert "_totals_title()" in text
    assert '"📊 GLOBAL RUN TOTALS (ALL MODELS)"' not in text
