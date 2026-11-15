"""Fansly in the GUI: a separate process, config.json and auth file per site."""

from __future__ import annotations

import json
import os
import pathlib
import sys
from types import SimpleNamespace

import pytest

from ofscraper.gui import site_context


@pytest.fixture
def fansly(monkeypatch):
    monkeypatch.setattr(site_context, "current_site", lambda: site_context.FANSLY)


@pytest.fixture
def onlyfans(monkeypatch):
    monkeypatch.setattr(site_context, "current_site", lambda: site_context.ONLYFANS)


# --- starting each site's process ------------------------------------------------------

def test_fansly_process_always_gets_its_own_config(monkeypatch, tmp_path):
    monkeypatch.setattr(site_context, "default_config_home", lambda: tmp_path / "ofscraper")
    args = site_context.site_arguments(site_context.FANSLY, ["--daemon", "5"], config="/x/c.json")
    assert args[:3] == ["--gui", "--site", "fansly"]
    assert args[3:5] == ["--config", str(tmp_path / "ofscraper" / "fansly" / "config.json")]
    assert args[5:] == ["--daemon", "5"]


def test_onlyfans_process_keeps_a_config_the_user_gave():
    assert site_context.site_arguments("onlyfans", [], config="/x/c.json") == [
        "--gui", "--site", "onlyfans", "--config", "/x/c.json",
    ]
    assert site_context.site_arguments("onlyfans") == ["--gui", "--site", "onlyfans"]


def test_forwarded_arguments_drop_what_the_tab_window_sets():
    argv = ["--gui", "--site", "fansly", "--config=/a.json", "-u", "bob", "--config", "/b", "--daemon", "5"]
    assert site_context.strip_site_args(argv) == ["-u", "bob", "--daemon", "5"]


def test_site_command_runs_this_python():
    cmd = site_context.site_command("onlyfans")
    assert cmd[:3] == [sys.executable, "-m", "ofscraper"]


def test_children_are_marked_and_unbuffered():
    env = site_context.child_environment(embed=True)
    assert env[site_context.ENV_CHILD] == "1"
    assert env[site_context.ENV_EMBED] == "1"
    assert env["PYTHONUNBUFFERED"] == "1"


# --- the channel to the tab window ---------------------------------------------------------

def test_channel_round_trip(monkeypatch, capsys):
    monkeypatch.setenv(site_context.ENV_CHILD, "1")
    monkeypatch.setattr(sys, "__stdout__", sys.stdout)
    site_context.send("notify", {"title": "Done", "message": "3 files ✓"})
    line = capsys.readouterr().out.strip()
    assert site_context.parse_channel_line(line) == ("notify", {"title": "Done", "message": "3 files ✓"})


def test_nothing_is_sent_outside_a_child(monkeypatch, capsys):
    monkeypatch.delenv(site_context.ENV_CHILD, raising=False)
    site_context.send("busy")
    assert capsys.readouterr().out == ""


def test_console_lines_are_not_channel_lines():
    assert site_context.parse_channel_line("INFO downloading @@OFSC_GUI busy") is None
    assert site_context.parse_channel_line("@@OFSC_GUI idle") == ("idle", None)


def test_tabs_can_be_turned_off(monkeypatch):
    monkeypatch.setenv(site_context.ENV_TABS, "0")
    assert not site_context.tabs_enabled()
    monkeypatch.delenv(site_context.ENV_TABS)
    assert site_context.tabs_enabled()


# --- each site's files ------------------------------------------------------------------------

def test_fansly_profile_gets_site_json_and_its_own_auth_file(monkeypatch, tmp_path, fansly):
    import ofscraper.sites.fansly.auth as fansly_auth
    import ofscraper.utils.paths.common as common_paths

    home = tmp_path / "ofscraper"
    profile = home / "fansly" / "main_profile"
    monkeypatch.setattr(site_context, "default_config_home", lambda: home)
    monkeypatch.setattr(common_paths, "get_profile_path", lambda *a, **k: profile)
    monkeypatch.setattr(common_paths, "get_config_home", lambda: home / "fansly")
    monkeypatch.setattr(fansly_auth, "auth_path", lambda: profile / "fansly_auth.json")
    home.mkdir(parents=True)
    (home / "gui_settings.json").write_text(
        json.dumps({"theme": "light", "gui_font_size": 15, "last_site": "onlyfans",
                    "area_checks": {"Timeline": False}})
    )

    site_context.prepare_site_files()

    assert json.loads((profile / "site.json").read_text()) == {"site": "fansly"}
    assert json.loads((profile / "fansly_auth.json").read_text())["authorization_token"] == ""
    assert not (profile / "auth.json").exists()
    # the look carries over; selections and the tab choice don't
    assert json.loads((home / "fansly" / "gui_settings.json").read_text()) == {
        "theme": "light", "gui_font_size": 15,
    }


