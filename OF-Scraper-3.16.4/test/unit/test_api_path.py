"""Unit tests for OnlyFans API path normalize/rewrite helpers."""

import pytest

from ofscraper.utils.api_path import (
    DEFAULT_API_PATH,
    apply_api_path_prefix,
    normalize_api_path,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, DEFAULT_API_PATH),
        ("", DEFAULT_API_PATH),
        ("   ", DEFAULT_API_PATH),
        ("/api2/v2", "/api2/v2"),
        ("api2/v3", "/api2/v3"),
        ("/api2/v3/", "/api2/v3"),
        ("//api2/v3//", "/api2/v3"),
        ("https://onlyfans.com/api2/v3", DEFAULT_API_PATH),
        ("/", DEFAULT_API_PATH),
    ],
)
def test_normalize_api_path(raw, expected):
    assert normalize_api_path(raw) == expected


@pytest.mark.unit
def test_apply_api_path_prefix_noop_default():
    url = "https://onlyfans.com/api2/v2/users/me"
    assert apply_api_path_prefix(url, "/api2/v2") == url
    assert apply_api_path_prefix(url, None) == url


@pytest.mark.unit
def test_apply_api_path_prefix_rewrites():
    url = "https://onlyfans.com/api2/v2/users/me"
    assert (
        apply_api_path_prefix(url, "/api2/v3")
        == "https://onlyfans.com/api2/v3/users/me"
    )
    assert apply_api_path_prefix("/api2/v2/posts", "api2/v3") == "/api2/v3/posts"


@pytest.mark.unit
def test_apply_api_path_prefix_non_string():
    assert apply_api_path_prefix(None, "/api2/v3") is None
    assert apply_api_path_prefix(42, "/api2/v3") == 42


@pytest.mark.unit
def test_of_env_getattr_rewrites_with_env(monkeypatch):
    import ofscraper.utils.of_env.of_env as of_env

    of_env.clear_api_path_cache()
    monkeypatch.setenv("OFSC_API_PATH", "/api2/v3")
    try:
        # meEP is a known default that contains /api2/v2
        val = of_env.getattr("meEP")
        assert isinstance(val, str)
        assert "/api2/v3" in val
        assert "/api2/v2" not in val
    finally:
        monkeypatch.delenv("OFSC_API_PATH", raising=False)
        of_env.clear_api_path_cache()


@pytest.mark.unit
def test_of_env_getattr_default_unchanged(monkeypatch):
    import ofscraper.utils.of_env.of_env as of_env

    of_env.clear_api_path_cache()
    monkeypatch.delenv("OFSC_API_PATH", raising=False)
    # Force cache miss and empty config path so we stay on default.
    of_env.clear_api_path_cache()
    val = of_env.getattr("meEP")
    assert isinstance(val, str)
    assert "/api2/v2" in val
