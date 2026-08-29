import json
import logging
import os
import pathlib
import re

import ofscraper.utils.config.schema as schema
import ofscraper.utils.console as console_
import ofscraper.utils.paths.common as common_paths
from ofscraper.utils.config.path_norm import (
    normalize_config_paths_for_os,
    normalize_windows_path,
)

console = console_.get_shared_console()
log = logging.getLogger("shared")

_cached_config = None

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
]


def make_config(config=False):
    global _cached_config
    _cached_config = None
    config = schema.get_current_config_schema(config=config)
    if isinstance(config, str):
        config = json_loads(config)

    p = pathlib.Path(common_paths.get_config_path())
    if not p.parent.is_dir():
        p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w") as f:
        f.write(json.dumps(config, indent=4))
    console.print(f"config file created at {p}")


def make_config_original():
    make_config(config=False)


def open_config():
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    import ofscraper.utils.config.utils.context as config_context

    with config_context.config_context():
        configText = config_string()
        config = json_loads(configText)
        if config.get("config"):
            _cached_config = config.get("config")
        else:
            _cached_config = config
        
        # Support dynamic metadata directory override via environment variable
        import os
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
    if updated_config.get("config"):
        updated_config = updated_config["config"]
    normalize_config_paths_for_os(updated_config)
    p = common_paths.get_config_path()
    if not p.parent.is_dir():
        p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        f.write(json.dumps(updated_config, indent=4))


def auto_update_config(config: dict) -> dict:
    log.info("Auto updating config...")
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
