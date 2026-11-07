# GUI tree tests from the 3.14.7 tree's test/unit/test_url_log.py that the fork's test/test_url_log.py does not have
import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
from types import SimpleNamespace

import ofscraper.commands.scraper.actions.utils.log as log_utils


def _media(url, filename):
    return SimpleNamespace(url=url, mpd=None, filename=filename)


def test_download_logs_never_print_the_raw_url():
    # every logged media link goes through get_url_log, which hides the path
    import pathlib
    import re

    managers = pathlib.Path(log_utils.__file__).parents[1] / "download" / "managers"
    raw = re.compile(r"\{(ele|media|c)\.(url|mpd)\}")
    hits = [
        f"{path.name}:{n}"
        for path in managers.glob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if raw.search(line)
    ]
    assert hits == []
