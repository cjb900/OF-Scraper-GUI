import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import importlib  # noqa: E402
import importlib.util  # noqa: E402
import struct  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

pytestmark = pytest.mark.unit

pytest.importorskip("PyQt6.QtCore")

PLUGIN_DIR = Path(__file__).resolve().parents[3] / "Available Plugins" / "live_stream_monitor"
if not PLUGIN_DIR.is_dir():
    pytest.skip("live_stream_monitor plugin not in this checkout", allow_module_level=True)


def _load(name):
    """Import a plugin module as the ``live_stream_monitor`` package (relative imports work)."""
    if "live_stream_monitor" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "live_stream_monitor",
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        pkg = importlib.util.module_from_spec(spec)
        sys.modules["live_stream_monitor"] = pkg
        spec.loader.exec_module(pkg)
    return importlib.import_module(f"live_stream_monitor.{name}")


lsm = _load("main")
probe = _load("live_probe")
api = _load("of_live_api")


# ── WebM helpers ──────────────────────────────────────────────────────────────

def _cluster(ts_ms: int) -> bytes:
    # Cluster ID, unknown size (as Chrome writes it), Timestamp element (E7, 4 bytes)
    return b"\x1F\x43\xB6\x75" + b"\x01" + b"\xFF" * 7 + b"\xE7\x84" + ts_ms.to_bytes(4, "big")


def _webm(cluster_times, payload=b"\x00" * 64) -> bytes:
    ebml = b"\x1A\x45\xDF\xA3\x84" + b"webm"
    seg_info_content = b"\x2A\xD7\xB1\x83\x0F\x42\x40"  # TimestampScale = 1,000,000
    seg_info = b"\x15\x49\xA9\x66" + bytes([0x80 | len(seg_info_content)]) + seg_info_content
    segment = b"\x18\x53\x80\x67" + b"\x01" + b"\xFF" * 7
    tracks = b"\x16\x54\xAE\x6B\x80"
    clusters = b"".join(_cluster(t) + payload for t in cluster_times)
    return ebml + segment + seg_info + tracks + clusters


def _duration_in(data: bytes):
    i = data.find(b"\x44\x89\x88")
    return None if i == -1 else struct.unpack(">d", data[i + 3:i + 11])[0]


@pytest.fixture
def no_whole_file_reads(monkeypatch):
    """Fail if anything loads a recording with Path.read_bytes()."""
    def boom(self):
        raise AssertionError(f"whole-file read of {self}")
    monkeypatch.setattr(Path, "read_bytes", boom)


def test_last_cluster_is_read_from_the_end_of_the_file(tmp_path, no_whole_file_reads):
    f = tmp_path / "rec.webm"
    f.write_bytes(_webm([0, 5000, 10000, 15000]))
    assert lsm._read_webm_last_cluster_ms(f) == 15000.0


def test_last_cluster_falls_back_to_a_chunked_scan(tmp_path, monkeypatch, no_whole_file_reads):
    # Tail too small to hold a cluster, chunks too small to hold a whole one:
    # the scan must still find the last timestamp across chunk boundaries.
    f = tmp_path / "rec.webm"
    f.write_bytes(_webm([1000, 2000, 3000], payload=b"\x00" * 50) + b"\x00" * 40)
    monkeypatch.setattr(lsm, "_WEBM_TAIL_BYTES", 8)
    monkeypatch.setattr(lsm, "_WEBM_SCAN_CHUNK", 7)
    assert lsm._read_webm_last_cluster_ms(f) == 3000.0


def test_duration_is_inserted_without_touching_the_media(tmp_path, no_whole_file_reads):
    original = _webm([0, 5000, 10000])
    f = tmp_path / "rec.webm"
    f.write_bytes(original)
    assert lsm._patch_webm_duration(f, 12000.0) is True
    with open(f, "rb") as fh:
        patched = fh.read()
    assert _duration_in(patched) == 12000.0
    assert len(patched) == len(original) + 11
    # everything after Segment Info (tracks + clusters) is byte-identical
    tracks_at = original.find(b"\x16\x54\xAE\x6B")
    assert patched.endswith(original[tracks_at:])
    assert not (tmp_path / "rec.tmp.webm").exists()


def test_existing_duration_is_overwritten_in_place(tmp_path, no_whole_file_reads):
    f = tmp_path / "rec.webm"
    f.write_bytes(_webm([0, 5000]))
    lsm._patch_webm_duration(f, 1000.0)
    size = f.stat().st_size
    lsm._patch_webm_duration(f, 7000.0)
    with open(f, "rb") as fh:
        data = fh.read()
    assert f.stat().st_size == size
    assert _duration_in(data) == 7000.0


# ── Sandbox / launch ──────────────────────────────────────────────────────────

def test_sandbox_stays_on_for_a_normal_desktop(monkeypatch, tmp_path):
    monkeypatch.setattr(lsm, "_needs_no_sandbox", lambda: False)
    monkeypatch.setattr(lsm, "_chromium_channel_for_host", lambda: None)
    kw = lsm._capture_launch_kwargs(tmp_path, True, None)
    assert kw["chromium_sandbox"] is True
    assert "--no-sandbox" not in kw["args"]


def test_sandbox_is_off_only_where_chrome_cannot_use_it(monkeypatch, tmp_path):
    monkeypatch.setattr(lsm, "_needs_no_sandbox", lambda: True)
    monkeypatch.setattr(lsm, "_chromium_channel_for_host", lambda: None)
    kw = lsm._capture_launch_kwargs(tmp_path, False, None)
    assert kw["chromium_sandbox"] is False
    assert "--no-sandbox" in kw["args"]


FIREFOX_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:156.0) Gecko/20100101 Firefox/156.0"


def test_headless_has_no_window_and_uses_full_chrome(monkeypatch, tmp_path):
    monkeypatch.setattr(lsm, "_needs_no_sandbox", lambda: False)
    monkeypatch.setattr(lsm, "_chromium_channel_for_host", lambda: None)
    kw = lsm._capture_launch_kwargs(tmp_path, True, None, headless=True)
    assert kw["headless"] is True
    assert not any(a.startswith("--window-position") for a in kw["args"])
    # a Chrome channel = new headless mode, not Playwright's "headless shell"
    assert kw["channel"] == "chromium"
    windowed = lsm._capture_launch_kwargs(tmp_path, True, None)
    assert windowed["headless"] is False
    assert "--window-position=-20000,-20000" in windowed["args"]


def test_the_authentication_user_agent_is_always_used(monkeypatch, tmp_path):
    # OnlyFans ties sess to the UA it was made with, even a Firefox one.
    monkeypatch.setattr(lsm, "_needs_no_sandbox", lambda: False)
    monkeypatch.setattr(lsm, "_chromium_channel_for_host", lambda: None)
    kw = lsm._capture_launch_kwargs(tmp_path, False, FIREFOX_UA, headless=True)
    assert kw["user_agent"] == FIREFOX_UA
    assert "user_agent" not in lsm._capture_launch_kwargs(tmp_path, False, "  ")


