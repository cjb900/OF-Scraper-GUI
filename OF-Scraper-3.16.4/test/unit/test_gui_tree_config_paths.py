# GUI tree tests from the 3.14.7 tree's test/unit/test_config_paths.py that the fork's test/test_config_paths.py does not have
import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.config.data as data


@pytest.fixture
def ffmpeg_env(monkeypatch):
    real = data.of_env.getattr
    monkeypatch.setattr(
        data.of_env,
        "getattr",
        lambda key, *a: "/opt/ffmpeg" if key == "FFMPEG_DEFAULT" else real(key),
    )


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
