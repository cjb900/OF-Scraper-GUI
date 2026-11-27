"""The GUI's update check looks only at the GUI's own GitHub releases."""

import pathlib

import pytest

from ofscraper.gui.utils import version_check as vc

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _release_channel(monkeypatch):
    # never read this machine's GUI settings
    monkeypatch.setattr(vc, "update_channel", lambda: vc.RELEASE)


def release(body="", assets=("patch_ofscraper_3.17.1_gui.py",), tag="OF-Scraper-3.17.1_11-20-2026",
            published="2026-11-20T08:00:00Z"):
    return {
        "tag_name": tag,
        "name": "GUI update",
        "body": body,
        "html_url": f"https://github.com/{vc.GITHUB_REPO}/releases/tag/{tag}",
        "published_at": published,
        "assets": [{"name": a} for a in assets],
    }


INSTALLED = vc.parse_patch_id("20261115_gui_3_17_1_v434")


def check(monkeypatch, rel):
    monkeypatch.setattr(vc, "fetch_latest_release", lambda timeout=8.0: rel)
    return vc.check_for_updates(INSTALLED)


def test_patch_id_is_read():
    assert INSTALLED == vc.PatchInfo(434, "20261115", "3.17.1")
    assert INSTALLED.label == "v434 for OF-Scraper 3.17.1"


def test_newer_gui_release_is_offered(monkeypatch):
    result = check(monkeypatch, release("Patch tip is now `20261120_gui_3_17_1_v440` (from v434)."))
    assert result.status == "update_available"
    assert "v440" in result.message and "PyPI" not in result.message
    assert result.project_url.startswith(f"https://github.com/{vc.GITHUB_REPO}/releases")
    assert result.latest == "OF-Scraper-3.17.1_11-20-2026"


def test_release_for_a_newer_ofscraper_names_it(monkeypatch):
    rel = release("tip `20261201_gui_3_18_0_v450`", assets=["patch_ofscraper_3.18.0_gui.py"])
    result = check(monkeypatch, rel)
    assert result.status == "update_available"
    assert "for OF-Scraper 3.18.0" in result.message


def test_older_release_is_up_to_date(monkeypatch):
    # today's latest release: the 3.14.7 patch v422
    rel = release("GUI patch tip is now **`20261111_gui_3_14_7_v422`**.",
                  assets=["patch_ofscraper_3.14.7_gui.py"], published="2026-11-11T07:56:00Z")
    assert check(monkeypatch, rel).status == "up_to_date"


def test_notes_without_a_patch_id_use_the_release_date(monkeypatch):
    assert check(monkeypatch, release("bug fixes")).status == "update_available"
    old = release("bug fixes", published="2026-11-01T00:00:00Z")
    assert check(monkeypatch, old).status == "up_to_date"


def test_github_unreachable_is_an_error_not_a_prompt(monkeypatch):
    result = check(monkeypatch, None)
    assert result.status == "error"
    assert not vc.should_prompt_startup(result)


def test_pypi_is_never_asked(monkeypatch):
    urls = []

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            urls.append(url)
            raise OSError("offline")

    import httpx

    monkeypatch.setattr(httpx, "Client", Client)
    vc.check_for_updates(INSTALLED)
    assert urls == [vc.LATEST_RELEASE_API]
    assert "api.github.com" in urls[0]


