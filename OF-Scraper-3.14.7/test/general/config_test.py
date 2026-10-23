import json
import tempfile

from pytest_check import check

import ofscraper.utils.config.config as config_
import ofscraper.utils.paths.paths as paths_
from ofscraper.utils.config.config import *
from ofscraper.utils.config.data import *
from ofscraper.utils.of_env.values.test.test_constants import *
from ofscraper.utils.profiles.data import *
import ofscraper.utils.of_env.of_env as of_env
from ofscraper.utils.paths.common import get_save_location
import ofscraper.utils.args.accessors.read as args_

# def test_current_schema(mocker):
#     migrationConfig={"config":{
#         "main_profile": of_env.getattr("PROFILE_DEFAULT"),
#         "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
#         "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
#         "dir_format": of_env.getattr("DIR_FORMAT_DEFAULT"),
#         "file_format": FILEFORMAT_POSTID,
#         "textlength": of_env.getattr("TEXTLENGTH_DEFAULT"),
#         "date": of_env.getattr("DATE_DEFAULT"),
#         "metadata": of_env.getattr("METADATA_DEFAULT"),
#         "filter": of_env.getattr("FILTER_DEFAULT"),
#         "mp4decrypt":MP4DECRYPT_DEFAULT
#     }}

#     currentConfig=get_current_data.schema(migrationConfig)

#     assert(sorted(set(currentConfig["config"].keys())))==sorted(set(data.KEYS))


# def test_current_schema2(mocker):
#     migrationConfig={"config":{
#         "main_profile": of_env.getattr("PROFILE_DEFAULT"),
#         "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
#         "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
#     }}
#     currentConfig=get_current_data.schema(migrationConfig)

#     assert(sorted(set(currentConfig["config"].keys())))==sorted(set(data.KEYS))


def test_savelocation(mocker):
    assert (get_save_location(config=None)) == of_env.getattr("SAVE_PATH_DEFAULT")


def test_savelocation2(mocker):
    config = {"save_location": SAVE_LOCATION_ALT}
    assert (get_save_location(config=config)) == SAVE_LOCATION_ALT


def test_savelocation3(mocker):
    config = {}
    assert (get_save_location(config=config)) == of_env.getattr("SAVE_PATH_DEFAULT")


def test_mainprofile(mocker):
    assert (get_main_profile(config=None)) == of_env.getattr("PROFILE_DEFAULT")


def test_mainprofile2(mocker):
    config = {"main_profile": PROFILE_ALT}
    assert (get_main_profile(config=config)) == PROFILE_ALT


def test_mainprofile3(mocker):
    config = {}
    assert (get_main_profile(config=config)) == of_env.getattr("PROFILE_DEFAULT")


def test_dirformat(mocker):
    assert (get_dirformat(config=None)) == of_env.getattr("DIR_FORMAT_DEFAULT")


def test_dirformat2(mocker):
    config = {"dir_format": DIR_FORMAT_ALLVALID}
    assert (get_dirformat(config=config)) == DIR_FORMAT_ALLVALID


def test_dirformat3(mocker):
    config = {}
    assert (get_dirformat(config=config)) == of_env.getattr("DIR_FORMAT_DEFAULT")


def test_fileformat(mocker):
    assert (get_fileformat(config=None)) == of_env.getattr("FILE_FORMAT_DEFAULT")


def test_fileformat2(mocker):
    config = {"file_format": FILEFORMAT_VALID_ALL}
    assert (get_fileformat(config=config)) == FILEFORMAT_VALID_ALL


def test_fileformat3(mocker):
    config = {}
    assert (get_fileformat(config=config)) == of_env.getattr("FILE_FORMAT_DEFAULT")


def test_textlength(mocker):
    assert (get_textlength(config=None)) == of_env.getattr("TEXTLENGTH_DEFAULT")


def test_textlength2(mocker):
    config = {"textlength": TEXTLENGTH_ALT}
    assert (get_textlength(config=config)) == TEXTLENGTH_ALT


