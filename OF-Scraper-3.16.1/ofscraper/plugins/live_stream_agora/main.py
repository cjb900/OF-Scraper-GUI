#Enabled 0 / Disabled — deprecated; use live_stream_monitor (Playwright)
plugin_enabled = 0

"""Experimental Live Stream capture via native Agora RTC (no Playwright)."""

import datetime
import json
import logging
import threading
import time
import traceback
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from ofscraper.plugins.base import BasePlugin
from ofscraper.utils.paths.common import get_save_location

try:
    from .agora_recorder import AgoraSessionRecorder, sdk_available
    from .capture_backend import (
        backend_label,
        ensure_playwright_live_plugin,
        find_playwright_live_plugin,
        host_os,
        os_capture_summary,
        preferred_capture_backend,
        set_force_backend,
    )
    from .of_live_api import resolve_live_join
    from .sdk_install import describe_install_plan, install_agora_sdk
except ImportError:
    from agora_recorder import AgoraSessionRecorder, sdk_available  # type: ignore
    from capture_backend import (  # type: ignore
        backend_label,
        ensure_playwright_live_plugin,
        find_playwright_live_plugin,
        host_os,
        os_capture_summary,
        preferred_capture_backend,
        set_force_backend,
    )
    from of_live_api import resolve_live_join  # type: ignore
    from sdk_install import describe_install_plan, install_agora_sdk  # type: ignore


class _LogBridge(QObject):
    log_msg = pyqtSignal(str)


class SdkInstallWorker(QThread):
    """Install agora_python_server_sdk via uv / pipx / pip (matches ofscraper)."""

    log_msg = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def run(self):
        try:
            method, cmd, plan = describe_install_plan()
            self.log_msg.emit(f"[SDK] ofscraper install method: {method}")
            self.log_msg.emit(f"[SDK] {plan}")
            self.log_msg.emit(f"[SDK] Command: {' '.join(cmd)}")
            ok = install_agora_sdk(self.log_msg.emit)
            if ok:
                avail, detail = sdk_available()
                self.log_msg.emit(f"[SDK] Post-install check: {detail}")
                self.finished.emit(avail)
            else:
                self.finished.emit(False)
        except Exception as e:
            self.log_msg.emit(f"[SDK] Install worker error: {e}")
            self.finished.emit(False)


