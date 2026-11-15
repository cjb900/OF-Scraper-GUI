"""get_my_info() must read the profile again when its data isn't there.

Stock 3.14.7 recorded the active profile before it called scrape_user(),
and returned the cached data whenever the profile matched, even None:
- after a failed scrape_user() (for example a network error), the next
  call returned None;
- Test Credentials clears only profile_data.currentData, so the next call
  returned None too.
parse_user() then failed on None["name"], and the GUI's auth_errors turns
"'NoneType' object is not subscriptable" into a false "Wrong user".
"""

import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit
from types import SimpleNamespace

import httpx

import ofscraper.data.api.me as me
import ofscraper.utils.me as me_util
import ofscraper.utils.profiles.data as profile_data
import ofscraper.utils.settings as settings

USER = {"isAuth": True, "id": 1, "username": "u1", "name": "n1"}


@pytest.fixture
def profile(monkeypatch):
    monkeypatch.setattr(profile_data, "currentProfile", None)
    monkeypatch.setattr(profile_data, "currentData", None)
    monkeypatch.setattr(profile_data, "get_active_profile", lambda: "main_profile")
    monkeypatch.setattr(settings, "get_settings", lambda: SimpleNamespace(anon=False))
    calls = []

    def scrape_user():
        calls.append(1)
        return dict(USER)

    monkeypatch.setattr(me, "scrape_user", scrape_user)
    return calls


def test_profile_cleared_by_test_credentials_is_read_again(profile):
    me_util.parse_user()
    # what Test Credentials does before it checks new auth (auth_dialog.py)
    profile_data.currentData = None

    assert me_util.parse_user() == ("n1", "u1")
    assert len(profile) == 2


def test_failed_scrape_is_retried_on_the_next_call(profile, monkeypatch):
    def offline():
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(me, "scrape_user", offline)
    with pytest.raises(httpx.ConnectTimeout):
        profile_data.get_my_info()

    monkeypatch.setattr(me, "scrape_user", lambda: dict(USER))
    assert profile_data.get_my_info() == USER


def test_successful_scrape_is_reused(profile):
    profile_data.get_my_info()
    profile_data.get_my_info()
    assert len(profile) == 1
