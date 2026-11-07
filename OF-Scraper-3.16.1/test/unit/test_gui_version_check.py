"""The GUI's update check must not offer PyPI's older upstream release.

OF-Scraper-Community installs from git report e.g. 3.16.1+g8e8cb815 while
PyPI's ofscraper is the upstream 3.14.7. Without the packaging module the
compare was inconclusive and the GUI said "Newer version reported on PyPI:
3.14.7" on every start.
"""

import pytest

import ofscraper.gui.utils.version_check as vc

pytestmark = pytest.mark.unit


@pytest.fixture(params=[True, False], ids=["packaging", "no-packaging"])
def compare(request, monkeypatch):
    if not request.param:
        monkeypatch.setattr(vc, "_parse_version", lambda text: None)
    return vc._is_newer


@pytest.mark.parametrize(
    "latest,current,newer",
    [
        ("3.14.7", "3.16.1+g8e8cb815", False),
        ("3.14.7", "3.16.1", False),
        ("3.16.1", "3.16.1+g8e8cb815", False),
        ("3.16.2", "3.16.1+g8e8cb815", True),
        ("3.17.0", "3.16.1", True),
    ],
)
def test_compare(compare, latest, current, newer):
    assert compare(latest, current) is newer


def test_fork_build_is_up_to_date_against_pypi(monkeypatch):
    monkeypatch.setattr(vc, "_parse_version", lambda text: None)
    monkeypatch.setattr(vc, "fetch_pypi_latest", lambda timeout=8.0: ("3.14.7", vc.DEFAULT_PROJECT_URL))
    result = vc.check_for_updates("3.16.1+g8e8cb815")
    assert result.status == "up_to_date"
    assert not vc.should_prompt_startup(result)
