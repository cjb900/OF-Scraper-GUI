"""The patch script's --force option (reinstall ofscraper + GUI deps from scratch)."""

import collections
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_PY312 = collections.namedtuple("version_info", "major minor micro releaselevel serial")(3, 12, 0, "final", 0)
_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.17.1_gui.py"
PKG = "ofscraper==3.17.1"


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
    # no old "ofscraper" package and no pipx metadata unless a test says so
    monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: False)
    monkeypatch.setattr(patch_mod, "_pipx_package_info", lambda *a, **k: None)
    # never look at this machine's own pipx / uv installs
    monkeypatch.setattr(patch_mod, "_get_pipx_home", lambda: None)
    monkeypatch.setattr(patch_mod, "_get_uv_tool_dir", lambda: None)
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
    assert PKG in cmd
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
    assert runs[-1] == ["uv", "tool", "install", "--force", PKG]


def test_pipx_force_uninstalls_first_for_a_fresh_venv(patch_mod, runs):
    assert patch_mod._install_ofscraper("pipx", force=True)
    assert runs[0] == ["pipx", "uninstall", "ofscraper"]
    assert runs[1] == ["pipx", "install", "--force", PKG]


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
                     "--force-reinstall", PKG]]


def test_pipx_without_force_does_not_uninstall(patch_mod, runs):
    assert patch_mod._install_ofscraper("pipx")
    assert not any(cmd[:2] == ["pipx", "uninstall"] for cmd in runs)


def test_pip_force_uses_force_reinstall(patch_mod, runs):
    assert patch_mod._install_ofscraper("pip", force=True)
    assert runs[-1] == [sys.executable, "-m", "pip", "install", "--upgrade",
                        "--force-reinstall", PKG]


# --- the "ofscraper-community" package (3.16.2-3.16.13) ---------------------------

@pytest.mark.parametrize(
    "method, uninstall",
    [
        ("pipx", ["pipx", "uninstall", "ofscraper-community"]),
        ("uv", ["uv", "tool", "uninstall", "ofscraper-community"]),
        ("pip", [sys.executable, "-m", "pip", "uninstall", "-y", "ofscraper-community"]),
    ],
)
def test_old_package_is_removed_before_installing_the_new_one(patch_mod, runs, monkeypatch,
                                                              method, uninstall):
    # both install the ofscraper/ folder: removing the old one afterwards
    # would delete the new one's files
    monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: True)
    assert patch_mod._install_ofscraper(method)
    assert runs[0] == uninstall
    assert PKG in runs[1]


def test_skip_deps_reinstall_of_an_old_pipx_venv_makes_a_new_one(patch_mod, runs, monkeypatch):
    # runpip inside the "ofscraper-community" venv can't change the package name
    monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: True)
    assert patch_mod._install_ofscraper("pipx", force=True, keep_gui_deps=True)
    assert runs[0] == ["pipx", "uninstall", "ofscraper-community"]
    assert not any(cmd[:2] == ["pipx", "runpip"] for cmd in runs)
    assert runs[-1][:2] == ["pipx", "install"] and PKG in runs[-1]


def test_failed_removal_of_the_old_package_stops_the_install(patch_mod, runs, monkeypatch):
    monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: True)

    def fail(cmd, *a, check=False, **kw):
        runs.append(list(cmd))
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(patch_mod.subprocess, "run", fail)
    assert patch_mod._install_ofscraper("pip") is False
    assert len(runs) == 1


def test_pip_detection_accepts_either_package_name(patch_mod, monkeypatch):
    import importlib.metadata as meta

    def version(name):
        if name == "ofscraper-community":
            return "3.16.13"
        raise meta.PackageNotFoundError(name)

    monkeypatch.setattr(meta, "version", version)
    assert patch_mod._pip_installed_name() == "ofscraper-community"

    # with both registered, the current name wins
    monkeypatch.setattr(meta, "version", lambda name: "3.17.1")
    assert patch_mod._pip_installed_name() == "ofscraper"