def test_existing_fansly_files_are_left_alone(monkeypatch, tmp_path, fansly):
    import ofscraper.sites.fansly.auth as fansly_auth
    import ofscraper.utils.paths.common as common_paths

    profile = tmp_path / "fansly" / "main_profile"
    profile.mkdir(parents=True)
    (profile / "fansly_auth.json").write_text('{"authorization_token": "keep"}')
    monkeypatch.setattr(site_context, "default_config_home", lambda: tmp_path)
    monkeypatch.setattr(common_paths, "get_profile_path", lambda *a, **k: profile)
    monkeypatch.setattr(common_paths, "get_config_home", lambda: tmp_path / "fansly")
    monkeypatch.setattr(fansly_auth, "auth_path", lambda: profile / "fansly_auth.json")

    site_context.prepare_site_files()
    assert json.loads((profile / "fansly_auth.json").read_text()) == {"authorization_token": "keep"}


def test_onlyfans_profile_gets_auth_json(monkeypatch, tmp_path, onlyfans):
    import ofscraper.utils.paths.common as common_paths

    monkeypatch.setattr(common_paths, "get_profile_path", lambda *a, **k: tmp_path / "main_profile")
    monkeypatch.setattr(common_paths, "get_auth_file", lambda: tmp_path / "main_profile" / "auth.json")
    site_context.prepare_site_files()
    assert (tmp_path / "main_profile" / "auth.json").exists()
    assert not (tmp_path / "main_profile" / "site.json").exists()


def test_shared_temp_folder_is_reported(monkeypatch, tmp_path, fansly):
    import ofscraper.utils.config.data as config_data

    monkeypatch.setattr(site_context, "default_config_home", lambda: tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({"config": {"advanced_options": {"temp_dir": "/tmp/t"}}}))
    monkeypatch.setattr(config_data, "get_TempDir", lambda config=None: "/tmp/t")
    assert "same temp folder" in site_context.temp_folder_conflict()

    monkeypatch.setattr(config_data, "get_TempDir", lambda config=None: (
        "/tmp/other" if config is None else "/tmp/t"))
    assert site_context.temp_folder_conflict() is None


# --- what Fansly offers --------------------------------------------------------------------------

def test_fansly_areas_and_walls(fansly):
    assert site_context.site_areas() == ("Timeline", "Messages", "Purchased", "Labels")
    assert site_context.area_label("Labels") == "Walls"
    assert site_context.area_label("Timeline") == "Timeline"


def test_onlyfans_areas_are_unchanged(onlyfans):
    assert site_context.site_areas() is None
    assert site_context.area_label("Labels") == "Labels"


@pytest.mark.parametrize("action", ["like", "unlike", "post_check", "msg_check", "paid_check",
                                    "story_check", "metadata", "paid_all", "manual_url"])
def test_onlyfans_only_actions(fansly, action):
    assert not site_context.action_supported(action)
    assert site_context.action_supported(action, site=site_context.ONLYFANS)


def test_download_is_offered_on_fansly(fansly):
    assert site_context.action_supported("download")


def test_fansly_media_hosts_are_allowed():
    from ofscraper.utils.hardening import is_allowed_media_host

    assert is_allowed_media_host("cdn3.fansly.com")
    assert is_allowed_media_host("fansly.com")
    assert not is_allowed_media_host("notfansly.com")
    assert not is_allowed_media_host("fansly.com.evil.example")


