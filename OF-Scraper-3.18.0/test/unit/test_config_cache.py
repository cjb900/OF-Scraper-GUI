"""open_config() keeps config.json in memory, but reads it again once it changes."""

import json
import os

import pytest

import ofscraper.utils.config.file as config_file


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(config_file.common_paths, "get_config_path", lambda: path)
    monkeypatch.setattr(config_file, "_cached_config", None)
    monkeypatch.setattr(config_file, "_cached_stamp", None)
    return path


def _write(path, data, bump=0):
    path.write_text(json.dumps(data), encoding="utf-8")
    if bump:
        # some filesystems keep coarse modified times; make the change visible
        stat = path.stat()
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + bump))


def test_an_unchanged_file_is_read_once(config_path, monkeypatch):
    _write(config_path, {"discord": "a"})
    reads = []
    real = config_file.config_string
    monkeypatch.setattr(config_file, "config_string", lambda: reads.append(1) or real())
    assert config_file.open_config()["discord"] == "a"
    assert config_file.open_config()["discord"] == "a"
    assert reads == [1]


def test_a_file_edited_outside_the_app_is_read_again(config_path):
    _write(config_path, {"discord": "a"})
    assert config_file.open_config()["discord"] == "a"
    _write(config_path, {"discord": "bb"}, bump=10_000_000)
    assert config_file.open_config()["discord"] == "bb"


def test_another_config_path_is_read(config_path, tmp_path, monkeypatch):
    _write(config_path, {"discord": "a"})
    assert config_file.open_config()["discord"] == "a"
    other = tmp_path / "fansly.json"
    _write(other, {"discord": "f"})
    monkeypatch.setattr(config_file.common_paths, "get_config_path", lambda: other)
    assert config_file.open_config()["discord"] == "f"
