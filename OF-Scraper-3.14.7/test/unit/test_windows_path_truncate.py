import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pathlib

import pytest

import ofscraper.utils.paths.paths as paths_mod

pytestmark = pytest.mark.unit

# 30 characters, like C:\Users\abcde\Data\ofscraper
SAVE = "/C/Users/abcde/Data/ofscraper"
DIR = f"{SAVE}/katie_darling/Free/Posts/2865052866"


@pytest.fixture
def long_paths(monkeypatch):
    def set_(value):
        monkeypatch.setattr(paths_mod, "windows_long_paths_enabled", lambda: value)

    set_(False)
    return set_


def _len(p):
    return paths_mod.windows_path_length(p)


def test_counts_like_windows():
    assert _len("abc") == 3
    # outside the Basic Multilingual Plane: two UTF-16 units
    assert _len("💕") == 2
    assert _len("’") == 1


def test_short_path_unchanged(long_paths):
    p = pathlib.Path(DIR, "11-03-2026-short.jpeg")
    assert paths_mod._windows_truncateHelper(p) == p


@pytest.mark.parametrize("extra", [0, 1, 3, 6, 10, 60])
def test_path_ends_within_259_characters(long_paths, extra):
    # the reported failures were 260-265 characters long
    stem = "11-03-2026-2048x2048_651e3d9e91e6ad33470c48ac38b63c23-" + "Hey everyone! " * 20
    stem = stem[: 259 - len(DIR) - 1 - len(".jpeg") + extra]
    p = pathlib.Path(DIR, stem + ".jpeg")
    out = paths_mod._windows_truncateHelper(p)
    assert _len(out) <= 259
    assert out.parent == p.parent
    assert out.name.endswith(".jpeg")
    if extra == 0:
        assert out == p


def test_emoji_count_double(long_paths):
    stem = "11-03-2026-a-" + "💕" * 200
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, stem + ".jpeg"))
    assert _len(out) <= 259
    assert _len(out) >= 257  # used the room it had


def test_collision_suffix_kept(long_paths):
    stem = "a" * 300
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, stem + "_4785179205.jpeg"))
    assert out.name.endswith("_4785179205.jpeg")
    assert _len(out) <= 259


def test_extension_text_inside_name_is_kept(long_paths):
    # the old code removed every ".jpeg"-like match, not only the last one
    stem = "see.jpeg and more " + "x" * 300
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, stem + ".jpeg"))
    assert out.name.startswith("see.jpeg and more ")


def test_no_extension_drops_trailing_space_and_dot(long_paths):
    stem = "a" * (259 - len(DIR) - 1 - 2) + " ." + "b" * 50
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, stem))
    assert not out.name.endswith((" ", "."))


def test_env_value_can_lower_the_limit(long_paths, monkeypatch):
    real = paths_mod.of_env.getattr
    monkeypatch.setattr(
        paths_mod.of_env,
        "getattr",
        lambda key: 500 if key == "WINDOWS_MAX_PATH_BYTES" else real(key),
    )
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, "a" * 300 + ".jpeg"))
    assert _len(out) <= 250


def test_env_value_cannot_raise_the_limit(long_paths, monkeypatch):
    real = paths_mod.of_env.getattr
    monkeypatch.setattr(
        paths_mod.of_env,
        "getattr",
        lambda key: 2000 if key == "WINDOWS_MAX_PATH_BYTES" else real(key),
    )
    out = paths_mod._windows_truncateHelper(pathlib.Path(DIR, "a" * 300 + ".jpeg"))
    assert _len(out) <= 259


def test_long_paths_only_limit_the_name(long_paths):
    long_paths(True)
    deep = pathlib.Path(DIR, *["folder" * 5] * 10)
    p = pathlib.Path(deep, "a" * 100 + ".jpeg")
    assert paths_mod._windows_truncateHelper(p) == p
    out = paths_mod._windows_truncateHelper(pathlib.Path(deep, "a" * 300 + ".jpeg"))
    assert _len(out.name) == 255
    assert out.parent == deep


def test_folder_too_long_returns_path_and_warns(long_paths, caplog):
    deep = pathlib.Path("/C", "f" * 270)
    p = pathlib.Path(deep, "name.jpeg")
    assert paths_mod._windows_truncateHelper(p) == p


def test_long_path_check_is_false_off_windows():
    paths_mod._long_paths_enabled = None
    try:
        assert paths_mod.windows_long_paths_enabled() is False
    finally:
        paths_mod._long_paths_enabled = None
