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


def test_filename_with_regex_characters_is_hidden():
    # a profile header uploaded as "Untitled design (7).png": Media.filename
    # strips the trailing ")", leaving an unbalanced "(" at position 16
    url = "https://public.onlyfans.com/files/a/ab/abc/123/Untitled design (7).png"
    logged = log_utils.get_url_log(_media(url, "Untitled design (7"))
    assert "Untitled design (7" not in logged and "{hidden}" in logged


def test_ordinary_filename_is_hidden():
    url = "https://cdn2.onlyfans.com/files/a/ab/abc/1000x1800_cb46.jpeg"
    logged = log_utils.get_url_log(_media(url, "1000x1800_cb46"))
    assert "1000x1800_cb46" not in logged


def test_no_part_of_the_filename_is_left_behind():
    # the filename is hidden before the generic "/word" rule runs, so that
    # rule can't replace "Untitled" first and leave " design (7)" showing
    url = "https://public.onlyfans.com/files/a/ab/abc/123/Untitled design (7).png"
    logged = log_utils.get_url_log(_media(url, "Untitled design (7"))
    assert "design" not in logged


def test_empty_filename_leaves_url_readable():
    # str.replace("") would put "{hidden}" between every character
    url = "https://cdn2.onlyfans.com/files/a/ab/abc/().jpg"
    logged = log_utils.get_url_log(_media(url, ""))
    assert logged.count("{hidden}") <= 2


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
