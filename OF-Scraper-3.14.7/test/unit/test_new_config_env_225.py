"""A new config.json, and settings filled into an older one, get the built-in
defaults, not OFSC_* environment overrides; those still apply at runtime."""

import json
import os

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.config.data as data  # noqa: E402
import ofscraper.utils.config.file as config_file  # noqa: E402
import ofscraper.utils.of_env.of_env as of_env  # noqa: E402
import ofscraper.utils.paths.common as common_paths  # noqa: E402
from ofscraper.utils.of_env import get_all_configs  # noqa: E402


@pytest.fixture
def env_overrides(monkeypatch, tmp_path):
    # a temp config.json; OFSC_* is read when the defaults load
    path = tmp_path / "config.json"
    monkeypatch.setattr(common_paths, "get_config_path", lambda: path)
    monkeypatch.setenv("OFSC_MAX_LENGTH_DEFAULT", "4242")
    monkeypatch.setenv("OFSC_DATE_DEFAULT", "YYYY")
    get_all_configs(forced=True)
    yield path
    monkeypatch.undo()
    get_all_configs(forced=True)


def test_new_config_holds_builtin_defaults(env_overrides):
    config_file.make_config()
    written = json.loads(env_overrides.read_text())
    assert written["content_filter_options"]["length_max"] == 0
    assert written["file_options"]["date"] == "MM-DD-YYYY"


def test_auto_update_fills_missing_keys_with_builtin_defaults(env_overrides):
    # an older config.json without these keys gets them filled in on update
    config_file.make_config()
    old = json.loads(env_overrides.read_text())
    del old["content_filter_options"]["length_max"]
    del old["file_options"]["date"]
    config_file.auto_update_config(old)
    written = json.loads(env_overrides.read_text())
    assert written["content_filter_options"]["length_max"] == 0
    assert written["file_options"]["date"] == "MM-DD-YYYY"
    assert of_env.getattr("MAX_LENGTH_DEFAULT") == 4242


def test_environment_still_applies_after_new_config(env_overrides):
    config_file.make_config()
    assert os.environ["OFSC_MAX_LENGTH_DEFAULT"] == "4242"
    assert os.environ["OFSC_DATE_DEFAULT"] == "YYYY"
    assert of_env.getattr("MAX_LENGTH_DEFAULT") == 4242
    # a config without the key still falls back to the environment
    assert data.get_max_length(config={"content_filter_options": {}}) == 4242
    assert data.get_date(config={"file_options": {}}) == "YYYY"
