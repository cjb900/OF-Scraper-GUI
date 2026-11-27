import logging
import traceback

import ofscraper.main.close.exit as exit_manager
import ofscraper.main.close.exit_status as exit_status
import ofscraper.utils.console as console
import ofscraper.utils.context.exit as exit_context
from ofscraper.managers.manager import start_manager


def check_database():
    """With PostgreSQL configured, connect before any work starts: a server
    that can't be used stops the run here with one sentence."""
    import ofscraper.db.postgres as postgres

    if _gui_tab_window():
        return  # the tab window never opens the database; each site's window checks
    if postgres.enabled():
        try:
            version = postgres.POSTGRES.check()
        except postgres.PostgresUnavailable as e:
            if not _gui_run():
                raise
            # the GUI is where the address is fixed (Manage DBs > PostgreSQL)
            # or PostgreSQL turned off: it opens, and a scrape reports the
            # same reason until the server can be used
            logging.getLogger("shared").warning(
                f"{e} The GUI opens anyway: start the server, or change or turn off "
                "PostgreSQL under Manage DBs > PostgreSQL."
            )
            return
        logging.getLogger("shared").info(
            f"Using the PostgreSQL database at {postgres.describe()} "
            f"(server version {version})"
        )


def _gui_run() -> bool:
    try:
        import ofscraper.utils.settings as settings

        return bool(getattr(settings.get_args(), "gui", False))
    except Exception:
        return False


def _gui_tab_window() -> bool:
    """The GUI's tab window: it only starts each site's GUI process."""
    if not _gui_run():
        return False
    try:
        from ofscraper.gui import site_context

        return not site_context.is_child() and site_context.tabs_enabled()
    except Exception:
        return False


def check_dry_run():
    """Refuse a dry run that can't be one, before anything connects."""
    import ofscraper.utils.dry_run as dry_run

    if dry_run.active() and dry_run.refuse_reason():
        logging.getLogger("shared").error(dry_run.refuse_reason())
        raise SystemExit(2)


def main():
    exit_status.reset()
    try:
        # before the --profiles daemon too, so a dry run is checked there
        check_dry_run()
        import ofscraper.utils.settings as settings

        args = settings.get_args()
        if getattr(args, "profiles", None):
            from ofscraper.commands.scraper.multi_profile import run_multi_profile_daemon

            run_multi_profile_daemon(args)
            exit_manager.shutdown()
            raise SystemExit(exit_status.OK)
        check_database()
        start_manager()
    except SystemExit as exc:
        if exc.code in {
            exit_status.AUTH,
            exit_status.UNAVAILABLE,
            exit_status.INTERRUPTED,
        }:
            exit_manager.shutdown()
        raise
    except KeyboardInterrupt as exc:
        console.get_shared_console().print("handling force closing of script")
        try:
            # the ordinary shutdown closes the logs, so Discord gets what is
            # queued (the "stopped" summary); a second Ctrl+C skips that, so
            # it isn't held back here
            exit_manager.shutdown()
        except KeyboardInterrupt:
            with exit_context.DelayedKeyboardInterrupt():
                exit_manager.forcedShutDown()
        if not isinstance(exc, exit_context.SigtermInterrupt):
            raise SystemExit(exit_status.INTERRUPTED)
        return
    except Exception as E:
        logging.getLogger("shared").debug(traceback.format_exc())
        logging.getLogger("shared").error(E)
        try:
            with exit_context.DelayedKeyboardInterrupt():
                exit_manager.shutdown()
        except KeyboardInterrupt:
            with exit_context.DelayedKeyboardInterrupt():
                exit_manager.forcedShutDown()
            raise SystemExit(exit_status.INTERRUPTED)
        # The run failed; don't report success to scripts and schedulers
        import ofscraper.db.postgres as postgres

        if isinstance(E, postgres.PostgresUnavailable):
            raise SystemExit(exit_status.CONFIG)
        from ofscraper.utils.checkers import LoginRejected

        if isinstance(E, LoginRejected):
            raise SystemExit(exit_status.AUTH)
        raise SystemExit(exit_status.ERROR)
    raise SystemExit(exit_status.code())
