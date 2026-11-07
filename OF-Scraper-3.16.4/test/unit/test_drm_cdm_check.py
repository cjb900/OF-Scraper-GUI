import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import asyncio
import inspect
from types import SimpleNamespace

import pytest

import ofscraper.commands.scraper.actions.download.utils.keyhelpers as keyhelpers
from ofscraper.commands.scraper.actions.download.managers.alt_download import AltDownloadManager
from ofscraper.commands.scraper.actions.download.utils.retries import download_retry
from tenacity import stop_after_attempt, wait_none

pytestmark = pytest.mark.unit


@pytest.fixture
def cdm(tmp_path, monkeypatch):
    client = tmp_path / "client_id.bin"
    key = tmp_path / "private_key.pem"
    client.write_bytes(b"c")
    key.write_bytes(b"k")
    s = SimpleNamespace(key_mode="manual", client_id=str(client), private_key=str(key))
    monkeypatch.setattr(keyhelpers.settings, "get_settings", lambda: s)
    monkeypatch.setattr(keyhelpers, "_cdm_problem_logged", False)

    async def no_cache(ele):
        return False

    monkeypatch.setattr(keyhelpers, "has_cached_key", no_cache)
    return s


def test_files_present_is_fine(cdm):
    assert keyhelpers.manual_cdm_problem() is None


@pytest.mark.parametrize("blank", ["", None, "   "])
def test_blank_path_is_reported_not_read_as_a_folder(cdm, blank):
    cdm.private_key = blank
    msg = keyhelpers.manual_cdm_problem()
    assert "private-key is not set" in msg and "client-id is not set" not in msg


def test_missing_file_is_reported(cdm, tmp_path):
    cdm.client_id = str(tmp_path / "nope.bin")
    assert "client-id file not found" in keyhelpers.manual_cdm_problem()


def test_check_stops_manual_mode_without_files(cdm, caplog):
    cdm.private_key = ""
    with pytest.raises(keyhelpers.CdmFilesMissing):
        asyncio.run(keyhelpers.check_manual_cdm(object()))
    with pytest.raises(keyhelpers.CdmFilesMissing):
        asyncio.run(keyhelpers.check_manual_cdm(object()))
    # the plain message is logged once, not once per video
    assert sum("Key Mode is manual" in r.getMessage() for r in caplog.records) == 1


@pytest.mark.parametrize("mode", ["cdrm", "keydb"])
def test_other_key_modes_are_not_checked(cdm, mode):
    cdm.key_mode, cdm.private_key = mode, ""
    asyncio.run(keyhelpers.check_manual_cdm(object()))


def test_cached_key_still_works_without_files(cdm, monkeypatch):
    cdm.private_key = ""

    async def cached(ele):
        return True

    monkeypatch.setattr(keyhelpers, "has_cached_key", cached)
    asyncio.run(keyhelpers.check_manual_cdm(object()))


def _attempts(exc):
    calls = 0

    async def run():
        nonlocal calls
        async for attempt in download_retry(stop=stop_after_attempt(3), wait=wait_none()):
            with attempt:
                calls += 1
                raise exc

    with pytest.raises(type(exc)):
        asyncio.run(run())
    return calls


def test_missing_cdm_files_are_not_retried():
    assert _attempts(keyhelpers.CdmFilesMissing("x")) == 1
    assert _attempts(RuntimeError("network")) == 3


def test_check_runs_before_the_drm_download():
    src = inspect.getsource(AltDownloadManager.alt_download)
    assert src.index("check_manual_cdm(ele)") < src.index("_alt_download_downloader(")


def _run_download_with(monkeypatch, exc):
    import ofscraper.commands.scraper.actions.download.run as run

    async def boom(self, *a, **k):
        raise exc

    lines = []
    monkeypatch.setattr(AltDownloadManager, "alt_download", boom)
    monkeypatch.setattr(run, "_record_gui_failure", lambda *a, **k: None)
    monkeypatch.setattr(run.common_globals, "log", SimpleNamespace(debug=lines.append), raising=False)
    ele = SimpleNamespace(url=None, mpd="https://example.invalid/x.mpd", id=1, postid=2)
    monkeypatch.setattr(run, "get_medialog", lambda e: "Media:1")
    assert asyncio.run(run.download(None, ele, 1, "u")) == ("skipped", 0)
    return lines


def test_missing_cdm_files_skip_without_a_traceback_per_video(monkeypatch):
    lines = _run_download_with(monkeypatch, keyhelpers.CdmFilesMissing("no key"))
    assert len(lines) == 1 and "Traceback" not in lines[0]


def test_other_download_errors_keep_their_traceback(monkeypatch):
    lines = _run_download_with(monkeypatch, RuntimeError("boom"))
    assert any("Traceback" in l for l in lines)
