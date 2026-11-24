"""Objects and lists in JSON/YAML env files are stored as JSON text."""

import json
import logging
import os

import pytest

import ofscraper.utils.auth.request as auth_request
import ofscraper.utils.config.data as config_data
import ofscraper.utils.of_env.of_env as of_env
from ofscraper.utils.of_env.load import load_env_files

pytestmark = pytest.mark.unit

KEYS = (
    "OFSC_TEST_OBJECT",
    "OFSC_TEST_LIST",
    "OFSC_TEST_STRING",
    "OFSC_TEST_INT",
    "OFSC_TEST_FLOAT",
    "OFSC_TEST_BOOL",
    "OFSC_TEST_NULL",
    "OFSC_TEST_DATE_MAP",
    "OFSC_TEST_DATETIME_LIST",
    "OFSC_TEST_SET_MAP",
    "OFSC_TEST_BINARY_LIST",
    "OFSC_TEST_SELF_LIST",
    "OFSC_TEST_DATE_KEY",
)


@pytest.fixture
def clean_env(tmp_path, monkeypatch):
    # load_env_files also reads a .env from the working directory
    monkeypatch.chdir(tmp_path)
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


JSON_FILE = """{
  "OFSC_TEST_OBJECT": {"static_param": "abc", "checksum_indexes": [1, 2]},
  "OFSC_TEST_LIST": ["a", "b"],
  "OFSC_TEST_STRING": "plain",
  "OFSC_TEST_INT": 5,
  "OFSC_TEST_FLOAT": 1.5,
  "OFSC_TEST_BOOL": true,
  "OFSC_TEST_NULL": null
}
"""

YAML_FILE = """OFSC_TEST_OBJECT:
  static_param: abc
  checksum_indexes: [1, 2]
OFSC_TEST_LIST:
  - a
  - b
OFSC_TEST_STRING: plain
OFSC_TEST_INT: 5
OFSC_TEST_FLOAT: 1.5
OFSC_TEST_BOOL: true
OFSC_TEST_NULL: null
"""


@pytest.mark.parametrize("name,text", [("env.json", JSON_FILE), ("env.yaml", YAML_FILE)])
def test_objects_and_lists_are_stored_as_json(clean_env, name, text):
    path = clean_env / name
    path.write_text(text, encoding="utf-8")

    load_env_files([str(path)])

    assert json.loads(os.environ["OFSC_TEST_OBJECT"]) == {
        "static_param": "abc",
        "checksum_indexes": [1, 2],
    }
    assert json.loads(os.environ["OFSC_TEST_LIST"]) == ["a", "b"]


@pytest.mark.parametrize("name,text", [("env.json", JSON_FILE), ("env.yaml", YAML_FILE)])
def test_other_values_are_stored_as_before(clean_env, name, text):
    path = clean_env / name
    path.write_text(text, encoding="utf-8")

    load_env_files([str(path)])

    assert os.environ["OFSC_TEST_STRING"] == "plain"
    assert os.environ["OFSC_TEST_INT"] == "5"
    assert os.environ["OFSC_TEST_FLOAT"] == "1.5"
    assert os.environ["OFSC_TEST_BOOL"] == "True"
    assert os.environ["OFSC_TEST_NULL"] == "None"


# YAML types that JSON doesn't have, inside an object or list. They loaded
# (as Python text) before objects and lists were stored as JSON, and the
# rest of the file must still load.
def _date_map(text):
    assert json.loads(text) == {"since": "2024-01-02"}


def _datetime_list(text):
    assert json.loads(text) == ["2024-01-02 10:00:00"]


def _set_map(text):
    # a set has no order and no JSON form: it is stored as text in the object
    assert json.loads(text)["s"] in ("{'a', 'b'}", "{'b', 'a'}")


def _binary_list(text):
    assert len(json.loads(text)) == 1


def _self_list(text):
    # json can't write a list that contains itself; it keeps the str() form
    assert text == "[1, [...]]"


