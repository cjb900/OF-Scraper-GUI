"""Inspect Agora AccessToken2 payloads without the App Certificate.

OF issues tokens; we cannot regenerate them. We *can* parse AccessToken2
(``007…``) to compare the embedded app id / channel / uid against what we
pass to ``connection.connect()``.
"""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any


def _unpack_u16(buf: bytes) -> tuple[int, bytes]:
    return struct.unpack("<H", buf[:2])[0], buf[2:]


def _unpack_u32(buf: bytes) -> tuple[int, bytes]:
    return struct.unpack("<I", buf[:4])[0], buf[4:]


def _unpack_str(buf: bytes) -> tuple[bytes, bytes]:
    n, buf = _unpack_u16(buf)
    return buf[:n], buf[n:]


def _unpack_map_u32(buf: bytes) -> tuple[dict[int, int], bytes]:
    count, buf = _unpack_u16(buf)
    out: dict[int, int] = {}
    for _ in range(count):
        k, buf = _unpack_u16(buf)
        v, buf = _unpack_u32(buf)
        out[k] = v
    return out, buf


def inspect_agora_token(token: str) -> dict[str, Any]:
    """
    Best-effort decode of an Agora token.

    Returns a dict with keys such as:
      version, app_id, issue_ts, expire, channel, uid, uid_is_wildcard,
      services, parse_ok, error
    """
    raw = (token or "").strip()
    result: dict[str, Any] = {
        "parse_ok": False,
        "token_len": len(raw),
        "token_prefix": raw[:3] if raw else "",
        "version": None,
        "app_id": None,
        "issue_ts": None,
        "expire": None,
        "channel": None,
        "uid": None,
        "uid_is_wildcard": None,
        "services": [],
        "error": None,
    }
    if not raw:
        result["error"] = "empty token"
        return result

    # AccessToken2
    if raw.startswith("007"):
        try:
            blob = zlib.decompress(base64.b64decode(raw[3:]))
            _sig, buf = _unpack_str(blob)
            app_id_b, buf = _unpack_str(buf)
            issue_ts, buf = _unpack_u32(buf)
            expire, buf = _unpack_u32(buf)
            _salt, buf = _unpack_u32(buf)
            svc_count, buf = _unpack_u16(buf)
            result.update(
                {
                    "version": "007",
                    "app_id": app_id_b.decode("utf-8", errors="replace"),
                    "issue_ts": issue_ts,
                    "expire": expire,
                }
            )
            services = []
            for _ in range(svc_count):
                svc_type, buf = _unpack_u16(buf)
                privileges, buf = _unpack_map_u32(buf)
                entry: dict[str, Any] = {
                    "type": svc_type,
                    "privileges": privileges,
                }
                # ServiceRtc = 1 → channel + uid strings
                if svc_type == 1:
                    ch_b, buf = _unpack_str(buf)
                    uid_b, buf = _unpack_str(buf)
                    channel = ch_b.decode("utf-8", errors="replace")
                    uid_s = uid_b.decode("utf-8", errors="replace")
                    entry["channel"] = channel
                    entry["uid"] = uid_s if uid_s else "0"
                    entry["uid_is_wildcard"] = uid_s == ""
                    result["channel"] = channel
                    result["uid"] = entry["uid"]
                    result["uid_is_wildcard"] = entry["uid_is_wildcard"]
                elif svc_type in (3, 6):  # Streaming / FCDN
                    ch_b, buf = _unpack_str(buf)
                    acct_b, buf = _unpack_str(buf)
                    entry["channel"] = ch_b.decode("utf-8", errors="replace")
                    entry["account"] = acct_b.decode("utf-8", errors="replace")
                elif svc_type in (2, 5, 8):  # RTM / Chat / RTM2
                    uid_b, buf = _unpack_str(buf)
                    entry["user_id"] = uid_b.decode("utf-8", errors="replace")
                elif svc_type == 7:  # APaaS
                    room_b, buf = _unpack_str(buf)
                    user_b, buf = _unpack_str(buf)
                    role, buf = _unpack_u16(buf)  # packed as int16 in builder; uint16 ok for dump
                    entry["room"] = room_b.decode("utf-8", errors="replace")
                    entry["user"] = user_b.decode("utf-8", errors="replace")
                    entry["role"] = role
                services.append(entry)
            result["services"] = services
            result["parse_ok"] = True
            return result
        except Exception as e:
            result["error"] = f"AccessToken2 parse failed: {e}"
            return result

    # Older DynamicKey / AccessToken1 — often start with 006 / 005 / 004
    result["version"] = raw[:3]
    result["error"] = (
        f"unsupported token version prefix {raw[:3]!r} "
        "(expected AccessToken2 '007'); cannot inspect claims"
    )
    return result


def compare_join_to_token(
    *,
    token: str,
    app_id: str,
    channel: str,
    user_id: int | str,
) -> dict[str, Any]:
    """
    Compare OF join args against token claims.

    Returns inspection plus ``mismatches`` list and ``recommended_uid``.
    """
    insp = inspect_agora_token(token)
    mismatches: list[str] = []
    join_uid = str(user_id)
    recommended_uid = join_uid

    if not insp.get("parse_ok"):
        insp["mismatches"] = mismatches
        insp["recommended_uid"] = recommended_uid
        insp["join_app_id"] = app_id
        insp["join_channel"] = channel
        insp["join_uid"] = join_uid
        return insp

    tok_app = insp.get("app_id") or ""
    tok_ch = insp.get("channel") or ""
    tok_uid = insp.get("uid")
    wild = bool(insp.get("uid_is_wildcard"))

    if tok_app and app_id and tok_app.lower() != str(app_id).lower():
        mismatches.append(
            f"app_id mismatch: join={app_id!r} token={tok_app!r}"
        )
    if tok_ch and channel and tok_ch != channel:
        mismatches.append(
            f"channel mismatch: join={channel!r} token={tok_ch!r}"
        )

    if wild:
        # Token uid "" / 0 → any join uid is allowed
        recommended_uid = join_uid
    elif tok_uid is not None and str(tok_uid) not in ("", "0") and str(tok_uid) != join_uid:
        mismatches.append(
            f"uid mismatch: join={join_uid!r} token={tok_uid!r}"
        )
        recommended_uid = str(tok_uid)

    insp["mismatches"] = mismatches
    insp["recommended_uid"] = recommended_uid
    insp["join_app_id"] = app_id
    insp["join_channel"] = channel
    insp["join_uid"] = join_uid
    return insp
