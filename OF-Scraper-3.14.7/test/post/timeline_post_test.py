import re

from pytest_check import check

import ofscraper.utils.args.accessors.read as args_
from ofscraper.classes.of.media import Media
from ofscraper.classes.of.posts import Post
from ofscraper.utils.of_env.values.test.test_constants import *
import ofscraper.utils.of_env.of_env as of_env


def test_postcreate_timeline():
    username = "test"
    model_id = TEST_ID
    try:
        Post(TIMELINE_EXAMPLE, model_id, username)
    except Exception as E:
        raise Exception(f"Exception: {E}\nPost Creation Failed")


def test_media_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (len(t.post_media)) == len(TIMELINE_EXAMPLE["media"])


def test_post_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.post) == t._post


def test_modelid_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.model_id) == model_id


def test_username_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.username) == username


def test_text_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.text) == TIMELINE_EXAMPLE.get("text")


def test_title_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.title) == TIMELINE_EXAMPLE.get("title")


def test_id_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.id) == TIMELINE_EXAMPLE.get("id")


def test_date_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.date) == TIMELINE_EXAMPLE.get("createdAt") or TIMELINE_EXAMPLE.get(
        "postedAt"
    )


def test_value_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.value) == "free"


def test_price_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.price) == 0


def test_paid_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.paid) is True


def test_fromuser_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.fromuser) == model_id


def test_preview_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    assert (t.preview) == TIMELINE_EXAMPLE["preview"]


def test_mediacanview_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    for ele in t.media:
        assert (ele.canview) is True


def test_mediaclass_timeline():
    username = "test"
    model_id = TEST_ID
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    for ele in t.media:
        assert (isinstance(ele, Media)) is True


# Media Test
def test_mediaclass_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    try:
        Media(t.media[index], index, t)
    except Exception as E:
        raise E


def test_mediaurl_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (re.search("http", media.url)) is not None


def test_mediapost_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.post) == t


def test_media_id_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.id) == mediaDict["id"]


def test_medialen_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (len(media.post.post_media)) == len(TIMELINE_EXAMPLE["media"])


def test_mediacount_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.count) == index + 1


def test_mediapreview_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (TIMELINE_EXAMPLE["preview"]) == []
    assert (media.preview) == 0


def test_mediamedia_timeline():
    username = "test"
    model_id = TEST_ID
    index = 1
    t = Post(TIMELINE_EXAMPLE, model_id, username)
    mediaDict = TIMELINE_EXAMPLE["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.media) == mediaDict