@pytest.mark.parametrize("path", [
    "ofscraper/gui/utils/version_check.py",
    "ofscraper/gui/main_window.py",
    "ofscraper/gui/dialogs/about_dialog.py",
])
def test_no_pypi_links_in_the_gui(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert "pypi.org" not in text
    assert "Open PyPI" not in text


def test_a_newer_ofscraper_release_wins_over_a_higher_patch_number(monkeypatch):
    # patch numbers run across versions: the 3.14.7 GUI can be v436 while the
    # 3.17.1 GUI release is v435
    monkeypatch.setattr(vc, "fetch_latest_release", lambda timeout=8.0: release(
        "tip `20261115_gui_3_17_1_v435`"))
    result = vc.check_for_updates(vc.parse_patch_id("20261115_gui_3_14_7_v436"))
    assert result.status == "update_available"
    assert "for OF-Scraper 3.17.1" in result.message


def test_a_release_for_an_older_ofscraper_is_not_an_update(monkeypatch):
    monkeypatch.setattr(vc, "fetch_latest_release", lambda timeout=8.0: release(
        "tip `20261115_gui_3_14_7_v436`", assets=["patch_ofscraper_3.14.7_gui.py"]))
    assert check(monkeypatch, vc.fetch_latest_release()).status == "up_to_date"


# --- testing builds ------------------------------------------------------------------


class FakeGitHub:
    """httpx.Client stand-in: the testing branch's file list and patch heads."""

    def __init__(self, files, patch_ids):
        self.files, self.patch_ids, self.requests = files, patch_ids, []

    def client(self, *a, **k):
        gh = self

        class Client:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url, headers=None):
                gh.requests.append((url, headers or {}))
                import httpx

                req = httpx.Request("GET", url)
                if url == vc.TESTING_BRANCH_API:
                    return httpx.Response(200, json={"commit": {"sha": "abc123"}}, request=req)
                if url == vc.TESTING_CONTENTS_API.format(ref="abc123"):
                    return httpx.Response(200, json=[{"name": n} for n in gh.files], request=req)
                name = url.rsplit("/", 1)[-1]
                body = f'import os\n\nPATCH_ID = "{gh.patch_ids[name]}"\nZIP_B64 = "{"A" * 20000}"\n'
                return httpx.Response(206, content=body.encode()[:8192], request=req)

        return Client()


def fake_testing_branch(monkeypatch, files, patch_ids):
    import httpx

    gh = FakeGitHub(files, patch_ids)
    monkeypatch.setattr(httpx, "Client", gh.client)
    return gh


def test_testing_build_is_offered(monkeypatch):
    gh = fake_testing_branch(monkeypatch, [
        "README.md", "patch_ofscraper_3.14.7_gui.py", "patch_ofscraper_3.17.1_gui.py",
    ], {"patch_ofscraper_3.17.1_gui.py": "20261116_gui_3_17_1_v439"})
    result = vc.check_for_updates(INSTALLED, channel=vc.TESTING)
    assert result.status == "update_available" and result.channel == vc.TESTING
    assert "testing build" in result.message and "v439" in result.message
    assert result.project_url == vc.TESTING_URL
    # only the highest version's script, and only its first bytes
    url, headers = gh.requests[-1]
    # read at the branch's commit, never the cached branch name
    assert url.endswith("/abc123/patch_ofscraper_3.17.1_gui.py")
    assert result.download_url == url
    assert headers["Range"] == f"bytes=0-{vc.PATCH_HEAD_BYTES - 1}"


def test_same_testing_build_is_up_to_date(monkeypatch):
    fake_testing_branch(monkeypatch, ["patch_ofscraper_3.17.1_gui.py"],
                   {"patch_ofscraper_3.17.1_gui.py": "20261115_gui_3_17_1_v434"})
    result = vc.check_for_updates(INSTALLED, channel=vc.TESTING)
    assert result.status == "up_to_date"
    assert not vc.should_prompt_startup(result)


def test_testing_check_unreachable(monkeypatch):
    def broken(*a, **k):
        raise OSError("offline")

    import httpx

    monkeypatch.setattr(httpx, "Client", broken)
    result = vc.check_for_updates(INSTALLED, channel=vc.TESTING)
    assert result.status == "error" and not vc.should_prompt_startup(result)


def test_channel_setting_round_trips(monkeypatch):
    store = {}
    import ofscraper.gui.utils.gui_settings as gs

    monkeypatch.undo()  # drop the autouse release-channel stub for this test
    monkeypatch.setattr(gs, "load_gui_settings", lambda: dict(store))
    monkeypatch.setattr(gs, "save_gui_settings", lambda s: store.update(s))
    assert vc.update_channel() == vc.RELEASE
    vc.set_update_channel(vc.TESTING)
    assert vc.update_channel() == vc.TESTING
    vc.set_update_channel("anything else")
    assert vc.update_channel() == vc.RELEASE
