"""The patch script's --force option (reinstall ofscraper + GUI deps from scratch)."""

import collections
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_PY312 = collections.namedtuple("version_info", "major minor micro releaselevel serial")(3, 12, 0, "final", 0)
_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.16.1_gui.py"
# OF-Scraper-Community isn't on PyPI: pip and uv get a direct reference,
# pipx install the bare URL
_URL = "git+https://github.com/cloakedkeys/OF-Scraper-Community@3.16.1"
_SPEC = f"ofscraper @ {_URL}"


@pytest.fixture
def patch_mod(monkeypatch):
    spec = importlib.util.spec_from_file_location("_patch_script_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def runs(patch_mod, monkeypatch):
    """Record subprocess.run commands; every command succeeds."""
    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(patch_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version",
                        lambda method=None: patch_mod.TARGET_OFSCRAPER_VERSION)
    monkeypatch.setattr(patch_mod.sys, "version_info", _PY312)
    monkeypatch.setattr(patch_mod, "_git_missing", lambda: False)
    return calls


def _gui_with_args(mod):
    out = []
    for name in mod._gui_dep_names():
        out += ["--with", name]
    return out


# --- _install_ofscraper ---------------------------------------------------------

def test_uv_force_reinstalls_everything_and_keeps_gui_packages(patch_mod, runs):
    assert patch_mod._install_ofscraper("uv", force=True)
    cmd = runs[-1]
    assert cmd[:5] == ["uv", "tool", "install", "--force", "--reinstall"]
    assert _SPEC in cmd
    # uv replaces the tool env, so the GUI packages must be listed.
    for name in patch_mod._gui_dep_names():
        assert ["--with", name] == cmd[cmd.index(name) - 1: cmd.index(name) + 1]


def test_uv_force_skip_deps_reinstalls_only_ofscraper(patch_mod, runs):
    assert patch_mod._install_ofscraper("uv", force=True, keep_gui_deps=True)
    cmd = runs[-1]
    assert "--reinstall" not in cmd
    assert cmd[4:6] == ["--reinstall-package", "ofscraper"]
    assert cmd[-len(_gui_with_args(patch_mod)):] == _gui_with_args(patch_mod)


def test_uv_without_force_is_unchanged(patch_mod, runs):
    assert patch_mod._install_ofscraper("uv")
    assert runs[-1] == ["uv", "tool", "install", "--force", _SPEC]


def test_pipx_force_uninstalls_first_for_a_fresh_venv(patch_mod, runs):
    assert patch_mod._install_ofscraper("pipx", force=True)
    assert runs[0] == ["pipx", "uninstall", "ofscraper"]
    assert runs[1] == ["pipx", "install", "--force", _URL]


def test_pipx_force_continues_when_nothing_to_uninstall(patch_mod, runs, monkeypatch):
    calls = []

    def fake_run(cmd, *a, check=False, **kw):
        calls.append(list(cmd))
        rc = 1 if cmd[:2] == ["pipx", "uninstall"] else 0
        if rc and check:
            raise subprocess.CalledProcessError(rc, cmd)
        return subprocess.CompletedProcess(cmd, rc)

    monkeypatch.setattr(patch_mod.subprocess, "run", fake_run)
    assert patch_mod._install_ofscraper("pipx", force=True)
    assert calls[-1][:2] == ["pipx", "install"]


def test_pipx_force_skip_deps_reinstalls_inside_existing_venv(patch_mod, runs):
    assert patch_mod._install_ofscraper("pipx", force=True, keep_gui_deps=True)
    assert runs == [["pipx", "runpip", "ofscraper", "install", "--upgrade",
                     "--force-reinstall", _SPEC]]


def test_pipx_without_force_does_not_uninstall(patch_mod, runs):
    assert patch_mod._install_ofscraper("pipx")
    assert ["pipx", "uninstall", "ofscraper"] not in runs


def test_pip_force_uses_force_reinstall(patch_mod, runs):
    assert patch_mod._install_ofscraper("pip", force=True)
    assert runs[-1] == [sys.executable, "-m", "pip", "install", "--upgrade",
                        "--force-reinstall", _SPEC]


# --- _install_gui_deps ----------------------------------------------------------

def test_gui_deps_force_reinstalls_all_even_when_present(patch_mod, runs, monkeypatch):
    monkeypatch.setattr(patch_mod, "_check_missing_gui_deps", lambda *a, **k: [])
    assert patch_mod._install_gui_deps("pip", force=True)
    assert runs[-1] == ([sys.executable, "-m", "pip", "install", "--force-reinstall"]
                        + patch_mod._gui_dep_names())


def test_gui_deps_without_force_skips_when_present(patch_mod, runs, monkeypatch):
    monkeypatch.setattr(patch_mod, "_check_missing_gui_deps", lambda *a, **k: [])
    assert patch_mod._install_gui_deps("pip")
    assert runs == []


def test_gui_deps_force_pipx_injects_every_package_with_force(patch_mod, runs):
    assert patch_mod._install_gui_deps("pipx", force=True)
    assert runs == [["pipx", "inject", "--force", "ofscraper", n] for n in patch_mod._gui_dep_names()]


def test_gui_deps_force_uv_reinstalls(patch_mod, runs):
    assert patch_mod._install_gui_deps("uv", force=True)
    assert runs[-1] == (["uv", "tool", "install", "--force", "--reinstall", _SPEC]
                        + _gui_with_args(patch_mod))


# --- main() ---------------------------------------------------------------------

@pytest.fixture
def main_env(patch_mod, monkeypatch):
    """Stub everything main() touches; record install / deps / apply calls."""
    log = []
    monkeypatch.setattr(patch_mod.sys, "version_info", _PY312)
    monkeypatch.setattr(patch_mod, "_confirm_warning", lambda skip=False: True)
    monkeypatch.setattr(patch_mod, "_pipx_text_mentions_package", lambda *a: False)
    monkeypatch.setattr(patch_mod, "_windows_ofscraper_cli_version", lambda: None)
    monkeypatch.setattr(patch_mod, "_check_and_offer_upgrade",
                        lambda method: log.append(("upgrade_check", method)) or True)
    monkeypatch.setattr(patch_mod, "_install_ofscraper",
                        lambda method, **kw: log.append(("install", method, kw)) or True)
    monkeypatch.setattr(patch_mod, "_install_gui_deps",
                        lambda method, **kw: log.append(("deps", method, kw)) or True)
    monkeypatch.setattr(patch_mod, "apply", lambda **kw: log.append(("apply", kw)) or 0)

    def run(method, *argv):
        monkeypatch.setattr(patch_mod, "_detect_install_method", lambda: method)
        monkeypatch.setattr(sys, "argv", ["patch", "-y", *argv])
        log.clear()
        return patch_mod.main(), list(log)

    return run


@pytest.mark.parametrize("method", ["pip", "pipx"])
def test_main_force_reinstalls_ofscraper_then_all_gui_deps_then_patches(main_env, method):
    rc, log = main_env(method, "--force")
    assert rc == 0
    assert log == [
        ("install", method, {"force": True, "keep_gui_deps": False}),
        ("deps", method, {"force": True}),
        ("apply", {"target": None, "backup_dir": None, "dry_run": False}),
    ]


def test_main_force_uv_does_not_reinstall_gui_deps_twice(main_env):
    rc, log = main_env("uv", "--force")
    assert rc == 0
    assert [entry[0] for entry in log] == ["install", "apply"]


def test_main_force_skip_deps_reinstalls_only_ofscraper(main_env):
    rc, log = main_env("pip", "--force", "--skip-deps")
    assert rc == 0
    assert log[0] == ("install", "pip", {"force": True, "keep_gui_deps": True})
    assert [entry[0] for entry in log] == ["install", "apply"]


def test_main_force_dry_run_installs_nothing(main_env):
    rc, log = main_env("pip", "--force", "--dry-run")
    assert rc == 0
    assert not any(entry[0] == "install" for entry in log)
    assert ("deps", "pip", {"force": False}) in log


def test_main_without_force_keeps_the_upgrade_check(main_env):
    rc, log = main_env("pip")
    assert rc == 0
    assert log[0] == ("upgrade_check", "pip")
    assert ("deps", "pip", {"force": False}) in log
    assert not any(entry[0] == "install" for entry in log)


def test_main_force_stops_when_reinstall_fails(main_env, patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda method, **kw: False)
    rc, log = main_env("pip", "--force")
    assert rc == 5
    assert not any(entry[0] == "apply" for entry in log)


def test_force_and_restore_together_is_an_error(main_env):
    with pytest.raises(SystemExit) as exc:
        main_env("pip", "--force", "--restore", "/tmp/x")
    assert exc.value.code == 2
