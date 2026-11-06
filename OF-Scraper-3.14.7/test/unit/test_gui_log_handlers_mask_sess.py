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
from ofscraper.utils.logs.classes.classes import LogFileFormatter  # noqa: E402

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


# the normal log file's format, from utils/logs/other.py
NORMAL_LOG_FMT = r" %(asctime)s:\[%(module)s.%(funcName)s:%(lineno)d]  %(message)s"


def test_verbose_log_keeps_the_location_like_the_normal_log(verbose_log):
    handler, folder = verbose_log
    rec = logging.LogRecord(
        "shared", logging.DEBUG, "sessionmanager.py", 584, "a plain line", None, None,
        func="requests",
    )
    handler.handle(rec)
    handler.flush()
    (path,) = folder.rglob("ofscraper_gui_verbose_*.log")
    written = path.read_text(encoding="utf-8").splitlines()[-1]
    assert "[sessionmanager.requests:584]" in written
    normal = LogFileFormatter(NORMAL_LOG_FMT, "%Y-%m-%d %H:%M:%S").format(rec)
    assert written == normal


# -- Privacy mode: model names and ids ---------------------------------------


def load_models(monkeypatch, subs):
    monkeypatch.setattr(pm, "_KNOWN_CACHE", {"key": None, "names": None, "ids": None})
    monkeypatch.setattr(
        manager_mod,
        "Manager",
        SimpleNamespace(
            _model_manager=SimpleNamespace(_all_subs_dict=subs),
            _profile_manager=SimpleNamespace(model_managers={}),
        ),
    )


@pytest.fixture
def loaded_model(monkeypatch):
    load_models(monkeypatch, {"realname": SimpleNamespace(id=MODEL_ID)})


def test_model_id_inside_sess_does_not_split_it(loaded_model, privacy):
    # the id rule doesn't match next to a letter or digit, so the whole
    # value is still there for the mask table
    privacy(True)
    out = pm.redact_log_message(DICT_LINE)
    assert "{sess}" in out
    assert "{model_id}" not in out
    for part in SESS.split(str(MODEL_ID)):
        assert part not in out
    # model ids elsewhere in the line are still hidden
    assert pm.redact_log_message(f"user {MODEL_ID}") == "user {model_id}"
    assert pm.redact_log_message(f"/.data/{MODEL_ID}/user_data.db") == "/.data/{model_id}/user_data.db"


CREATOR_LINES = [
    "Downloading from {name}",
    "saved to /data/{name}/Posts/Videos/clip.mp4",
    "GET https://onlyfans.com/{name}/media",
]


@pytest.mark.parametrize("name", ["happiness_jo", "pippa.rose"])
@pytest.mark.parametrize("line", CREATOR_LINES)
def test_home_folder_name_inside_a_creator_name_doesnt_expose_it(
    monkeypatch, privacy, name, line
):
    # home folder "pi": its mask matches anywhere, and used to cut into the
    # creator name before the name rule could hide it
    load_models(monkeypatch, {name: SimpleNamespace(id=55512345)})
    monkeypatch.setattr(sensitive.paths, "get_username", lambda: "pi")
    privacy(True)
    out = pm.redact_log_message(line.format(name=name))
    assert "{model}" in out
    assert "{home_directory}" not in out
    for piece in name.split("pi"):
        if len(piece) >= 3:
            assert piece not in out


@pytest.mark.parametrize("line", CREATOR_LINES)
def test_creator_name_holding_the_users_id_doesnt_expose_it(monkeypatch, privacy, line):
    # me.py registers the user's own id as a plain pattern that matches anywhere
    name = "creator123456789x"
    load_models(monkeypatch, {name: SimpleNamespace(id=55512345)})
    sensitive.add_sensitive_pattern(123456789, "userid")
    privacy(True)
    out = pm.redact_log_message(line.format(name=name))
    assert "{model}" in out
    assert "creator" not in out
    assert "userid" not in out


def test_handle_made_of_a_letter_and_the_model_id_is_still_hidden(monkeypatch, privacy):
    # the id rule no longer matches next to a letter; the name rule covers it
    load_models(monkeypatch, {"u1234567": SimpleNamespace(id=1234567)})
    privacy(True)
    assert pm.redact_log_message("Downloading from u1234567") == "Downloading from {model}"
    assert pm.redact_log_message("model id 1234567 done") == "model id {model_id} done"