def test_x_bc_goes_where_the_web_app_reads_it():
    script = lsm._session_init_script({"x-bc": "abc123"})
    assert "localStorage.setItem('bcTokenSha', \"abc123\")" in script
    assert "onlyfans.com" in script
    assert lsm._session_init_script({}) == ""


def test_each_capture_starts_with_a_clean_profile(tmp_path):
    prof = tmp_path / "playwright_profiles" / "creator"
    (prof / "Default").mkdir(parents=True)
    (prof / "Default" / "Cookies").write_text("old session")
    out = lsm._reset_profile(prof)
    assert out == prof and prof.is_dir() and not any(prof.iterdir())


def test_no_window_is_the_default_and_is_remembered(tmp_path):
    p = lsm.Plugin({"name": "x"}, str(tmp_path))
    assert p.no_window is True
    p.set_page_settings(no_window=False)
    assert lsm.Plugin({"name": "x"}, str(tmp_path)).no_window is False


def test_needs_no_sandbox_rules(monkeypatch):
    monkeypatch.setattr(lsm.sys, "platform", "win32")
    assert lsm._needs_no_sandbox() is False
    monkeypatch.setattr(lsm.sys, "platform", "linux")
    monkeypatch.setattr(lsm, "_in_container", lambda: False)
    monkeypatch.setattr(lsm.os, "geteuid", lambda: 1000, raising=False)
    assert lsm._needs_no_sandbox() is False
    monkeypatch.setattr(lsm.os, "geteuid", lambda: 0, raising=False)
    assert lsm._needs_no_sandbox() is True


def test_launch_retries_without_sandbox_only_when_it_cannot_start():
    calls = []

    class Chromium:
        def launch_persistent_context(self, **kw):
            calls.append(kw)
            if kw["chromium_sandbox"]:
                raise RuntimeError("No usable sandbox! ...")
            return "ctx"

    class P:
        chromium = Chromium()

    logs = []
    ctx = lsm._launch_capture_context(P(), {"chromium_sandbox": True, "args": []}, logs.append)
    assert ctx == "ctx" and len(calls) == 2
    assert calls[1]["chromium_sandbox"] is False and logs


def test_other_launch_errors_are_not_retried():
    class Chromium:
        def launch_persistent_context(self, **kw):
            raise RuntimeError("Executable doesn't exist")

    class P:
        chromium = Chromium()

    with pytest.raises(RuntimeError):
        lsm._launch_capture_context(P(), {"chromium_sandbox": True}, lambda m: None)


# ── FFmpeg ────────────────────────────────────────────────────────────────────

def test_ffmpeg_from_configuration_is_used(monkeypatch):
    import ofscraper.utils.system.ffmpeg as ff
    monkeypatch.setattr(ff, "get_ffmpeg", lambda: "/configured/ffmpeg")
    assert lsm._ffmpeg_binary() == "/configured/ffmpeg"


class _Sized:
    def __init__(self, size):
        self._size = size

    def stat(self):
        return type("St", (), {"st_size": self._size})()


def test_remux_timeout_grows_with_the_file():
    assert lsm._remux_timeout(_Sized(1)) == 300
    assert lsm._remux_timeout(_Sized(6 * 1024**3)) > 300


# ── Auth errors / URLs ────────────────────────────────────────────────────────

class _StatusError(Exception):
    def __init__(self, status):
        super().__init__("request failed")
        self.status = status


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_StatusError(401), True),
        (_StatusError(403), True),
        (_StatusError(500), False),
        (Exception("Auth fields not configured: sess"), True),
        (Exception("HTTP status 403 Forbidden"), True),
        (Exception("Read timed out after 400 ms"), False),
        (Exception("model 140032 not found"), False),
    ],
)
def test_auth_errors_are_matched_on_status_codes(exc, expected):
    assert lsm._is_auth_error(exc) is expected


def test_auth_error_is_found_in_the_exception_chain():
    try:
        try:
            raise _StatusError(401)
        except Exception:
            raise Exception("OnlyFans returned unauthorized for this session")
    except Exception as wrapped:
        assert lsm._is_auth_error(wrapped) is True


@pytest.mark.parametrize(
    "url, ok",
    [
        ("https://onlyfans.com/Creator/live", True),
        ("https://onlyfans.com/creator/live/", True),
        ("https://onlyfans.com/?return_to=/creator/live", False),
        ("https://onlyfans.com/other/live", False),
    ],
)
def test_live_url_check(url, ok):
    assert lsm._url_is_live_stream(url, "creator") is ok


def test_api_urls_follow_the_api_path_setting(monkeypatch):
    import ofscraper.utils.of_env.of_env as of_env
    monkeypatch.setattr(of_env, "_configured_api_path", lambda: "/api3/v9")
    assert api._api("https://onlyfans.com/api2/v2/streams/1/look") == (
        "https://onlyfans.com/api3/v9/streams/1/look"
    )


def test_reports_hide_email_addresses():
    data = probe.redact_json({"email": "me@example.com", "bio": "write me@example.com", "id": 5})
    assert data["email"] == "[REDACTED]"
    assert "me@example.com" not in data["bio"]
    assert data["id"] == 5
    assert "a@b.co" not in probe.redact_text("x a@b.co y")


# ── Plugin sessions ───────────────────────────────────────────────────────────

@pytest.fixture
def plugin(tmp_path, monkeypatch):
    p = lsm.Plugin({"name": "Live Stream Monitor"}, str(tmp_path))
    monkeypatch.setattr(p, "_emit_log", lambda msg: None)
    return p


def _blocking_capture(plugin, monkeypatch, save_seconds=0.0):
    """Fake capture: runs until stopped, then takes *save_seconds* to save."""
    def fake_record(username, save_location, stop_event):
        try:
            stop_event.wait(10)
            time.sleep(save_seconds)
        finally:
            plugin._end_session(username)
    monkeypatch.setattr(plugin, "record_stream", fake_record)


def test_a_creator_gets_one_session_at_a_time(plugin, monkeypatch):
    _blocking_capture(plugin, monkeypatch)
    assert plugin.start_recording("creator", None) is True
    assert plugin.start_recording("creator", None) is False
    assert plugin.session_snapshot()["creator"][0] == "connecting"
    plugin.stop_all_captures()


def test_stop_monitor_does_not_block_the_gui(plugin, monkeypatch):
    _blocking_capture(plugin, monkeypatch, save_seconds=2)
    plugin.start_recording("creator", None)
    t0 = time.monotonic()
    plugin.stop_monitor()
    assert time.monotonic() - t0 < 1
    deadline = time.monotonic() + 5
    while plugin.session_snapshot() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert plugin.session_snapshot() == {}


