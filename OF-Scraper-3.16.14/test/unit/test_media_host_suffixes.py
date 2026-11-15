"""Unit tests for media / DRM host-suffix helpers."""

import pytest

from ofscraper.utils.hardening import assert_allowed_download_url, is_allowed_media_host
from ofscraper.utils.media_host_suffixes import (
    normalize_media_host_suffixes,
    parse_media_host_suffixes,
    validate_media_host_suffixes,
)


@pytest.mark.unit
def test_parse_and_normalize():
    assert parse_media_host_suffixes(None) == []
    assert parse_media_host_suffixes("") == []
    assert parse_media_host_suffixes(" ExampleCDN.net , .other.com ") == [
        "examplecdn.net",
        "other.com",
    ]
    assert parse_media_host_suffixes("https://cdn.foo.test/path") == ["cdn.foo.test"]
    assert normalize_media_host_suffixes("a.com,b.com") == "a.com,b.com"


@pytest.mark.unit
def test_validate():
    assert validate_media_host_suffixes("") is None
    assert validate_media_host_suffixes("cdn.ok.com") is None
    assert validate_media_host_suffixes("not a host!!!") is not None
    assert validate_media_host_suffixes("x.com:443") is not None


@pytest.mark.unit
def test_allowlist_with_extra_suffix():
    assert is_allowed_media_host("d111.cloudfront.net")
    assert not is_allowed_media_host("cdn.evil.example")
    assert is_allowed_media_host(
        "cdn.evil.example", extra_suffixes="evil.example"
    )
    assert_allowed_download_url(
        "https://cdn.evil.example/x.mpd",
        kind="drm-mpd",
        extra_suffixes="evil.example",
    )
    with pytest.raises(ValueError):
        assert_allowed_download_url("https://cdn.evil.example/x.mpd", kind="drm-mpd")
