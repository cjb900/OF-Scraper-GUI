"""Privacy mode's locked Configuration fields say why they can't be edited.

With Privacy mode on, the webhook, save location and other private fields are
read-only. A field with a value shows "[Hidden for Privacy]", but an empty one
looked like a normal blank box that ignored typing. A locked field now shows a
grey hint, and its own placeholder comes back when Privacy mode is turned off.
"""

from types import SimpleNamespace

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from ofscraper.gui.dialogs.config_dialog import ConfigPage  # noqa: E402
from ofscraper.gui.utils.privacy_mode import (  # noqa: E402
    PRIVACY_EDIT_HINT,
    PRIVACY_PLACEHOLDER,
)

WEBHOOK_HINT = "https://discord.com/api/webhooks/..."


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def page(**values):
    widgets = {}
    for key, text in values.items():
        w = QLineEdit()
        w.setPlaceholderText(WEBHOOK_HINT if key == "discord" else "")
        w.setText(text)
        widgets[key] = w
    widgets["metadata"] = QLineEdit("{configpath}/{profile}/.data/{model_id}")
    return SimpleNamespace(_widgets=widgets, _privacy_actual={})


def test_empty_locked_field_says_why(qapp):
    p = page(discord="")
    ConfigPage._apply_privacy_mask(p, True)
    w = p._widgets["discord"]
    assert w.isReadOnly()
    assert w.text() == ""
    assert w.placeholderText() == PRIVACY_EDIT_HINT == "Hidden by Privacy mode — turn it off to edit"


def test_turning_privacy_off_restores_the_field(qapp):
    p = page(discord="https://discord.com/api/webhooks/1/abc")
    ConfigPage._apply_privacy_mask(p, True)
    w = p._widgets["discord"]
    assert w.text() == PRIVACY_PLACEHOLDER
    ConfigPage._apply_privacy_mask(p, True)  # applied twice, as on a reload
    ConfigPage._apply_privacy_mask(p, False)
    assert not w.isReadOnly()
    assert w.text() == "https://discord.com/api/webhooks/1/abc"
    assert w.placeholderText() == WEBHOOK_HINT


def test_fields_privacy_doesnt_cover_stay_editable(qapp):
    p = page(discord="")
    ConfigPage._apply_privacy_mask(p, True)
    metadata = p._widgets["metadata"]
    assert not metadata.isReadOnly()
    assert metadata.placeholderText() != PRIVACY_EDIT_HINT
