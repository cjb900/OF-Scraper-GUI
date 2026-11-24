"""Unit tests for per-endpoint API URL override helpers."""

import json

import pytest

from ofscraper.utils.api_endpoint_overrides import (
    KNOWN_ENDPOINT_KEYS,
    endpoint_env_is_set,
    normalize_endpoint_overrides_dict,
    normalize_endpoint_overrides_json,
    parse_endpoint_overrides,
    resolve_endpoint_override,
    validate_endpoint_overrides,
)


@pytest.mark.unit
def test_known_keys_include_meep():
    assert "meEP" in KNOWN_ENDPOINT_KEYS
    assert "timelineEP" in KNOWN_ENDPOINT_KEYS
    assert "LICENCE_URL" in KNOWN_ENDPOINT_KEYS


@pytest.mark.unit
def test_parse_and_validate():
    assert parse_endpoint_overrides(None) == {}
    assert parse_endpoint_overrides("") == {}
    assert parse_endpoint_overrides("not json") is None
    assert parse_endpoint_overrides("[1]") is None
    d = parse_endpoint_overrides('{"meEP":"https://onlyfans.com/api2/v2/users/me"}')
    assert d == {"meEP": "https://onlyfans.com/api2/v2/users/me"}
    assert validate_endpoint_overrides(d) is None
    assert validate_endpoint_overrides({"nopeEP": "https://x"}) is not None
    assert validate_endpoint_overrides("[]") is not None


@pytest.mark.unit
def test_normalize_and_resolve(monkeypatch):
    raw = {"meEP": "https://onlyfans.com/api2/v3/users/me"}
    pretty = normalize_endpoint_overrides_json(raw)
    assert json.loads(pretty)["meEP"].endswith("/users/me")
    assert normalize_endpoint_overrides_dict(raw)["meEP"].endswith("/users/me")

    assert (
        resolve_endpoint_override("meEP", env_set=False, config_map=raw)
        == "https://onlyfans.com/api2/v3/users/me"
    )
    assert resolve_endpoint_override("meEP", env_set=True, config_map=raw) is None
    assert resolve_endpoint_override("timelineEP", env_set=False, config_map=raw) is None

    monkeypatch.setenv("OFSC_API_ME_EP", "https://env.example/me")
    assert endpoint_env_is_set("meEP") is True
    monkeypatch.delenv("OFSC_API_ME_EP", raising=False)
    assert endpoint_env_is_set("meEP") is False
