import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.config.data as data


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"C:\\keys\\private_key.pem"', "C:\\keys\\private_key.pem"),
        ("'/keys/private_key.pem'", "/keys/private_key.pem"),
        ('  "/keys/a b.pem"  ', "/keys/a b.pem"),
        ("/keys/private_key.pem", "/keys/private_key.pem"),
        ('"', '"'),
        (None, None),
    ],
)
def test_strip_path_quotes(raw, expected):
    assert data.strip_path_quotes(raw) == expected


def test_cdm_paths_are_unquoted():
    config = {
        "cdm_options": {
            "private-key": '"C:\\keys\\private_key.pem"',
            "client-id": '"C:\\keys\\client_id.bin"',
        }
    }
    assert data.get_private_key(config=config) == "C:\\keys\\private_key.pem"
    assert data.get_client_id(config=config) == "C:\\keys\\client_id.bin"


def test_ffmpeg_path_is_unquoted():
    config = {"binary_options": {"ffmpeg": '"C:\\ffmpeg\\bin\\ffmpeg.exe"'}}
    assert data.get_ffmpeg(config=config) == "C:\\ffmpeg\\bin\\ffmpeg.exe"


@pytest.fixture
def ffmpeg_env(monkeypatch):
    real = data.of_env.getattr
    monkeypatch.setattr(
        data.of_env,
        "getattr",
        lambda key, *a: "/opt/ffmpeg" if key == "FFMPEG_DEFAULT" else real(key),
    )


def test_empty_ffmpeg_is_not_replaced_by_env_default(ffmpeg_env):
    assert data.get_ffmpeg(config={"binary_options": {"ffmpeg": ""}}) == ""


def test_config_rewrite_keeps_empty_ffmpeg(ffmpeg_env):
    # auto_update_config writes this schema back to config.json
    import ofscraper.utils.config.schema as schema

    new = schema.get_current_config_schema({"binary_options": {"ffmpeg": ""}})
    assert new["binary_options"]["ffmpeg"] == ""


def test_settings_falls_back_to_env_default_for_empty_ffmpeg(ffmpeg_env, monkeypatch):
    import ofscraper.utils.settings as settings

    monkeypatch.setattr(settings.config_data, "get_ffmpeg", lambda: "")
    assert settings.merged_settings().ffmpeg == "/opt/ffmpeg"


def test_save_location_is_unquoted():
    import ofscraper.utils.paths.common as common_paths

    config = {"file_options": {"save_location": r'"D:\Media\OnlyFans"'}}
    assert common_paths.get_save_location(config=config) == r"D:\Media\OnlyFans"


@pytest.fixture
def quoted_cdm_files(tmp_path):
    client = tmp_path / "client_id.bin"
    private = tmp_path / "private_key.pem"
    client.write_bytes(b"x")
    private.write_bytes(b"x")
    return f'"{client}"', f'"{private}"'


def test_key_chip_accepts_quoted_cdm_paths(quoted_cdm_files, monkeypatch):
    # the GUI's status chip read the raw value and warned "Key: CDM?"
    # although downloads worked
    import types

    import ofscraper.utils.config.config as config
    from ofscraper.gui.utils.health_check import _key_chip

    # the real key_mode_warning imports PyQt6, which test/unit doesn't install
    key_mode_warning = types.ModuleType("ofscraper.gui.utils.key_mode_warning")
    key_mode_warning.get_configured_key_mode = lambda: "manual"
    key_mode_warning.is_remote_key_mode = lambda mode: False
    monkeypatch.setitem(sys.modules, key_mode_warning.__name__, key_mode_warning)

    client, private = quoted_cdm_files
    cfg = {"cdm_options": {"client-id": client, "private-key": private}}
    monkeypatch.setattr(config, "read_config", lambda *a, **k: cfg)
    assert _key_chip().level == "ok"


def test_config_check_accepts_quoted_ffmpeg_and_save_location(tmp_path):
    from ofscraper.gui.utils.config_validation import validate_config

    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_bytes(b"x")
    result = validate_config(
        {
            "file_options": {"save_location": f'"{tmp_path}"'},
            "binary_options": {"ffmpeg": f'"{ffmpeg}"'},
        }
    )
    issues = result.errors + result.warnings
    assert not [i for i in issues if i.field in ("FFmpeg Path", "Save Location")]
    assert not [i for i in issues if '"' in i.message]
