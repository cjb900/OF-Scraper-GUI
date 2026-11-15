import json
import logging
import os
import pathlib
import re

from ofscraper.utils.markup import escape_text

import ofscraper.utils.config.schema as schema
import ofscraper.utils.console as console_
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.paths.common as common_paths
from ofscraper.utils.config.path_norm import (
    normalize_config_paths_for_os,
    normalize_windows_path,
)

console = console_.get_shared_console()
log = logging.getLogger("shared")

# open_config() reads config.json once and keeps it until the file changes
# (its path, size or modified time), so a fix made in an editor, or another
# config path, is read again
_cached_config = None
_cached_stamp = None


def _config_stamp():
    try:
        path = common_paths.get_config_path()
        stat = pathlib.Path(path).stat()
        return (str(path), stat.st_mtime_ns, stat.st_size)
    except Exception:
        return None


__all__ = [
    "normalize_config_paths_for_os",
    "normalize_windows_path",
    "make_config",
    "make_config_original",
    "open_config",
    "config_string",
    "write_config",
    "auto_update_config",
    "json_loads",
    "unwrap",
    "NotAnObjectError",
]


def make_config(config=False):
    global _cached_config
    _cached_config = None
    if config is False:
        # a new file holds the built-in defaults, not environment values
        with of_env.builtin_defaults():
            config = schema.get_current_config_schema(config=config)
    else:
        config = schema.get_current_config_schema(config=config)
    if isinstance(config, str):
        config = json_loads(config)

    p = pathlib.Path(common_paths.get_config_path())
    if not p.parent.is_dir():
        p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w") as f:
        f.write(json.dumps(config, indent=4))
    console.print(f"config file created at {escape_text(p)}")


def make_config_original():
    make_config(config=False)


class NotAnObjectError(ValueError):
    """config.json is valid JSON but doesn't hold an object of settings"""


def _json_type(value):
    if isinstance(value, bool):
        return "true or false"
    if value is None:
        return "null"
    if isinstance(value, list):
        return "a list"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, (int, float)):
        return "a number"
    return type(value).__name__


def unwrap(config):
    """
    The settings in a parsed config.json: the object itself, or the one under
    "config" in the older {"config": {...}} form (an empty "config" is
    ignored, as before). Raises NotAnObjectError when either isn't an object.
    """
    if not isinstance(config, dict):
        raise NotAnObjectError(
            f"config.json holds {_json_type(config)}, not an object of settings"
        )
    wrapped = config.get("config")
    if not wrapped:
        return config
    if not isinstance(wrapped, dict):
        raise NotAnObjectError(
            f'"config" in config.json holds {_json_type(wrapped)}, '
            "not an object of settings"
        )
    return wrapped


def open_config():
    global _cached_config, _cached_stamp
    if _cached_config is not None:
        stamp = _config_stamp()
        if stamp is not None and stamp == _cached_stamp:
            return _cached_config
        _cached_config = None

    import ofscraper.utils.config.utils.context as config_context

    with config_context.config_context():
        configText = config_string()
        _cached_config = unwrap(json_loads(configText))
        # the prompts above may have rewritten the file: stamp what was read
        _cached_stamp = _config_stamp()

        # Support dynamic metadata directory override via environment variable
        metadata_override = os.getenv("OFSC_METADATA_OVERRIDE")
        if metadata_override:
            _cached_config["metadata"] = metadata_override

        return _cached_config


def config_string():
    p = pathlib.Path(common_paths.get_config_path())
    with open(p, "r") as f:
        configText = f.read()
    return configText


def write_config(updated_config):
    global _cached_config
    _cached_config = None
    if isinstance(updated_config, str):
        updated_config = json_loads(updated_config)
    updated_config = unwrap(updated_config)
    normalize_config_paths_for_os(updated_config)
    p = common_paths.get_config_path()
    if not p.parent.is_dir():
        p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(updated_config, indent=4))


def auto_update_config(config: dict) -> dict:
    log.info("Auto updating config...")
    # keys missing from the file get the built-in defaults, not environment
    # values; the environment still applies at runtime
    with of_env.builtin_defaults():
        new_config = schema.get_current_config_schema(config)
    write_config(new_config)
    return new_config


def json_loads(configText):
    try:
        config = json.loads(configText)
    except json.JSONDecodeError:
        configText = re.sub("\\\\+", "/", configText)
        config = json.loads(configText)
    return config