def test_pipx_text_matches_the_new_package_name(patch_mod, monkeypatch):
    monkeypatch.setattr(
        patch_mod, "_pipx_list_text",
        lambda: "venvs are in ~/.local/share/pipx/venvs\n   package ofscraper 3.17.1, installed using Python 3.12\n",
    )
    assert patch_mod._pipx_text_mentions_package()


def test_pipx_list_json_is_parsed(patch_mod, monkeypatch):
    # json was used without being imported, so this always returned None
    monkeypatch.setattr(
        patch_mod.subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout='{"venvs": {}}', stderr=""),
    )
    assert patch_mod._pipx_list_json() == {"venvs": {}}


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
    assert runs == [["pipx", "inject", "--force", "ofscraper", n]
                    for n in patch_mod._gui_dep_names()]


def test_gui_deps_force_uv_reinstalls(patch_mod, runs):
    assert patch_mod._install_gui_deps("uv", force=True)
    assert runs[-1] == (["uv", "tool", "install", "--force", "--reinstall", PKG]
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


# --- upgrading an existing pipx install -----------------------------------------------------

def test_pipx_upgrade_happens_inside_the_existing_venv(patch_mod, runs, monkeypatch, tmp_path):
    # `pipx install --force` over an existing venv fails with pipx's uv backend
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: tmp_path)
    assert patch_mod._install_ofscraper("pipx")
    assert runs == [["pipx", "runpip", "ofscraper", "install", "--upgrade", PKG]]


def test_failed_in_place_upgrade_rebuilds_the_venv(patch_mod, monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, *a, **kw):
        calls.append(list(cmd))
        code = 1 if cmd[:2] == ["pipx", "runpip"] else 0
        if kw.get("check") and code:
            raise subprocess.CalledProcessError(code, cmd)
        return subprocess.CompletedProcess(cmd, code, stdout="", stderr="")

    monkeypatch.setattr(patch_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version",
                        lambda method=None: patch_mod.TARGET_OFSCRAPER_VERSION)
    monkeypatch.setattr(patch_mod.sys, "version_info", _PY312)
    monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: False)
    monkeypatch.setattr(patch_mod, "_pipx_package_info", lambda *a, **k: None)
    monkeypatch.setattr(patch_mod, "_get_pipx_home", lambda: None)
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: tmp_path)
    assert patch_mod._install_ofscraper("pipx")
    assert [c[:2] for c in calls] == [["pipx", "runpip"], ["pipx", "uninstall"], ["pipx", "install"]]


@pytest.fixture
def installed(patch_mod, monkeypatch):
    def set_version(version, upgrade_ok=True, answers=()):
        monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda method=None: version)
        monkeypatch.setattr(patch_mod, "_legacy_install_present", lambda *a, **k: False)
        monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda *a, **k: upgrade_ok)
        replies = iter(answers)
        monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))
    return set_version


def test_failed_upgrade_does_not_patch(patch_mod, installed):
    installed("3.14.7", upgrade_ok=False, answers=["yes"])
    assert patch_mod._check_and_offer_upgrade("pipx") is False


def test_older_series_cannot_be_patched_without_upgrading(patch_mod, installed, capsys):
    installed("3.14.7", answers=["no"])
    assert patch_mod._check_and_offer_upgrade("pipx") is False
    assert "would no longer start" in capsys.readouterr().out


def test_same_series_may_still_continue(patch_mod, installed):
    installed("3.17.0", answers=["no", "yes"])
    assert patch_mod._check_and_offer_upgrade("pipx") is True


def test_successful_upgrade_patches(patch_mod, installed):
    installed("3.14.7", answers=["yes"])
    assert patch_mod._check_and_offer_upgrade("pipx") is True


def test_a_3_16_install_must_upgrade_to_3_17(patch_mod, installed, capsys):
    # the 3.17 patch files don't run on a 3.16 install
    installed("3.16.14", answers=["no"])
    assert patch_mod._check_and_offer_upgrade("pipx") is False
    assert "would no longer start" in capsys.readouterr().out
