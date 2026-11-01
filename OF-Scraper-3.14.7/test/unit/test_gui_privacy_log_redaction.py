"""Privacy mode: console arg dumps must not show usernames held in lists.

A check-mode run logged "'url': ['realname']" in the Scraper console with
Privacy on.
"""
import pytest

from ofscraper.gui.utils import privacy_mode as pm

pytestmark = pytest.mark.unit


@pytest.fixture
def privacy():
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
