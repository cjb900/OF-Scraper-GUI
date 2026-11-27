"""A Fansly creator's avatar is shown as a display-size copy.

The model's avatar was the original upload, which can be a full-size photo:
Discord's desktop and web clients showed an empty box for it in the run's
Discord message (the phone app showed it). Downloads keep the original.
"""
import pytest

from ofscraper.sites.fansly import normalize

pytestmark = pytest.mark.unit

LOC = normalize.DIRECT_LOCATION


def _pic(url, w, h, mimetype="image/jpeg", variants=()):
    return {
        "id": 1, "mimetype": mimetype, "width": w, "height": h,
        "locations": [{"locationId": LOC, "location": url}],
        "variants": list(variants),
    }


def test_a_big_avatar_shows_its_largest_small_enough_copy():
    avatar = _pic("orig", 4000, 6000, variants=[
        _pic("v1080", 1080, 1620), _pic("v720", 683, 1024), _pic("v360", 240, 360),
    ])
    assert normalize.preview_url(avatar) == "v720"


def test_a_small_avatar_is_used_as_it_is():
    assert normalize.preview_url(_pic("orig", 800, 800, variants=[_pic("v", 400, 400)])) == "orig"


def test_no_usable_copy_falls_back_to_the_original():
    avatar = _pic("orig", 4000, 6000, variants=[
        _pic("big", 2000, 3000), _pic("clip", 480, 720, mimetype="video/mp4"),
    ])
    assert normalize.preview_url(avatar) == "orig"
    assert normalize.preview_url(_pic("orig", 0, 0)) == "orig"


def test_the_model_shows_the_copy_and_downloads_keep_the_original():
    avatar = _pic("orig", 4000, 6000, variants=[_pic("v720", 683, 1024)])
    account = {"id": "7", "username": "maplemistyx", "avatar": avatar, "createdAt": 1700000000}
    assert normalize.model(account)["avatar"] == "v720"
    items = normalize.profile_items(account)
    if items:  # downloads read the raw picture
        assert items[0]["media"][0]["files"]["full"]["url"] == "orig"