def test_a_failed_start_gets_a_cooldown(plugin, monkeypatch):
    # Fails before recording starts (e.g. no playwright): no retry next poll.
    monkeypatch.setattr(lsm, "get_config_path", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    plugin.record_stream("creator", None, threading.Event())
    assert plugin._cooldown_left("creator") > 60
    assert plugin.session_snapshot() == {}


def test_a_user_stop_does_not_get_the_failure_cooldown(plugin, monkeypatch):
    monkeypatch.setattr(lsm, "get_config_path", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    stopped = threading.Event()
    stopped.set()
    plugin.record_stream("creator", None, stopped)
    assert plugin._cooldown_left("creator") <= 0


def test_stream_summary_skips_temp_and_counts_webm(plugin, tmp_path):
    d = tmp_path / "creator" / "Live_Streams"
    d.mkdir(parents=True)
    (d / "Live_Stream_a.webm").write_bytes(b"x" * 10)
    (d / "Live_Stream_a.tmp.webm").write_bytes(b"x")
    (d / "notes.txt").write_text("x")
    count, tip = plugin.stream_files_summary("creator", str(tmp_path))
    assert count == 1 and "Live_Stream_a.webm" in tip


def test_clearing_logins_refuses_while_capturing(plugin, monkeypatch, tmp_path):
    root = tmp_path / "profiles"
    (root / "creator").mkdir(parents=True)
    monkeypatch.setattr(plugin, "browser_profiles_dir", lambda: root)
    _blocking_capture(plugin, monkeypatch)
    plugin.start_recording("creator", None)
    with pytest.raises(RuntimeError):
        plugin.clear_browser_profiles()
    plugin.stop_monitor(wait_seconds=5)
    assert plugin.clear_browser_profiles() == 1
    assert not root.exists()


# ── GUI: the Chromium check never runs on the GUI thread ─────────────────────
# The widget itself needs a QApplication (another test may already have made a
# QCoreApplication), so the tab's methods run against a small stand-in.

class _Stub:
    def __getattr__(self, name):
        return lambda *a, **k: None


def _fake_tab(plugin, username="creator"):
    gui = _load("gui")
    from types import SimpleNamespace

    tab = SimpleNamespace(
        plugin=plugin,
        logs=[],
        checks=0,
        _pending_chromium_action=None,
        install_btn=_Stub(),
        browser_status_label=_Stub(),
        setup_details=_Stub(),
        manage_btn=_Stub(),
        headless_check=SimpleNamespace(isChecked=lambda: True),
    )
    tab.append_log = tab.logs.append
    tab._selected_username = lambda: username
    tab._capture_dir = lambda: "/captures"

    def start_background_check():
        tab.checks += 1

    tab._check_browser_status = start_background_check
    for name in ("_with_chromium", "_on_chromium_check_done", "_on_capture_selected"):
        method = getattr(gui.LiveMonitorTab, name)
        setattr(tab, name, lambda *a, _m=method: _m(tab, *a))
    return tab


def test_capture_waits_for_the_background_chromium_check(plugin, monkeypatch):
    started = []
    monkeypatch.setattr(plugin, "start_recording", lambda u, d: started.append((u, d)))
    monkeypatch.setattr(
        plugin, "check_chromium_installed",
        lambda: pytest.fail("Chromium check ran on the GUI thread"),
    )
    plugin.chromium_ready = None
    tab = _fake_tab(plugin)
    tab._on_capture_selected()
    assert tab.checks == 1 and started == []  # waiting for the background check
    tab._on_chromium_check_done(True)  # the check worker reports back
    assert started == [("creator", "/captures")]
    assert plugin.chromium_ready is True


def test_a_known_good_chromium_skips_the_check(plugin, monkeypatch):
    started = []
    monkeypatch.setattr(plugin, "start_recording", lambda u, d: started.append(u))
    plugin.chromium_ready = True
    tab = _fake_tab(plugin)
    tab._on_capture_selected()
    assert started == ["creator"] and tab.checks == 0


def test_the_check_worker_runs_off_the_calling_thread(plugin, monkeypatch):
    ran_on = []
    monkeypatch.setattr(
        plugin, "check_chromium_installed",
        lambda: ran_on.append(threading.get_ident()) or True,
    )
    worker = lsm.ChromiumCheckWorker(plugin)
    results = []
    from PyQt6.QtCore import Qt

    # no event loop here: deliver in the worker thread
    worker.completed.connect(results.append, Qt.ConnectionType.DirectConnection)
    worker.start()
    assert worker.wait(5000)
    assert ran_on and ran_on[0] != threading.get_ident()
    assert results == [True]



class _Button:
    def __init__(self):
        self.enabled = None

    def setEnabled(self, on):
        self.enabled = bool(on)


def _button_tab(plugin, username):
    gui = _load("gui")
    from types import SimpleNamespace

    names = ("capture_selected_btn", "probe_selected_btn", "fetch_api_btn",
             "stop_all_btn")
    tab = SimpleNamespace(plugin=plugin, **{n: _Button() for n in names})
    tab._selected_username = lambda: username
    gui.LiveMonitorTab._update_action_buttons(tab)
    return {n: getattr(tab, n).enabled for n in names}


def test_buttons_only_enable_when_they_can_act(plugin, monkeypatch):
    off = _button_tab(plugin, None)
    assert not any(off.values())

    idle = _button_tab(plugin, "creator")
    assert idle["capture_selected_btn"] and idle["probe_selected_btn"]
    assert not idle["stop_all_btn"]

    plugin.set_ignored("creator", True)
    assert not _button_tab(plugin, "creator")["capture_selected_btn"]
    plugin.set_ignored("creator", False)

    _blocking_capture(plugin, monkeypatch)
    plugin.start_recording("creator", None)
    busy = _button_tab(plugin, "creator")
    assert busy["stop_all_btn"]
    assert not busy["capture_selected_btn"]
    other = _button_tab(plugin, "someone_else")
    assert other["stop_all_btn"] and other["capture_selected_btn"]
    plugin.stop_monitor(wait_seconds=5)


def _header(plugin, statuses=None):
    gui = _load("gui")
    from types import SimpleNamespace

    label = SimpleNamespace(text="")
    label.setText = lambda t: setattr(label, "text", t)
    tab = SimpleNamespace(plugin=plugin, monitor_status_label=label,
                          _last_statuses=statuses or {})
    gui.LiveMonitorTab._update_monitor_status(tab)
    return label.text


def test_header_shows_whether_the_monitor_is_working(plugin):
    from types import SimpleNamespace

    assert _header(plugin) == "Monitor off"
    now = time.time()
    plugin.worker = SimpleNamespace(polling=False, last_poll_at=now - 5,
                                    last_poll_ok=True, next_poll_at=now + 30)
    text = _header(plugin, {"a": {"is_live": True}, "b": {"is_live": False}})
    assert "Last check" in text and "next in" in text and "1 live" in text
    assert "failed" not in text
    plugin.worker.last_poll_ok = False
    assert "failed" in _header(plugin)
    plugin.worker.polling = True
    assert _header(plugin).startswith("Checking")
    plugin.worker = None



def test_recording_size_follows_the_file_being_written(plugin, tmp_path):
    f = tmp_path / "rec.webm"
    f.write_bytes(b"x" * 2048)
    assert plugin.recording_size("creator") is None
    with plugin._state_lock:
        plugin._recording_files["creator"] = f
    assert plugin.recording_size("creator") == 2048
    plugin._end_session("creator")
    assert plugin.recording_size("creator") is None


def test_sizes_are_shown_in_mb_or_gb():
    gui = _load("gui")
    assert gui._format_size(850 * 1024 * 1024) == "850 MB"
    assert gui._format_size(3 * 1024 ** 3 // 2) == "1.50 GB"


def test_notifications_follow_the_setting_and_privacy_mode(plugin, monkeypatch):
    from ofscraper.gui.signals import app_signals
    import ofscraper.gui.utils.privacy_mode as pm

    sent = []

    def on_note(_title, message):
        sent.append(message)

    app_signals.show_notification.connect(on_note)
    try:
        plugin.notify = False
        plugin._notify("x", "creator")
        assert sent == []
        plugin.notify = True
        monkeypatch.setattr(pm, "_enabled", True)
        plugin._notify("x", "creator")
        assert sent and "creator" not in sent[0]
    finally:
        app_signals.show_notification.disconnect(on_note)


def test_opening_recordings_never_creates_folders(plugin, tmp_path):
    gui = _load("gui")
    from types import SimpleNamespace

    tab = SimpleNamespace(logs=[])
    tab.append_log = tab.logs.append
    tab._recordings_dir = lambda u: tmp_path / u / "Live_Streams"
    gui.LiveMonitorTab._open_recordings(tab, "creator")
    assert not (tmp_path / "creator").exists()
    assert "No recordings yet" in tab.logs[0]

def test_page_settings_survive_a_restart(tmp_path):
    p = lsm.Plugin({"name": "x"}, str(tmp_path))
    assert (p.poll_interval, p.capture_dir, p.auto_capture) == (60, "", False)
    p.set_page_settings(poll_interval=120, capture_dir="/caps", auto_capture=True)
    again = lsm.Plugin({"name": "x"}, str(tmp_path))
    assert (again.poll_interval, again.capture_dir, again.auto_capture) == (120, "/caps", True)


def test_a_bad_saved_interval_is_clamped(tmp_path):
    (tmp_path / "live_stream_settings.json").write_text('{"poll_interval": 1}')
    assert lsm.Plugin({"name": "x"}, str(tmp_path)).poll_interval == 10

# ── Poller ───────────────────────────────────────────────────────────────────

@pytest.fixture
def poll_env(monkeypatch):
    import ofscraper.data.api.me as me_api
    import ofscraper.data.models.utils.retriver as retriver
    import ofscraper.utils.auth.file as auth_file
    import ofscraper.utils.auth.request as auth_req

    calls = {"invalidate": 0, "me": 0, "models": 0}
    monkeypatch.setattr(
        auth_file, "read_auth",
        lambda *a, **k: {"sess": "s", "auth_id": "1", "user_agent": "ua", "x-bc": "x"},
    )
    monkeypatch.setattr(
        auth_req, "invalidate_auth_cache",
        lambda: calls.__setitem__("invalidate", calls["invalidate"] + 1),
    )

    def me():
        calls["me"] += 1
        return {"isAuth": True}

    monkeypatch.setattr(me_api, "scrape_user", me)
    models = {"result": []}

    async def get_models(all_main_models=False):
        calls["models"] += 1
        r = models["result"]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(retriver, "get_models", get_models)
    return calls, models


def _run_polls(plugin, polls):
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    seen = []

    def on_status(statuses):
        seen.append(statuses)
        if len(seen) >= polls:
            worker.running = False

    worker.status_updated.connect(on_status)
    auth_errors = []
    worker.auth_error.connect(lambda: auth_errors.append(True))
    # Safety stop: a broken worker must fail the test, not hang it.
    deadline = time.monotonic() + 5
    worker.log_msg.connect(
        lambda _m: setattr(worker, "running", worker.running and time.monotonic() < deadline)
    )
    worker.run()  # in this thread: signals are delivered directly
    return seen, auth_errors


def test_signing_rules_are_refreshed_on_the_first_poll_only(plugin, poll_env):
    calls, _models = poll_env
    seen, auth_errors = _run_polls(plugin, 3)
    assert len(seen) == 3 and not auth_errors
    assert calls["models"] == 3
    assert calls["invalidate"] == 1 and calls["me"] == 1


def test_the_poller_records_when_it_last_checked(plugin, poll_env):
    _calls, models = poll_env
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    worker.status_updated.connect(lambda _s: setattr(worker, "running", False))
    worker.run()
    assert worker.last_poll_ok is True and worker.polling is False
    assert worker.next_poll_at >= worker.last_poll_at

    models["result"] = Exception("Read timed out")
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    worker.log_msg.connect(
        lambda m: setattr(worker, "running", False) if "[Error]" in m else None
    )
    worker.run()
    assert worker.last_poll_ok is False


def test_a_401_pauses_the_monitor(plugin, poll_env):
    _calls, models = poll_env
    models["result"] = _StatusError(401)
    seen, auth_errors = _run_polls(plugin, 1)
    assert auth_errors == [True] and seen == []


def test_other_errors_keep_polling(plugin, poll_env):
    calls, models = poll_env
    models["result"] = Exception("Read timed out after 400 ms")
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    auth_errors = []
    worker.auth_error.connect(lambda: auth_errors.append(True))
    deadline = time.monotonic() + 5
    worker.log_msg.connect(
        lambda m: setattr(
            worker, "running", calls["models"] < 2 and time.monotonic() < deadline
        )
    )
    worker.run()
    assert calls["models"] >= 2 and not auth_errors


# ── Installing playwright follows how OF-Scraper was installed ───────────────

@pytest.mark.parametrize(
    "method, expected",
    [
        ("pipx", ["pipx"]),
        ("uv", ["uv"]),
        ("pip", ["pip", "pip-target"]),
    ],
)
def test_playwright_is_installed_with_the_same_tool(tmp_path, monkeypatch, method, expected):
    worker = lsm.ChromiumInstallWorker(tmp_path / "browsers", tmp_path / "deps")
    logs, used = [], []
    monkeypatch.setattr(worker, "_emit", logs.append)
    monkeypatch.setattr(lsm, "_inspect_playwright_install", lambda: (False, "not installed", None))
    monkeypatch.setattr(lsm, "_detect_ofscraper_install_method", lambda: method)
    for name, label in (
        ("_pipx_inject", "pipx"),
        ("_uv_install", "uv"),
        ("_pip_install_venv", "pip"),
        ("_pip_install_target", "pip-target"),
    ):
        monkeypatch.setattr(worker, name, lambda _l=label: used.append(_l) or False)
    assert worker._ensure_playwright_package() is False
    assert used == expected
    hint = {"pipx": "pipx inject", "uv": "uv pip install", "pip": "-m pip install"}[method]
    assert any(hint in line for line in logs)


@pytest.mark.parametrize(
    "exe, pipx_home, name",
    [
        ("/home/u/.local/share/pipx/venvs/ofscraper/bin/python", None, "ofscraper"),
        (r"C:\Users\u\pipx\venvs\ofscraper\Scripts\python.exe", None, "ofscraper"),
        ("/opt/tools/venvs/ofscraper/bin/python", "/opt/tools", "ofscraper"),
        ("/opt/venv/bin/python", None, None),
    ],
)
def test_pipx_app_name_from_the_python_path(monkeypatch, exe, pipx_home, name):
    if exe.startswith("C:") and not sys.platform.startswith("win"):
        exe = exe.replace("\\", "/")
    if pipx_home:
        monkeypatch.setenv("PIPX_HOME", pipx_home)
    else:
        monkeypatch.delenv("PIPX_HOME", raising=False)
    assert lsm._pipx_venv_name(exe) == name


def test_uv_install_adds_to_the_tool_env_without_reinstalling(tmp_path, monkeypatch):
    worker = lsm.ChromiumInstallWorker(tmp_path / "b", tmp_path / "d")
    monkeypatch.setattr(worker, "_emit", lambda m: None)
    monkeypatch.setattr(lsm, "_find_uv_binary", lambda: "/usr/bin/uv")
    cmds = []
    monkeypatch.setattr(lsm, "_popen_logged", lambda cmd, *a, **k: cmds.append(cmd) or 0)
    assert worker._uv_install() is True
    assert cmds[0][:3] == ["/usr/bin/uv", "pip", "install"]
    assert "--python" in cmds[0] and "tool" not in cmds[0]


@pytest.mark.parametrize("root", [False, True])
def test_system_libraries_are_only_installed_with_admin_rights(tmp_path, monkeypatch, root):
    # As a normal user install-deps runs sudo, which asks for a password in the
    # terminal behind the GUI: it must not run then.
    worker = lsm.ChromiumInstallWorker(tmp_path / "b", tmp_path / "d")
    logs, cmds = [], []
    monkeypatch.setattr(worker, "_emit", logs.append)
    monkeypatch.setattr(worker, "_ensure_playwright_package", lambda: True)
    monkeypatch.setattr(lsm, "_inspect_playwright_install", lambda: (True, "ok", None))
    monkeypatch.setattr(lsm.sys, "platform", "linux")
    monkeypatch.setattr(lsm, "_is_root", lambda: root)
    monkeypatch.setattr(lsm, "_chromium_channel_for_host", lambda: "chrome")
    monkeypatch.setattr(lsm, "_probe_chromium_launch", lambda **k: (True, "OK"))
    monkeypatch.setattr(lsm, "_popen_logged", lambda cmd, *a, **k: cmds.append(cmd) or 0)
    assert worker._run_install() is True
    ran_deps = any("install-deps" in c for cmd in cmds for c in cmd)
    assert ran_deps is root
    if not root:
        assert any("sudo" in line and "install-deps" in line for line in logs)


# ── Stream end while recording ───────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_recording_stops_after_two_not_live_answers():
    answers = iter([False, False])
    clock = _Clock()
    w = lsm._StreamEndWatch("creator", check=lambda u: next(answers), clock=clock)
    clock.t = 30; w.got_data()
    assert w.reason() is None  # not time to ask yet
    clock.t = 61; w.got_data()
    assert w.reason() is None  # first "not live": could be a blip
    clock.t = 122; w.got_data()
    assert "stream has ended" in w.reason()


def test_a_live_answer_or_failed_check_resets_the_count():
    answers = iter([False, True, False, None, False])
    clock = _Clock()
    w = lsm._StreamEndWatch("creator", check=lambda u: next(answers), clock=clock)
    for i in range(1, 6):
        clock.t = 61 * i; w.got_data()
        assert w.reason() is None


def test_recording_stops_when_no_data_arrives():
    clock = _Clock()
    w = lsm._StreamEndWatch("creator", check=lambda u: True, clock=clock)
    clock.t = 299
    assert w.reason() is None
    clock.t = 300
    assert "No new data" in w.reason()


def test_live_check_uses_the_active_stream_api(monkeypatch):
    monkeypatch.setattr(api, "fetch_active_stream", lambda u: None)
    assert lsm._stream_still_live("creator") is False
    monkeypatch.setattr(api, "fetch_active_stream", lambda u: {"isActive": True})
    assert lsm._stream_still_live("creator") is True
    monkeypatch.setattr(api, "fetch_active_stream", lambda u: (_ for _ in ()).throw(RuntimeError("net")))
    assert lsm._stream_still_live("creator") is None


def test_the_recording_loop_feeds_and_asks_the_end_watch():
    import inspect

    src = inspect.getsource(lsm.Plugin.record_stream)
    assert "end_watch = _StreamEndWatch(\n                    username, log=self._emit_log, debug=self.log.debug" in src
    # new chunks reset the no-data timer; every loop pass asks whether to stop
    flush = src.index("_chunk_file.flush()")
    assert src.index("end_watch.got_data()", flush) < src.index("end_watch.reason()")


def test_a_failed_live_check_is_logged_once():
    logs = []
    clock = _Clock()
    w = lsm._StreamEndWatch("creator", check=lambda u: None, clock=clock, log=logs.append)
    for i in range(1, 4):
        clock.t = 61 * i; w.got_data()
        assert w.reason() is None
    assert len(logs) == 1 and "Couldn't ask OnlyFans" in logs[0]


# ── The poller stops recordings whose stream has ended ───────────────────────

class _Model:
    def __init__(self, name, live):
        self.active = True
        self.name = name
        self.model = {"hasStream": live}
        self.expired_string = "2036-01-01"


@pytest.fixture
def recording(plugin, monkeypatch):
    """*plugin* with one recording session for "creator"; records stop calls."""
    stops = []
    session = {"creator": ("recording", 1.0)}
    monkeypatch.setattr(plugin, "session_snapshot", lambda: dict(session))
    monkeypatch.setattr(plugin, "stop_capture", lambda u: stops.append(u) or True)
    monkeypatch.setattr(plugin, "start_recording", lambda *a, **k: True)
    monkeypatch.setattr(plugin, "stream_files_summary", lambda *a, **k: (0, ""))
    return stops, session


def _watch(worker, answers, kind="recording"):
    return [worker._stop_ended_recording("creator", kind, live) for live in answers]


def test_a_recording_stops_after_two_not_live_polls(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    assert _watch(worker, [True, False, False]) == [False, False, True]
    assert stops == ["creator"]


def test_one_not_live_poll_is_a_blip(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    assert _watch(worker, [True, False, True, False, True]) == [False] * 5
    assert stops == []


def test_a_capture_never_seen_live_is_not_stopped(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    assert _watch(worker, [False, False, False]) == [False] * 3
    assert stops == []


def test_connecting_sessions_are_left_alone(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    assert _watch(worker, [True, False, False, False], kind="connecting") == [False] * 4
    assert stops == []


def test_the_watch_resets_when_the_session_ends(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    _watch(worker, [True, False])
    worker._stop_ended_recording("creator", None, False)  # session over
    assert _watch(worker, [False, False]) == [False, False]  # new manual capture
    assert stops == []


def test_polls_stop_a_recording_after_the_stream_ends(plugin, poll_env, recording, monkeypatch):
    """End to end through the poll loop: live, then two polls without hasStream."""
    _calls, models = poll_env
    stops, _ = recording
    answers = iter([True, False, False])
    seen = []
    worker = lsm.LiveMonitorWorker(plugin, 0, None)

    async def get_models(all_main_models=False):
        return [_Model("creator", next(answers))]

    import ofscraper.data.models.utils.retriver as retriver
    monkeypatch.setattr(retriver, "get_models", get_models)

    def on_status(statuses):
        seen.append(statuses["creator"]["status"])
        if len(seen) >= 3:
            worker.running = False

    worker.status_updated.connect(on_status)
    deadline = time.monotonic() + 5
    worker.log_msg.connect(
        lambda _m: setattr(worker, "running", worker.running and time.monotonic() < deadline)
    )
    worker.run()
    assert stops == ["creator"]
    assert seen == ["Recording 🔴"] * 3  # until the capture thread has saved


# ── Discord @here when a creator goes live ───────────────────────────────────

@pytest.fixture
def discord(plugin, monkeypatch):
    """Webhook calls made by announce_live, collected synchronously."""
    sent, logs = [], []
    monkeypatch.setattr(plugin, "_emit_log", logs.append)
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "https://discord.test/hook")

    class _NowThread:
        def __init__(self, target, args=(), daemon=None):
            self._run = lambda: target(*args)

        def start(self):
            self._run()

    monkeypatch.setattr(lsm.threading, "Thread", _NowThread)
    monkeypatch.setattr(lsm, "_post_discord", lambda url, content, log, user, *what: sent.append((url, content, user)))
    return sent, logs


def test_discord_alert_is_off_by_default_and_needs_notifications(plugin, discord):
    sent, _ = discord
    assert plugin.discord_live_ping is False
    assert plugin.announce_live("creator") is False
    plugin.discord_live_ping = True
    plugin.notify = False
    assert plugin.announce_live("creator") is False
    plugin.notify = True
    assert plugin.announce_live("creator") is True
    assert sent == [("https://discord.test/hook", lsm._live_message("creator"), "creator")]


def test_a_missing_webhook_is_said_once(plugin, discord, monkeypatch):
    sent, logs = discord
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "")
    plugin.discord_live_ping = True
    assert plugin.announce_live("a") is False and plugin.announce_live("b") is False
    assert sent == [] and len(logs) == 1 and "Discord Webhook URL" in logs[0]


def test_the_alert_names_the_creator_and_links_the_stream():
    msg = lsm._live_message("katie_darling")
    assert msg.startswith("@here ")
    assert "**katie\\_darling**" in msg  # "_" would turn into italics
    assert "<https://onlyfans.com/katie_darling/live>" in msg


class _Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


def _fake_post(monkeypatch, responses):
    import httpx

    calls = []

    def post(url, json=None, timeout=None):
        calls.append(json)
        return responses.pop(0)

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(lsm.time, "sleep", lambda s: None)
    return calls


def test_webhook_post_lets_here_ping(monkeypatch):
    calls = _fake_post(monkeypatch, [_Resp(204)])
    logs = []
    assert lsm._post_discord("https://discord.test/secret", "@here hi", logs.append, "creator")
    assert calls == [{"content": "@here hi", "allowed_mentions": {"parse": ["everyone"]}}]
    assert logs == ["[Discord] Sent @here live alert for creator."]


def test_webhook_rate_limit_is_retried_once(monkeypatch):
    calls = _fake_post(monkeypatch, [_Resp(429, {"retry_after": 1.5}), _Resp(204)])
    assert lsm._post_discord("https://discord.test/secret", "x", None, "creator")
    assert len(calls) == 2


def test_webhook_failure_is_logged_without_the_url(monkeypatch):
    _fake_post(monkeypatch, [_Resp(404)])
    logs = []
    assert not lsm._post_discord("https://discord.test/secret", "x", logs.append, "creator")
    assert logs == ["[Discord] Live alert for creator failed: HTTP 404"]
    assert "secret" not in " ".join(logs)


def test_one_alert_per_go_live(plugin, poll_env, monkeypatch):
    """live, live, offline, live → two alerts; an ignored creator gets none."""
    announced = []
    monkeypatch.setattr(plugin, "announce_live", announced.append)
    monkeypatch.setattr(plugin, "start_recording", lambda *a, **k: False)
    monkeypatch.setattr(plugin, "stream_files_summary", lambda *a, **k: (0, ""))
    plugin.set_ignored("quiet", True)
    answers = iter([True, True, False, True])

    async def get_models(all_main_models=False):
        live = next(answers)
        return [_Model("creator", live), _Model("quiet", live)]

    import ofscraper.data.models.utils.retriver as retriver
    monkeypatch.setattr(retriver, "get_models", get_models)
    _run_polls(plugin, 4)
    assert announced == ["creator", "creator"]


def test_the_discord_option_is_remembered(tmp_path):
    p = lsm.Plugin({"name": "x"}, str(tmp_path))
    p.set_page_settings(discord_live_ping=True)
    assert lsm.Plugin({"name": "x"}, str(tmp_path)).discord_live_ping is True


def test_missing_webhook_only_matters_when_alerts_are_on(plugin, monkeypatch):
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "")
    assert not plugin.discord_alerts_missing_webhook()  # option off
    plugin.discord_live_ping = True
    assert plugin.discord_alerts_missing_webhook()
    plugin.notify = False
    assert not plugin.discord_alerts_missing_webhook()  # parent option off
    plugin.notify = True
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "https://discord.test/hook")
    assert not plugin.discord_alerts_missing_webhook()


class _FakeBox:
    shown = []

    class Icon:
        Warning = "warning"

    class StandardButton:
        Ok = "ok"

    def __init__(self, parent=None):
        self.visible = False
        self.texts = []
        self.modal = None

    def setIcon(self, _i): pass
    def setWindowTitle(self, t): self.texts.append(t)
    def setText(self, t): self.texts.append(t)
    def setInformativeText(self, t): self.texts.append(t)
    def setStandardButtons(self, _b): pass
    def setModal(self, m): self.modal = m
    def isVisible(self): return self.visible

    def show(self):
        self.visible = True
        _FakeBox.shown.append(self)


def _warning_tab(plugin, monkeypatch):
    gui = _load("gui")
    from types import SimpleNamespace

    _FakeBox.shown = []
    monkeypatch.setattr(gui, "QMessageBox", _FakeBox)
    tab = SimpleNamespace(plugin=plugin, logs=[], _discord_warning=None)
    tab.append_log = tab.logs.append
    return tab, lambda: gui.LiveMonitorTab._warn_if_no_discord_webhook(tab)


def test_no_webhook_pops_up_a_non_blocking_warning(plugin, monkeypatch):
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "")
    plugin.discord_live_ping = True
    tab, warn = _warning_tab(plugin, monkeypatch)
    assert warn() is True
    (box,) = _FakeBox.shown
    assert box.modal is False  # never holds up an unattended start
    text = " ".join(box.texts)
    assert "Configuration → General → Discord Webhook URL" in text
    assert plugin.discord_live_ping is True  # the option stays on
    assert any("No webhook set" in line for line in tab.logs)
    assert warn() is True and len(_FakeBox.shown) == 1  # an open warning is reused


def test_no_warning_once_a_webhook_is_set(plugin, monkeypatch):
    monkeypatch.setattr(lsm, "_discord_webhook_url", lambda: "https://discord.test/hook")
    plugin.discord_live_ping = True
    tab, warn = _warning_tab(plugin, monkeypatch)
    assert warn() is False and _FakeBox.shown == [] and tab.logs == []


def test_the_warning_is_checked_on_tick_and_on_monitor_start():
    import inspect

    gui = _load("gui")
    assert "_warn_if_no_discord_webhook()" in inspect.getsource(gui.LiveMonitorTab._on_discord_ping_toggled)
    assert "_warn_if_no_discord_webhook()" in inspect.getsource(gui.LiveMonitorTab._start_monitor_now)


# ── The page's "Live video has ended" message stops a recording quickly ──────

def _page_watch(answers):
    calls = []
    answers = list(answers)

    def check(u):
        calls.append(u)
        return answers.pop(0) if answers else answers_last[0]

    answers_last = [answers[-1] if answers else None]
    clock = _Clock()
    debug = []
    w = lsm._StreamEndWatch("creator", check=check, clock=clock, debug=debug.append)
    return w, clock, calls, debug


def test_end_message_confirmed_by_onlyfans_stops_at_once():
    w, clock, calls, debug = _page_watch([False])
    clock.t = 5; w.got_data(); w.page_shows_ended(True)
    assert "has ended and OnlyFans confirms it" in w.reason()
    assert calls == ["creator"]  # one API call, right away
    assert any("end message on page, OnlyFans live=False" in d for d in debug)


def test_end_message_while_onlyfans_says_live_keeps_recording():
    """The words could be in chat: never stop on the page text alone."""
    w, clock, calls, _ = _page_watch([True])
    for t in range(5, 125, 5):
        clock.t = t; w.got_data(); w.page_shows_ended(True)
        assert w.reason() is None
    # asked at most every 10 s while the message is up (+ the minute checks)
    assert len(calls) <= 12 + 2


def test_end_message_without_an_answer_stops_after_30_s():
    w, clock, _calls, _ = _page_watch([None])
    for t in (5, 10, 20, 30):
        clock.t = t; w.got_data(); w.page_shows_ended(True)
        assert w.reason() is None
    clock.t = 35; w.got_data(); w.page_shows_ended(True)
    assert "for 30 s (OnlyFans couldn't be asked)" in w.reason()


def test_end_message_going_away_resets():
    w, clock, _calls, debug = _page_watch([None])
    clock.t = 5; w.page_shows_ended(True); w.reason()
    clock.t = 20; w.page_shows_ended(False); w.got_data()
    clock.t = 40; w.page_shows_ended(True); w.got_data()
    assert w.reason() is None  # the 30 s start again
    assert any("end message gone" in d for d in debug)


def test_the_recording_loop_checks_the_page_each_pass():
    import inspect

    src = inspect.getsource(lsm.Plugin.record_stream)
    assert src.index("end_watch.page_shows_ended(page_ended)") < src.index("end_watch.reason()")
    assert "rec_page.evaluate(_PAGE_ENDED_JS)" in src


# ── Plugin log file ──────────────────────────────────────────────────────────

def test_the_plugin_logs_to_its_own_log_file_logger(plugin):
    # BasePlugin's logger is the one the plugin manager gives a log file.
    assert plugin.log.name == "ofscraper_plugin.Live Stream Monitor"


def test_console_lines_go_to_the_plugin_log(plugin, monkeypatch):
    gui = _load("gui")
    from types import SimpleNamespace

    written = []
    monkeypatch.setattr(plugin.log, "info", written.append)
    sb = SimpleNamespace(value=lambda: 0, maximum=lambda: 0, setValue=lambda v: None)
    out = SimpleNamespace(verticalScrollBar=lambda: sb, appendPlainText=lambda t: None)
    tab = SimpleNamespace(plugin=plugin, log_output=out)
    gui.LiveMonitorTab.append_log(tab, "[Monitor] Polling subscriptions status...\n")
    assert written == ["[Monitor] Polling subscriptions status..."]


def test_each_poll_writes_a_debug_line(plugin, poll_env, monkeypatch):
    lines = []
    monkeypatch.setattr(plugin.log, "debug", lines.append)
    monkeypatch.setattr(plugin, "start_recording", lambda *a, **k: False)
    monkeypatch.setattr(plugin, "stream_files_summary", lambda *a, **k: (0, ""))

    async def get_models(all_main_models=False):
        return [_Model("creator", True), _Model("other", False)]

    import ofscraper.data.models.utils.retriver as retriver
    monkeypatch.setattr(retriver, "get_models", get_models)
    _run_polls(plugin, 1)
    assert any(l.startswith("[Monitor] poll ok: 2 creators, live: creator;") for l in lines)


# ── Startup waits poll instead of sleeping ───────────────────────────────────

class _StopAt:
    """stop_event stand-in: advances the fake clock on wait(); set after *n* waits."""
    def __init__(self, clock, stop_after=None):
        self.clock, self.waits, self.stop_after = clock, 0, stop_after

    def wait(self, seconds):
        self.clock.t += seconds
        self.waits += 1
        return self.stop_after is not None and self.waits >= self.stop_after


def test_poll_returns_as_soon_as_it_is_ready():
    clock = _Clock()
    answers = iter(["", "", "non-dom-audio-play"])
    value, waited, stopped = lsm._poll_until(lambda: next(answers), bool, 8, 0.5, _StopAt(clock), clock)
    assert (value, waited, stopped) == ("non-dom-audio-play", 1.0, False)


def test_poll_gives_up_at_the_limit():
    clock = _Clock()
    value, waited, stopped = lsm._poll_until(lambda: "", bool, 8, 0.5, _StopAt(clock), clock)
    assert value == "" and waited == 8 and not stopped


def test_poll_stops_when_the_user_stops():
    clock = _Clock()
    value, waited, stopped = lsm._poll_until(lambda: "", bool, 8, 0.5, _StopAt(clock, stop_after=2), clock)
    assert stopped and waited == 1.0


def test_poll_treats_probe_errors_as_not_ready():
    clock = _Clock()
    calls = []

    def probe():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("Execution context was destroyed")
        return 2

    value, _w, _s = lsm._poll_until(probe, lambda s: s == 2, 60, 1, _StopAt(clock), clock)
    assert value == 2 and len(calls) == 2


def test_no_fixed_startup_sleeps_are_left():
    import inspect

    src = inspect.getsource(lsm.Plugin.record_stream)
    assert "Waiting 8 s" not in src and "range(12)" not in src
    assert "_PLAYER_STATE_JS" in src and "_AUDIO_SOURCE_JS" in src
    # audio is waited for after the player, before the recorder starts
    assert src.index("_PLAYER_STATE_JS") < src.index("_AUDIO_SOURCE_JS") < src.index("new MediaRecorder")
    after_join = src[src.index("join_btn.first.click()"):src.index("Joined the live stream")]
    assert "wait_for_timeout(1000)" in after_join  # was a fixed 3 s


def test_the_login_check_polls_instead_of_waiting_5_s():
    import inspect

    src = inspect.getsource(lsm.Plugin.record_stream)
    before_check = src[src.index("rec_page.goto(live_url"):src.index("Auth check URL")]
    assert "wait_for_timeout(5000)" not in before_check
    assert "_LIVE_PAGE_STATE_JS" in before_check and "_poll_until(" in before_check
    assert lsm._LIVE_PAGE_WAIT_SECONDS == 5  # the old fixed wait is the limit



# ── Discord @here when a stream ends ─────────────────────────────────────────

def test_end_alert_text():
    assert lsm._ended_message("katie_darling") == "@here ⚫ **katie\\_darling** has ended their live stream."
    msg = lsm._ended_message("creator", (3725, 1536 * 1024 * 1024))
    assert msg.endswith("Recorded 1:02:05 (1.50 GB).")
    assert lsm._ended_message("creator", (65, 50 * 1024 * 1024)).endswith("Recorded 1:05 (50 MB).")


def test_end_alert_follows_a_live_alert_once(plugin, discord):
    sent, _ = discord
    plugin.discord_live_ping = plugin.discord_end_ping = True
    assert plugin.announce_ended("creator") is False  # never announced live
    assert plugin.announce_live("creator") is True
    assert plugin.announce_ended("creator", (60, 1024 * 1024)) is True
    assert plugin.announce_ended("creator") is False  # once per stream
    assert [s[1].split()[1] for s in sent] == ["🔴", "⚫"]
    assert "Recorded 1:00 (1 MB)." in sent[1][1]


def test_end_alert_needs_its_option_and_the_ones_above(plugin, discord):
    sent, _ = discord
    plugin.discord_live_ping = True
    plugin.announce_live("creator")
    assert plugin.announce_ended("creator") is False  # end option off
    assert not plugin.was_announced_live("creator")  # but the stream is done
    plugin.discord_end_ping = True
    plugin.notify = False
    plugin._live_announced.add("creator")
    assert plugin.announce_ended("creator") is False


def test_sender_names_which_alert(monkeypatch):
    _fake_post(monkeypatch, [_Resp(204), _Resp(500)])
    logs = []
    lsm._post_discord("u", "x", logs.append, "creator", "stream-ended alert")
    lsm._post_discord("u", "x", logs.append, "creator", "stream-ended alert")
    assert logs == ["[Discord] Sent @here stream-ended alert for creator.",
                    "[Discord] Stream-ended alert for creator failed: HTTP 500"]


def test_poller_announces_an_end_without_a_recording(plugin, monkeypatch):
    ended = []
    monkeypatch.setattr(plugin, "announce_ended", lambda u, r=None: ended.append(u) or True)
    plugin._live_announced.add("creator")
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    end = worker._announce_end_without_recording
    assert [end("creator", None, live) for live in (False, True, False, False)] == [False, False, False, True]
    assert ended == ["creator"]


def test_poller_leaves_the_end_alert_to_a_running_recording(plugin, monkeypatch):
    ended = []
    monkeypatch.setattr(plugin, "announce_ended", lambda u, r=None: ended.append(u) or True)
    plugin._live_announced.add("creator")
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    for _ in range(3):
        worker._announce_end_without_recording("creator", "recording", False)
    assert ended == []


def test_a_poller_stop_counts_as_the_stream_ending(plugin, recording):
    stops, _ = recording
    worker = lsm.LiveMonitorWorker(plugin, 0, None)
    _watch(worker, [True, False, False])
    assert stops == ["creator"]
    assert plugin.take_stopped_as_ended("creator") is True
    assert plugin.take_stopped_as_ended("creator") is False


def test_the_recording_sends_the_end_alert_only_when_the_stream_ended():
    import inspect

    src = inspect.getsource(lsm.Plugin.record_stream)
    assert src.count("stream_ended = True") == 3  # left /live, end check, poller stop
    save = src.index("[Capture] Stream saved")
    assert save < src.index("self.take_stopped_as_ended(username):") < src.index("self.announce_ended(username, recorded)")
    assert "if stream_ended and recording_started:" in src


def test_discord_options_enable_from_the_top_down():
    gui = _load("gui")
    from types import SimpleNamespace

    def box(checked):
        b = SimpleNamespace(checked=checked, enabled=None)
        b.isChecked = lambda: b.checked
        b.setEnabled = lambda on: setattr(b, "enabled", on)
        return b

    for notify, live, want_live, want_end in [
        (True, True, True, True), (True, False, True, False),
        (False, True, False, False), (False, False, False, False),
    ]:
        tab = SimpleNamespace(notify_check=box(notify), discord_ping_check=box(live),
                              discord_end_check=box(False))
        gui.LiveMonitorTab._update_discord_options(tab)
        assert (tab.discord_ping_check.enabled, tab.discord_end_check.enabled) == (want_live, want_end)


def test_the_end_option_is_remembered(tmp_path):
    p = lsm.Plugin({"name": "x"}, str(tmp_path))
    p.set_page_settings(discord_end_ping=True)
    assert lsm.Plugin({"name": "x"}, str(tmp_path)).discord_end_ping is True
