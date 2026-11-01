"""The patch script's "pipx not found" help must match the user's OS."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPTS = [
    Path(__file__).resolve().parents[2] / "patch_ofscraper_3.14.7_gui.py",
    _REPO / "patch_ofscraper_3.14.7_gui.py",
    _REPO / "patch_ofscraper_3.14.5_gui.py",
    _REPO / "patch_ofscraper_3.14.3_gui.py",
    _REPO / "patch_ofscraper_3.12.9_gui.py",
]


@pytest.fixture(params=_SCRIPTS, ids=lambda p: f"{p.parent.name}/{p.name}")
def patch_mod(request):
    if not request.param.is_file():
        pytest.skip(f"{request.param.name} not in this checkout")
    spec = importlib.util.spec_from_file_location("_patch_script_pipx_hint", request.param)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _no_pipx_module(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: None if name == "pipx" else real(name, *a)
    )


@pytest.mark.parametrize("system", ["Windows", "Darwin"])
def test_no_apt_command_off_linux(patch_mod, monkeypatch, system):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: system)
    _no_pipx_module(monkeypatch)
    text = "\n".join(patch_mod._pipx_install_hint_lines())
    assert "apt" not in text and "sudo" not in text


def test_windows_hint_uses_pip_and_ensurepath(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    _no_pipx_module(monkeypatch)
    text = "\n".join(patch_mod._pipx_install_hint_lines())
    assert "python -m pip install --user pipx" in text
    assert "python -m pipx ensurepath" in text


def test_linux_hint_keeps_apt(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Linux")
    _no_pipx_module(monkeypatch)
    assert "sudo apt install pipx" in "\n".join(patch_mod._pipx_install_hint_lines())


def test_pipx_module_off_path_says_ensurepath(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    real = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *a: object() if name == "pipx" else real(name, *a)
    )
    text = "\n".join(patch_mod._pipx_install_hint_lines())
    assert "not on your PATH" in text and "python -m pipx ensurepath" in text


def test_install_without_pipx_prints_windows_hint(patch_mod, monkeypatch, capsys):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    _no_pipx_module(monkeypatch)

    def missing(*a, **k):
        raise FileNotFoundError("pipx")

    monkeypatch.setattr(patch_mod.subprocess, "run", missing)
    assert patch_mod._install_ofscraper("pipx") is False
    out = capsys.readouterr().out
    assert "Could not find pipx" in out
    assert "apt" not in out


def test_menu_reprompts_when_pipx_missing(patch_mod, monkeypatch, capsys):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    _no_pipx_module(monkeypatch)
    monkeypatch.setattr(patch_mod.shutil, "which", lambda name: None if name == "pipx" else "/x/" + name)
    answers = iter(["2", "1"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    assert patch_mod._prompt_install_method() == ("pip", None)
    out = capsys.readouterr().out
    assert "Could not find pipx" in out and "Choose another option" in out


def test_menu_accepts_pipx_when_present(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod.shutil, "which", lambda name: "/x/" + name)
    monkeypatch.setattr("builtins.input", lambda *a: "2")
    assert patch_mod._prompt_install_method() == ("pipx", None)
