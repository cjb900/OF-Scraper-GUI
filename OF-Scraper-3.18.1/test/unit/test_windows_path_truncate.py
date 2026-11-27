"""Windows path shortening with long paths turned on.

Upstream's _windows_truncateHelper (3.18.1) keeps a whole path within
MAX_PATH (WINDOWS_MAX_PATH_BYTES, 518 bytes = 259 UTF-16 units) and is tested
by test/test_path_truncation.py. The GUI patch adds one case: when Windows
long paths are on (LongPathsEnabled and the program's manifest, checked with
RtlAreLongPathsEnabled), only each name is limited (NTFS: 255 units), so a
deep folder no longer cuts the file name short.
"""
import sys

sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import ntpath  # noqa: E402

import pytest  # noqa: E402

import ofscraper.utils.paths.paths as paths_mod  # noqa: E402

pytestmark = pytest.mark.unit

DIR = "C:\\Users\\abcde\\Data\\ofscraper\\katie_darling\\Free\\Posts\\2865052866"


@pytest.fixture
def long_paths(monkeypatch):
    def set_(value):
        monkeypatch.setattr(paths_mod, "windows_long_paths_enabled", lambda: value)

    set_(False)
    return set_


def _units(text):
    return paths_mod.windows_path_length(text)


def _name(path):
    return ntpath.basename(str(path))


def test_counts_like_windows():
    assert _units("abc") == 3
    # outside the Basic Multilingual Plane: two UTF-16 units
    assert _units("💕") == 2
    assert _units("’") == 1


def test_without_long_paths_the_whole_path_fits_max_path(long_paths):
    name = "a" * 300 + ".jpeg"
    out = paths_mod._windows_truncateHelper(ntpath.join(DIR, name))
    assert _units(str(out)) <= 259
    assert _name(out).endswith(".jpeg")


def test_long_paths_keep_a_long_path_whose_names_fit(long_paths):
    long_paths(True)
    deep = ntpath.join(DIR, *(["folder" * 5] * 8))
    path = ntpath.join(deep, "b" * 200 + ".jpeg")
    assert _units(path) > 259
    out = paths_mod._windows_truncateHelper(path)
    assert str(out) == ntpath.normpath(path)


def test_long_paths_still_limit_the_name(long_paths):
    long_paths(True)
    path = ntpath.join(DIR, "c" * 400 + "_1.jpeg")
    out = paths_mod._windows_truncateHelper(path)
    assert _units(_name(out)) == 255
    # the "_1.jpeg" a collision added stays
    assert _name(out).endswith("_1.jpeg")
    assert ntpath.dirname(str(out)) == DIR


def test_long_paths_count_utf16_units(long_paths):
    long_paths(True)
    path = ntpath.join(DIR, "💕" * 200 + ".jpg")
    out = _name(paths_mod._windows_truncateHelper(path))
    assert _units(out) <= 255
    assert out.endswith(".jpg")
    # a heart is never cut in half
    assert out[:-4] == "💕" * ((255 - 4) // 2)
