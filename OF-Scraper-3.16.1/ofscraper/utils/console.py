import sys

from rich.console import Console
from rich.theme import Theme

from ofscraper.utils.args.accessors.output import low_output


def replace_unencodable_output(streams=None):
    """
    Model names and post text can contain emoji. On a stdout/stderr that is not
    UTF-8 (e.g. cp1252 on Windows when output is redirected, or in the bundled
    exe), printing them raised UnicodeEncodeError and aborted the run. Print a
    replacement character instead.
    """
    for stream in streams or (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding in {"utf8", "utf16", "utf32"}:
            continue
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass  # not a TextIOWrapper (e.g. replaced by a test runner)


replace_unencodable_output()

theme = Theme(
    {
        "logging.level.error": "green",
        "logging.level.warning": "green",
        "logging.level.debug": "yellow",
        "logging.level.info": "white",
        "logging.level.traceback": "red",
    }
)

quiet = low_output() is True
shared_console = None

other_console = None


def get_console():
    if not low_output():
        return get_shared_console()
    return get_other_console()


def get_shared_console():
    global shared_console
    if not shared_console:
        shared_console = Console(theme=theme, quiet=quiet, markup=True)

    return shared_console


def get_other_console():
    global other_console
    if not other_console:
        other_console = Console(theme=theme, markup=True)
    return other_console


def update_shared(console_):
    global shared_console
    shared_console = console_
