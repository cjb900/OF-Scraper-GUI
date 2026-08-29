"""Unit tests for custom dynamic-rules URL helpers."""

import pytest

from ofscraper.utils.dynamic_rules_url import (
    normalize_dynamic_rules_url,
    resolve_dynamic_rules_url,
    validate_dynamic_rules_url,
)


@pytest.mark.unit
def test_normalize_dynamic_rules_url():
    assert normalize_dynamic_rules_url(None) == ""
    assert normalize_dynamic_rules_url("  https://x.test/r.json  ") == (
        "https://x.test/r.json"
    )


@pytest.mark.unit
def test_validate_dynamic_rules_url():
    assert validate_dynamic_rules_url("") is None
    assert validate_dynamic_rules_url(None) is None
    assert validate_dynamic_rules_url("https://example.com/rules.json") is None
    assert validate_dynamic_rules_url("http://localhost:8080/r.json") is None
    assert validate_dynamic_rules_url("ftp://example.com/r.json") is not None
    assert validate_dynamic_rules_url("not-a-url") is not None
    assert validate_dynamic_rules_url("https://") is not None


@pytest.mark.unit
def test_resolve_prefers_env_over_config():
    assert (
        resolve_dynamic_rules_url(
            "https://env.example/r.json", "https://cfg.example/r.json"
        )
        == "https://env.example/r.json"
    )
    assert (
        resolve_dynamic_rules_url(None, "https://cfg.example/r.json")
        == "https://cfg.example/r.json"
    )
    assert resolve_dynamic_rules_url("", "https://cfg.example/r.json") == (
        "https://cfg.example/r.json"
    )
    assert resolve_dynamic_rules_url("ftp://bad", "https://cfg.example/r.json") == (
        "https://cfg.example/r.json"
    )
    assert resolve_dynamic_rules_url(None, None) is None
