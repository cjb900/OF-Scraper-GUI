"""Native Agora RTC join + record (Linux/macOS via agora_python_server_sdk)."""

from __future__ import annotations

import platform
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

LogFn = Callable[[str], None]


def sdk_platform_supported() -> bool:
    return platform.system() in ("Linux", "Darwin")


def sdk_available() -> tuple[bool, str]:
    """Return (ok, detail)."""
    try:
        from .sdk_install import describe_install_plan, sdk_version_status
    except ImportError:
        from sdk_install import describe_install_plan, sdk_version_status  # type: ignore

    method, _cmd, plan = describe_install_plan()

    if not sdk_platform_supported():
        return (
            False,
            f"agora_python_server_sdk has no Windows native RTC libs "
            f"(ofscraper install method: {method}). "
            f"Install mapping still applies under WSL/Linux ({plan}).",
        )
    try:
        import agora.rtc.agora_service  # noqa: F401

        ver, ver_ok, ver_msg = sdk_version_status()
        detail = f"importable via {method}; {ver_msg}"
        if not ver_ok:
            # Still "available" so experimental path can run, but warn loudly.
            detail = f"WARN {detail}"
        return True, detail
    except Exception as e:
        return (
            False,
            f"agora_python_server_sdk not installed (ofscraper via {method}: {plan}). "
            f"Use Install SDK in this tab. ({e})",
        )


def _buffer_to_bytes(buf, length: int | None = None) -> bytes:
    """Copy Agora callback buffers (bytes / memoryview / ctypes / buffer protocol)."""
    if buf is None:
        return b""
    try:
        if length is not None and length > 0:
            return bytes(memoryview(buf)[:length])
    except Exception:
        pass
    try:
        if length is not None and length > 0:
            return bytes(buf[:length])
    except Exception:
        pass
    try:
        data = bytes(buf)
        if length is not None and length > 0:
            return data[:length]
        return data
    except Exception:
        return b""


