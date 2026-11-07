"""Manual OnlyFans dynamic-rules helpers (import-safe, no config side effects).

Used when Dynamic Mode is ``manual``: paste/load signing-rules JSON into
``advanced_options.dynamic_rules_manual``, optionally overridden by
``OFSC_DYNAMIC_RULE_MANUAL``.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Optional


def resolve_manual_rules_text(
    env_value: Any = None, config_value: Any = None
) -> Optional[str]:
    """Prefer non-empty env text, else config; return stripped string or None."""
    for raw in (env_value, config_value):
        if raw is None:
            continue
        if isinstance(raw, Mapping):
            try:
                text = json.dumps(raw, indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                continue
            if text.strip():
                return text.strip()
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def parse_manual_rules(raw: Any) -> Optional[dict]:
    """Parse raw rules into a dict, or return None if empty/invalid JSON."""
    if raw is None:
        return None
    if isinstance(raw, Mapping):
        return dict(raw)
    text = str(raw).strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def validate_manual_rules(obj: Any) -> Optional[str]:
    """Return an error message if *obj* is not usable signing rules, else None."""
    if not isinstance(obj, Mapping):
        return "Manual rules must be a JSON object"
    if not obj.get("static_param"):
        return "Missing required field: static_param"
    if "checksum_indexes" not in obj:
        return "Missing required field: checksum_indexes"
    indexes = obj.get("checksum_indexes")
    if not isinstance(indexes, (list, tuple)):
        return "checksum_indexes must be a list"
    if "checksum_constant" not in obj:
        return "Missing required field: checksum_constant"
    has_format = bool(obj.get("format"))
    has_prefix_suffix = bool(obj.get("prefix")) and bool(obj.get("suffix"))
    if not has_format and not has_prefix_suffix:
        return "Need either 'format' or both 'prefix' and 'suffix'"
    return None


def normalize_manual_rules_json(raw: Any) -> str:
    """Pretty-print valid rules JSON, or return stripped raw text / empty string."""
    parsed = parse_manual_rules(raw)
    if parsed is None:
        if raw is None:
            return ""
        if isinstance(raw, Mapping):
            try:
                return json.dumps(dict(raw), indent=2, ensure_ascii=False)
            except (TypeError, ValueError):
                return ""
        return str(raw).strip()
    err = validate_manual_rules(parsed)
    if err:
        # Keep user text for editing; only pretty-print when valid.
        if isinstance(raw, Mapping):
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        return str(raw).strip()
    return json.dumps(parsed, indent=2, ensure_ascii=False)


def load_manual_rules_dict(env_value: Any = None, config_value: Any = None) -> Optional[dict]:
    """Resolve + parse + validate; return dict or None if missing/invalid."""
    text = resolve_manual_rules_text(env_value, config_value)
    if not text:
        return None
    parsed = parse_manual_rules(text)
    if parsed is None:
        return None
    if validate_manual_rules(parsed) is not None:
        return None
    return parsed
