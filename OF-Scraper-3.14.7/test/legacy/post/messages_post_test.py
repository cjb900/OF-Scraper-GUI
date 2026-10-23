import re

from pytest_check import check

import ofscraper.utils.args.accessors.read as args_
from ofscraper.classes.of.media import Media
from ofscraper.classes.of.posts import Post
from ofscraper.utils.of_env.values.test.test_constants import *
import ofscraper.utils.of_env.of_env as of_env


def test_archived_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.archived) is False


def test_ogresponse_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    assert (t.responsetype) == MESSAGES_DICT.get("responseType")


def test_mediaclass_messages():
    username = "test"
    model_id = TEST_ID
    t = Post(MESSAGES_DICT, model_id, username)
    for ele in t.media:
        assert (isinstance(ele, Media)) is True


# Media Test


def test_mediatype_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (mediaDict["type"]) == "photo"
    assert (media.mediatype) == "images"


def test_medialinked_messages():
    username = "test"
    model_id = TEST_ID
    index = 0
    t = Post(MESSAGES_DICT, model_id, username)
    mediaDict = MESSAGES_DICT["media"][index]
    media = Media(mediaDict, index, t)
    assert (media.linked) is None


def test_messages_text_wordtruncate(mocker):
    length = TEXTLENGTH_ALT2
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": TEXTLENGTH_ALT2,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    with check:
        assert (len(wordarray)) >= length - 1

    with check:
        assert (len(wordarray)) < length + 1


def test_messages_text_wordtruncate2(mocker):
    length = int(TEXTLENGTH_ALT2 / 2)
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    with check:
        assert (len(wordarray)) >= length - 1

    with check:
        assert (len(wordarray)) < length + 1


def test_messages_text_wordtruncate3(mocker):
    length = of_env.getattr("TEXTLENGTH_DEFAULT")
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    textarray = list(
        filter(
            lambda x: len(x) != 0,
            re.split("( )", f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"),
        )
    )
    with check:
        assert (len(wordarray)) >= len(textarray) - 1
    with check:
        assert (len(wordarray)) <= len(textarray) + 2


def test_messages_text_wordtruncate4(mocker):
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": TEXTLENGTH_ALT2,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    with check:
        assert (len(wordarray)) >= TEXTLENGTH_ALT2 - 1

    with check:
        assert (len(wordarray)) < TEXTLENGTH_ALT2 + 1


def test_messages_text_wordtruncate5(mocker):
    length = int(TEXTLENGTH_ALT2 / 2)
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    with check:
        assert (len(wordarray)) >= length - 1

    with check:
        assert (len(wordarray)) < length + 1


def test_messages_text_wordtruncate6(mocker):
    length = of_env.getattr("TEXTLENGTH_DEFAULT")
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }
    args_.getargs([])
    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = list(filter(lambda x: len(x) != 0, re.split("( )", t.file_text)))
    assert (len(wordarray)) >= len(
        "{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )


def test_messages_text_lettertruncate(mocker):
    length = TEXTLENGTH_ALT
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": TEXTLENGTH_ALT,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = t.file_text
    assert (len(wordarray)) == length


def test_messages_text_lettertruncate2(mocker):
    length = int(TEXTLENGTH_ALT2 / 2)
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = t.file_text
    assert (len(wordarray)) == length


def test_messages_text_lettertruncate3(mocker):
    length = of_env.getattr("TEXTLENGTH_DEFAULT")
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = ["", ""]
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 2, post)
    wordarray = t.file_text
    assert (len(wordarray)) == len(
        f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    ) + 2


def test_messages_text_lettertruncate4(mocker):
    length = TEXTLENGTH_ALT2
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = t.file_text
    assert (len(wordarray)) == length


def test_messages_text_lettertruncate5(mocker):
    length = int(TEXTLENGTH_ALT2 / 2)
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = t.file_text
    assert (len(wordarray)) == length


def test_messages_text_lettertruncate6(mocker):
    length = of_env.getattr("TEXTLENGTH_DEFAULT")
    migrationConfig = {
        "main_profile": of_env.getattr("PROFILE_DEFAULT"),
        "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
        "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
        "file_format": FILEFORMAT_TEXT,
        "textlength": length,
        "date": of_env.getattr("DATE_DEFAULT"),
        "metadata": of_env.getattr("METADATA_DEFAULT"),
        "filter": of_env.getattr("FILTER_DEFAULT"),
    }

    mocker.patch(
        "ofscraper.classes.of.posts.config.read_config", return_value=migrationConfig
    )
    post = mocker.PropertyMock()
    post.post_media = []
    mocker.patch.object(
        Media, "text", new=f"{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
    t = Media(None, 0, post)
    wordarray = t.file_text
    assert (len(wordarray)) >= len(
        "{LONG_STRING}{LONG_STRING}{LONG_STRING}{LONG_STRING}"
    )
