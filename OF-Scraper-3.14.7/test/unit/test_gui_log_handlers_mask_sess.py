"""The GUI's own log handlers must mask the session cookie too.

The GUI console handlers and the Verbose Log file used a plain
logging.Formatter, so the session value showed in full there even after
read_auth() registered it.
"""

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.app as gui_app  # noqa: E402
import ofscraper.gui.utils.workflow as workflow_mod  # noqa: E402
import ofscraper.managers.manager as manager_mod  # noqa: E402
import ofscraper.utils.auth.file as auth_file  # noqa: E402
import ofscraper.utils.config.data as config_data  # noqa: E402
import ofscraper.utils.logs.utils.sensitive as sensitive  # noqa: E402
import ofscraper.utils.paths.common as common_paths  # noqa: E402
from ofscraper.gui.main_window import MainWindow  # noqa: E402
from ofscraper.gui.signals import app_signals  # noqa: E402
from ofscraper.gui.utils import privacy_mode as pm  # noqa: E402

pytestmark = pytest.mark.unit

# fake value; holds a 9-digit run that matches a loaded model id below
SESS = "fakesess168143417abc+def/XYZ"
MODEL_ID = 168143417

# the forms the value is logged in: the failed-request header dump (a dict
# repr holding the cookie header) and a cookie dict
COOKIE_LINE = "requests headers " + str(
    {"cookie": f"auth_id=1;sess={SESS};auth_uid_=1;", "user-agent": "ua"}
)
DICT_LINE = "cookies " + str({"sess": SESS, "auth_id": "1"})


@pytest.fixture(autouse=True)
def registered_sess(monkeypatch):
    monkeypatch.setattr(sensitive, "_USER_ADDED_PATTERNS", {})
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: None)
    auth_file.hide_secrets({"sess": SESS})


@pytest.fixture
def privacy():
    def set_to(value):
        pm.set_privacy_mode(value, persist=False, emit=False)

    before = pm.is_privacy_mode()
    yield set_to
    set_to(before)


@pytest.fixture
def console_lines():
    got = []

    def slot(level, msg):
        got.append(msg)

    app_signals.log_message.connect(slot)
    yield got
    app_signals.log_message.disconnect(slot)


def record(msg, level=logging.INFO, name="shared"):
    return logging.LogRecord(name, level, __file__, 1, msg, None, None)


def shown_in_console(lines):
    # what ConsoleLogWidget._append_log puts on screen
    return [pm.redact_log_message(line) for line in lines]


# -- GUI console: app.py handler (on "shared" and "shared_other") -----------


@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
def test_app_console_handler_masks_sess_with_privacy_off(console_lines, privacy, line):
    privacy(False)
    gui_app._make_gui_log_handler().handle(record(line))
    (out,) = shown_in_console(console_lines)
    assert SESS not in out
    assert "{sess}" in out


def test_app_console_handler_still_hides_cookie_with_privacy_on(console_lines, privacy):
    privacy(True)
    gui_app._make_gui_log_handler().handle(record(COOKIE_LINE))
    (out,) = shown_in_console(console_lines)
    assert SESS not in out
    assert "sess={hidden}" in out


# -- GUI console: workflow.py handler (on "shared_other") --------------------


@pytest.fixture
def workflow_handler():
    workflow_mod._install_gui_log_handler()
    try:
        yield workflow_mod._gui_log_handler
    finally:
        workflow_mod._uninstall_gui_log_handler()


@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
def test_workflow_console_handler_masks_sess_with_privacy_off(
    workflow_handler, console_lines, privacy, line
):
    privacy(False)
    workflow_handler.handle(record(line, name="shared_other"))
    (out,) = shown_in_console(console_lines)
    assert SESS not in out
    assert "{sess}" in out


def test_workflow_console_handler_still_hides_cookie_with_privacy_on(
    workflow_handler, console_lines, privacy
):
    privacy(True)
    workflow_handler.handle(record(COOKIE_LINE, name="shared_other"))
    (out,) = shown_in_console(console_lines)
    assert SESS not in out
    assert "sess={hidden}" in out


# -- Verbose Log file (main_window._apply_verbose_log) -----------------------


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
        (handler,) = [h for h in logger.handlers if getattr(h, "_gui_verbose_handler", False)]
        yield handler, tmp_path
    finally:
        MainWindow._apply_verbose_log(win, False)
        logger.setLevel(level_before)
        for h, lvl in levels_before.items():
            h.setLevel(lvl)


@pytest.mark.parametrize("line", [COOKIE_LINE, DICT_LINE])
def test_verbose_log_file_masks_sess(verbose_log, line):
    handler, folder = verbose_log
    handler.handle(record(f"[bold]{line}[/bold]", level=logging.DEBUG))
    handler.flush()
    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
    text = path.read_text(encoding="utf-8")
    assert SESS not in text
    assert "{sess}" in text
    assert "[bold]" not in text  # Rich markup stripped like the normal log file


# -- Privacy mode: a model id inside the session value -----------------------


@pytest.fixture
def loaded_model(monkeypatch):
    subs = {"realname": SimpleNamespace(id=MODEL_ID)}
    monkeypatch.setattr(
        manager_mod,
        "Manager",
        SimpleNamespace(
            _model_manager=SimpleNamespace(_all_subs_dict=subs),
            _profile_manager=SimpleNamespace(model_managers={}),
        ),
    )


def test_model_id_inside_sess_does_not_split_it(loaded_model, privacy):
    # the mask table runs before model ids are replaced, so the whole value
    # is still there to match
    privacy(True)
    out = pm.redact_log_message(DICT_LINE)
    assert "{sess}" in out
    assert "{model_id}" not in out
    for part in SESS.split(str(MODEL_ID)):
        assert part not in out
    # model ids elsewhere in the line are still hidden
    assert pm.redact_log_message(f"user {MODEL_ID}") == "user {model_id}"