@pytest.mark.parametrize(
    "key,yaml_value,check",
    [
        ("OFSC_TEST_DATE_MAP", "{since: 2024-01-02}", _date_map),
        ("OFSC_TEST_DATETIME_LIST", "[2024-01-02 10:00:00]", _datetime_list),
        ("OFSC_TEST_SET_MAP", "{s: !!set {a, b}}", _set_map),
        ("OFSC_TEST_BINARY_LIST", "[!!binary aGVsbG8=]", _binary_list),
        ("OFSC_TEST_SELF_LIST", "&r [1, *r]", _self_list),
    ],
    ids=["nested-date", "datetime-list", "set", "binary", "circular-anchor"],
)
def test_yaml_only_types_inside_objects_still_load(clean_env, key, yaml_value, check):
    path = clean_env / "env.yaml"
    path.write_text(f"{key}: {yaml_value}\nOFSC_TEST_STRING: plain\n", encoding="utf-8")

    load_env_files([str(path)])

    check(os.environ[key])
    assert os.environ["OFSC_TEST_STRING"] == "plain"


@pytest.mark.parametrize(
    "key,yaml_value,stored",
    [
        ("OFSC_TEST_SELF_LIST", "&r [1, *r]", "[1, [...]]"),
        # JSON keys must be text, and default=str doesn't apply to keys
        ("OFSC_TEST_DATE_KEY", "{2024-01-02: a}", "{datetime.date(2024, 1, 2): 'a'}"),
    ],
    ids=["circular-anchor", "date-key"],
)
def test_python_text_fallback_warns_with_the_key(
    clean_env, caplog, key, yaml_value, stored
):
    path = clean_env / "env.yaml"
    path.write_text(f"{key}: {yaml_value}\nOFSC_TEST_STRING: plain\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="shared"):
        load_env_files([str(path)])

    assert os.environ[key] == stored
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith(f"{key}: couldn't store the value as JSON")


# The GUI's manual dynamic rules read OFSC_DYNAMIC_RULE_MANUAL as JSON text,
# and a non-empty env value is used ahead of the config.json rules.
RULES = {
    "static_param": "fake_static_param",
    "format": "1:{}:{:x}:2",
    "checksum_indexes": [1, 2, 3],
    "checksum_constant": 7,
}


@pytest.fixture
def manual_rule_env(clean_env, monkeypatch):
    monkeypatch.delenv("OFSC_DYNAMIC_RULE_MANUAL", raising=False)
    monkeypatch.setattr(config_data, "get_dynamic_rules_manual", lambda *a, **k: None)
    yield clean_env
    # load_env_files writes os.environ directly; drop the value and reload the
    # cached settings so later tests don't see it
    os.environ.pop("OFSC_DYNAMIC_RULE_MANUAL", None)
    of_env.get_all_configs(forced=True)


@pytest.mark.parametrize("name", ["env.json", "env.yaml"])
def test_manual_dynamic_rule_from_an_env_file_is_used(manual_rule_env, name):
    path = manual_rule_env / name
    if name.endswith(".json"):
        path.write_text(json.dumps({"OFSC_DYNAMIC_RULE_MANUAL": RULES}), encoding="utf-8")
    else:
        path.write_text(
            "OFSC_DYNAMIC_RULE_MANUAL:\n"
            "  static_param: fake_static_param\n"
            "  format: '1:{}:{:x}:2'\n"
            "  checksum_indexes: [1, 2, 3]\n"
            "  checksum_constant: 7\n",
            encoding="utf-8",
        )

    # the same two steps settings.setup_settings() runs at start-up
    load_env_files([str(path)])
    of_env.get_all_configs(forced=True)

    assert auth_request.get_request_auth_dynamic_rule_manual() == (
        "fake_static_param",
        "1:{}:{:x}:2",
        [1, 2, 3],
        7,
    )
