import ofscraper.data.api.me as me
import ofscraper.data.api.profile as profile
import ofscraper.utils.me as me
from ofscraper.utils.of_env.values.test.test_constants import *


def test_me():
    assert (me.parse_user(OWNPROFILE_DICT_EXAMPLE)) == ("simpsimp", "u300")


def test_parse_profile():
    profile_ = USERPROFILE_EXAMPLE_DICT

    assert (profile.parse_profile(profile_))[0][0]["url"] == USERPROFILE_EXAMPLE_DICT[
        "avatar"
    ]


def test_parse_profile2():
    profile_ = USERPROFILE_EXAMPLE_DICT
    assert (profile.parse_profile(profile_))[0][0]["responsetype"] == "profile"


def test_parse_profile3():
    profile_ = USERPROFILE_EXAMPLE_DICT
    assert (set(profile.parse_profile(profile_)[0][0].keys())) == set(
        [
            "url",
            "responsetype",
            "mediatype",
            "value",
            "createdAt",
            "text",
            "id",
            "mediaid",
        ]
    )
