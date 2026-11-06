"""OFSC_BATCH_TEMPFILE_CLEANUP accepts "true" like the other flags."""

import pytest

from ofscraper.utils.of_env.values.path.general import load_general_paths_config

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("false", False),
        ("0", False),
        ("", False),
    ],
)
def test_batch_tempfile_cleanup_flag(monkeypatch, value, expected):
    monkeypatch.setenv("OFSC_BATCH_TEMPFILE_CLEANUP", value)
    assert load_general_paths_config()["BATCH_TEMPFILE_CLEANUP"] is expected


def test_batch_tempfile_cleanup_defaults_to_off(monkeypatch):
    monkeypatch.delenv("OFSC_BATCH_TEMPFILE_CLEANUP", raising=False)
    assert load_general_paths_config()["BATCH_TEMPFILE_CLEANUP"] is False
