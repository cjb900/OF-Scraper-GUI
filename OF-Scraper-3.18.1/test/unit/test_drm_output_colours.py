"""The DRM Key Creation log shows the tool's output without colour codes."""

import pytest

pytest.importorskip("PyQt6")

from ofscraper.gui.dialogs.drm_dialog import strip_ansi  # noqa: E402


@pytest.mark.parametrize("raw, clean", [
    ("\x1b[32m2026-11-15 18:35:49\x1b[0m \x1b[1;34m[I]\x1b[0m done",
     "2026-11-15 18:35:49 [I] done"),
    ("\x1b[35mCore:\x1b[0m \x1b[37m\x1b[37mExporting file\x1b[0m\x1b[0m", "Core: Exporting file"),
    ("\x1b[2K\x1b[1Gprogress 50%", "progress 50%"),
    ("plain text, no codes", "plain text, no codes"),
    ("stray \x1b escape", "stray  escape"),
    ("", ""),
])
def test_strip_ansi(raw, clean):
    assert strip_ansi(raw) == clean
