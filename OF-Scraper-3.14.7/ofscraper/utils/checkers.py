import logging

import ofscraper.data.api.init as init
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.make as make
import ofscraper.utils.settings as settings

log = logging.getLogger("shared")


def check_auth():
    status = None
    log.info("checking auth status")
    while status != "UP":
        status = init.getstatus()
        if status != "UP":
            log.info("Auth Failed")
            # In GUI mode skip interactive prompts; the GUI auth dialog handles re-auth
            if getattr(settings.get_args(), "gui", False):
                log.debug("GUI mode: skipping interactive auth prompt on auth failure")
                return
            make.make_auth(auth=auth_file.read_auth())
        else:
            break
