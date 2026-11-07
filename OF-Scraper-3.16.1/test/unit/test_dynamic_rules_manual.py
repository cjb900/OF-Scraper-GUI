"""Unit tests for manual dynamic-rules parse/validate helpers."""

import json

import pytest

from ofscraper.utils.dynamic_rules_manual import (
    load_manual_rules_dict,
    normalize_manual_rules_json,
    parse_manual_rules,
    resolve_manual_rules_text,
    validate_manual_rules,
)

_FORMAT_RULES = {
    "static_param": "abc",
    "format": "1:{}:{:x}:2",
    "checksum_indexes": [0, 1, 2],
    "checksum_constant": 5,
}

_PREFIX_RULES = {
    "static_param": "abc",
    "prefix": "63708",
    "suffix": "6a7f22a1",
    "checksum_indexes": [0, 1, 2],
    "checksum_constant": 5,
    "app_token": "token",
}


@pytest.mark.unit
def test_resolve_prefers_env_over_config():
    assert (
        resolve_manual_rules_text('{"a":1}', '{"b":2}')
        == '{"a":1}'
    )
    assert resolve_manual_rules_text(None, "  cfg  ") == "cfg"
    assert resolve_manual_rules_text("", "cfg") == "cfg"
    assert resolve_manual_rules_text(None, None) is None
    assert resolve_manual_rules_text(_FORMAT_RULES, None).startswith("{")


@pytest.mark.unit
def test_parse_manual_rules():
    assert parse_manual_rules(None) is None
    assert parse_manual_rules("") is None
    assert parse_manual_rules("not json") is None
    assert parse_manual_rules("[1,2]") is None
    assert parse_manual_rules(_FORMAT_RULES) == _FORMAT_RULES
    assert parse_manual_rules(json.dumps(_FORMAT_RULES)) == _FORMAT_RULES


@pytest.mark.unit
def test_validate_manual_rules():
    assert validate_manual_rules(_FORMAT_RULES) is None
    assert validate_manual_rules(_PREFIX_RULES) is None
    assert validate_manual_rules({}) is not None
    assert validate_manual_rules({"static_param": "x"}) is not None
    bad = dict(_FORMAT_RULES)
    del bad["format"]
    assert validate_manual_rules(bad) is not None
    assert validate_manual_rules("nope") is not None


@pytest.mark.unit
def test_load_manual_rules_dict_and_normalize():
    text = json.dumps(_FORMAT_RULES)
    assert load_manual_rules_dict(text, None) == _FORMAT_RULES
    assert load_manual_rules_dict(None, text) == _FORMAT_RULES
    assert load_manual_rules_dict('{"a":1}', text) is None  # env wins but invalid
    pretty = normalize_manual_rules_json(text)
    assert '"static_param"' in pretty
    assert load_manual_rules_dict(pretty, None) == _FORMAT_RULES
