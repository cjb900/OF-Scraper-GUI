"""The patch script starts the GUI detached, as its own window."""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.17.1_gui.py"


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_launch_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_gui_is_detached_from_the_console(patch_mod, monkeypatch, system):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: system)
    kw = patch_mod._detached_gui_kwargs({"PATH": "/bin"})
    assert kw["stdin"] is patch_mod.subprocess.DEVNULL
    if system == "Windows":
        assert kw["creationflags"] & 0x200 and kw["creationflags"] & 0x08000000
    else:
        assert kw["start_new_session"] is True
        assert kw["env"]["QT_QPA_PLATFORM"] == "xcb"


def test_tab_variables_are_dropped(patch_mod):
    env = {"OFSC_GUI_CHILD": "1", "OFSC_GUI_EMBED": "1", "PATH": "/bin"}
    out = patch_mod._detached_gui_kwargs(env)["env"]
    assert "OFSC_GUI_CHILD" not in out and "OFSC_GUI_EMBED" not in out
    assert out["PATH"] == "/bin"