class LiveMonitorWorker(QThread):
    log_msg = pyqtSignal(str)
    status_updated = pyqtSignal(dict)
    auth_error = pyqtSignal()

    def __init__(self, plugin, interval, save_location):
        super().__init__()
        self.plugin = plugin
        self.interval = interval
        self.save_location = save_location
        self.running = True

    def run(self):
        backend = preferred_capture_backend()
        self.log_msg.emit(
            f"[System] Live monitor active ({host_os()} -> {backend_label(backend)})."
        )
        self.log_msg.emit(f"[System] {os_capture_summary()}")
        while self.running:
            try:
                self.log_msg.emit("[Monitor] Polling subscriptions…")
                models = self.fetch_models()
                model_statuses = {}
                pw = find_playwright_live_plugin() if backend == "playwright" else None
                for m in models:
                    if not m.active:
                        continue
                    username = m.name
                    is_live = bool(m.model.get("hasStream", False))
                    expired_date = m.expired_string or "Active"
                    status = "Offline"
                    pw_active = False
                    pw_connecting = False
                    if pw is not None:
                        try:
                            pw_active = username in getattr(pw, "active_recordings", {})
                            pw_connecting = username in getattr(
                                pw, "_connecting_recordings", {}
                            )
                        except Exception:
                            pass
                    if username in self.plugin.active_recordings or pw_active:
                        status = "Recording 🔴"
                    elif username in self.plugin._connecting or pw_connecting:
                        status = "Connecting 🟡"
                    elif is_live:
                        status = "Live 🟢"
                    model_statuses[username] = {
                        "username": username,
                        "subscription": expired_date,
                        "status": status,
                        "is_live": is_live,
                    }
                    already = (
                        username in self.plugin.active_recordings
                        or username in self.plugin._connecting
                        or pw_active
                        or pw_connecting
                    )
                    if is_live and not already:
                        if self.plugin.is_ignored(username):
                            self.log_msg.emit(
                                f"[Monitor] {username} live but ignored — skip."
                            )
                        else:
                            cool = float(
                                getattr(self.plugin, "_capture_cooldown", {}).get(
                                    username, 0
                                )
                                or 0
                            )
                            if cool > time.time():
                                model_statuses[username]["status"] = "Blocked ⚠"
                                continue
                            self.log_msg.emit(
                                f"[Live] {username} live — starting "
                                f"{backend_label(backend)} capture…"
                            )
                            started = self.plugin.start_capture(
                                username, self.save_location
                            )
                            if started:
                                model_statuses[username]["status"] = "Connecting 🟡"
                                # Refresh PW handle after possible auto-load
                                if backend == "playwright":
                                    pw = find_playwright_live_plugin()
                            else:
                                model_statuses[username]["status"] = "Blocked ⚠"
                self.status_updated.emit(model_statuses)
            except Exception as e:
                err = str(e)
                if any(
                    x in err
                    for x in (
                        "Auth fields not configured",
                        "Authentication validation failed",
                        "400",
                        "401",
                        "403",
                        "unauthorized",
                    )
                ):
                    self.log_msg.emit(f"\n[Error] {err}")
                    self.auth_error.emit()
                    break
                self.log_msg.emit(f"[Error] Monitor loop: {e}")
                self.log_msg.emit(traceback.format_exc())

            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)
        self.log_msg.emit("[System] Agora monitor worker stopped.")

    def fetch_models(self):
        """Same subscription poll path as Live Stream Monitor / Areas."""
        import asyncio
        import sys

        from ofscraper.data.models.utils.retriver import get_models
        from ofscraper.utils.auth.file import read_auth
        from ofscraper.utils.live import updater as live_updater

        auth_data = read_auth()
        required = ["sess", "auth_id", "user_agent", "x-bc"]
        missing = [k for k in required if not auth_data.get(k)]
        if missing:
            raise Exception(
                f"Auth fields not configured: {', '.join(missing)}. "
                "Fix Authentication tab first."
            )

        try:
            import ofscraper.utils.auth.request as auth_req

            if hasattr(auth_req, "invalidate_auth_cache"):
                auth_req.invalidate_auth_cache()
        except Exception:
            pass

        import ofscraper.data.api.me as me_api

        user_info = me_api.scrape_user()
        if not user_info or not user_info.get("isAuth"):
            raise Exception(
                "OnlyFans returned unauthorized (isAuth=false). Re-import cookies."
            )

        restores = []
        try:
            for attr in ("update_task", "update_activity", "update_activity_task"):
                obj = getattr(live_updater, "activity", None)
                if obj is None or not hasattr(obj, attr):
                    continue
                old = getattr(obj, attr)
                setattr(obj, attr, lambda *a, **k: None)
                restores.append((obj, attr, old))
        except Exception:
            pass
        try:
            from ofscraper.gui.utils.workflow import _install_gui_live_stubs

            _install_gui_live_stubs()
        except Exception:
            pass

        async def _do_fetch():
            return await get_models(all_main_models=False)

        if sys.platform == "win32":
            loop = asyncio.SelectorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(_do_fetch())
        finally:
            try:
                loop.close()
            except Exception:
                pass
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            for obj, attr, old in restores:
                try:
                    setattr(obj, attr, old)
                except Exception:
                    pass


