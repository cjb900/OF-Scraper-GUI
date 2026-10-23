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


def test_new_config_location(mocker):
    migrationConfig = {
        "config": {
            "main_profile": of_env.getattr("PROFILE_DEFAULT"),
            "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
            "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
        }
    }
    currentConfig = get_current_config_schema(migrationConfig)
    with tempfile.TemporaryDirectory() as p:
        mocker.patch(
            "ofscraper.utils.args.getargs", return_value=args_.getargs(["--config", p])
        )
        configPath = paths_.get_config_path()
        configPath.parent.mkdir(parents=True, exist_ok=True)

        with open(configPath, "w") as w:
            w.write(json.dumps(currentConfig))

        new_config = config_.read_config()
        for key in new_config:
            with check:
                assert (new_config[key]) == currentConfig["config"][key]


# def test_current_schema2(mocker):
#     migrationConfig={"config":{
#         "main_profile": of_env.getattr("PROFILE_DEFAULT"),
#         "save_location": of_env.getattr("SAVE_PATH_DEFAULT"),
#         "file_size_max": of_env.getattr("FILE_SIZE_MAX_DEFAULT"),
#     }}
#     currentConfig=get_current_data.schema(migrationConfig)

#     assert(sorted(set(currentConfig["config"].keys())))==sorted(set(data.KEYS))


def test_filesize(mocker):
    assert (get_filesize_limit(config=None)) == FILE_SIZE_LIMIT_DEFAULT


def test_filesize2(mocker):
    config = {"file_size_limit": FILE_SIZE_ALT}
    assert (get_filesize_limit(config=config)) == FILE_SIZE_ALT


def test_filesize3(mocker):
    config = {}
    assert (get_filesize_limit(config=config)) == FILE_SIZE_LIMIT_DEFAULT


def test_mp4decrypt(mocker):
    assert (get_mp4decrypt(None)) == MP4DECRYPT_DEFAULT


def test_mp4decrypt2(mocker):
    config = {"mp4decrypt": ALT_MP4DECRYPT}
    assert (get_mp4decrypt(config)) == ALT_MP4DECRYPT


def test_mp4decrypt3(mocker):
    config = {}
    assert (get_mp4decrypt(config)) == MP4DECRYPT_DEFAULT


def test_filter2(mocker):
    config = {"filter": []}
    assert (get_filter(config=config)) == []
