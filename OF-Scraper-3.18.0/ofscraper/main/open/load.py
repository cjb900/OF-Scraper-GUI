import logging
import os
import platform
import traceback

import ofscraper.main.open.run as run
import ofscraper.utils.config.config as config_
import ofscraper.utils.dates as dates
import ofscraper.utils.logs.logger as logger
import ofscraper.utils.logs.logs as logs
import ofscraper.utils.paths.manage as paths_manage
import ofscraper.utils.system.system as system
import ofscraper.utils.settings as settings


def main():
    try:
        systemSet()
        settings_loader()
        setdate()
        readConfig()
        setLogger()
        make_folder()

        if _is_gui_tab_window():
            # the tab window only starts the sites' GUI processes, which load
            # the plugins themselves
            run.main()
            return

        # Initialize plugins for headless/scrape execution
        from ofscraper.plugins.manager import plugin_manager
        # On Windows, pre-load plugin DLLs (e.g. torch/c10.dll) BEFORE
        # discover_and_load(), which imports plugin GUI modules (ai_tagger/gui.py
        # → PyQt6).  Once PyQt6.QtCore's SIP layer initializes, torch's c10.dll
        # DllMain fails with WinError 1114.  Pre-loading the DLLs first prevents
        # this because Windows returns the existing handle on subsequent
        # LoadLibrary calls without re-running DllMain.
        import sys as _sys
        if _sys.platform == "win32":
            try:
                plugin_manager.preload_for_windows_gui()
            except Exception:
                pass
        plugin_manager.discover_and_load()

        run.main()
    except Exception as E:
        print(E)
        print(traceback.format_exc())
        try:
            logging.getLogger("shared").debug(traceback.format_exc())
            logging.getLogger("shared").debug(E)
        except Exception as E:
            print(E)
            print(traceback.format_exc())


def _is_gui_tab_window() -> bool:
    try:
        if not getattr(settings.get_args(), "gui", False):
            return False
        from ofscraper.gui import site_context

        return not site_context.is_child() and site_context.tabs_enabled()
    except Exception:
        return False


def settings_loader():
    settings.get_settings()


def setdate():
    dates.resetLogDate()


def setLogger():
    logger.get_shared_logger()
    logs.discord_warning()
    paths_manage.cleanup_logs()


def systemSet():
    system.setName()
    system.set_eventloop()
    if platform.system() == "Windows":
        os.system("color")


def readConfig():
    config_.read_config()


def make_folder():
    paths_manage.make_folders()
