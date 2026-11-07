from ofscraper.gui.utils.auth_errors import format_cred_test_failure


class _Response:
    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _HTTPError(Exception):
    def __init__(self, message, body):
        super().__init__(message)
        self.response = _Response(body)


def _bad_request(code, message=""):
    return _HTTPError(
        "Client error '400 Bad Request' for url "
        "'https://onlyfans.com/api2/v2/subscriptions/count/all'",
        {"error": {"code": code, "message": message}},
    )


def test_code_117_explains_age_verification():
    text = format_cred_test_failure(_bad_request(117))
    assert "verifying your age (code 117)" in text
    assert "manual copy" in text
    # the generic hints don't apply to this failure
    assert "Dynamic Mode" not in text


def test_code_117_as_text_is_recognised():
    text = format_cred_test_failure(_bad_request("117"))
    assert "verifying your age" in text


def test_wrong_user_is_unchanged():
    text = format_cred_test_failure(_bad_request(301, "Wrong user"))
    assert "Wrong user" in text
    assert "verifying your age" not in text


def test_other_codes_keep_the_generic_message():
    text = format_cred_test_failure(_bad_request(999))
    assert text.startswith("Could not verify credentials against OnlyFans.")
    assert "verifying your age" not in text
