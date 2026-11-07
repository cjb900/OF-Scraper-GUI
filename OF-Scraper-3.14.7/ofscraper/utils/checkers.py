import logging

import ofscraper.data.api.init as init
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.make as make
import ofscraper.utils.settings as settings

log = logging.getLogger("shared")


class AuthCheckUnavailable(Exception):
    """The auth couldn't be checked (network, server or dynamic rule problem)."""

    # auth_status has logged the reason; run.main needn't repeat it
    already_logged = True


class AuthCheckLeft(Exception):
    """The user chose "Go to Main Menu" in the auth prompt."""


def check_auth(include_main_menu=False):
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
            _, choice = make.make_auth(
                auth=auth_file.read_auth(), include_main_menu=include_main_menu
            )
            if choice == "quit":
                raise SystemExit(0)
            if choice == "main":
                # the main menu catches this and shows itself again
                raise AuthCheckLeft("back to the main menu")
        else:
            break
