"""Save & Test failures on the Fansly page are explained in plain words."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui.dialogs.fansly_auth_dialog import explain_test_failure  # noqa: E402

RAW_401 = ("Client error '401 Unauthorized' for url 'https://apiv3.fansly.com/api/v1/account/me?ngsw-bypass=true'\n"
           "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/401")


def test_unauthorized():
    msg = explain_test_failure(RAW_401)
    assert "invalid, expired, or that browser was signed out" in msg
    assert "apiv3" not in msg and "mozilla" not in msg


@pytest.mark.parametrize("raw, words", [
    ("Client error '403 Forbidden' for url 'x'", "user agent may not match"),
    ("Client error '429 Too Many Requests' for url 'x'", "limiting requests"),
    ("ConnectError: [Errno 11001] getaddrinfo failed", "couldn't reach Fansly"),
    ("ReadTimeout: timed out", "couldn't reach Fansly"),
])
def test_common_failures(raw, words):
    assert words in explain_test_failure(raw)


def test_other_errors_keep_their_text_without_the_link():
    msg = explain_test_failure("Server error '502 Bad Gateway' for url 'x'\nFor more information check: https://m")
    assert "502 Bad Gateway" in msg and "For more information" not in msg
