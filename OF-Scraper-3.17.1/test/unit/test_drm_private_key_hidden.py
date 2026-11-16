"""DRM Key Creation never puts the device's private key in the log or output box."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui.dialogs.drm_dialog import KEY_HIDDEN, PrivateKeyFilter  # noqa: E402

KEYDIVE = [
    "2026-11-15 18:54:30 [I] Cdm: Received RSA private key:",
    "-----BEGIN RSA PRIVATE KEY-----",
    "MIIEowIBAAKCAQEAsecretsecretsecret",
    "/10lmoresecretmoresecret",
    "-----END RSA PRIVATE KEY-----",
    "2026-11-15 18:54:30 [I] Cdm: Received client ID:",
]


def run(lines, f=None):
    f = f or PrivateKeyFilter()
    return [out for out in (f.filter(line) for line in lines) if out is not None]


def test_key_block_is_replaced_by_one_line():
    out = run(KEYDIVE)
    assert out == [KEYDIVE[0], KEY_HIDDEN, KEYDIVE[-1]]
    assert not any("secret" in line for line in out)


@pytest.mark.parametrize("kind", ["PRIVATE KEY", "EC PRIVATE KEY", "ENCRYPTED PRIVATE KEY"])
def test_other_key_types(kind):
    out = run([f"-----BEGIN {kind}-----", "abcSECRET", f"-----END {kind}-----", "next"])
    assert out == [KEY_HIDDEN, "next"]


def test_key_on_one_line():
    line = "key: -----BEGIN PRIVATE KEY-----SECRET-----END PRIVATE KEY----- done"
    assert run([line]) == [f"key: {KEY_HIDDEN} done"]


def test_public_text_is_untouched():
    lines = ["-----BEGIN CERTIFICATE-----", "MIIC...", "-----END CERTIFICATE-----", "OK"]
    assert run(lines) == lines


def test_on_line_filters_before_logging(monkeypatch):
    from ofscraper.gui.dialogs import drm_dialog

    logged, shown = [], []
    monkeypatch.setattr(drm_dialog.log, "info", lambda fmt, line: logged.append(line))

    class Box:
        def appendPlainText(self, t):
            shown.append(t)

        def verticalScrollBar(self):
            class SB:
                def setValue(self, v): ...
                def maximum(self): return 0
            return SB()

    class Page:  # stands in for the widget: _on_line only uses these
        pass

    page = Page()
    page.output_text = Box()
    for line in KEYDIVE:
        drm_dialog.DRMKeyPage._on_line(page, line)
    assert not any("secret" in t for t in logged + shown)
    assert KEY_HIDDEN in logged and KEY_HIDDEN in shown