def test_fansly_health_chips(monkeypatch, fansly):
    import ofscraper.sites.fansly.auth as fansly_auth
    from ofscraper.gui.utils import health_check

    monkeypatch.setattr(fansly_auth, "read_auth", lambda: fansly_auth.empty())
    chips = {c.key: c for c in health_check.gather_health()}
    assert chips["auth"].level == "error" and "Fansly" in chips["auth"].detail
    assert chips["key"].level == "ok"

    good = fansly_auth.empty()
    good.update(authorization_token="t" * 60, user_agent="Mozilla/5.0 " + "x" * 40)
    monkeypatch.setattr(fansly_auth, "read_auth", lambda: good)
    assert {c.key: c for c in health_check.gather_health()}["auth"].level == "ok"


def test_model_list_needs_fansly_credentials_not_onlyfans_ones(monkeypatch, fansly):
    import ofscraper.sites.fansly.auth as fansly_auth
    from ofscraper.gui.utils import model_fetch

    monkeypatch.setattr(fansly_auth, "read_auth", lambda: fansly_auth.empty())
    with pytest.raises(Exception, match="Fansly auth not configured"):
        model_fetch._fetch_subscription_models_locked(userlist=None, timeout_sec=1)


# --- pages --------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_action_page_hides_onlyfans_only_choices(qapp, fansly):
    from ofscraper.gui.pages.action_page import ActionPage

    page = ActionPage()
    shown = {
        tuple(sorted(b.property("actions")))
        for b in page._button_group.buttons()
        if not b.isHidden()
    }
    assert shown == {("download",)}


def test_area_page_offers_fansly_areas(qapp, fansly, monkeypatch):
    from ofscraper.gui.pages.area_selector_page import AreaSelectorPage

    page = AreaSelectorPage()
    page._current_actions = {"download"}
    page._update_available_areas()
    visible = {a for a, cb in page._area_checks.items() if not cb.isHidden()}
    assert visible == {"Timeline", "Messages", "Purchased", "Labels"}
    assert page._area_checks["Labels"].text() == "Walls"


# --- the tab window -------------------------------------------------------------------------------

def test_tab_shows_busy_and_forwards_notices(qapp, monkeypatch):
    from ofscraper.gui import site_host

    _, host_class = site_host._define_classes()
    host = host_class(initial="onlyfans", forwarded=[], onlyfans_config=None, embed=False)
    notices = []
    monkeypatch.setattr(host, "notify", lambda t, m: notices.append((t, m)))
    tab = host.site_tabs["fansly"]

    tab._on_message("busy", None)
    assert host.tabs.tabText(host.tabs.indexOf(tab)) == "● Fansly"
    tab._on_message("notify", {"title": "Scrape done", "message": "12 files"})
    assert notices == [("Fansly: Scrape done", "12 files")]
    tab._on_message("idle", None)
    assert host.tabs.tabText(host.tabs.indexOf(tab)) == "Fansly"
    host.deleteLater()


def test_host_without_running_sites_closes_at_once(qapp):
    from ofscraper.gui import site_host

    _, host_class = site_host._define_classes()
    host = host_class(initial="onlyfans", forwarded=[], onlyfans_config=None, embed=False)
    host.show()
    assert host.close()
    host.deleteLater()


def test_x11_is_preferred_on_linux_with_a_display(monkeypatch):
    from ofscraper.gui import site_host

    monkeypatch.setattr(site_host.platform, "system", lambda: "Linux")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setenv("DISPLAY", ":1")
    site_host.prefer_x11()
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


# --- links -----------------------------------------------------------------------------------------

def test_post_links_go_to_the_rows_site():
    assert site_context.post_url("123", "bob", "Timeline", site="onlyfans") == "https://onlyfans.com/123/bob"
    assert site_context.post_url("123", "", "Timeline", site="onlyfans") is None
    assert site_context.post_url("456", "bob", "Timeline", site="fansly") == "https://fansly.com/post/456"
    assert site_context.post_url("456", "bob", "Labels", site="fansly") == "https://fansly.com/post/456"
    assert site_context.post_url("456", "bob", "Messages", site="fansly") == "https://fansly.com/messages"
    assert site_context.post_url("", "bob", "Timeline", site="fansly") is None


def test_profile_links_go_to_the_site():
    assert site_context.profile_url("bob", site="fansly") == "https://fansly.com/bob"
    assert site_context.profile_url("bob", site="onlyfans") == "https://onlyfans.com/bob"


