r"""
This module provides a centralized way to access environment variables and
default settings for the ofscraper application.
"""

import os
import threading

from ofscraper.utils.api_endpoint_overrides import (
    KNOWN_ENDPOINT_KEYS,
    endpoint_env_is_set,
    normalize_endpoint_overrides_dict,
    resolve_endpoint_override,
)
from ofscraper.utils.api_path import (
    DEFAULT_API_PATH,
    apply_api_path_prefix,
    normalize_api_path,
)

# Re-export aggregator used by settings.setup_settings and callers.
from ofscraper.utils.of_env import get_all_configs  # noqa: F401

_ENV_API_PATH = "OFSC_API_PATH"
_api_path_lock = threading.Lock()
_api_path_cache: str | None = None
_resolving_api_path = False

_endpoint_overrides_lock = threading.Lock()
_endpoint_overrides_cache: dict[str, str] | None = None
_resolving_endpoint_overrides = False


def clear_api_path_cache() -> None:
    """Drop cached API path (e.g. after config save)."""
    global _api_path_cache
    with _api_path_lock:
        _api_path_cache = None


def clear_api_endpoint_overrides_cache() -> None:
    """Drop cached per-endpoint URL overrides (e.g. after config save)."""
    global _endpoint_overrides_cache
    with _endpoint_overrides_lock:
        _endpoint_overrides_cache = None


def _default_config_json_path():
    """Resolve config.json without calling ``getattr`` (avoids recursion)."""
    from pathlib import Path

    config_dir = os.getenv("OFSC_CONFIG_DIR", ".config/ofscraper")
    config_file = os.getenv("OFSC_CONFIG_FILE_NAME", "config.json")
    custom = os.getenv("OFSC_CONFIG_PATH") or os.getenv("OF_CONFIG_PATH")
    if custom:
        p = Path(custom)
        if p.is_dir():
            return p / config_file
        return p
    return Path.home() / config_dir / config_file


def _read_api_path_from_config_file() -> str:
    """Best-effort read of ``advanced_options.api_path`` from disk.

    Reads JSON directly — never calls ``open_config()`` / ``getattr`` (that
    would deadlock under the api-path lock).
    """
    try:
        import json
        from pathlib import Path

        path = _default_config_json_path()
        if not Path(path).is_file():
            return DEFAULT_API_PATH
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return DEFAULT_API_PATH
        adv = data.get("advanced_options") or {}
        if isinstance(adv, dict) and adv.get("api_path") is not None:
            return normalize_api_path(adv.get("api_path"))
        if data.get("api_path") is not None:
            return normalize_api_path(data.get("api_path"))
    except Exception:
        return DEFAULT_API_PATH
    return DEFAULT_API_PATH


def _configured_api_path() -> str:
    """``OFSC_API_PATH`` env overrides config; default ``/api2/v2``."""
    global _api_path_cache, _resolving_api_path
    env = os.environ.get(_ENV_API_PATH)
    if env is not None and str(env).strip() != "":
        return normalize_api_path(env)

    # Fast path under lock; never do I/O or re-enter getattr while holding it.
    with _api_path_lock:
        if _api_path_cache is not None:
            return _api_path_cache
        if _resolving_api_path:
            return DEFAULT_API_PATH
        _resolving_api_path = True

    try:
        path = _read_api_path_from_config_file()
        with _api_path_lock:
            _api_path_cache = path
            return path
    finally:
        with _api_path_lock:
            _resolving_api_path = False


def _read_endpoint_overrides_from_config_file() -> dict[str, str]:
    """Best-effort read of ``advanced_options.api_endpoint_overrides`` from disk."""
    try:
        import json
        from pathlib import Path

        path = _default_config_json_path()
        if not Path(path).is_file():
            return {}
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        adv = data.get("advanced_options") or {}
        raw = None
        if isinstance(adv, dict) and adv.get("api_endpoint_overrides") is not None:
            raw = adv.get("api_endpoint_overrides")
        elif data.get("api_endpoint_overrides") is not None:
            raw = data.get("api_endpoint_overrides")
        return normalize_endpoint_overrides_dict(raw)
    except Exception:
        return {}


def _configured_endpoint_overrides() -> dict[str, str]:
    global _endpoint_overrides_cache, _resolving_endpoint_overrides
    with _endpoint_overrides_lock:
        if _endpoint_overrides_cache is not None:
            return _endpoint_overrides_cache
        if _resolving_endpoint_overrides:
            return {}
        _resolving_endpoint_overrides = True

    try:
        overrides = _read_endpoint_overrides_from_config_file()
        with _endpoint_overrides_lock:
            _endpoint_overrides_cache = overrides
            return overrides
    finally:
        with _endpoint_overrides_lock:
            _resolving_endpoint_overrides = False


def getattr(key, default=None):
    """
    Retrieves a configuration value by key.

    Known API endpoint keys may be overridden via
    ``advanced_options.api_endpoint_overrides`` unless a dedicated ``OFSC_API_*``
    env var is set. String values that still contain the canonical OnlyFans
    prefix ``/api2/v2`` are rewritten to the configured API path.

    Args:
        key (str): The key of the configuration value to retrieve.
        default: The value to return if the key is not found. Defaults to None.

    Returns:
        The configuration value if found, otherwise the default value.
    """
    value = get_all_configs().get(key, default)
    if key in KNOWN_ENDPOINT_KEYS:
        ov = resolve_endpoint_override(
            key,
            env_set=endpoint_env_is_set(key),
            config_map=_configured_endpoint_overrides(),
        )
        if ov is not None:
            value = ov
    if isinstance(value, str):
        return apply_api_path_prefix(value, _configured_api_path())
    return value