class Plugin(BasePlugin):
    def __init__(self, metadata: dict, plugin_dir: str):
        super().__init__(metadata, plugin_dir)
        self.plugin_dir = Path(plugin_dir)
        self.gui = None
        self.worker = None
        self._connecting = {}
        self.active_recordings = {}
        # username -> unix time; avoid hammering start_capture every poll on failure
        self._capture_cooldown: dict = {}
        self.ignored_creators: set = set()
        self._load_ignored()
        self._log_bridge = _LogBridge()
        self.log = logging.getLogger("ofscraper_plugins")

    def on_load(self):
        backend = preferred_capture_backend()
        self.log.info(
            "Live Stream Agora loaded. OS=%s backend=%s. %s",
            host_os(),
            backend,
            os_capture_summary(),
        )

    def capture_backend(self) -> str:
        return preferred_capture_backend()

    def _main_window(self):
        try:
            if self.gui is not None:
                return getattr(self.gui, "main_window", None)
        except Exception:
            pass
        return None

    def start_capture(self, username, save_location=None) -> bool:
        """Start capture for *username*. Returns True if a session was started."""
        backend = preferred_capture_backend()
        if backend == "playwright":
            return self._start_playwright_capture(username, save_location)
        return self._start_agora_capture(username, save_location)

    def _start_playwright_capture(self, username, save_location=None) -> bool:
        """Windows path: auto-load Live Stream Monitor if needed, then delegate."""
        now = time.time()
        cool_until = float(self._capture_cooldown.get(username) or 0)
        if cool_until > now:
            return False

        if username in self._connecting or username in self.active_recordings:
            self._emit_log(f"[Capture] {username} already active — skip.")
            return True

        mw = self._main_window()
        pw, msg = ensure_playwright_live_plugin(
            main_window=mw, log=self._emit_log
        )
        if pw is None:
            self._emit_log(f"[Capture] Playwright backend unavailable: {msg}")
            # Don't retry every poll — wait 5 minutes (or until user reloads plugin)
            self._capture_cooldown[username] = now + 300
            return False

        # Clear cooldown once we have a working bridge
        self._capture_cooldown.pop(username, None)

        if username in getattr(pw, "active_recordings", {}) or username in getattr(
            pw, "_connecting_recordings", {}
        ):
            self._emit_log(f"[Capture] {username} already active in Live Stream Monitor.")
            return True
        try:
            if hasattr(pw, "set_headless_capture") and self.gui is not None:
                hide = getattr(self.gui, "headless_check", None)
                if hide is not None:
                    pw.set_headless_capture(hide.isChecked())
        except Exception:
            pass
        self._emit_log(
            f"[Capture] Delegating to Live Stream Monitor (Playwright) for {username}…"
        )
        try:
            pw.start_recording(username, save_location or get_save_location())
            return True
        except Exception as e:
            self._emit_log(f"[Capture] Playwright start_recording failed: {e}")
            self._capture_cooldown[username] = now + 120
            return False

    def _start_agora_capture(self, username, save_location=None) -> bool:
        if username in self._connecting or username in self.active_recordings:
            self._emit_log(f"[Capture] {username} already active — skip.")
            return True
        stop_event = threading.Event()
        t = threading.Thread(
            target=self.capture_stream,
            args=(username, save_location, stop_event),
            daemon=True,
        )
        self._connecting[username] = (t, stop_event, None)
        t.start()
        return True
    def _emit_log(self, msg: str) -> None:
        try:
            self._log_bridge.log_msg.emit(str(msg))
        except Exception:
            try:
                if self.gui is not None:
                    self.gui.append_log(str(msg))
            except Exception:
                pass

    def _ignored_path(self) -> Path:
        return self.plugin_dir / "agora_live_ignored.json"

    def _load_ignored(self):
        try:
            data = json.loads(self._ignored_path().read_text(encoding="utf-8"))
            self.ignored_creators = set(data.get("ignored", []))
        except Exception:
            self.ignored_creators = set()

    def _save_ignored(self):
        try:
            self._ignored_path().write_text(
                json.dumps({"ignored": sorted(self.ignored_creators)}, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def is_ignored(self, username: str) -> bool:
        return username in self.ignored_creators

    def set_ignored(self, username: str, ignored: bool):
        if ignored:
            self.ignored_creators.add(username)
        else:
            self.ignored_creators.discard(username)
        self._save_ignored()

    def attempts_dir(self) -> Path:
        p = self.plugin_dir / "agora_attempts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def on_ui_setup(self, main_window):
        from .gui import AgoraLiveTab
        from ofscraper.gui.widgets.styled_button import NavButton

        self.gui = AgoraLiveTab(main_window, self)
        self._page_id = "live_monitor_agora"
        try:
            self._log_bridge.log_msg.disconnect()
        except Exception:
            pass
        self._log_bridge.log_msg.connect(self.gui.append_log)

        self.btn = NavButton("📡 Live Agora")
        main_window._nav_buttons["live_monitor_agora"] = self.btn
        main_window._nav_group.addButton(self.btn)
        layout = main_window._nav_frame.layout()
        theme_btn = getattr(main_window, "_theme_btn", None)
        theme_idx = layout.indexOf(theme_btn) if theme_btn is not None else -1
        if theme_idx >= 0:
            layout.insertWidget(theme_idx, self.btn)
        else:
            help_btn = main_window._nav_buttons.get("help")
            if help_btn:
                layout.insertWidget(layout.indexOf(help_btn), self.btn)
            else:
                layout.addWidget(self.btn)
        self.btn.clicked.connect(
            lambda checked: main_window._navigate("live_monitor_agora")
        )
        main_window._add_page("live_monitor_agora", self.gui)
        self._emit_log(f"[System] {os_capture_summary()}")
        backend = preferred_capture_backend()
        if backend == "agora":
            ok, detail = sdk_available()
            self._emit_log(f"[SDK] {'OK' if ok else 'Unavailable'}: {detail}")
            try:
                method, cmd, plan = describe_install_plan()
                self._emit_log(f"[SDK] Install plan ({method}): {plan}")
                self._emit_log(f"[SDK] Would run: {' '.join(cmd)}")
            except Exception:
                pass
        else:
            pw = find_playwright_live_plugin()
            if pw is None:
                self._emit_log(
                    "[System] Playwright backend selected — load Live Stream Monitor "
                    "plugin to capture on this OS."
                )
            else:
                self._emit_log(
                    "[System] Playwright backend ready (Live Stream Monitor is loaded)."
                )

    def install_sdk(self, log_sink=None, finished_cb=None):
        """Start background install into ofscraper's uv/pipx/pip environment."""
        self._sdk_install_worker = SdkInstallWorker()
        sink = log_sink or self._emit_log
        self._sdk_install_worker.log_msg.connect(sink)
        if finished_cb:
            self._sdk_install_worker.finished.connect(finished_cb)
        self._sdk_install_worker.start()

    def on_ui_teardown(self, main_window):
        try:
            self.stop_monitor()
        except Exception:
            pass
        try:
            if main_window is not None and hasattr(main_window, "_remove_page"):
                main_window._remove_page("live_monitor_agora")
        except Exception:
            pass
        self.btn = None
        self.gui = None

    def on_unload(self):
        self.stop_monitor()

    def start_monitor(self, interval, save_location):
        self.worker = LiveMonitorWorker(self, interval, save_location)
        self.worker.log_msg.connect(self.gui.append_log)
        self.worker.status_updated.connect(self.gui.update_status_table)
        self.worker.auth_error.connect(self.gui.handle_auth_error)
        self.worker.start()

    def stop_monitor(self, *, terminate_recordings: bool = True):
        if self.worker:
            self.worker.running = False
            self.worker.quit()
        if terminate_recordings:
            # Prefer per-user stop so Playwright + Agora both get signalled
            try:
                self.stop_all_captures()
            except Exception:
                pass
            sessions = {}
            sessions.update(self._connecting)
            sessions.update(self.active_recordings)
            for username, tup in list(sessions.items()):
                try:
                    tup[0].join(timeout=8)
                except Exception:
                    pass
            self._connecting.clear()
            self.active_recordings.clear()
        if self.worker:
            self.worker.wait(5000)
            self.worker = None

    def fetch_creds_only(self, username: str) -> dict:
        """Fetch + save redacted Agora creds without joining (works on Windows)."""
        self._emit_log(f"[API] Resolving live join for {username}…")
        info = resolve_live_join(username)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = self.attempts_dir() / f"creds_{username}_{stamp}.json"
        safe = {
            "username": username,
            "fetched_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "stream_id": info.get("stream_id"),
            "model_user_id": info.get("model_user_id"),
            "stream_type": info.get("stream_type"),
            "viewer_available_types": info.get("viewer_available_types"),
            "room": info.get("room"),
            "agora_summary": info.get("agora_summary"),
            "sdk": dict(zip(("available", "detail"), sdk_available())),
        }
        out.write_text(json.dumps(safe, indent=2), encoding="utf-8")
        self._emit_log(f"[API] Creds summary saved: {out}")
        self._emit_log(f"[API] agora_summary={info.get('agora_summary')}")
        # Inspect token claims (safe: no secrets dumped beyond lengths / uids)
        try:
            try:
                from .token_inspect import compare_join_to_token
            except ImportError:
                from token_inspect import compare_join_to_token  # type: ignore
            agora = info.get("agora") or {}
            for i, tok in enumerate(agora.get("token_candidates") or [agora.get("token")]):
                if not tok:
                    continue
                cmp = compare_join_to_token(
                    token=tok,
                    app_id=agora.get("app_id") or "",
                    channel=agora.get("channel") or "",
                    user_id=agora.get("user_id") or "",
                )
                self._emit_log(
                    f"[API] Token[{i}] claims: parse_ok={cmp.get('parse_ok')} "
                    f"tok_uid={cmp.get('uid')!r} tok_ch={cmp.get('channel')} "
                    f"wildcard={cmp.get('uid_is_wildcard')} "
                    f"mismatches={cmp.get('mismatches') or []}"
                )
        except Exception as e:
            self._emit_log(f"[API] Token inspect failed: {e}")
        return info

    def capture_stream(self, username, save_location, stop_event):
        recorder = None
        try:
            info = self.fetch_creds_only(username)
            agora = info["agora"]
            ok, detail = sdk_available()
            if not ok:
                self._emit_log(f"[Capture] Cannot join RTC on this host: {detail}")
                self._emit_log(
                    "[Capture] Falling back to Playwright (Live Stream Monitor)…"
                )
                self._connecting.pop(username, None)
                self.active_recordings.pop(username, None)
                if not self._start_playwright_capture(username, save_location):
                    self._emit_log(
                        "[Capture] Playwright fallback failed — ensure "
                        "live_stream_monitor is installed/enabled."
                    )
                return

            save_base = save_location or get_save_location()
            stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            out_dir = (
                Path(save_base) / username / "Live_Streams_Agora" / f"Agora_{stamp}"
            )
            out_dir.mkdir(parents=True, exist_ok=True)

            recorder = AgoraSessionRecorder(
                app_id=agora["app_id"],
                channel=agora["channel"],
                token=agora["token"],
                user_id=agora["user_id"],
                out_dir=out_dir,
                log=self._emit_log,
            )
            try:
                recorder.set_token_candidates(agora.get("token_candidates"))
            except Exception:
                pass
            # Promote to active (include start_time for UI duration timer)
            self._connecting.pop(username, None)
            start_time = datetime.datetime.now()
            self.active_recordings[username] = (
                threading.current_thread(),
                stop_event,
                recorder,
                start_time,
            )

            def _watch_stop():
                while not stop_event.is_set():
                    time.sleep(0.5)
                recorder.stop()

            threading.Thread(target=_watch_stop, daemon=True).start()

            # Mirror browser /streams/{id}/look heartbeat while capturing
            stream_id = info.get("stream_id")
            if stream_id is not None:
                def _look_heartbeat():
                    try:
                        from .of_live_api import post_stream_look
                    except ImportError:
                        from of_live_api import post_stream_look  # type: ignore
                    while not stop_event.is_set():
                        try:
                            post_stream_look(stream_id)
                            self._emit_log(f"[API] POST /streams/{stream_id}/look ok")
                        except Exception as e:
                            self._emit_log(f"[API] /look heartbeat failed: {e}")
                        for _ in range(60):
                            if stop_event.is_set():
                                return
                            time.sleep(1)

                threading.Thread(target=_look_heartbeat, daemon=True).start()

            stats = recorder.run(max_seconds=0)
            self._emit_log(f"[Capture] Finished {username}: {stats}")

            # OF rejects native Server SDK joins (reason 10) → Playwright fallback
            video_b = int((stats or {}).get("video_bytes") or 0)
            audio_b = int((stats or {}).get("audio_bytes") or 0)
            fail_reason = (stats or {}).get("conn_fail_reason")
            if (video_b <= 0 and audio_b <= 0) and not stop_event.is_set():
                self._emit_log(
                    "[Capture] Native Agora produced no media "
                    f"(conn_fail_reason={fail_reason}). "
                    "Falling back to Playwright…"
                )
                self.active_recordings.pop(username, None)
                self._connecting.pop(username, None)
                ok = self._start_playwright_capture(username, save_location)
                if not ok:
                    self._emit_log(
                        "[Capture] Playwright fallback failed — ensure "
                        "live_stream_monitor is installed/enabled."
                    )
        except Exception as e:
            self._emit_log(f"[Error] Capture failed for {username}: {e}")
            self._emit_log(traceback.format_exc())
        finally:
            self._connecting.pop(username, None)
            self.active_recordings.pop(username, None)

    def recording_start_time(self, username: str):
        """Return datetime when capture started, or None."""
        tup = self.active_recordings.get(username)
        if tup and len(tup) >= 4:
            return tup[3]
        # Playwright-delegated session
        pw = find_playwright_live_plugin()
        if pw is not None:
            at = getattr(pw, "active_recordings", {}).get(username)
            if at and len(at) >= 3:
                return at[2]
        return None

    def stop_capture(self, username: str) -> bool:
        """Stop one active/connecting capture (Agora or Playwright)."""
        username = (username or "").strip()
        if not username:
            return False
        stopped = False

        # Our Agora sessions
        for store_name in ("_connecting", "active_recordings"):
            store = getattr(self, store_name, {})
            if username not in store:
                continue
            tup = store[username]
            stop_event = tup[1]
            rec = tup[2] if len(tup) > 2 else None
            self._emit_log(f"[Capture] Stopping {username}…")
            try:
                stop_event.set()
            except Exception:
                pass
            if rec is not None and hasattr(rec, "stop"):
                try:
                    rec.stop()
                except Exception:
                    pass
            stopped = True

        # Playwright-delegated
        pw = find_playwright_live_plugin()
        if pw is not None:
            for attr in ("_connecting_recordings", "active_recordings"):
                store = getattr(pw, attr, {})
                if username not in store:
                    continue
                tup = store[username]
                stop_event = tup[1]
                self._emit_log(
                    f"[Capture] Stopping Playwright session for {username}…"
                )
                try:
                    stop_event.set()
                except Exception:
                    pass
                stopped = True

        if not stopped:
            self._emit_log(f"[Capture] No active session for {username}.")
        return stopped

    def stop_all_captures(self) -> int:
        """Stop every active Agora + Playwright capture. Returns count requested."""
        names = set(self._connecting) | set(self.active_recordings)
        pw = find_playwright_live_plugin()
        if pw is not None:
            names |= set(getattr(pw, "_connecting_recordings", {}) or {})
            names |= set(getattr(pw, "active_recordings", {}) or {})
        n = 0
        for u in sorted(names):
            if self.stop_capture(u):
                n += 1
        return n
