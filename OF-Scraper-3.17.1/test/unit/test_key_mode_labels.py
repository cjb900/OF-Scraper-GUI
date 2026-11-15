"""The Key Mode list marks manual as recommended and the remote modes as not working."""

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QLocale, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication, QComboBox  # noqa: E402

from ofscraper.gui.utils import key_mode_warning as kmw  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_labels():
    assert kmw.key_mode_label("manual") == "manual (recommended)"
    for mode in ("cdrm", "cdrm2", "keydb"):
        assert kmw.key_mode_label(mode) == f"{mode} (currently not working)"


def test_reasons_match_what_happens():
    import ofscraper.utils.config.data as data

    assert "offline" in kmw.not_working_reason("cdrm")
    for mode in ("cdrm2", "keydb"):
        assert "use manual" in kmw.not_working_reason(mode)
        # the config reader really does run them as manual
        assert data.get_key_mode(config={"cdm_options": {"key-mode-default": mode}}) == "manual"
    assert kmw.not_working_reason("manual") == ""


def test_scrape_warning_says_it_isnt_working():
    assert "isn't working right now" in kmw._warning_body("keydb")


def test_list_shows_labels_but_keeps_plain_values(qapp):
    from ofscraper.gui.dialogs.config_dialog import ConfigPage

    combo = QComboBox()
    combo.addItems(["manual", "cdrm", "cdrm2", "keydb"])
    ConfigPage._label_key_modes(combo)
    shown = [combo.itemDelegate().displayText(combo.itemText(i), QLocale()) for i in range(4)]
    assert shown == ["manual (recommended)", "cdrm (currently not working)",
                     "cdrm2 (currently not working)", "keydb (currently not working)"]
    combo.setCurrentIndex(3)
    assert combo.currentText() == "keydb"  # what gets saved
    assert "manual instead" in combo.itemData(3, Qt.ItemDataRole.ToolTipRole)
    assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) is None
