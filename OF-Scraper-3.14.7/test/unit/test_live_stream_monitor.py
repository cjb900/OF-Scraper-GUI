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
    assert "end_watch = _StreamEndWatch(username)" in src
    # new chunks reset the no-data timer; every loop pass asks whether to stop
    flush = src.index("_chunk_file.flush()")
    assert src.index("end_watch.got_data()", flush) < src.index("end_watch.reason()")
