import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit

import ofscraper.classes.of.posts as posts_
from ofscraper.classes.of.media import Media


def _media(post_data, responsetype=None):
    post = posts_.Post(post_data, 1, "model", responsetype=responsetype)
    media = Media({"id": 111}, 0, post)
    media.mpd = "https://cdn/manifest.mpd"
    return media


@pytest.mark.parametrize(
    "post_data,responsetype,kind",
    [
        ({"id": 5, "responseType": "post"}, None, "post"),
        ({"id": 5, "responseType": "message"}, None, "message"),
        ({"id": 5, "responseType": "post", "isArchived": True}, None, "post"),
        ({"id": 5}, "streams", "post"),
        # purchased tab: the raw responseType decides
        ({"id": 5, "responseType": "post"}, "Paid", "post"),
        ({"id": 5, "responseType": "message"}, "Paid", "message"),
        ({"id": 5}, "Paid", "message"),
        # a message pinned in the chat still uses the message endpoint
        ({"id": 5, "responseType": "message", "isPinned": True}, None, "message"),
        ({"id": 5, "responseType": "message", "isArchived": True}, None, "message"),
        ({"id": 5, "responseType": "message", "streamId": 9}, None, "message"),
        # a pinned timeline post is still a post
        ({"id": 5, "responseType": "post", "isPinned": True}, None, "post"),
    ],
)
def test_license_endpoint(post_data, responsetype, kind):
    url = _media(post_data, responsetype).license
    assert f"/users/media/111/drm/{kind}/5?" in url


@pytest.mark.parametrize(
    "post_data,expected",
    [
        ({"id": 5, "responseType": "message", "isPinned": True}, "Messages"),
        ({"id": 5, "responseType": "message"}, "Messages"),
        ({"id": 5, "responseType": "post", "isPinned": True}, "Pinned"),
        ({"id": 5, "responseType": "post", "isArchived": True}, "Archived"),
        ({"id": 5, "responseType": "post", "streamId": 9}, "Streams"),
        ({"id": 5, "responseType": "post"}, "Timeline"),
    ],
)
def test_pinned_message_stays_a_message(post_data, expected):
    # the type also picks the folder and the database table
    assert posts_.Post(post_data, 1, "model").responsetype == expected


def test_pinned_message_goes_to_the_messages_table():
    post = posts_.Post({"id": 5, "responseType": "message", "isPinned": True}, 1, "m")
    # make_changes_to_content_tables routes by these exact names
    assert post.responsetype.capitalize() == "Messages"
    assert post.responsetype.capitalize() not in {"Timeline", "Pinned", "Archived", "Streams"}
