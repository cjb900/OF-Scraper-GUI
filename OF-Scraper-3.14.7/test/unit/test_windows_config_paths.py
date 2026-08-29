"""Windows filesystem path normalization for config GUI / config.json."""

import json
import os

import pytest

from ofscraper.utils.config.path_norm import (
    normalize_config_paths_for_os,
    normalize_windows_path,
)


@pytest.mark.skipif(os.name != "nt", reason="Windows path separators only")
def test_normalize_windows_drive_path():
    assert normalize_windows_path(r"C:/Downloads/OnlyFans/") == r"C:\Downloads\OnlyFans"
    assert normalize_windows_path(r"E:/Downloads/OnlyFans/ffmpeg.exe") == (
        r"E:\Downloads\OnlyFans\ffmpeg.exe"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows path separators only")
def test_normalize_leaves_templates_and_urls():
    tmpl = "{model_username}/{responsetype}/{mediatype}/"
    assert normalize_windows_path(tmpl) == tmpl
    meta = "{configpath}/{profile}/.data/{model_id}"
    assert normalize_windows_path(meta) == meta
    url = "https://discord.com/api/webhooks/123"
    assert normalize_windows_path(url) == url


@pytest.mark.skipif(os.name != "nt", reason="Windows path separators only")
def test_json_dumps_double_escapes_backslashes():
    path = normalize_windows_path(r"E:/Downloads/OnlyFans/client_id.bin")
    dumped = json.dumps({"client-id": path})
    assert r"E:\\Downloads\\OnlyFans\\client_id.bin" in dumped
    loaded = json.loads(dumped)
    assert loaded["client-id"] == path


@pytest.mark.skipif(os.name != "nt", reason="Windows path separators only")
def test_normalize_config_paths_for_os():
    cfg = {
        "file_options": {"save_location": "C:/Downloads/OF/", "dir_format": "{u}/{t}/"},
        "binary_options": {"ffmpeg": "E:/tools/ffmpeg.exe"},
        "cdm_options": {
            "client-id": "E:/keys/client_id.bin",
            "private-key": "E:/keys/private_key.pem",
        },
    }
    normalize_config_paths_for_os(cfg)
    assert cfg["file_options"]["save_location"] == r"C:\Downloads\OF"
    assert cfg["file_options"]["dir_format"] == "{u}/{t}/"
    assert cfg["binary_options"]["ffmpeg"] == r"E:\tools\ffmpeg.exe"
    assert cfg["cdm_options"]["client-id"] == r"E:\keys\client_id.bin"


@pytest.mark.skipif(os.name == "nt", reason="non-Windows must leave paths alone")
def test_normalize_noop_on_posix():
    p = "/home/user/Downloads/OF"
    assert normalize_windows_path(p) == p
    cfg = {"file_options": {"save_location": p}}
    normalize_config_paths_for_os(cfg)
    assert cfg["file_options"]["save_location"] == p
