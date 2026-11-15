"""temp_cleanup() removes temp_ files by file name, not by full path."""

from types import SimpleNamespace

import pytest

import ofscraper.utils.paths.paths as paths

pytestmark = pytest.mark.unit


def _run_cleanup(monkeypatch, root):
    real_getattr = paths.of_env.getattr

    def fake_getattr(key, *args, **kwargs):
        if key == "BATCH_TEMPFILE_CLEANUP":
            return True
        return real_getattr(key, *args, **kwargs)

    monkeypatch.setattr(paths.of_env, "getattr", fake_getattr)
    monkeypatch.setattr(
        paths.settings, "get_settings", lambda: SimpleNamespace(auto_resume=False)
    )
    monkeypatch.setattr(paths.data, "get_TempDir", lambda *a, **k: str(root))
    paths.temp_cleanup()


def test_removes_temp_prefixed_files(monkeypatch, tmp_path):
    # The DRM merge in alt_download.py writes temp_<id>.mp4, or
    # temp_<id>_<seq>.mp4 for a duplicate, under the temp folder.
    sub = tmp_path / "creator" / "Videos"
    sub.mkdir(parents=True)
    temp_top = tmp_path / "temp_123456.mp4"
    temp_nested = sub / "temp_654321.mp4"
    temp_seq = sub / "temp_654321_2.mp4"
    part = sub / "video.mp4.part"
    for f in (temp_top, temp_nested, temp_seq, part):
        f.write_bytes(b"x")

    _run_cleanup(monkeypatch, tmp_path)

    assert not temp_top.exists()
    assert not temp_nested.exists()
    assert not temp_seq.exists()
    assert not part.exists()


def test_keeps_other_files_and_folders(monkeypatch, tmp_path):
    # A folder named temp_ is left alone, and so is a file inside it or
    # with temp_ in the middle of its name.
    temp_dir = tmp_path / "temp_folder"
    temp_dir.mkdir()
    inside = temp_dir / "keep.mp4"
    middle = tmp_path / "my_temp_clip.mp4"
    done = tmp_path / "finished.mp4"
    for f in (inside, middle, done):
        f.write_bytes(b"x")

    _run_cleanup(monkeypatch, tmp_path)

    assert temp_dir.is_dir()
    assert inside.exists()
    assert middle.exists()
    assert done.exists()


def test_does_nothing_when_the_setting_is_off(monkeypatch, tmp_path):
    temp_file = tmp_path / "temp_123456.mp4"
    temp_file.write_bytes(b"x")
    monkeypatch.setattr(paths.data, "get_TempDir", lambda *a, **k: str(tmp_path))
    real_getattr = paths.of_env.getattr
    monkeypatch.setattr(
        paths.of_env,
        "getattr",
        lambda key, *a, **k: False
        if key == "BATCH_TEMPFILE_CLEANUP"
        else real_getattr(key, *a, **k),
    )

    paths.temp_cleanup()

    assert temp_file.exists()