def test_textlength3(mocker):
    config = {}
    assert (get_textlength(config=config)) == of_env.getattr("TEXTLENGTH_DEFAULT")


def test_date(mocker):
    assert (get_date(config=None)) == of_env.getattr("DATE_DEFAULT")


def test_date2(mocker):
    config = {"date": DATE_ALT}
    assert (get_date(config=config)) == DATE_ALT


def test_date3(mocker):
    config = {}
    assert (get_date(config=config)) == of_env.getattr("DATE_DEFAULT")


def test_metadata(mocker):
    assert (get_metadata(config=None)) == of_env.getattr("METADATA_DEFAULT")


def test_metadata2(mocker):
    config = {"metadata": METADATA_ALLVALID}
    assert (get_metadata(config=config)) == METADATA_ALLVALID


def test_metadata3(mocker):
    config = {}
    assert (get_metadata(config=config)) == of_env.getattr("METADATA_DEFAULT")


def test_ffmpeg(mocker):
    assert (get_ffmpeg(config=None)) == of_env.getattr("FFMPEG_DEFAULT")


def test_ffmpeg2(mocker):
    config = {"ffmpeg": ALT_FFMPEG}
    assert (get_ffmpeg(config=config)) == ALT_FFMPEG


def test_ffmpeg3(mocker):
    config = {}
    assert (get_ffmpeg(config=config)) == of_env.getattr("FFMPEG_DEFAULT")


def test_filter(mocker):
    assert (get_filter(config=None)) == of_env.getattr("FILTER_DEFAULT")


def test_filter3(mocker):
    config = {}
    assert (get_filter(config=config)) == of_env.getattr("FILTER_DEFAULT")


def test_timelineresponse(mocker):
    assert (get_timeline_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_timelineresponse2(mocker):
    config = {"responsetype": {"timeline": of_env.getattr("RESPONSE_TYPE_DEFAULT")["archived"]}}
    assert (get_timeline_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["archived"]


def test_timelineresponse3(mocker):
    config = {}
    assert (get_timeline_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_archived_response(mocker):
    assert (get_archived_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["archived"]


def test_archived2(mocker):
    config = {"responsetype": {"archived": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_archived_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_archivedresponse3(mocker):
    config = {}
    assert (get_archived_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["archived"]


def test_stories_response(mocker):
    assert (get_stories_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["stories"]


def test_stories2(mocker):
    config = {"responsetype": {"stories": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_stories_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_storiesresponse3(mocker):
    config = {}
    assert (get_stories_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["stories"]


def test_highlights_response(mocker):
    assert (get_highlights_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["highlights"]


def test_highlights2(mocker):
    config = {"responsetype": {"highlights": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_highlights_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_highlightsresponse3(mocker):
    config = {}
    assert (get_highlights_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["highlights"]


def test_paid_response(mocker):
    assert (get_paid_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["paid"]


def test_paid2(mocker):
    config = {"responsetype": {"paid": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_paid_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_paidresponse3(mocker):
    config = {}
    assert (get_paid_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["paid"]


def test_messages_response(mocker):
    assert (get_messages_progress_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")[
        "message"
    ]


def test_messages2(mocker):
    config = {"responsetype": {"message": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_messages_progress_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")[
        "timeline"
    ]


def test_messagesresponse3(mocker):
    config = {}
    assert (get_messages_progress_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")[
        "message"
    ]


def test_profiles_response(mocker):
    assert (get_profile_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["profile"]


def test_profiles2(mocker):
    config = {"responsetype": {"profile": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_profile_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_profilesresponse3(mocker):
    config = {}
    assert (get_profile_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["profile"]


def test_pinned_response(mocker):
    assert (get_pinned_responsetype(config=None)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["pinned"]


def test_pinned_response2(mocker):
    config = {"responsetype": {"profile": of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]}}
    assert (get_pinned_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]


def test_pinned_response3(mocker):
    config = {}
    assert (get_pinned_responsetype(config=config)) == of_env.getattr("RESPONSE_TYPE_DEFAULT")["pinned"]
