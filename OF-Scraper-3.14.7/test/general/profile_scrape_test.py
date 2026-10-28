import ofscraper.data.api.me as me
import ofscraper.data.api.profile as profile
import ofscraper.utils.me as me
from ofscraper.utils.of_env.values.test.test_constants import *


def test_parse_profile5():
    profile_ = USERPROFILE_EXAMPLE_DICT
    if USERPROFILE_EXAMPLE_DICT.get("profile"):
        assert (set(profile.parse_profile(profile_)[0][1].keys())) == set(
            ["url", "responsetype", "mediatype", "value", "createdAt", "text", "id"]
        )


def test_parse_profile6():
    profile_ = USERPROFILE_EXAMPLE_DICT
    assert (profile.parse_profile(profile_)[1][1]) == USERPROFILE_EXAMPLE_DICT[
        "username"
    ]


def test_parse_profile7():
    profile_ = USERPROFILE_EXAMPLE_DICT
    assert (profile.parse_profile(profile_)[1][2]) == USERPROFILE_EXAMPLE_DICT["id"]
