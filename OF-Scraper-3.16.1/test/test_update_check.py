import contextlib
import logging

import pytest

import ofscraper.__main__  # noqa: F401  (import order: avoids a circular import)
import ofscraper.utils.logs.logs as logs


class _Response:
    def __init__(self, version):
        self._version = version

    def json(self):
        return {"info": {"version": self._version, "project_url": "https://example.invalid"}}


@pytest.mark.parametrize(
    "pypi,current,newer",
    [
        ("3.14.7", "3.14.7+g705a2180", False),
        # a fork build ahead of PyPI is not out of date
        ("3.14.7", "3.15.0+g705a2180", False),
        ("3.14.7", "3.15.0", False),
        ("3.14.8", "3.14.7+g705a2180", True),
        ("3.15.1", "3.15.0+g705a2180", True),
        ("4.0", "3.15.0", True),
    ],
)
def test_update_check(monkeypatch, caplog, pypi, current, newer):
    monkeypatch.setattr(logs, "__version__", current)
    monkeypatch.setattr(
        logs.BareSession,
        "get_bare_session",
        lambda **kwargs: contextlib.nullcontext(_Response(pypi)),
    )
    with caplog.at_level(logging.WARNING, logger="shared"):
        logs.print_latest_version()
    assert ("new version of OF-Scraper available" in caplog.text) is newer
