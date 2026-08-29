from pathlib import Path

import pytest

from ofscraper.utils.hardening import (
    assert_allowed_download_url,
    assert_path_under_root,
    check_media_integrity,
    is_allowed_media_host,
    mpd_segment_url,
    parse_expected_file_size,
)
from ofscraper.utils.auth.cookie_allowlist import (
    filter_cookie_map,
    is_allowed_cookie_name,
    is_onlyfans_host,
)


@pytest.mark.unit
def test_hosts_allow_and_reject():
    assert is_allowed_media_host("cdn2.onlyfans.com")
    assert is_allowed_media_host("d111.cloudfront.net")
    assert not is_allowed_media_host("evil-onlyfans.com")
    assert_allowed_download_url("https://cdn2.onlyfans.com/x.mp4")
    with pytest.raises(ValueError):
        assert_allowed_download_url("https://example.com/x.mp4")
    with pytest.raises(ValueError):
        assert_allowed_download_url("file:///tmp/x")


@pytest.mark.unit
def test_path_confinement(tmp_path: Path):
    root = tmp_path / "save"
    root.mkdir()
    ok = assert_path_under_root(root / "a" / "b.mp4", root)
    assert ok == (root / "a" / "b.mp4").resolve()
    with pytest.raises(ValueError, match="escapes configured root"):
        assert_path_under_root(tmp_path / "outside.txt", root)
    with pytest.raises(ValueError, match="escapes configured root"):
        assert_path_under_root(root / ".." / "escape.txt", root)


@pytest.mark.unit
def test_expected_file_size_parsing():
    assert (
        parse_expected_file_size(
            {"Content-Range": "bytes 100-199/1000", "content-length": "100"},
            resume_size=100,
            content_length=100,
        )
        == 1000
    )
    assert (
        parse_expected_file_size(
            {"content-length": "50"}, resume_size=150, content_length=50
        )
        == 200
    )
    assert parse_expected_file_size({"content-length": "500"}, resume_size=0) == 500


@pytest.mark.unit
def test_cookie_allowlist():
    assert is_onlyfans_host("onlyfans.com")
    assert not is_onlyfans_host("notonlyfans.com")
    assert is_allowed_cookie_name("sess")
    assert not is_allowed_cookie_name("csrftoken")
    out = filter_cookie_map(
        {"sess": "a", "auth_id": "1", "tracking": "no", "user_agent": "UA", "x-bc": "bc"}
    )
    assert set(out) >= {"sess", "auth_id", "user_agent", "x-bc"}
    assert "tracking" not in out


@pytest.mark.unit
def test_mpd_segment_url_strips_query_and_manifest():
    mpd = (
        "https://cdn2.onlyfans.com/dash/files/9/93/"
        "93bd6e5dd36443189f31bbb8df88991d/0igiqhf747zcbvxnyga7l.mpd?Tag=2"
    )
    audio = mpd_segment_url(mpd, "0igiqhf747zcbvxnyga7l_audio.mp4")
    video = mpd_segment_url(mpd, "0igiqhf747zcbvxnyga7l_source.mp4")
    assert audio == (
        "https://cdn2.onlyfans.com/dash/files/9/93/"
        "93bd6e5dd36443189f31bbb8df88991d/0igiqhf747zcbvxnyga7l_audio.mp4?Tag=2"
    )
    assert video.endswith("0igiqhf747zcbvxnyga7l_source.mp4?Tag=2")
    assert ".mpd" not in audio
    # Regression: old re.sub(..., re.IGNORECASE-as-count) left the MPD URL intact.
    assert not audio.startswith(mpd)
    with pytest.raises(ValueError):
        mpd_segment_url(mpd, "x.mpd")
    with pytest.raises(ValueError):
        mpd_segment_url("", "a.mp4")


@pytest.mark.unit
def test_media_integrity_pure(tmp_path: Path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x" * 2048)
    assert check_media_integrity(f, 98.0, 100.0, match_threshold=0.98) is True
    assert check_media_integrity(f, 50.0, 100.0, match_threshold=0.98) is False
    assert check_media_integrity(f, None, 100.0) is False
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    assert check_media_integrity(empty, 10.0, 10.0) is False
    # Short clip: API whole seconds (12) vs remux 11.71 — under 98% but within 1s slack
    assert check_media_integrity(f, 11.71, 12.0, match_threshold=0.98) is True
    # Still reject clearly truncated long media (far beyond 1s slack and ratio)
    assert check_media_integrity(f, 500.0, 600.0, match_threshold=0.98) is False
