"""DRM Key Creation hides the client ID and keybox dumps too, not only the
private key: KeyDive prints them as JSON under a "Received ...:" heading."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui.dialogs.drm_dialog import (  # noqa: E402
    DUMP_HIDDEN,
    KEY_HIDDEN,
    PrivateKeyFilter,
)

# the shape of a real run, with made-up values
SECRETS = [
    "c3RhYmxlLWlkLXZhbHVlLWZvci10ZXN0",
    "0123456789abcdef0123456789abcdef",
    "ZGV2aWNlLWlkLXZhbHVlLWZvci10aGUtdGVzdC1vbmx5",
    "MIIEowIBAAKCAQEAfakefakefakefakefakefakefakefakefakefakefakefakefake",
    "Android SDK built for x86_64",
    "serial_number",
]
OUTPUT = """\
2026-01-02 03:04:05 [I] Core: Successfully attached hook to process: 1732
2026-01-02 03:04:06 [I] Cdm: Received encrypted keybox:
{
  "stable_id": "c3RhYmxlLWlkLXZhbHVlLWZvci10ZXN0",
  "device_aes_key": "0123456789abcdef0123456789abcdef",
  "device_id": "ZGV2aWNlLWlkLXZhbHVlLWZvci10aGUtdGVzdC1vbmx5"
}
Kaltura app is in the foreground.
2026-01-02 03:04:07 [I] Cdm: Received OEM certificate:
[
  {
    "subject": "CN=leaf",
    "serial_number": 9155532808282438952
  }
]
2026-01-02 03:04:08 [I] Cdm: Received RSA private key:
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEAfakefakefakefakefakefakefakefakefakefakefakefakefake
-----END RSA PRIVATE KEY-----
2026-01-02 03:04:09 [I] Cdm: Received client ID:
{
  "company_name": "Google",
  "model_name": "Android SDK built for x86_64"
}
2026-01-02 03:04:10 [I] Core: Exporting file: device/private_key.pem
""".splitlines()


def run(lines):
    f = PrivateKeyFilter()
    return [out for out in (f.filter(line) for line in lines) if out is not None]


def test_each_dump_becomes_one_note_under_its_heading():
    out = run(OUTPUT)
    assert not any(secret in line for line in out for secret in SECRETS)
    assert out == [
        OUTPUT[0],
        "2026-01-02 03:04:06 [I] Cdm: Received encrypted keybox:",
        DUMP_HIDDEN,
        "Kaltura app is in the foreground.",
        "2026-01-02 03:04:07 [I] Cdm: Received OEM certificate:",
        DUMP_HIDDEN,
        "2026-01-02 03:04:08 [I] Cdm: Received RSA private key:",
        KEY_HIDDEN,
        "2026-01-02 03:04:09 [I] Cdm: Received client ID:",
        DUMP_HIDDEN,
        "2026-01-02 03:04:10 [I] Core: Exporting file: device/private_key.pem",
    ]


def test_ordinary_output_after_a_colon_is_kept():
    lines = ["adb devices:", "List of devices attached", "emulator-5554\tdevice", "OK"]
    assert run(lines) == lines


def test_the_note_survives_rich_markup():
    from rich.text import Text

    assert DUMP_HIDDEN in Text.from_markup(f"[DRM] {DUMP_HIDDEN}").plain
