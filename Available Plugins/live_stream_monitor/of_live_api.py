"""OnlyFans live-stream API helpers (signed session via ofscraper)."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import quote

log = logging.getLogger("ofscraper_plugins")


def _api(url: str) -> str:
    """Apply the API Path setting (Configuration → Advanced) to a default URL."""
    try:
        from ofscraper.utils.api_path import apply_api_path_prefix
        from ofscraper.utils.of_env.of_env import _configured_api_path

        return apply_api_path_prefix(url, _configured_api_path()) or url
    except Exception:
        return url


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
    url = _api(f"https://onlyfans.com/api2/v2/streams/{sid}/look")
    return _of_post_json(url, {})


def fetch_active_stream(username: str) -> dict | None:
    """Return active stream metadata for *username*, or None if not live / empty."""
    user = (username or "").strip()
    if not user:
        return None
    url = _api(
        f"https://onlyfans.com/api2/v2/users/{user}/streams/active"
        f"?view=full_with_check"
    )
    try:
        data = _of_get_json(url)
    except Exception as e:
        # Session/HTTP failures must not look like a mysterious crash on
        # ``if not stream`` — surface a clear, catchable RuntimeError.
        raise RuntimeError(
            f"Failed to fetch active stream for {user}: {type(e).__name__}: {e}"
        ) from e
    if data is None:
        return None
    if not isinstance(data, dict):
        log.debug(
            "active stream for %s: unexpected JSON type %s",
            user,
            type(data).__name__,
        )
        return None
    # Some error payloads are dicts without isActive
    if data.get("error") and not data.get("isActive"):
        return None
    if not data.get("isActive") or data.get("isFinished"):
        return None
    return data


def _as_mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _first_id(*candidates: Any) -> int | str | None:
    """Return the first usable numeric/string id from *candidates*."""
    for raw in candidates:
        if raw is None or raw is False:
            continue
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            try:
                return int(raw)
            except (TypeError, ValueError):
                continue
        text = str(raw).strip()
        if not text or text.lower() in {"none", "null"}:
            continue
        return text
    return None


def extract_model_user_id(stream: dict) -> int | str | None:
    """
    Pull the creator/model user id from an /streams/active payload.

    OF has used several field names over time; try them all before failing.
    """
    user = _as_mapping(stream.get("user"))
    user_data = _as_mapping(stream.get("userData") or stream.get("user_data"))
    partner = _as_mapping(stream.get("primaryPartner") or stream.get("partner"))
    return _first_id(
        user.get("id"),
        user.get("user_id"),
        user.get("uid"),
        user_data.get("id"),
        user_data.get("user_id"),
        partner.get("id"),
        partner.get("user_id"),
        stream.get("primaryPartnerUserId"),
        stream.get("primaryPartnerUserID"),
        stream.get("userId"),
        stream.get("user_id"),
        stream.get("modelId"),
        stream.get("model_id"),
        stream.get("creatorId"),
        stream.get("creator_id"),
    )


def fetch_agora_credentials(model_user_id: int | str, stream_type: str = "agora_direct") -> dict:
    """Call /users/{id}/streams/active/url and return the raw JSON (includes agora_cred)."""
    extension = {
        "streamtype": stream_type or "agora_direct",
        "sbp": True,
        "preferred_servers": [],
    }
    ext_q = quote(json.dumps(extension, separators=(",", ":")), safe="")
    url = _api(
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

    Raises RuntimeError with an explicit message when the creator is offline,
    the payload lacks a model id, or the Agora URL cannot be parsed. Callers
    (GUI dump / diagnostics) should show ``str(exc)`` to the user.
    """
    try:
        stream = fetch_active_stream(username)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Active-stream lookup failed for {username}: {type(e).__name__}: {e}"
        ) from e

    # Use identity check — ``if not stream`` is fine for None/{} but a future
    # non-mapping payload must not blow up on truthiness before we raise.
    if stream is None:
        msg = f"{username} has no active stream (API)."
        log.info("[live_api] %s", msg)
        raise RuntimeError(msg)

    if not isinstance(stream, dict):
        msg = (
            f"{username}: active stream response is {type(stream).__name__}, "
            "expected object"
        )
        log.warning("[live_api] %s", msg)
        raise RuntimeError(msg)

    stream_id = stream.get("id")
    model_id = extract_model_user_id(stream)
    if model_id is None:
        keys = sorted(str(k) for k in stream.keys())
        user_keys = sorted(
            str(k) for k in _as_mapping(stream.get("user")).keys()
        )
        msg = (
            "Active stream missing model user id "
            f"(username={username!r} stream_id={stream_id!r} "
            f"stream_keys={keys} user_keys={user_keys})"
        )
        log.warning("[live_api] %s", msg)
        raise RuntimeError(msg)

    available = stream.get("viewerAvailableStreamTypes") or []
    if not isinstance(available, list):
        available = []
    stream_type = stream.get("streamType") or (
        available[0] if available else "agora_direct"
    )
    if stream_type and "agora" not in str(stream_type).lower():
        log.warning(
            "Stream type is %r (not agora_*); attempting Agora URL anyway.",
            stream_type,
        )

    try:
        payload = fetch_agora_credentials(model_id, stream_type=str(stream_type))
        agora = parse_agora_cred(payload)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Agora credential fetch failed for {username} "
            f"(model_id={model_id}): {type(e).__name__}: {e}"
        ) from e

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
