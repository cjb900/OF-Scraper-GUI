import pytest

from ofscraper.managers.stats import DownloadStats

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("size, shown", [(1009594, "1.01 MB"), (2_500_000_000, "2.5 GB"), (0, "0 bytes")])
def test_creator_size_uses_the_global_totals_units(size, shown):
    # the per-creator line and GLOBAL RUN TOTALS both use humanfriendly
    # (1 MB = 1000 KB), so the same download shows the same number
    stats = DownloadStats("alice")
    stats.total_bytes = size
    assert f"({shown})" in str(stats).replace("[bold]", "").replace("[/bold]", "")
