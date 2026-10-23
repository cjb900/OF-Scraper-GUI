import re

from pytest_check import check

import ofscraper.utils.args.accessors.read as args_
from ofscraper.classes.of.media import Media
from ofscraper.classes.of.posts import Post
from ofscraper.utils.of_env.values.test.test_constants import *
import ofscraper.utils.of_env.of_env as of_env


def test_postcreate_highlights():
    username = "test"
    model_id = TEST_ID
    try:
        Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    except Exception as E:
        raise Exception(f"Exception: {E}\nPost Creation Failed")


def test_media_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE["stories"][0], model_id, username, "highlights")
    assert (len(t.post_media)) == 1


def test_post_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.post) == t._post


def test_modelid_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.model_id) == model_id


def test_username_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.username) == username


def test_text_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE["stories"][0], model_id, username, "highlights")
    assert (t.text) == (HIGHLIGHT_EXAMPLE["stories"][0].get("text"))


def test_title_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.title) == HIGHLIGHT_EXAMPLE.get("title")


def test_id_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.id) == HIGHLIGHT_EXAMPLE.get("id")


def test_date_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.date) == HIGHLIGHT_EXAMPLE.get("createdAt") or HIGHLIGHT_EXAMPLE.get(
        "postedAt"
    )


def test_value_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.value) == "free"


def test_price_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.price) == 0


def test_fromuser_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.fromuser) == model_id


def test_preview_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    assert (t.preview) == HIGHLIGHT_EXAMPLE.get("preview")


def test_mediacanview_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    for ele in t.media:
        assert (ele.canview) is True


def test_mediaclass_highlights():
    username = "test"
    model_id = TEST_ID
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    for ele in t.media:
        assert (isinstance(ele, Media)) is True


# Media Test


def test_mediapost_highlights():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    mediaDict = {"url": HIGHLIGHT_EXAMPLE["cover"]}
    media = Media(mediaDict, index, t)
    assert (media.post) == t


def test_medialen_highlights():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(HIGHLIGHT_EXAMPLE["stories"][0], model_id, username, "highlights")
    mediaDict = {"url": HIGHLIGHT_EXAMPLE["cover"]}
    media = Media(mediaDict, index, t)
    assert (len(media.post.post_media)) == 1


def test_mediacount_highlights():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    mediaDict = {"url": HIGHLIGHT_EXAMPLE["cover"]}
    media = Media(mediaDict, index, t)
    assert (media.count) == index + 1


def test_mediapreview_highlights():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    mediaDict = {"url": HIGHLIGHT_EXAMPLE["cover"]}
    media = Media(mediaDict, index, t)
    assert (HIGHLIGHT_EXAMPLE.get("preview")) is None
    assert (media.preview) == 0


def test_mediamedia_highlights():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(HIGHLIGHT_EXAMPLE, model_id, username, "highlights")
    mediaDict = {"url": HIGHLIGHT_EXAMPLE["cover"]}
    media = Media(mediaDict, index, t)
    assert (media.media) == mediaDict
