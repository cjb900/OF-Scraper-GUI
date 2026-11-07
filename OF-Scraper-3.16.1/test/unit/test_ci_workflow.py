from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

WORKFLOW = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "codecov.yml"


@pytest.mark.skipif(not WORKFLOW.exists(), reason="CI workflow not in this checkout")
def test_ci_runs_the_gui_tests():
    # Without PyQt6 every GUI test file skips itself, so CI would check none of them.
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "--extra gui" in text
    assert text.count("QT_QPA_PLATFORM: offscreen") >= 2


@pytest.mark.skipif(not WORKFLOW.exists(), reason="CI workflow not in this checkout")
def test_ci_installs_ffmpeg_for_the_drm_test():
    # test_drm_decrypt_output skips itself when ffmpeg is missing
    assert "ffmpeg" in WORKFLOW.read_text(encoding="utf-8")
