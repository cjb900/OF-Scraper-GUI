"""Saving the Configuration page keeps what it didn't change, and applies.

- A space replacer of " ", size limits of 0 and an empty black list showed
  as empty boxes and were saved back as "" (found while testing h16).
- The run's settings kept the dynamic mode from when a scrape last started,
  so Test Credentials signed with the old mode after a save.
"""

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

import ofscraper.gui.utils.config_validation as config_validation  # noqa: E402
import ofscraper.utils.config.config as config_mod  # noqa: E402
import ofscraper.utils.config.file as config_file  # noqa: E402
import ofscraper.utils.settings as run_settings  # noqa: E402
from ofscraper.gui.dialogs import config_dialog  # noqa: E402

STORED = {
    "file_options": {"space_replacer": " ", "dir_format": "{model_username}", "file_format": "{filename}.{ext}"},
    "content_filter_options": {"file_size_max": 0, "file_size_min": 0},
    "advanced_options": {"default_black_list": [], "default_user_list": "main", "dynamic-mode-default": "digital"},
}


@pytest.fixture
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def page(qapp, monkeypatch):
    saved, refreshed = [], []
    monkeypatch.setattr(config_file, "write_config", lambda config: saved.append(config))
    monkeypatch.setattr(config_validation, "show_config_validation_dialog", lambda *a, **k: True)
    monkeypatch.setattr(run_settings, "update_settings", lambda: refreshed.append(True))
    monkeypatch.setattr(
        config_dialog.QMessageBox, "information", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(config_dialog.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    import copy

    stored = copy.deepcopy(STORED)
    monkeypatch.setattr(config_mod, "read_config", lambda update=False: stored)
    p = config_dialog.ConfigPage()
    p._config = stored
    p._load_config()
    p.saved, p.refreshed = saved, refreshed
    yield p
    p.deleteLater()


def test_saving_unchanged_keeps_spaces_zeros_and_lists(page):
    page._save_config()
    out = page.saved[-1]
    assert out["file_options"]["space_replacer"] == " "
    assert out["content_filter_options"]["file_size_max"] == 0
    assert out["content_filter_options"]["file_size_min"] == 0
    assert out["advanced_options"]["default_black_list"] == []


def test_a_save_refreshes_the_run_settings(page):
    page._save_config()
    assert page.refreshed == [True]