def test_table_opens_the_fansly_post(qapp, fansly, monkeypatch):
    from ofscraper.gui.widgets import data_table

    opened = []
    monkeypatch.setattr(data_table.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    table = SimpleNamespace(_display_data=[{"post_id": "9", "username": "bob", "responsetype": "Timeline"}])
    data_table.MediaDataTable._open_post(table, 0)
    assert opened == ["https://fansly.com/post/9"]


# --- walls --------------------------------------------------------------------------------------------

def test_walls_are_opt_in_on_fansly_only():
    assert not site_context.area_default("Labels", site="fansly")
    assert site_context.area_default("Timeline", site="fansly")
    assert site_context.area_default("Labels", site="onlyfans")


def test_area_page_leaves_walls_unticked(qapp, fansly, monkeypatch):
    from ofscraper.gui.pages import area_selector_page

    monkeypatch.setattr(area_selector_page.AreaSelectorPage, "_load_area_settings", lambda self: None)
    page = area_selector_page.AreaSelectorPage()
    assert not page._area_checks["Labels"].isChecked()
    assert page._area_checks["Timeline"].isChecked()


# --- save locations --------------------------------------------------------------------------------------

@pytest.fixture
def own_fansly_config(monkeypatch, tmp_path, fansly):
    import ofscraper.sites as sites
    import ofscraper.utils.paths.common as common_paths

    home = tmp_path / "ofscraper"
    monkeypatch.setattr(sites, "is_fansly", lambda: True)
    monkeypatch.setattr(sites, "current_site", lambda: sites.FANSLY)
    monkeypatch.setattr(site_context, "default_config_home", lambda: home)
    monkeypatch.setattr(common_paths, "get_config_path", lambda: home / "fansly" / "config.json")
    monkeypatch.setattr(common_paths, "get_config_home", lambda: home / "fansly")
    return home


def test_each_site_saves_under_its_own_folder_by_default(monkeypatch, tmp_path, own_fansly_config):
    import ofscraper.sites as sites
    import ofscraper.utils.of_env.of_env as of_env
    import ofscraper.utils.paths.common as common_paths

    root = tmp_path / "Data" / "ofscraper"
    real = of_env.getattr
    monkeypatch.setattr(of_env, "getattr", lambda k: str(root) if k == "SAVE_PATH_DEFAULT" else real(k))
    assert common_paths.get_save_location(config={"file_options": {}}) == str(root / "Fansly")
    assert common_paths.get_save_location(config=False) == str(root / "Fansly")

    # Fansly on a config it shares with OnlyFans: the bare root, + /Fansly later
    monkeypatch.setattr(common_paths, "get_config_path", lambda: own_fansly_config / "config.json")
    assert common_paths.get_save_location(config={"file_options": {}}) == str(root)

    monkeypatch.setattr(sites, "is_fansly", lambda: False)
    assert common_paths.get_save_location(config={"file_options": {}}) == str(root / "OnlyFans")
    # a save location in the config always wins
    assert common_paths.get_save_location(config={"file_options": {"save_location": "/x"}}) == "/x"


def test_fansly_files_go_to_its_save_location_as_is(monkeypatch, own_fansly_config):
    import ofscraper.classes.placeholder as placeholder
    import ofscraper.utils.paths.common as common_paths

    monkeypatch.setattr(common_paths, "get_save_location", lambda config=None: "/dl/Fansly")
    assert placeholder.site_save_location() == "/dl/Fansly"
    monkeypatch.setattr(common_paths, "get_config_path", lambda: own_fansly_config / "config.json")
    assert placeholder.site_save_location() == str(pathlib.Path("/dl/Fansly", "Fansly"))


def test_livestreams_follow_the_same_rule(monkeypatch, own_fansly_config):
    import datetime

    from ofscraper.sites.fansly import live

    when = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)
    assert live.recording_base("/dl/Fansly", "bob", when).parent == pathlib.Path("/dl/Fansly/bob/Livestreams")


def _write_config(path, save_location):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"config": {"file_options": {"save_location": save_location}}}))


