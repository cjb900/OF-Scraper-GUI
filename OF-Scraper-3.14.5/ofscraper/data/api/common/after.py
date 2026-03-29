import logging

import ofscraper.utils.settings as settings
from ofscraper.data.api.common.cache.read import read_full_after_scan_check

log = logging.getLogger("shared")


def get_after_pre_checks(model_id, api):
    if settings.get_settings().after is not None:
        log.debug(f"{api}: using provided value for after")
        if settings.get_settings().after != 0:
            return settings.get_settings().after.float_timestamp
        else:
            return 0
    elif not settings.get_settings().incremental_downloads:
        log.debug(f"{api}: incremental download is disabled using 0")
        return 0
    elif read_full_after_scan_check(model_id, api):
        log.debug(f"{api}: full scan has been trigger")
        return 0
    # scan action
    for setting in settings.get_settings().actions:
        if setting in {"like", "unlike"}:
            # In GUI mode, skip the forced full scan to avoid multi-hour stuck runs.
            # The GUI manages the scan range through its own controls.
            import ofscraper.utils.args.accessors.read as read_args
            if getattr(read_args.retriveArgs(), "gui", False):
                log.debug(f"{api}: GUI mode, skipping forced full scan for like/unlike")
                break
            log.debug(f"{api}: doing full scan for action like/unlike")
            return 0
