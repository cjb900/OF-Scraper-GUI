import logging

import ofscraper.data.api.init as init
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.make as make
import ofscraper.utils.settings as settings

log = logging.getLogger("shared")


class AuthCheckUnavailable(Exception):
    """The auth couldn't be checked (network, server or dynamic rule problem)."""


def check_auth():
    status = None
    log.info("checking auth status")
    while status != "UP":
        status, message = init.auth_status()
        if status == "UNAVAILABLE":
            # The auth may be fine, so don't report it as failed or ask for it
            # again, in the GUI or the CLI. An ordinary exception ends a one-off
            # run or a GUI scrape with this message, and lets the daemon try
            # its next pass.
            raise AuthCheckUnavailable(f"Couldn't check the auth: {message}")
        if status != "UP":
            log.info("Auth Failed")
            # In GUI mode skip interactive prompts; the GUI auth dialog handles re-auth
            if getattr(settings.get_args(), "gui", False):
                log.debug("GUI mode: skipping interactive auth prompt on auth failure")
                return
            make.make_auth(auth=auth_file.read_auth())
        else:
            break
