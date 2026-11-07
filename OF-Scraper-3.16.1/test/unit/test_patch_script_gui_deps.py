"""pipx / uv installs: GUI packages are looked up in ofscraper's venv.

The installer used to import them in the Python running the script, so on a
pipx install every GUI package looked missing and was injected again
("already seems to be injected" x5).
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.16.1_gui.py"


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_script_gui_deps", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _windows_venv(tmp_path, with_webengine=True):
    sp = tmp_path / "venvs" / "ofscraper" / "Lib" / "site-packages"
    (sp / "ofscraper").mkdir(parents=True)
    (sp / "ofscraper" / "__main__.py").write_text("")
    (sp / "PyQt6").mkdir()
    (sp / "PyQt6" / "__init__.py").write_text("")
    (sp / "PyQt6" / "QtCore.pyd").write_text("")
    if with_webengine:
        (sp / "PyQt6" / "QtWebEngineWidgets.pyd").write_text("")
    else:
        (sp / "PyQt6" / "QtWebEngineWidgets.pyi").write_text("")  # stub only
    for pkg in ("browser_cookie3", "secretstorage", "Crypto"):
        (sp / pkg).mkdir()
        (sp / pkg / "__init__.py").write_text("")
    return sp


@pytest.mark.parametrize("method, finder", [("pipx", "_find_pipx_ofscraper_pkg"), ("uv", "_find_uv_ofscraper_pkg")])
def test_tool_venv_with_everything_has_nothing_missing(patch_mod, monkeypatch, tmp_path, method, finder):
    sp = _windows_venv(tmp_path)
    monkeypatch.setattr(patch_mod, finder, lambda: sp / "ofscraper")
    assert patch_mod._check_missing_gui_deps(method) == []


def test_missing_webengine_extension_is_reported(patch_mod, monkeypatch, tmp_path):
    sp = _windows_venv(tmp_path, with_webengine=False)
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: sp / "ofscraper")
    assert [d[1] for d in patch_mod._check_missing_gui_deps("pipx")] == ["PyQt6-WebEngine"]


def test_linux_so_and_single_file_modules(patch_mod, tmp_path):
    sp = tmp_path / "site-packages"
    (sp / "PyQt6").mkdir(parents=True)
    (sp / "PyQt6" / "QtWebEngineWidgets.abi3.so").write_text("")
    (sp / "browser_cookie3.py").write_text("")
    assert patch_mod._module_in_site_packages(sp, "PyQt6.QtWebEngineWidgets")
    assert patch_mod._module_in_site_packages(sp, "browser_cookie3")
    assert not patch_mod._module_in_site_packages(sp, "secretstorage")


def test_venv_not_found_falls_back_to_import(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: None)
    monkeypatch.setattr(patch_mod, "_GUI_DEPS", [("json", "json", "json"), ("no_such_mod_xyz", "x", "x")])
    assert [d[0] for d in patch_mod._check_missing_gui_deps("pipx")] == ["no_such_mod_xyz"]


def test_install_skips_inject_when_venv_has_everything(patch_mod, monkeypatch, tmp_path, capsys):
    sp = _windows_venv(tmp_path)
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: sp / "ofscraper")
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda *a, **k: pytest.fail("ran pipx inject"))
    assert patch_mod._install_gui_deps("pipx") is True
    assert "All GUI dependencies already installed." in capsys.readouterr().out
