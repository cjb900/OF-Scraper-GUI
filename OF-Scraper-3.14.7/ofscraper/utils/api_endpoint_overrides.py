"""Per-endpoint OnlyFans API URL overrides (import-safe).

Config key: ``advanced_options.api_endpoint_overrides`` — JSON object mapping
of_env keys (e.g. ``meEP``) to full URL templates. Dedicated ``OFSC_API_*``
env vars still win when set.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping, Optional

# Keys from ofscraper.utils.of_env.values.url.url.load_api_endpoints_config
ENDPOINT_ENV_MAP: dict[str, str] = {
    "initEP": "OFSC_API_INIT_EP",
    "LICENCE_URL": "OFSC_API_LICENCE_URL",
    "INDIVIDUAL_TIMELINE": "OFSC_API_INDIVIDUAL_TIMELINE",
    "meEP": "OFSC_API_ME_EP",
    "subscriptionsEP": "OFSC_API_SUBSCRIPTIONS_EP",
    "subscriptionsActiveEP": "OFSC_API_SUBSCRIPTIONS_ACTIVE_EP",
    "subscriptionsExpiredEP": "OFSC_API_SUBSCRIPTIONS_EXPIRED_EP",
    "subscribeCountEP": "OFSC_API_SUBSCRIBE_COUNT_EP",
    "sortSubscriptions": "OFSC_API_SORT_SUBSCRIPTIONS",  # also OF_SORT_SUBSCRIPTIONS_URL
    "profileEP": "OFSC_API_PROFILE_EP",
    "timelineEP": "OFSC_API_TIMELINE_EP",
    "timelineNextEP": "OFSC_API_TIMELINE_NEXT_EP",
    "timelinePinnedEP": "OFSC_API_TIMELINE_PINNED_EP",
    "streamsEP": "OFSC_API_STREAMS_EP",
    "streamsNextEP": "OFSC_API_STREAMS_NEXT_EP",
    "archivedEP": "OFSC_API_ARCHIVED_EP",
    "archivedNextEP": "OFSC_API_ARCHIVED_NEXT_EP",
    "highlightsWithStoriesEP": "OFSC_API_HIGHLIGHTS_WITH_STORIES_EP",
    "highlightsWithAStoryEP": "OFSC_API_HIGHLIGHTS_WITH_A_STORY_EP",
    "storyEP": "OFSC_API_STORY_EP",
    "messagesEP": "OFSC_API_MESSAGES_EP",
    "messagesNextEP": "OFSC_API_MESSAGES_NEXT_EP",
    "favoriteEP": "OFSC_API_FAVORITE_EP",
    "postURL": "OFSC_POST_URL",
    "donateEP": "OFSC_DONATE_EP",
    "purchased_contentEP": "OFSC_PURCHASED_CONTENT_EP",
    "purchased_contentALL": "OFSC_PURCHASED_CONTENT_ALL_EP",
    "highlightSPECIFIC": "OFSC_HIGHLIGHT_SPECIFIC_EP",
    "storiesSPECIFIC": "OFSC_STORIES_SPECIFIC_EP",
    "messageSPECIFIC": "OFSC_MESSAGE_SPECIFIC_EP",
    "messageTableSPECIFIC": "OFSC_MESSAGE_TABLE_SPECIFIC_URL",
    "labelsEP": "OFSC_LABELS_EP",
    "labelledPostsEP": "OFSC_LABELLED_POSTS_EP",
    "listEP": "OFSC_LIST_EP",
    "listusersEP": "OFSC_LIST_USERS_EP",
}

KNOWN_ENDPOINT_KEYS: frozenset[str] = frozenset(ENDPOINT_ENV_MAP)

# Alternate env names used in url.py for the same keys
_ALT_ENV: dict[str, tuple[str, ...]] = {
    "sortSubscriptions": ("OF_SORT_SUBSCRIPTIONS_URL",),
}


def endpoint_env_is_set(key: str) -> bool:
    """True if a dedicated env var for *key* is non-empty."""
    primary = ENDPOINT_ENV_MAP.get(key)
    if primary and str(os.environ.get(primary) or "").strip():
        return True
    for alt in _ALT_ENV.get(key, ()):
        if str(os.environ.get(alt) or "").strip():
            return True
    return False


def parse_endpoint_overrides(raw: Any) -> Optional[dict[str, str]]:
    """Parse overrides into a dict, or None if empty/invalid JSON."""
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        data = dict(raw)
    else:
        text = str(raw).strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(parsed, dict):
            return None
        data = parsed
    out: dict[str, str] = {}
    for k, v in data.items():
        key = str(k).strip()
        if not key:
            continue
        if v is None:
            continue
        val = str(v).strip()
        if not val:
            continue
        out[key] = val
    return out


def validate_endpoint_overrides(obj: Any) -> Optional[str]:
    """Return error message if overrides are invalid, else None.

    Empty object / empty input is valid.
    """
    if obj is None:
        return None
    if isinstance(obj, str) and not obj.strip():
        return None
    parsed = parse_endpoint_overrides(obj)
    if parsed is None:
        return "API Endpoint Overrides must be a JSON object"
    unknown = sorted(k for k in parsed if k not in KNOWN_ENDPOINT_KEYS)
    if unknown:
        preview = ", ".join(unknown[:5])
        more = f" (+{len(unknown) - 5} more)" if len(unknown) > 5 else ""
        return f"Unknown endpoint key(s): {preview}{more}"
    for k, v in parsed.items():
        if not isinstance(v, str) or not v.strip():
            return f"Override for '{k}' must be a non-empty string"
    return None


def normalize_endpoint_overrides_json(raw: Any) -> str:
    """Pretty-print valid overrides JSON, or ``\"{}\"`` / raw text."""
    parsed = parse_endpoint_overrides(raw)
    if parsed is None:
        if raw is None:
            return "{}"
        return str(raw).strip() or "{}"
    err = validate_endpoint_overrides(parsed)
    if err:
        if isinstance(raw, Mapping):
            return json.dumps(dict(raw), indent=2, ensure_ascii=False, sort_keys=True)
        text = str(raw).strip()
        return text or "{}"
    if not parsed:
        return "{}"
    return json.dumps(parsed, indent=2, ensure_ascii=False, sort_keys=True)


def normalize_endpoint_overrides_dict(raw: Any) -> dict[str, str]:
    """Return a cleaned overrides dict (empty if invalid/empty)."""
    parsed = parse_endpoint_overrides(raw)
    if parsed is None:
        return {}
    if validate_endpoint_overrides(parsed) is not None:
        return {}
    return parsed


def resolve_endpoint_override(
    key: str, *, env_set: bool, config_map: Optional[Mapping[str, str]]
) -> Optional[str]:
    """Return config override for *key* when env is unset and override exists."""
    if env_set or not config_map:
        return None
    val = config_map.get(key)
    if val is None:
        return None
    text = str(val).strip()
    return text or None
