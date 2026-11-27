"""The Fansly auth page can save edits, clear the credentials and open the file."""

import json

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import ofscraper.gui.dialogs.fansly_auth_dialog as page_mod  # noqa: E402
import ofscraper.sites.fansly.auth as fansly_auth  # noqa: E402

TOKEN = "T" * 80
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0"


@pytest.fixture(scope="module")
def qapp():
    # keep a reference: an unreferenced QApplication is freed at once
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp, tmp_path, monkeypatch):
    auth_file = tmp_path / "fansly_auth.json"
    auth_file.write_text(json.dumps({"authorization_token": TOKEN, "user_agent": UA}))
    monkeypatch.setattr(fansly_auth, "auth_path", lambda: auth_file)
    monkeypatch.setattr(fansly_auth, "_cache", {"path": None, "mtime": None, "auth": None})
    browser = tmp_path / "browser_profile"
    (browser / "Local Storage").mkdir(parents=True)
    monkeypatch.setattr(page_mod, "_browser_profile_dir", lambda: str(browser))
    p = page_mod.FanslyAuthPage()
    p.auth_file, p.browser_dir = auth_file, browser
    return p


def saved(page):
    return json.loads(page.auth_file.read_text())


def test_fields_are_editable(page):
    assert not page.token_input.isReadOnly() and not page.ua_input.isReadOnly()
    assert page.token_input.text() == TOKEN


def test_save_keeps_an_edit_without_testing(page):
    page.ua_input.setText(UA + " Edg/126.0.0.0")
    page._save_only()
    assert saved(page)["user_agent"].endswith("Edg/126.0.0.0")
    assert "not checked" in page.status_label.text()


def test_incomplete_save_asks_first(page, monkeypatch):
    page.token_input.setText("short")
    monkeypatch.setattr(page_mod.QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.No)
    page._save_only()
    assert saved(page)["authorization_token"] == TOKEN
    monkeypatch.setattr(page_mod.QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    page._save_only()
    assert saved(page)["authorization_token"] == "short"


class FakeBox:
    """QMessageBox stand-in: clicks Clear or Cancel; keeps or unticks the checkbox."""

    choice, sign_out = "Clear", True

    class Icon:
        Warning = None

    class ButtonRole:
        DestructiveRole = None

    class StandardButton:
        Cancel = None

    def __init__(self, *a):
        self._buttons, self._cb = {}, None

    def setWindowTitle(self, *a): ...
    def setIcon(self, *a): ...
    def setText(self, *a): ...

    def setCheckBox(self, cb):
        self._cb = cb

    def addButton(self, label, *a):
        self._buttons[label] = object()
        return self._buttons[label]

    def exec(self):
        self._cb.setChecked(FakeBox.sign_out)

    def clickedButton(self):
        return self._buttons.get(FakeBox.choice)


@pytest.mark.parametrize("sign_out", [True, False])
def test_clear_removes_the_credentials(page, monkeypatch, sign_out):
    monkeypatch.setattr(page_mod, "QMessageBox", FakeBox)
    monkeypatch.setattr(FakeBox, "choice", "Clear")
    monkeypatch.setattr(FakeBox, "sign_out", sign_out)
    page._clear()
    assert saved(page)["authorization_token"] == "" and saved(page)["user_agent"] == ""
    assert page.token_input.text() == "" and page.ua_input.text() == ""
    assert page.browser_dir.exists() is not sign_out


def test_cancelled_clear_changes_nothing(page, monkeypatch):
    monkeypatch.setattr(page_mod, "QMessageBox", FakeBox)
    monkeypatch.setattr(FakeBox, "choice", "Cancel")
    page._clear()
    assert saved(page)["authorization_token"] == TOKEN
    assert page.browser_dir.exists()


def test_open_file_when_missing_says_so(page):
    page.auth_file.unlink()
    page._open_file()
    assert "doesn't exist" in page.status_label.text()