class AgoraSessionRecorder:
    """
    Join an Agora live-broadcast channel as audience and write encoded A/V.

    Outputs (under out_dir):
      - video.h264 (or codec-dependent elementary stream)
      - audio.pcm  (s16le mono 16k — matches server-SDK receive examples)
      - optional muxed .mp4 via ffmpeg if available
    """

    def __init__(
        self,
        *,
        app_id: str,
        channel: str,
        token: str,
        user_id: int,
        out_dir: Path,
        log: LogFn | None = None,
    ):
        self.app_id = (app_id or "").strip()
        self.channel = (channel or "").strip()
        self.token = token or ""
        self.user_id = int(user_id)
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._log = log or (lambda m: None)
        self._stop = threading.Event()
        self._video_path = self.out_dir / "video.h264"
        self._audio_path = self.out_dir / "audio.pcm"
        self._bytes_video = 0
        self._bytes_audio = 0
        self._remote_users: set[str] = set()
        self._connected = False
        self._conn_err: str | None = None
        self._conn_fail_reason: int | None = None
        self._token_candidates: list[str] = []
        if token:
            self._token_candidates.append(str(token))

    def stop(self):
        self._stop.set()

    def set_token_candidates(self, tokens: list[str] | None):
        """Optional alternate RTC tokens (e.g. top-level OF ``Token``)."""
        seen: list[str] = []
        for t in tokens or []:
            s = str(t or "").strip()
            if s and s not in seen:
                seen.append(s)
        if self.token and self.token not in seen:
            seen.insert(0, self.token)
        elif not seen and self.token:
            seen = [self.token]
        self._token_candidates = seen
        if seen:
            self.token = seen[0]

    def run(self, max_seconds: int = 0) -> dict:
        """
        Blocking join/record until stop() or *max_seconds* (0 = until stop only).

        Returns stats dict.
        """
        ok, detail = sdk_available()
        if not ok:
            raise RuntimeError(detail)
        if not self.app_id:
            raise RuntimeError("Agora app_id is empty — cannot initialize SDK")
        if not self.channel:
            raise RuntimeError("Agora channel is empty — cannot connect")
        if not self.token:
            raise RuntimeError("Agora token is empty — cannot connect")

        from agora.rtc.agora_base import (
            AudioSubscriptionOptions,
            ChannelProfileType,
            ClientRoleType,
            RTCConnConfig,
            RtcConnectionPublishConfig,
            VideoStreamType,
            VideoSubscriptionOptions,
            AudioProfileType,
            AudioPublishType,
            VideoPublishType,
        )
        from agora.rtc.agora_service import AgoraService, AgoraServiceConfig
        from agora.rtc.video_encoded_frame_observer import IVideoEncodedFrameObserver
        from agora.rtc.audio_frame_observer import IAudioFrameObserver

        try:
            from agora.rtc.local_user_observer import IRTCConnectionObserver
        except Exception:
            try:
                from agora.rtc.rtc_connection_observer import IRTCConnectionObserver
            except Exception:
                IRTCConnectionObserver = object  # type: ignore

        # Scenario: prefer DEFAULT for live broadcast (OF web publisher).
        try:
            from agora.rtc.agora_base import AudioScenarioType

            _scenario = getattr(
                AudioScenarioType,
                "AUDIO_SCENARIO_DEFAULT",
                getattr(AudioScenarioType, "AUDIO_SCENARIO_CHORUS", None),
            )
        except Exception:
            _scenario = None

        # Publish-type "none" when available (receiver-only)
        try:
            _audio_pub = getattr(
                AudioPublishType,
                "AUDIO_PUBLISH_TYPE_NONE",
                getattr(AudioPublishType, "NO_PUBLISH", AudioPublishType.AUDIO_PUBLISH_TYPE_PCM),
            )
        except Exception:
            _audio_pub = AudioPublishType.AUDIO_PUBLISH_TYPE_PCM
        try:
            _video_pub = getattr(
                VideoPublishType,
                "VIDEO_PUBLISH_TYPE_NONE",
                getattr(VideoPublishType, "NO_PUBLISH", VideoPublishType.VIDEO_PUBLISH_TYPE_YUV),
            )
        except Exception:
            _video_pub = VideoPublishType.VIDEO_PUBLISH_TYPE_YUV

        self._log(
            f"[Agora] Joining channel={self.channel} uid={self.user_id} "
            f"app_id={self.app_id[:8]}… as audience"
        )

        # Inspect OF-issued token claims (no App Certificate required to *read*)
        try:
            from .token_inspect import compare_join_to_token
        except ImportError:
            from token_inspect import compare_join_to_token  # type: ignore
        try:
            from .sdk_install import sdk_version_status
        except ImportError:
            from sdk_install import sdk_version_status  # type: ignore
        try:
            _ver, _ver_ok, _ver_msg = sdk_version_status()
            self._log(f"[Agora] {_ver_msg}")
        except Exception:
            pass

        join_uid = str(self.user_id)
        for i, tok in enumerate(self._token_candidates or [self.token]):
            cmp = compare_join_to_token(
                token=tok,
                app_id=self.app_id,
                channel=self.channel,
                user_id=join_uid,
            )
            self._log(
                f"[Agora] Token[{i}] inspect: parse_ok={cmp.get('parse_ok')} "
                f"ver={cmp.get('version')} tok_app={cmp.get('app_id')} "
                f"tok_ch={cmp.get('channel')} tok_uid={cmp.get('uid')!r} "
                f"wildcard={cmp.get('uid_is_wildcard')} "
                f"expire={cmp.get('expire')} err={cmp.get('error')}"
            )
            for m in cmp.get("mismatches") or []:
                self._log(f"[Agora] Token[{i}] MISMATCH: {m}")
            # Align join uid to the token's bound uid when OF cred user_id differs
            rec = cmp.get("recommended_uid")
            if (
                i == 0
                and cmp.get("parse_ok")
                and rec
                and str(rec) != join_uid
                and not cmp.get("uid_is_wildcard")
            ):
                self._log(
                    f"[Agora] Aligning join uid {join_uid} → token uid {rec}"
                )
                join_uid = str(rec)
                try:
                    self.user_id = int(rec)
                except Exception:
                    pass
        self._join_uid_str = join_uid

        video_fp = open(self._video_path, "wb")
        audio_fp = open(self._audio_path, "wb")
        lock = threading.Lock()
        obs_err_logged = {"v": 0, "a": 0}

        class _ConnObs(IRTCConnectionObserver):  # type: ignore[misc,valid-type]
            def on_connected(self_inner, agora_rtc_conn, conn_info, reason):
                self._connected = True
                self._log(f"[Agora] on_connected reason={reason} info={conn_info}")

            def on_disconnected(self_inner, agora_rtc_conn, conn_info, reason):
                self._log(f"[Agora] on_disconnected reason={reason}")

            def on_connecting(self_inner, *a, **k):
                self._log("[Agora] on_connecting…")

            def on_connection_failure(self_inner, agora_rtc_conn, conn_info, reason):
                try:
                    from .capture_backend import agora_reason_name
                except ImportError:
                    from capture_backend import agora_reason_name  # type: ignore
                self._conn_fail_reason = int(reason) if reason is not None else None
                name = agora_reason_name(reason)
                self._conn_err = f"connection_failure reason={reason} ({name})"
                self._log(f"[Agora] {self._conn_err}")
                # Do not set _stop here — run() may retry an alternate token.

            def on_user_joined(self_inner, agora_rtc_conn, user_id):
                uid = str(user_id)
                self._remote_users.add(uid)
                self._log(f"[Agora] remote user joined: {uid}")

            def on_user_left(self_inner, agora_rtc_conn, user_id, reason):
                uid = str(user_id)
                self._remote_users.discard(uid)
                self._log(f"[Agora] remote user left: {uid} reason={reason}")

            def on_error(self_inner, agora_rtc_conn, error):
                self._conn_err = f"sdk_error={error}"
                self._log(f"[Agora] on_error: {error}")

            def on_token_privilege_will_expire(self_inner, *a, **k):
                self._log("[Agora] token will expire soon")

            def on_token_privilege_did_expire(self_inner, *a, **k):
                self._conn_err = "token_expired"
                self._log("[Agora] token expired")

        class _VideoObs(IVideoEncodedFrameObserver):
            def on_encoded_video_frame(
                self_inner, uid, image_buffer, length, video_encoded_frame_info
            ):
                try:
                    n = int(length or 0)
                    if n <= 0 or image_buffer is None:
                        return 1
                    data = _buffer_to_bytes(image_buffer, n)
                    if not data:
                        return 1
                    with lock:
                        video_fp.write(data)
                        self._bytes_video += len(data)
                except Exception as e:
                    if obs_err_logged["v"] < 3:
                        obs_err_logged["v"] += 1
                        self._log(f"[Agora] video observer error: {e}")
                return 1

        class _AudioObs(IAudioFrameObserver):
            def on_playback_audio_frame_before_mixing(
                self_inner,
                channel_id,
                uid,
                frame,
                *extra,
            ):
                try:
                    if frame is None:
                        return 1
                    buf = getattr(frame, "buffer", None)
                    bytes_per = getattr(frame, "bytes_per_sample", 2) or 2
                    samples = getattr(frame, "samples_per_channel", 0) or 0
                    ch = getattr(frame, "channels", 1) or 1
                    if not buf or samples <= 0:
                        return 1
                    n = int(samples) * int(ch) * int(bytes_per)
                    data = _buffer_to_bytes(buf, n)
                    if not data:
                        return 1
                    with lock:
                        audio_fp.write(data)
                        self._bytes_audio += len(data)
                except Exception as e:
                    if obs_err_logged["a"] < 3:
                        obs_err_logged["a"] += 1
                        self._log(f"[Agora] audio observer error: {e}")
                return 1

            def on_record_audio_frame(self_inner, *a, **k):
                return 1

            def on_mixed_audio_frame(self_inner, *a, **k):
                return 1

            def on_ear_monitoring_audio_frame(self_inner, *a, **k):
                return 1

            def on_playback_audio_frame(self_inner, *a, **k):
                return 1

            def on_get_audio_frame_position(self_inner, *a, **k):
                return 0

        sdk_log = self.out_dir / "agorasdk.log"
        serv_cfg = AgoraServiceConfig()
        # CRITICAL: appid was previously never set → join with empty App ID → 0B files
        serv_cfg.appid = self.app_id
        serv_cfg.enable_video = 1
        serv_cfg.enable_audio_processor = 1
        serv_cfg.enable_audio_device = 0
        try:
            serv_cfg.log_path = str(sdk_log)
            serv_cfg.log_size = 5 * 1024
        except Exception:
            pass
        if _scenario is not None:
            try:
                serv_cfg.audio_scenario = _scenario
            except Exception:
                pass
        try:
            serv_cfg.channel_profile = (
                ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING
            )
        except Exception:
            pass

        agora_service = AgoraService()
        init_ret = agora_service.initialize(serv_cfg)
        self._log(f"[Agora] service.initialize() returned {init_ret}")
        if init_ret not in (0, None):
            raise RuntimeError(f"AgoraService.initialize failed: {init_ret}")

        # Explicit subscribe (matches official ReceiverPcmH264 examples)
        sub_opt = AudioSubscriptionOptions(
            packet_only=0,
            pcm_data_only=1,
            bytes_per_sample=2,
            number_of_channels=1,
            sample_rate_hz=16000,
        )
        con_config = RTCConnConfig(
            auto_subscribe_audio=0,
            auto_subscribe_video=0,
            client_role_type=ClientRoleType.CLIENT_ROLE_AUDIENCE,
            channel_profile=ChannelProfileType.CHANNEL_PROFILE_LIVE_BROADCASTING,
            audio_recv_media_packet=0,
            audio_subs_options=sub_opt,
            enable_audio_recording_or_playout=0,
        )
        publish_kwargs = dict(
            audio_profile=AudioProfileType.AUDIO_PROFILE_DEFAULT,
            audio_publish_type=_audio_pub,
            video_publish_type=_video_pub,
            is_publish_audio=False,
            is_publish_video=False,
        )
        if _scenario is not None:
            publish_kwargs["audio_scenario"] = _scenario
        publish_config = RtcConnectionPublishConfig(**publish_kwargs)

        connection = None
        # Keep observer refs alive for the whole session (native callbacks)
        conn_obs = _ConnObs()
        v_obs = _VideoObs()
        a_obs = _AudioObs()

        try:
            connection = agora_service.create_rtc_connection(con_config, publish_config)
            if connection is None:
                raise RuntimeError("create_rtc_connection returned None")

            local_user = connection.get_local_user()

            try:
                r = connection.register_observer(conn_obs)
                self._log(f"[Agora] register_observer → {r}")
            except Exception as e:
                self._log(f"[Agora] register_observer failed: {e}")

            # Audio: set PCM format, subscribe, register observer (conn and/or local_user)
            try:
                r = local_user.set_playback_audio_frame_before_mixing_parameters(1, 16000)
                self._log(f"[Agora] set_playback_audio_frame_before_mixing_parameters → {r}")
            except Exception as e:
                self._log(f"[Agora] set_playback_audio_frame_before_mixing_parameters: {e}")

            try:
                r = local_user.subscribe_all_audio()
                self._log(f"[Agora] subscribe_all_audio → {r}")
            except Exception as e:
                self._log(f"[Agora] subscribe_all_audio: {e}")

            audio_reg_ok = False
            for label, target in (
                ("connection.register_audio_frame_observer", connection),
                ("local_user.register_audio_frame_observer", local_user),
            ):
                if audio_reg_ok:
                    break
                try:
                    fn = getattr(target, "register_audio_frame_observer", None)
                    if fn is None:
                        continue
                    # Some SDK builds take (observer), others (observer, enable_vad, vad_config)
                    try:
                        r = fn(a_obs)
                    except TypeError:
                        r = fn(a_obs, False, None)
                    self._log(f"[Agora] {label} → {r}")
                    audio_reg_ok = True
                except Exception as e:
                    self._log(f"[Agora] {label} failed: {e}")

            # Video: encoded-only subscription + observer
            try:
                vsub = VideoSubscriptionOptions(
                    type=VideoStreamType.VIDEO_STREAM_HIGH,
                    encodedFrameOnly=1,
                )
                r = local_user.subscribe_all_video(vsub)
                self._log(f"[Agora] subscribe_all_video(encoded) → {r}")
            except Exception as e:
                self._log(f"[Agora] subscribe_all_video: {e}")

            video_reg_ok = False
            for label, target, names in (
                (
                    "connection",
                    connection,
                    (
                        "register_video_encoded_frame_observer",
                        "set_encoded_video_frame_observer",
                        "register_encoded_video_frame_observer",
                    ),
                ),
                (
                    "local_user",
                    local_user,
                    (
                        "register_video_encoded_frame_observer",
                        "set_encoded_video_frame_observer",
                        "register_encoded_video_frame_observer",
                    ),
                ),
            ):
                if video_reg_ok:
                    break
                for name in names:
                    fn = getattr(target, name, None)
                    if fn is None:
                        continue
                    try:
                        r = fn(v_obs)
                        self._log(f"[Agora] {label}.{name} → {r}")
                        video_reg_ok = True
                        break
                    except Exception as e:
                        self._log(f"[Agora] {label}.{name} failed: {e}")

            if not video_reg_ok:
                self._log(
                    "[Agora] WARN: no encoded-video observer registered — "
                    "video.h264 will stay empty"
                )

            join_as = getattr(self, "_join_uid_str", None) or str(self.user_id)
            ret = connection.connect(self.token, self.channel, join_as)
            self._log(f"[Agora] connect() returned {ret} (uid={join_as})")
            if ret not in (0, None):
                raise RuntimeError(f"connection.connect failed with code {ret}")

            # If first token is rejected, try alternates once each
            started = time.time()
            last_report = started
            warned_empty = False
            token_idx = 0
            while not self._stop.is_set():
                if self._conn_fail_reason is not None:
                    if token_idx + 1 < len(self._token_candidates):
                        token_idx += 1
                        alt = self._token_candidates[token_idx]
                        self._log(
                            f"[Agora] Retrying connect with token candidate "
                            f"{token_idx + 1}/{len(self._token_candidates)} "
                            f"(len={len(alt)})…"
                        )
                        # Re-inspect alternate and realign uid if needed
                        try:
                            from .token_inspect import compare_join_to_token
                        except ImportError:
                            from token_inspect import compare_join_to_token  # type: ignore
                        cmp = compare_join_to_token(
                            token=alt,
                            app_id=self.app_id,
                            channel=self.channel,
                            user_id=join_as,
                        )
                        self._log(
                            f"[Agora] Token[{token_idx}] inspect: "
                            f"parse_ok={cmp.get('parse_ok')} "
                            f"tok_uid={cmp.get('uid')!r} "
                            f"mismatches={cmp.get('mismatches')}"
                        )
                        if (
                            cmp.get("parse_ok")
                            and cmp.get("recommended_uid")
                            and not cmp.get("uid_is_wildcard")
                        ):
                            join_as = str(cmp["recommended_uid"])
                        self._conn_fail_reason = None
                        self._conn_err = None
                        try:
                            connection.disconnect()
                        except Exception:
                            pass
                        time.sleep(0.3)
                        self.token = alt
                        ret = connection.connect(self.token, self.channel, join_as)
                        self._log(
                            f"[Agora] connect() retry returned {ret} (uid={join_as})"
                        )
                        if ret not in (0, None):
                            break
                        started = time.time()
                        last_report = started
                        continue

                    self._log(
                        "[Agora] Giving up — channel join rejected "
                        f"({self._conn_err}). Token claims matched join "
                        "args but OF still refused the Server SDK client "
                        "(typical: reason 10 REJECTED_BY_SERVER). Native "
                        "Agora capture is not viable for OF; use Playwright."
                    )
                    break

                if max_seconds and (time.time() - started) >= max_seconds:
                    self._log("[Agora] max_seconds reached — stopping.")
                    break
                now = time.time()
                if now - last_report >= 10:
                    self._log(
                        f"[Agora] receiving… video={self._bytes_video}B "
                        f"audio={self._bytes_audio}B "
                        f"connected={self._connected} "
                        f"remotes={sorted(self._remote_users) or '-'}"
                    )
                    if (
                        not warned_empty
                        and self._bytes_video == 0
                        and self._bytes_audio == 0
                        and (now - started) >= 20
                    ):
                        warned_empty = True
                        hint = self._conn_err or "no A/V frames yet"
                        self._log(
                            f"[Agora] WARN: still 0B after 20s ({hint}). "
                            f"SDK log: {sdk_log}"
                        )
                    last_report = now
                time.sleep(0.5)

            try:
                connection.disconnect()
            except Exception:
                pass
        finally:
            try:
                if connection is not None:
                    connection.release()
            except Exception:
                pass
            try:
                agora_service.release()
            except Exception:
                pass
            try:
                video_fp.close()
            except Exception:
                pass
            try:
                audio_fp.close()
            except Exception:
                pass

        mp4 = self._try_mux()
        stats = {
            "video_path": str(self._video_path),
            "audio_path": str(self._audio_path),
            "video_bytes": self._bytes_video,
            "audio_bytes": self._bytes_audio,
            "mp4_path": str(mp4) if mp4 else None,
            "connected": self._connected,
            "remote_users": sorted(self._remote_users),
            "conn_err": self._conn_err,
            "conn_fail_reason": self._conn_fail_reason,
            "sdk_log": str(sdk_log) if sdk_log.exists() else None,
        }
        self._log(f"[Agora] Session done: {stats}")
        return stats

    def _try_mux(self) -> Path | None:
        if self._bytes_video <= 0 and self._bytes_audio <= 0:
            return None
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self._log("[Agora] ffmpeg not found — left raw .h264/.pcm")
            return None
        out = self.out_dir / "capture.mp4"
        cmd = [ffmpeg, "-y"]
        if self._bytes_video > 0:
            cmd += ["-i", str(self._video_path)]
        if self._bytes_audio > 0:
            cmd += [
                "-f",
                "s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-i",
                str(self._audio_path),
            ]
        if self._bytes_video > 0 and self._bytes_audio > 0:
            cmd += ["-c:v", "copy", "-c:a", "aac", "-shortest", str(out)]
        elif self._bytes_video > 0:
            cmd += ["-c:v", "copy", str(out)]
        else:
            cmd += ["-c:a", "aac", str(out)]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=180)
            if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
                self._log(f"[Agora] Muxed MP4: {out}")
                return out
            self._log(
                f"[Agora] ffmpeg mux failed (exit {proc.returncode}): "
                f"{(proc.stderr or b'')[:300]!r}"
            )
        except Exception as e:
            self._log(f"[Agora] ffmpeg error: {e}")
        return None
