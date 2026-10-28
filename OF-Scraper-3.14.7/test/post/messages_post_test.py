import re

from pytest_check import check

import ofscraper.utils.args.accessors.read as args_
from ofscraper.classes.of.media import Media
from ofscraper.classes.of.posts import Post
from ofscraper.utils.of_env.values.test.test_constants import *
import ofscraper.utils.of_env.of_env as of_env


def test_postcreate_messages():
    username = "test"
    model_id = TEST_ID
    try:
        Post(MESSAGES_DICT, model_id, username)
    except Exception as E:
        raise Exception(f"Exception: {E}\nPost Creation Failed")


def test_media_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (len(t.post_media)) == len(MESSAGES_DICT["media"])


def test_post_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.post) == t._post


def test_modelid_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.model_id) == model_id


def test_username_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.username) == username


def test_text_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.text) == MESSAGES_DICT.get("text")


def test_title_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.title) == MESSAGES_DICT.get("title")


def test_id_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.id) == MESSAGES_DICT.get("id")


def test_date_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.date) == MESSAGES_DICT.get("createdAt") or MESSAGES_DICT.get("postedAt")


def test_value_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.price) > 0
    assert (t.value) == "paid"


def test_price_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.price) == MESSAGES_DICT["price"]


def test_paid_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.paid) is True


def test_fromuser_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.fromuser) == MESSAGES_DICT.get("fromUser") or model_id


def test_preview_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.preview) == MESSAGES_DICT.get("preview")


def test_mediacanview_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    for ele in t.media:
        assert (ele.canview) is True


def test_mediaclass_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    for ele in t.media:
        assert (isinstance(ele, Media)) is True


# Media Test
def test_mediaclass_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    try:
        Media(t.media[index], index, t)
    except Exception as E:
        raise E


def test_mediaurl_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (re.search("http", media.url)) is not None


def test_mediapost_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.post) == t


def test_media_id_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.id) == mediaDict["id"]


def test_medialen_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (len(media.post.post_media)) == len(MESSAGES_DICT["media"])


def test_mediacount_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.count) == index + 1


def test_mediapreview_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (MESSAGES_DICT.get("preview")) is None or []
    assert (media.preview) == 0


def test_mediamedia_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.media) == mediaDict
