r"""
This module provides a centralized way to access environment variables and
default settings for the ofscraper application.
"""

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

from ofscraper.utils.of_env import get_all_configs
import os


from ofscraper.utils.of_env import get_all_configs
import contextlib
import os
import json
import logging

log = logging.getLogger("shared")
# (key, value) pairs already warned about
_warned = set()


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


def _as_type_of(text, current):
    """
    Convert an environment variable's text to the type of the configured
    value, the way the loaders in values/ convert their own variables.
    """
    if isinstance(current, bool):
        return text.strip().lower() in ("true", "1")
    if isinstance(current, (int, float)):
        return type(current)(text)
    if isinstance(current, (list, tuple, set, frozenset)):
        # A JSON array, or comma-separated text. Env files (load.py) write
        # lists as Python text, e.g. ['a', 'b'], which isn't read: that needs
        # #168, which makes them write JSON
        if text.strip().startswith("["):
            items = json.loads(text)
        else:
            items = [s.strip() for s in text.split(",") if s.strip()]
        return type(current)(items)
    if isinstance(current, dict):
        # JSON only; from an env file this also needs #168
        return json.loads(text)
    return text


def _env_or_config(val, default=None):
    """
    Retrieves a configuration value.
    Order of precedence: Environment Variable > Custom Config > Default Config.
    Returns default if the key isn't set anywhere.
    """
    # Load all settings if not already loaded
    config_dict = get_all_configs()
    # 1. Check Environment Variable
    env_val = os.environ.get(val)
    if env_val is not None:
        if val not in config_dict:
            return env_val
        try:
            return _as_type_of(env_val, config_dict[val])
        except (TypeError, ValueError) as E:
            # once per key and value: settings are read again and again
            if (val, env_val) not in _warned:
                _warned.add((val, env_val))
                log.warning(
                    f"{val}: can't use the environment value {env_val!r} ({E}), "
                    f"using {config_dict[val]!r}"
                )
            return config_dict[val]
    if val in config_dict:  # Check if key exists in the aggregated settings
        return config_dict.get(val)
    return default


def getattr(val, default=None):
    """
    Retrieves a configuration value.
    Order of precedence: Environment Variable > Custom Config > Default Config.
    Returns default if the key isn't set anywhere.

    GUI: known API endpoint keys may be overridden via
    ``advanced_options.api_endpoint_overrides`` unless a dedicated ``OFSC_API_*``
    env var is set. String values that still contain the canonical OnlyFans
    prefix ``/api2/v2`` are rewritten to the configured API path.
    """
    value = _env_or_config(val, default)
    if val in KNOWN_ENDPOINT_KEYS:
        ov = resolve_endpoint_override(
            val,
            env_set=endpoint_env_is_set(val),
            config_map=_configured_endpoint_overrides(),
        )
        if ov is not None:
            value = ov
    if isinstance(value, str):
        return apply_api_path_prefix(value, _configured_api_path())
    return value


@contextlib.contextmanager
def builtin_defaults():
    """
    While the block runs, hide OFSC_* variables and variables named after a
    setting, so getattr returns the built-in defaults. A new config.json is
    written inside this, so environment values aren't saved as the user's
    settings; they still apply at runtime once the block ends.
    """
    keys = set(get_all_configs())
    hidden = {
        name: value
        for name, value in os.environ.items()
        if name.startswith("OFSC_") or name in keys
    }
    for name in hidden:
        del os.environ[name]
    get_all_configs(forced=True)
    try:
        yield
    finally:
        os.environ.update(hidden)
        get_all_configs(forced=True)


def getkeys(forced=False):
    return get_all_configs(forced=forced)