def test_v426_fansly_save_location_keeps_its_folder(own_fansly_config):
    import ofscraper.utils.config.file as config_file

    config = own_fansly_config / "fansly" / "config.json"
    _write_config(config, "/dl/ofscraper")
    site_context.migrate_fansly_save_location()
    saved = json.loads(config.read_text())
    assert saved["file_options"]["save_location"] == str(pathlib.Path("/dl/ofscraper", "Fansly"))
    # once only: a later change by the user is left alone
    _write_config(config, "/elsewhere")
    config_file._cached_config = None
    site_context.migrate_fansly_save_location()
    assert json.loads(config.read_text())["config"]["file_options"]["save_location"] == "/elsewhere"


def test_new_fansly_config_is_not_moved(own_fansly_config):
    config = own_fansly_config / "fansly" / "config.json"
    _write_config(config, "/dl/ofscraper/Fansly")
    site_context.migrate_fansly_save_location()
    assert json.loads(config.read_text())["config"]["file_options"]["save_location"] == "/dl/ofscraper/Fansly"


# --- Fansly CDN refusals ------------------------------------------------------------------------------------

def _forbidden(url):
    import aiohttp
    from yarl import URL

    info = aiohttp.RequestInfo(URL(url), "GET", {}, URL(url))
    return aiohttp.ClientResponseError(info, (), status=403)


def test_fansly_cdn_403_is_not_retried():
    from ofscraper.managers.sessionmanager.sessionmanager import is_signed_cdn_forbidden

    assert is_signed_cdn_forbidden(_forbidden("https://cdn3.fansly.com/new/1/2/audio/aac/und/segment-0.aac"))
    assert not is_signed_cdn_forbidden(_forbidden("https://apiv3.fansly.com/api/v1/account/me"))


def test_refused_stream_file_fails_at_once(monkeypatch, tmp_path):
    import asyncio

    from ofscraper.commands.scraper.actions.download.managers import fansly_stream_download as sd

    calls = []

    async def refuse(self, c, url, path, cookies):
        calls.append(url)
        raise _forbidden(url)

    monkeypatch.setattr(sd.FanslyStreamDownloadManager, "_fetch_segment_once", refuse)
    url = "https://cdn3.fansly.com/new/1/2/audio/aac/und/segment-0.aac"
    with pytest.raises(sd.SegmentError) as err:
        asyncio.run(sd.FanslyStreamDownloadManager()._fetch_segment(None, url, tmp_path / "a0.aac", {}))
    assert err.value.forbidden and err.value.no_retry
    assert len(calls) == 1


# --- embedding and logs -------------------------------------------------------------------------------------

def test_embedded_window_is_only_resized_by_hand_on_windows(monkeypatch):
    from ofscraper.gui import site_host

    monkeypatch.setattr(site_host.platform, "system", lambda: "Linux")
    assert site_host.fit_foreign_window(123, 456) is False


def test_logger_reset_has_its_helpers():
    import ofscraper.utils.logs.logger as logger

    assert hasattr(logger, "other_logs")


def test_default_save_folder_never_builds_the_settings(monkeypatch, tmp_path):
    """A new config.json is written while the settings are being set up; asking
    for them then would wait forever on their lock."""
    import ofscraper.utils.paths.common as common_paths
    import ofscraper.utils.settings as settings

    monkeypatch.setattr(settings, "settings", {})
    monkeypatch.setattr(settings, "get_settings", lambda: pytest.fail("settings were built"))
    monkeypatch.setattr(site_context, "default_config_home", lambda: tmp_path)
    monkeypatch.setattr(common_paths, "get_config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(settings, "get_args", lambda: SimpleNamespace(site=None))
    assert site_context.default_save_folder() == "OnlyFans"
    monkeypatch.setattr(settings, "get_args", lambda: SimpleNamespace(site="fansly"))
    assert site_context.default_save_folder() is None
    monkeypatch.setattr(common_paths, "get_config_path", lambda: tmp_path / "fansly" / "config.json")
    assert site_context.default_save_folder() == "Fansly"


def test_embedded_site_window_has_no_frame():
    """The site window drops its frame when the tab window embeds it."""
    import inspect

    from ofscraper.gui import app

    src = inspect.getsource(app.launch_gui)
    assert "site_context.is_embedded()" in src
    assert src.index("FramelessWindowHint") < src.index("window.show()")
