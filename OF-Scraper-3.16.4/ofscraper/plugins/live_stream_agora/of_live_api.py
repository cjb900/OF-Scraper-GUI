"""OnlyFans live-stream API helpers (signed session via ofscraper)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

log = logging.getLogger("ofscraper_plugins")


def _of_get_json(url: str) -> Any:
    """GET *url* with a signed OF session; return parsed JSON."""
    import ofscraper.managers.manager as manager

    with manager.Manager.session.get_ofsession() as c:
        with c.requests(url) as r:
            return r.json_()


def _of_post_json(url: str, payload: dict | None = None) -> Any:
    """POST *url* with a signed OF session; return parsed JSON if any."""
    import ofscraper.managers.manager as manager

    with manager.Manager.session.get_ofsession() as c:
        with c.requests(url, method="post", json=payload or {}) as r:
            try:
                return r.json_()
            except Exception:
                return {"ok": True, "status": getattr(r, "status", None)}


def post_stream_look(stream_id: int | str) -> Any:
    """
    Browser posts /streams/{id}/look after joining the live room.

    Best-effort heartbeat so OF keeps treating us as an active viewer.
    """
    sid = str(stream_id).strip()
    if not sid:
        raise RuntimeError("stream_id required for /look")
    url = f"https://onlyfans.com/api2/v2/streams/{sid}/look"
    return _of_post_json(url, {})


def fetch_active_stream(username: str) -> dict | None:
    """Return active stream metadata for *username*, or None if not live / empty."""
    user = (username or "").strip()
    if not user:
        return None
    url = (
        f"https://onlyfans.com/api2/v2/users/{user}/streams/active"
        f"?view=full_with_check"
    )
    data = _of_get_json(url)
    if not isinstance(data, dict):
        return None
    if not data.get("isActive") or data.get("isFinished"):
        return None
    return data


def fetch_agora_credentials(model_user_id: int | str, stream_type: str = "agora_direct") -> dict:
    """Call /users/{id}/streams/active/url and return the raw JSON (includes agora_cred)."""
    extension = {
        "streamtype": stream_type or "agora_direct",
        "sbp": True,
        "preferred_servers": [],
    }
    ext_q = quote(json.dumps(extension, separators=(",", ":")), safe="")
    url = (
        f"https://onlyfans.com/api2/v2/users/{model_user_id}/streams/active/url"
        f"?extension={ext_q}"
    )
    data = _of_get_json(url)
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected /streams/active/url response: {type(data)}")
    return data


def parse_agora_cred(url_payload: dict) -> dict:
    """
    Normalize agora join fields from /streams/active/url JSON.

    Returns dict with keys: app_id, channel, token, user_id, streamname, …
    Also exposes ``token_candidates`` (agora_cred.token then top-level Token)
    so the recorder can retry if OF's edge rejects the first.
    """
    msg = url_payload.get("Message") or {}
    if not isinstance(msg, dict):
        msg = {}
    cred = msg.get("agora_cred") or {}
    if not isinstance(cred, dict):
        cred = {}

    app_id = (cred.get("app_id") or "").strip()
    channel = (cred.get("channel") or cred.get("streamname") or "").strip()
    cred_token = str(cred.get("token") or "").strip()
    top_token = str(url_payload.get("Token") or "").strip()
    # Only AccessToken2 (007…) belongs in RTC connect(). OF's top-level
    # ``Token`` is often a 32-char opaque value (not Agora) — keep it out of
    # join retries so we don't get a misleading INVALID_TOKEN after a real
    # REJECTED_BY_SERVER on the RTC token.
    token_candidates: list[str] = []
    for t in (cred_token, top_token):
        if not t or t in token_candidates:
            continue
        if t.startswith("007"):
            token_candidates.append(t)
    # Fallback: if neither looks like AccessToken2, still keep cred_token so
    # connect can attempt (and token_inspect can report the format).
    if not token_candidates and cred_token:
        token_candidates.append(cred_token)
    elif not token_candidates and top_token:
        token_candidates.append(top_token)
    token = token_candidates[0] if token_candidates else ""
    # Preserve non-RTC top-level Token for diagnostics only
    other_tokens = [
        t
        for t in (cred_token, top_token)
        if t and t not in token_candidates
    ]
    user_id = cred.get("user_id")
    if user_id is None:
        raise RuntimeError("agora_cred missing user_id")
    if not app_id or not channel or not token:
        raise RuntimeError(
            "agora_cred incomplete "
            f"(app_id={bool(app_id)} channel={bool(channel)} token={bool(token)})"
        )
    return {
        "app_id": app_id,
        "channel": channel,
        "token": str(token),
        "token_candidates": token_candidates,
        "non_rtc_tokens": other_tokens,
        "user_id": int(user_id),
        "streamname": (cred.get("streamname") or channel),
        "sbp": msg.get("sbp"),
        "success": bool(msg.get("Success")),
    }


def redact_cred_summary(cred: dict) -> dict:
    """Safe-to-log summary of join credentials."""
    candidates = cred.get("token_candidates") or (
        [cred["token"]] if cred.get("token") else []
    )
    return {
        "app_id": cred.get("app_id"),
        "channel": cred.get("channel"),
        "streamname": cred.get("streamname"),
        "user_id": cred.get("user_id"),
        "token_present": bool(cred.get("token")),
        "token_len": len(cred.get("token") or ""),
        "token_candidate_count": len(candidates),
        "token_lens": [len(t) for t in candidates],
        "non_rtc_token_lens": [
            len(t) for t in (cred.get("non_rtc_tokens") or [])
        ],
        "success": cred.get("success"),
        "sbp_endpoint": ((cred.get("sbp") or {}) or {}).get("endpoint")
        if isinstance(cred.get("sbp"), dict)
        else None,
    }


def resolve_live_join(username: str) -> dict:
    """
    Full join prep for a live creator.

    Returns:
      {
        "username", "stream", "agora": <parse_agora_cred>,
        "stream_type", "stream_id", "model_user_id"
      }
    """
    stream = fetch_active_stream(username)
    if not stream:
        raise RuntimeError(f"{username} has no active stream (API).")

    stream_id = stream.get("id")
    user = stream.get("user") or {}
    model_id = user.get("id") or stream.get("primaryPartnerUserId")
    if model_id is None:
        raise RuntimeError("Active stream missing model user id")

    available = stream.get("viewerAvailableStreamTypes") or []
    stream_type = stream.get("streamType") or (
        available[0] if available else "agora_direct"
    )
    if stream_type and "agora" not in str(stream_type).lower():
        log.warning(
            "Stream type is %r (not agora_*); attempting Agora URL anyway.",
            stream_type,
        )

    payload = fetch_agora_credentials(model_id, stream_type=str(stream_type))
    agora = parse_agora_cred(payload)
    return {
        "username": username,
        "stream": stream,
        "stream_id": stream_id,
        "model_user_id": model_id,
        "stream_type": stream_type,
        "viewer_available_types": available,
        "room": stream.get("room"),
        "agora": agora,
        "agora_summary": redact_cred_summary(agora),
    }
