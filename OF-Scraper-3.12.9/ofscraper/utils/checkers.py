import logging

import ofscraper.data.api.init as init
import ofscraper.utils.auth.file as auth_file
import ofscraper.utils.auth.make as make
import ofscraper.utils.config.config as config_
import ofscraper.utils.config.data as data
import ofscraper.utils.console as console
import ofscraper.utils.paths.check as check
import ofscraper.utils.settings as settings
import ofscraper.utils.args.accessors.read as read_args

log = logging.getLogger("shared")


def check_auth():
    status = None
    log.info("checking auth status")
    while status != "UP":
        status = init.getstatus()
        if status != "UP":
            log.warning("Auth Failed")
            # In GUI mode, skip InquirerPy prompts — let the GUI handle it
            if getattr(read_args.retriveArgs(), "gui", False):
                return
            make.make_auth(auth=auth_file.read_auth())
            continue
        break


def check_config():
    # In GUI mode we do NOT run interactive terminal prompts.
    # Missing ffmpeg is handled by the GUI popup after the window opens.
    try:
        if getattr(read_args.retriveArgs(), "gui", False):
            log.debug("GUI mode: skipping interactive ffmpeg config check")
            return
    except Exception:
        pass

    while not check.ffmpegchecker(settings.get_ffmpeg()):
        console.get_shared_console().print("There is an issue with the ffmpeg path\n\n")
        log.debug(f"[bold]current ffmpeg path[/bold] {settings.get_ffmpeg()}")
        config_.update_ffmpeg()
    log.debug(f"[bold]final ffmpeg path[/bold] {settings.get_ffmpeg()}")


def check_config_key_mode():
    if settings.get_key_mode() == "keydb" and not settings.get_keydb_api():
        console.shared_console.print(
            "[red]You must setup keydb API Key\nhttps://keysdb.net[/red]"
        )
