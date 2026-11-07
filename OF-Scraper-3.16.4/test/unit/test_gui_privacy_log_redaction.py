"""Privacy mode: console arg dumps must not show usernames held in lists.

A check-mode run logged "'url': ['realname']" in the Scraper console with
Privacy on.
"""
import pytest

from ofscraper.gui.utils import privacy_mode as pm

pytestmark = pytest.mark.unit


@pytest.fixture
def privacy(monkeypatch):
    # patterns other tests registered (a fake account id such as 1) would
    # otherwise rewrite the sample lines here
    import ofscraper.utils.logs.utils.sensitive as sensitive

    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
    before = pm.is_privacy_mode()
    pm.set_privacy_mode(True, persist=False, emit=False)
    yield
    pm.set_privacy_mode(before, persist=False, emit=False)


ARGS_DUMP = (
    "'command': 'post_check', 'url': ['realname'], 'check_usernames': [], "
    "'check_area': ['Timeline', 'Pinned'], 'usernames': ['first_one', 'second.two'], "
    "'excluded_username': [\"skipme\"], 'username': 'solo'"
)


def test_usernames_in_lists_are_hidden(privacy):
    out = pm.redact_log_message(ARGS_DUMP)
    for name in ("realname", "first_one", "second.two", "skipme", "solo"):
        assert name not in out
    assert "'url': ['{hidden}']" in out
    assert "'usernames': ['{hidden}']" in out


def test_other_lists_and_empty_lists_are_kept(privacy):
    out = pm.redact_log_message(ARGS_DUMP)
    assert "'check_area': ['Timeline', 'Pinned']" in out
    assert "'check_usernames': []" in out


def test_nothing_changes_without_privacy():
    before = pm.is_privacy_mode()
    pm.set_privacy_mode(False, persist=False, emit=False)
    try:
        assert pm.redact_log_message(ARGS_DUMP) == ARGS_DUMP
    finally:
        pm.set_privacy_mode(before, persist=False, emit=False)


# -- usernames / model IDs of loaded subscriptions, anywhere in a line -------

from types import SimpleNamespace  # noqa: E402

import ofscraper.managers.manager as manager_mod  # noqa: E402


@pytest.fixture
def loaded_subs(monkeypatch):
    subs = {"realname": SimpleNamespace(id=168143417)}
    profile_subs = {"othercreator": SimpleNamespace(id=55512345)}
    monkeypatch.setattr(
        manager_mod,
        "Manager",
        SimpleNamespace(
            _model_manager=SimpleNamespace(_all_subs_dict=subs),
            _profile_manager=SimpleNamespace(
                model_managers={"main": SimpleNamespace(_all_subs_dict=profile_subs)}
            ),
        ),
    )
    return subs


@pytest.mark.parametrize(
    "line",
    [
        "[DIAG] Calling _load_models_from_db for ['realname'], date_range={}",
        "Checking DB path for realname: C:\\x\\.data\\168143417\\user_data.db",
        "[INFO] Loaded 1 items from DB for RealName",
        "stats: {'realname': {'photos': 783}}",
        "modelid:168143417 placeholders [('model_id', 168143417)]",
        "Processing othercreator (55512345)",
    ],
)
def test_loaded_usernames_and_ids_are_hidden_anywhere(privacy, loaded_subs, line):
    out = pm.redact_log_message(line)
    for secret in ("realname", "RealName", "168143417", "othercreator", "55512345"):
        assert secret not in out


def test_partial_matches_are_left_alone(privacy, loaded_subs):
    line = "realnamexyz and 1681434170 and xrealname"
    assert pm.redact_log_message(line) == line


def test_new_subscriptions_are_picked_up(privacy, loaded_subs):
    assert "{model}" in pm.redact_log_message("for realname")
    loaded_subs["latecomer"] = SimpleNamespace(id=99999999)
    out = pm.redact_log_message("for latecomer 99999999")
    assert "latecomer" not in out and "99999999" not in out


def test_no_manager_is_fine(privacy, monkeypatch):
    monkeypatch.setattr(manager_mod, "Manager", None)
    assert pm.redact_log_message("for someone") == "for someone"
