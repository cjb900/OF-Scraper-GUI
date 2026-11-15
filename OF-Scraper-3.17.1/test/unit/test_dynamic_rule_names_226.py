"""Dynamic rule names in the config menus and the request code.

1. Given no dynamic rule in config.json, when the CLI config menu or the GUI
   Config page is shown, then the rule the default ("digital") picks is
   offered and selected.
2. Given another name for that rule ("dc", "digitalcriminals", ...), when the
   menu or page is shown, then that rule is selected, listed once as
   "digital", and saving writes "digital".
3. Given "digitalcriminal" in config.json, when it is read, then it is kept
   rather than replaced by the default, as the request code accepts it.
"""

import pytest

pytestmark = pytest.mark.unit

import ofscraper.prompts.prompt_groups.config as config_prompts  # noqa: E402
import ofscraper.utils.config.data as data  # noqa: E402
import ofscraper.utils.config.file as config_file  # noqa: E402

NAMES = ["dc", "digital", "digitals", "digitalcriminal", "digitalcriminals", "DC"]


class _Stop(Exception):
    pass


@pytest.fixture
def config(monkeypatch):
    cfg = {}
    monkeypatch.setattr(config_file, "open_config", lambda *a, **k: cfg)
    return cfg


def _dynamic_question(monkeypatch):
    asked = []

    def capture(*questions, **kwargs):
        asked.extend(questions)
        raise _Stop

    monkeypatch.setattr(config_prompts.promptClasses, "batchConverter", capture)
    with pytest.raises(_Stop):
        config_prompts.advanced_config()
    return next(q for q in asked if q.get("name") == "dynamic-mode-default")


def test_menu_offers_and_selects_the_default_rule(config, monkeypatch):
    question = _dynamic_question(monkeypatch)
    assert question["default"] in question["choices"]
    assert question["default"] == "digital"


@pytest.mark.parametrize("name", NAMES)
def test_menu_selects_the_rule_a_name_picks(config, monkeypatch, name):
    config["advanced_options"] = {"dynamic-mode-default": name}
    question = _dynamic_question(monkeypatch)
    assert question["default"] == "digital"
    assert question["choices"].count("digital") == 1
    assert "digitalcriminals" not in question["choices"]


def test_menu_choices_have_no_removed_rules(config, monkeypatch):
    question = _dynamic_question(monkeypatch)
    assert not {"dv", "dev", "deviint"} & set(question["choices"])


def test_get_dynamic_keeps_digitalcriminal():
    cfg = {"advanced_options": {"dynamic-mode-default": "digitalcriminal"}}
    assert data.get_dynamic(config=cfg) == "digitalcriminal"


def test_request_code_maps_every_name_to_its_rule():
    import ofscraper.utils.const as const

    for name in const.DYNAMIC_ALIASES:
        assert data.get_dynamic(
            config={"advanced_options": {"dynamic-mode-default": name}}
        ) == name
        assert const.DYNAMIC_ALIASES[name] == "digitalcriminals"


# The GUI's Config page


@pytest.fixture
def page(monkeypatch):
    QtWidgets = pytest.importorskip("PyQt6.QtWidgets")
    import ofscraper.gui.utils.config_validation as config_validation
    import ofscraper.utils.config.config as config_mod
    from ofscraper.gui.dialogs import config_dialog

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    saved = []
    monkeypatch.setattr(config_file, "write_config", lambda c: saved.append(c))
    monkeypatch.setattr(
        config_validation, "show_config_validation_dialog", lambda *a, **k: True
    )
    # the page reports with modal message boxes; record them instead
    messages = []

    class Boxes:
        StandardButton = QtWidgets.QMessageBox.StandardButton

        @staticmethod
        def _record(kind):
            def box(parent, title, text, *a, **k):
                messages.append((kind, title, text))
                return QtWidgets.QMessageBox.StandardButton.Ok

            return box

    for kind in ("information", "warning", "critical", "question"):
        setattr(Boxes, kind, staticmethod(Boxes._record(kind)))
    monkeypatch.setattr(config_dialog, "QMessageBox", Boxes)
    p = config_dialog.ConfigPage()

    def load(cfg):
        monkeypatch.setattr(config_mod, "read_config", lambda update=False: cfg)
        monkeypatch.setattr(config_mod, "reset_config_cache", lambda: None)
        p._load_config()

    p.load = load
    p.saved = saved
    p.messages = messages
    yield p
    p.deleteLater()


def _combo_items(combo):
    return [combo.itemText(i) for i in range(combo.count())]


@pytest.mark.parametrize("name", NAMES)
def test_gui_config_page_selects_and_saves_digital(page, name):
    page.load({"advanced_options": {"dynamic-mode-default": name}})
    combo = page._widgets["dynamic-mode-default"]
    assert combo.currentText() == "digital"
    assert _combo_items(combo).count("digital") == 1
    page._save_config()
    assert page.saved, f"the page didn't save: {page.messages}"
    assert page.saved[-1]["advanced_options"]["dynamic-mode-default"] == "digital"


def test_gui_config_page_keeps_other_rules(page):
    page.load({"advanced_options": {"dynamic-mode-default": "rafa"}})
    assert page._widgets["dynamic-mode-default"].currentText() == "rafa"
