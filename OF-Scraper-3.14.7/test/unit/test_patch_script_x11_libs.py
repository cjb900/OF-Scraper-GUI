"""Linux: the patch script finds and offers to install the X11 libraries Qt needs.

The GUI runs on X11 (XWayland on Wayland). Ubuntu 26.04 lacks some of the
libraries Qt's xcb plugin loads, and the GUI then aborts at start. Nothing
here loads a real library or runs a real command.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.14.7_gui.py"


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_script_x11", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def linux(patch_mod, monkeypatch):
    """A Linux desktop as a normal user with apt-get and sudo; records runs."""
    state = {"present": set(), "runs": [], "answers": [], "fail": False}
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(patch_mod.os, "geteuid", lambda: 1000, raising=False)
    monkeypatch.setattr(patch_mod.shutil, "which",
                        lambda exe: f"/usr/bin/{exe}" if exe in ("apt-get", "sudo") else None)
    monkeypatch.setattr(patch_mod, "_library_loads", lambda name: name in state["present"])

    def run(cmd, check=False, **kw):
        state["runs"].append(cmd)
        if state["fail"]:
            raise patch_mod.subprocess.CalledProcessError(100, cmd)
        state["present"].update(row[0] for row in patch_mod._X11_LIBS)

    monkeypatch.setattr(patch_mod.subprocess, "run", run)
    monkeypatch.setattr("builtins.input", lambda prompt="": state["answers"].pop(0))
    return state




def present_except(patch_mod, *missing):
    return {row[0] for row in patch_mod._X11_LIBS} - set(missing)


@pytest.mark.parametrize("env, expected", [
    ({"XDG_SESSION_TYPE": "wayland"}, "wayland"),
    ({"XDG_SESSION_TYPE": "x11"}, "x11"),
    ({"XDG_SESSION_TYPE": "tty", "WAYLAND_DISPLAY": "wayland-0"}, "wayland"),
    ({"DISPLAY": ":0"}, "x11"),
    ({}, ""),
])
def test_desktop_session(patch_mod, env, expected):
    assert patch_mod._desktop_session(env) == expected


def test_nothing_missing_runs_nothing(patch_mod, linux):
    linux["present"] = present_except(patch_mod)
    assert patch_mod._check_x11_libs() is True
    assert linux["runs"] == []


def test_missing_libraries_are_installed_with_sudo_apt_on_yes(patch_mod, linux):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0", "libxcb-shape.so.0")
    linux["answers"] = ["y"]
    assert patch_mod._check_x11_libs() is True
    assert linux["runs"] == [["sudo", "apt-get", "install", "-y", "libxcb-cursor0", "libxcb-shape0"]]


def test_yes_flag_installs_without_asking(patch_mod, linux):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0")
    assert patch_mod._check_x11_libs(assume_yes=True) is True
    assert linux["runs"] == [["sudo", "apt-get", "install", "-y", "libxcb-cursor0"]]


def test_no_answer_installs_nothing(patch_mod, linux, capsys):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0")
    linux["answers"] = ["n"]
    assert patch_mod._check_x11_libs() is False
    assert linux["runs"] == []
    assert "sudo apt-get install -y libxcb-cursor0" in capsys.readouterr().out


@pytest.mark.parametrize("kw", [{"install": False}, {"dry_run": True}])
def test_skip_deps_and_dry_run_only_list_the_command(patch_mod, linux, capsys, kw):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0")
    assert patch_mod._check_x11_libs(assume_yes=True, **kw) is False
    assert linux["runs"] == []
    assert "sudo apt-get install -y libxcb-cursor0" in capsys.readouterr().out


def test_a_failed_install_does_not_stop_the_patch(patch_mod, linux, capsys):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0")
    linux["fail"] = True
    assert patch_mod._check_x11_libs(assume_yes=True) is False
    assert "Run this yourself" in capsys.readouterr().out


def test_no_desktop_is_skipped(patch_mod, linux, monkeypatch):
    for name in ("XDG_SESSION_TYPE", "WAYLAND_DISPLAY", "DISPLAY"):
        monkeypatch.delenv(name, raising=False)
    assert patch_mod._check_x11_libs(assume_yes=True) is True
    assert linux["runs"] == []


def test_not_linux_is_skipped(patch_mod, linux, monkeypatch):
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    assert patch_mod._check_x11_libs(assume_yes=True) is True
    assert linux["runs"] == []


def test_root_does_not_use_sudo(patch_mod, linux, monkeypatch):
    monkeypatch.setattr(patch_mod.os, "geteuid", lambda: 0, raising=False)
    row = next(r for r in patch_mod._X11_LIBS if r[0] == "libxcb-cursor.so.0")
    cmd = patch_mod._x11_install_command([row])
    assert cmd == ["apt-get", "install", "-y", "libxcb-cursor0"]


def test_dnf_package_names_are_listed_once(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(patch_mod.shutil, "which", lambda exe: "/usr/bin/dnf" if exe == "dnf" else None)
    rows = [r for r in patch_mod._X11_LIBS if r[0] in ("libxcb-randr.so.0", "libxcb-xkb.so.1", "libxcb-cursor.so.0")]
    assert patch_mod._x11_install_command(rows) == ["dnf", "install", "-y", "xcb-util-cursor", "libxcb"]


def test_unknown_package_manager_lists_the_files(patch_mod, linux, monkeypatch, capsys):
    linux["present"] = present_except(patch_mod, "libxcb-cursor.so.0")
    monkeypatch.setattr(patch_mod.shutil, "which", lambda exe: None)
    assert patch_mod._check_x11_libs(assume_yes=True) is False
    assert linux["runs"] == []
    assert "libxcb-cursor.so.0" in capsys.readouterr().out


def test_library_loads_uses_the_dynamic_loader(patch_mod):
    assert patch_mod._library_loads("libdefinitely-not-here.so.9") is False


def test_libgl_is_checked_with_the_right_package_per_manager(patch_mod, monkeypatch):
    # pip's PyQt6 won't import without libGL.so.1 (Ubuntu 26.04 lacks libgl1)
    monkeypatch.setattr(patch_mod.os, "geteuid", lambda: 0, raising=False)
    row = next(r for r in patch_mod._X11_LIBS if r[0] == "libGL.so.1")
    for exe, package in [("apt-get", "libgl1"), ("dnf", "libglvnd-glx"), ("pacman", "libglvnd"),
                         ("zypper", "libGL1")]:
        monkeypatch.setattr(patch_mod.shutil, "which", lambda e, exe=exe: f"/usr/bin/{e}" if e == exe else None)
        assert patch_mod._x11_install_command([row])[-1] == package


def test_every_row_names_a_package_for_each_manager(patch_mod):
    for row in patch_mod._X11_LIBS:
        assert len(row) == 5 and all(row), row
