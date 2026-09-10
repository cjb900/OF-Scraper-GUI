"""Live-stream diagnostics helpers (HLS vs WebRTC evidence collection)."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# URL / path hints that matter for capture-path decisions
_INTERESTING_RE = re.compile(
    r"("
    r"\.m3u8(\?|$)|/hls/|\.mpd(\?|$)|/dash/"
    r"|agora|webrtc|ice\.|turn:|stun:|rtm\.|rtc"
    r"|stream\d*\.onlyfans\.com|onlyfans\.com/api2"
    r"|mediasoup|livekit|twilio|cloudflare.*stream"
    r")",
    re.IGNORECASE,
)

_SECRET_QUERY_KEYS = {
    "token",
    "access_token",
    "auth",
    "authorization",
    "sig",
    "signature",
    "key",
    "api_key",
    "apikey",
    "sess",
    "session",
    "cookie",
    "password",
    "secret",
    "pssh",
    "license",
}

_SECRET_HEADER_KEYS = {
    "cookie",
    "set-cookie",
    "authorization",
    "x-bc",
    "sign",
    "app-token",
    "user-id",
}

_SECRET_JSON_KEYS = {
    "sess",
    "session",
    "token",
    "accessToken",
    "access_token",
    "refreshToken",
    "password",
    "cookie",
    "cookies",
    "authorization",
    "privateKey",
    "private_key",
    "clientId",
    "secret",
    "x-bc",
    "sign",
}


def url_is_interesting(url: str) -> bool:
    return bool(url and _INTERESTING_RE.search(url))


def redact_url(url: str) -> str:
    """Strip/redact sensitive query values while keeping host + path for analysis."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() in _SECRET_QUERY_KEYS or any(
                s in k.lower() for s in ("token", "sig", "auth", "key", "sess")
            ):
                q.append((k, "[REDACTED]"))
            else:
                q.append((k, v if len(v) < 200 else v[:80] + "…"))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(q), "")
        )
    except Exception:
        return url[:240]


def redact_headers(headers: dict | None) -> dict:
    out = {}
    if not headers:
        return out
    for k, v in headers.items():
        lk = str(k).lower()
        if lk in _SECRET_HEADER_KEYS or "cookie" in lk or "auth" in lk:
            out[k] = "[REDACTED]"
        else:
            sv = str(v)
            out[k] = sv if len(sv) < 300 else sv[:120] + "…"
    return out


def redact_json(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "[TRUNCATED]"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in {x.lower() for x in _SECRET_JSON_KEYS} or any(
                s in lk for s in ("token", "sess", "secret", "password", "cookie", "auth")
            ):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_json(v, depth + 1)
        return out
    if isinstance(obj, list):
        if len(obj) > 40:
            return [redact_json(x, depth + 1) for x in obj[:40]] + ["…"]
        return [redact_json(x, depth + 1) for x in obj]
    if isinstance(obj, str) and len(obj) > 500:
        return obj[:200] + "…"
    return obj


def classify_delivery(
    urls: list[str],
    page_diag: dict | None,
    sdk_globals: list | None = None,
) -> dict:
    """Heuristic classification for capture-path decisions."""
    urls_l = [u.lower() for u in (urls or [])]
    has_hls = any(".m3u8" in u or "/hls/" in u for u in urls_l)
    has_dash = any(".mpd" in u or "/dash/" in u for u in urls_l)
    has_agora_url = any("agora" in u for u in urls_l)
    sdk = list(sdk_globals or [])
    if page_diag and not sdk:
        sdk = list(page_diag.get("sdkGlobals") or [])
    has_agora_sdk = any("agora" in str(s).lower() for s in sdk)
    has_hls_js = any(str(s).lower() in ("hls", "hls.js") for s in sdk)

    webrtc_media = False
    plain_src = False
    for v in (page_diag or {}).get("videos") or []:
        if v.get("srcObjectType") == "MediaStream":
            webrtc_media = True
        if v.get("src"):
            plain_src = True

    if has_hls or has_hls_js:
        suggested = "hls_ffmpeg_candidate"
        summary = (
            "HLS playlist evidence found — try ffmpeg/yt-dlp with session "
            "cookies/headers (verify outside the browser)."
        )
    elif has_dash:
        suggested = "dash_candidate"
        summary = "DASH (.mpd) evidence found — possible non-browser download path."
    elif has_agora_sdk or has_agora_url or webrtc_media:
        suggested = "webrtc_agora_browser"
        summary = (
            "WebRTC/Agora-style delivery — browser MediaRecorder (or a native "
            "Agora client with API tokens) remains the realistic capture path."
        )
    elif plain_src:
        suggested = "direct_media_src"
        summary = "Plain media src on <video> — inspect URL; may be downloadable."
    else:
        suggested = "unknown"
        summary = "No clear HLS/WebRTC signal — need a longer probe or manual HAR."

    return {
        "has_hls": has_hls,
        "has_dash": has_dash,
        "has_agora_url": has_agora_url,
        "has_agora_sdk": has_agora_sdk,
        "has_hls_js_sdk": has_hls_js,
        "webrtc_mediastream_on_video": webrtc_media,
        "plain_video_src": plain_src,
        "sdk_globals": sdk,
        "suggested_path": suggested,
        "summary": summary,
    }


def summarize_requests(entries: list[dict]) -> dict:
    media_urls = []
    api_urls = []
    other = []
    for e in entries:
        u = (e.get("url") or "").lower()
        if ".m3u8" in u or "/hls/" in u or ".mpd" in u or ".ts" in u:
            media_urls.append(e.get("url"))
        elif "onlyfans.com/api2" in u:
            api_urls.append(e.get("url"))
        else:
            other.append(e.get("url"))
    # unique preserve order
    def _uniq(seq):
        seen = set()
        out = []
        for x in seq:
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {
        "media_or_playlist_urls": _uniq(media_urls)[:80],
        "api2_urls": _uniq(api_urls)[:80],
        "other_interesting_urls": _uniq(other)[:80],
        "request_count": len(entries),
    }
