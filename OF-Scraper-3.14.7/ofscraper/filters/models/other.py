"""
other filters
"""

import logging

from ofscraper.filters.models.utils.logs import trace_log_user
import ofscraper.utils.settings as settings


def otherFilters(filterusername):
    log = logging.getLogger("shared")
    log.debug(f"Excluded usernames: {settings.get_settings().excluded_username}")
    if len(settings.get_settings().excluded_username) > 0:
        filterusername = list(
            filter(
                lambda x: x.name not in settings.get_settings().excluded_username,
                filterusername,
            )
        )
        log.debug(f"'excluded usernames' filter username count: {len(filterusername)}")
        trace_log_user(filterusername, "Excluded usernames")

    return filterusername


def is_excluded_username(username):
    """
    True if --excluded-username names this model.

    The option's callback already lowercases its values, so lowercasing the
    model's name here makes the match case-insensitive.
    """
    excluded = settings.get_settings().excluded_username or []
    return bool(username) and username.lower() in excluded
