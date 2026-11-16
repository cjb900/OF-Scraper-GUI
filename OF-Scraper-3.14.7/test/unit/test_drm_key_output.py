"""The DRM key page copied KeyDive's output to the screen and to the log file,
Widevine private key, client ID and keybox included. Sharing a debug log then
handed the keys over."""
import logging

import pytest

pytestmark = pytest.mark.unit

QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from ofscraper.gui.dialogs.drm_dialog import (  # noqa: E402
    KEY_MATERIAL_HIDDEN,
    DRMKeyPage,
    KeyMaterialFilter,
)

# The shape of a real run, with made-up values
SECRETS = [
    "c3RhYmxlLWlkLXZhbHVlLWZvci10ZXN0",
    "0123456789abcdef0123456789abcdef",
    "ZGV2aWNlLWlkLXZhbHVlLWZvci10aGUtdGVzdC1vbmx5",
    "MIIEowIBAAKCAQEAfakefakefakefakefakefakefakefakefakefakefakefakefake",
    "ZmFrZS1rZXktYm9keS1saW5lLXR3by1mb3ItdGhlLXRlc3Q9",
    "Android SDK built for x86_64",
    "serial_number",
]
OUTPUT = """\
🔑 Starting KeyDive...
2026-01-02 03:04:05 [I] Core: Successfully attached hook to process: 1732
🚀 Launching Kaltura Device Info app...
2026-01-02 03:04:06 [I] Cdm: Received encrypted keybox:
{
  "stable_id": "c3RhYmxlLWlkLXZhbHVlLWZvci10ZXN0",
  "device_aes_key": "0123456789abcdef0123456789abcdef",
  "device_id": "ZGV2aWNlLWlkLXZhbHVlLWZvci10aGUtdGVzdC1vbmx5"
}
✅ Kaltura app is in the foreground.
2026-01-02 03:04:07 [I] Cdm: Received OEM certificate:
[
  {
    "subject": "CN=leaf",
    "serial_number": 9155532808282438952,
    "valid_until": "2041-05-07 06:09:05+00:00"
  }
]
2026-01-02 03:04:08 [I] Cdm: Received RSA private key:
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAfakefakefakefakefakefakefakefakefakefakefakefakefake
ZmFrZS1rZXktYm9keS1saW5lLXR3by1mb3ItdGhlLXRlc3Q9
-----END RSA PRIVATE KEY-----
2026-01-02 03:04:09 [I] Cdm: Received client ID:
{
  "company_name": "Google",
  "model_name": "Android SDK built for x86_64",
  "oem_crypto_security_patch_level": 0
}
2026-01-02 03:04:10 [I] Core: Exporting file: device/private_key.pem
🎯 Keys exported: device
""".splitlines()
KEPT = [
    "🔑 Starting KeyDive...",
    "2026-01-02 03:04:05 [I] Core: Successfully attached hook to process: 1732",
    "🚀 Launching Kaltura Device Info app...",
    "✅ Kaltura app is in the foreground.",
    "2026-01-02 03:04:10 [I] Core: Exporting file: device/private_key.pem",
    "🎯 Keys exported: device",
]


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    elif not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    return app


def _filtered(lines):
    key_filter = KeyMaterialFilter()
    return [out for out in map(key_filter.filter, lines) if out is not None]


def test_filter_drops_the_key_material_and_keeps_the_rest():
    out = _filtered(OUTPUT)
    text = "\n".join(out)
    for secret in SECRETS:
        assert secret not in text
    for line in KEPT:
        assert line in out
    # each dump leaves its heading and one placeholder
    assert len([line for line in out if KEY_MATERIAL_HIDDEN in line]) == 4
    assert f"2026-01-02 03:04:08 [I] Cdm: Received RSA private key: {KEY_MATERIAL_HIDDEN}" in out


def test_filter_hides_a_key_block_with_no_heading():
    out = _filtered(
        [
            "before",
            "-----BEGIN PRIVATE KEY-----",
            "MIIEowIBAAKCAQEAfakefakefakefake",
            "-----END PRIVATE KEY-----",
            "after",
        ]
    )
    assert out == ["before", KEY_MATERIAL_HIDDEN, "after"]


def test_filter_leaves_ordinary_output_alone():
    lines = [
        "📦 Installing SDK components: emulator",
        "   URL: https://dl.google.com/android/repository/tools.zip",
        "adb devices:",
        "List of devices attached",
        "emulator-5554\tdevice",
        "   [sdkmanager] [====      ] 10% Computing updates...",
        "",
        "OK",
    ]
    assert _filtered(lines) == lines


def test_key_page_keeps_keys_off_the_screen_and_out_of_the_log(qapp, caplog):
    page = DRMKeyPage()
    with caplog.at_level(logging.INFO, logger="shared"):
        for line in OUTPUT:
            page._on_line(line)
    shown = page.output_text.toPlainText()
    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in SECRETS:
        assert secret not in shown
        assert secret not in logged
    for line in KEPT:
        assert line in shown
        assert line in logged
