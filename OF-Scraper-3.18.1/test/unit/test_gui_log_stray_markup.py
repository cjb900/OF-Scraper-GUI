"""GUI log paths with a line holding broken Rich markup ("[/bold]").

The Verbose Log file uses LogFileFormatter, so it needs the same fallback
as the normal log file. The GUI console never parses markup with Rich, and
GUI mode must still remove the terminal handlers now that they are a
RichHandler subclass.
"""

import logging
from types import SimpleNamespace

import pytest
from rich.logging import RichHandler

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.app as gui_app  # noqa: E402
import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
import ofscraper.utils.config.data as config_data  # noqa: E402
import ofscraper.utils.logs.stdout as stdout_mod  # noqa: E402
import ofscraper.utils.logs.utils.sensitive as sensitive  # noqa: E402
import ofscraper.utils.paths.common as common_paths  # noqa: E402
from ofscraper.gui.main_window import MainWindow  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402
from ofscraper.gui.utils import privacy_mode as pm  # noqa: E402

pytestmark = pytest.mark.unit

STRAY = "done [/bold] here"


@pytest.fixture(autouse=True)
def no_run_masks(monkeypatch):
    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)


def record(msg, level=logging.INFO, name="shared"):
    return logging.LogRecord(
        name, level, "sessionmanager.py", 584, msg, None, None, func="requests"
    )


# -- Verbose Log file ---------------------------------------------------------


@pytest.fixture
def verbose_log(monkeypatch, tmp_path):
    monkeypatch.setattr(common_paths, "get_log_folder", lambda: tmp_path)
    monkeypatch.setattr(config_data, "get_main_profile", lambda: "main")
    logger = logging.getLogger("shared")
    level_before = logger.level
    levels_before = {h: h.level for h in logger.handlers}
    win = SimpleNamespace()
    MainWindow._apply_verbose_log(win, True)
    try:
        (handler,) = [
            h for h in logger.handlers if getattr(h, "_gui_verbose_handler", False)
        ]
        yield handler, tmp_path
    finally:
        MainWindow._apply_verbose_log(win, False)
        logger.setLevel(level_before)
        for h, lvl in levels_before.items():
            h.setLevel(lvl)


def test_verbose_log_keeps_a_line_with_a_stray_closing_tag(verbose_log):
    handler, folder = verbose_log
    raised = []
    handler.handleError = lambda rec: raised.append(rec)
    handler.handle(record(STRAY, level=logging.DEBUG))
    handler.flush()
    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert not raised
    assert lines and lines[-1].endswith(":[sessionmanager.requests:584]  " + STRAY)
    assert "\\[" not in lines[-1]


# -- GUI console --------------------------------------------------------------


@pytest.fixture
def console_lines():
    got = []

    def slot(level, msg):
        got.append(msg)

    app_signals.log_message.connect(slot)
    yield got
    app_signals.log_message.disconnect(slot)


def test_app_console_handler_shows_a_line_with_a_stray_closing_tag(console_lines):
    gui_app._make_gui_log_handler().handle(record(STRAY))
    (out,) = [pm.redact_log_message(line) for line in console_lines]
    assert out.endswith(STRAY)


def test_workflow_console_handler_shows_a_line_with_a_stray_closing_tag(
    console_lines,
):
    workflow_mod._install_gui_log_handler()
    try:
        workflow_mod._gui_log_handler.handle(record(STRAY, name="shared_other"))
    finally:
        workflow_mod._uninstall_gui_log_handler()
    (out,) = [pm.redact_log_message(line) for line in console_lines]
    # its own regex drops the known tag, the rest of the line stays
    assert out.endswith("done  here")


# -- GUI mode removes the terminal handlers -----------------------------------


def test_gui_mode_removes_the_terminal_handlers():
    logger = logging.getLogger("shared")
    handlers_before = list(logger.handlers)
    level_before = logger.level
    try:
        stdout_mod.add_stdout_handler(logger, clear=False)
        added = [h for h in logger.handlers if h not in handlers_before]
        assert any(isinstance(h, RichHandler) for h in added)
        workflow_mod._strip_rich_stdout_handlers()
        assert not any(isinstance(h, RichHandler) for h in logger.handlers)
    finally:
        logger.handlers[:] = handlers_before
        logger.setLevel(level_before)
