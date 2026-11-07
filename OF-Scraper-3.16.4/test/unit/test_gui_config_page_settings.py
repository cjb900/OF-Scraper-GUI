"""The GUI's Config page lists and saves settings the way the scraper reads them.

1. Given another name for the digitalcriminals rule in config.json ("dc",
   "digitalcriminals", ...), when the Config page is shown, then that rule is
   selected, listed once as "digital", and saving writes "digital" (as the
   CLI config menu does, fork #226).
2. Given cache-mode "api_disabled" in config.json, when the Config page is
   shown and saved, then it stays "api_disabled" (fork #200).

The scraper side of both (the CLI menu, reading config.json) is covered by
the fork's own tests.
"""

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.config.file as config_file  # noqa: E402

NAMES = ["dc", "digital", "digitals", "digitalcriminal", "digitalcriminals", "DC"]


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


def test_gui_config_page_lists_the_cli_menu_rules():
    # every rule the scraper offers is on the page, by its menu name
    pytest.importorskip("PyQt6.QtWidgets")
    from ofscraper.gui.dialogs import config_dialog
    from ofscraper.utils import const

    names = {config_dialog._dynamic_menu_name(rule) for rule in const.DYNAMIC_OPTIONS}
    assert names == {"digital", "manual", "generic", "datawhores", "xagler", "rafa"}


def test_gui_config_page_keeps_cache_mode_api_disabled(page):
    page.load({"advanced_options": {"cache-mode": "api_disabled"}})
    assert page._widgets["cache-mode"].currentText() == "api_disabled"
    page._save_config()
    assert page.saved, f"the page didn't save: {page.messages}"
    assert page.saved[-1]["advanced_options"]["cache-mode"] == "api_disabled"
