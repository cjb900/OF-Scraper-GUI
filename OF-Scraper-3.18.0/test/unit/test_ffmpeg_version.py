import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.system.ffmpeg as ffmpeg


def _fake_version(monkeypatch, line):
    monkeypatch.setattr(ffmpeg.shutil, "which", lambda p: p)
    monkeypatch.setattr(
        ffmpeg, "run", lambda *a, **k: SimpleNamespace(stdout=line, stderr="")
    )


@pytest.mark.parametrize(
    "line,ok",
    [
        ("ffmpeg version 5.1.6 Copyright", False),
        ("ffmpeg version 6.1.1 Copyright", True),
        ("ffmpeg version 7.1.1-essentials_build Copyright", True),
        # 8+ decrypts the same; it used to be rejected
        ("ffmpeg version 8.1.2-essentials_build Copyright", True),
        ("ffmpeg version 9.0.2-full_build Copyright", True),
        ("ffmpeg version N-118000-gabcdef Copyright", True),
        ("not ffmpeg", False),
    ],
)
def test_ffmpeg_version_gate(monkeypatch, line, ok):
    _fake_version(monkeypatch, line)
    assert ffmpeg._is_valid_ffmpeg("ffmpeg") is ok
