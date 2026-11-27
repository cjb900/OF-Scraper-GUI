"""Merge DBs > PostgreSQL > Install driver installs the driver the way
ofscraper was installed. pipx and uv tool envs have no pip, so
`python -m pip install` failed there ("No module named pip"). The patch
script keeps the driver when it rebuilds a pipx/uv env."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from ofscraper.gui.utils import postgres_setup as pg

REQ = pg.DRIVER_REQUIREMENT


def _venv(tmp_path, marker=None, *parts):
    prefix = tmp_path.joinpath(*parts) if parts else tmp_path / "env"
    prefix.mkdir(parents=True)
    if marker:
        (prefix / marker).write_text("")
    return prefix


@pytest.fixture
def no_tools(monkeypatch, tmp_path):
    monkeypatch.setattr(pg.shutil, "which", lambda name: None)
    monkeypatch.setattr(pg.pathlib.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("APPDATA", raising=False)


def test_pipx_env_is_injected_into(tmp_path, monkeypatch):
    prefix = _venv(tmp_path, "pipx_metadata.json", "pipx", "venvs", "ofscraper")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(pg.shutil, "which", lambda name: f"/bin/{name}" if name == "pipx" else None)

    plan = pg.install_driver_plan()

    assert plan.method == "pipx"
    assert plan.command == ["/bin/pipx", "inject", "ofscraper", REQ]
    assert plan.manual == f'pipx inject ofscraper "{REQ}"'
    assert plan.cwd == str(Path.home())


def test_pipx_found_from_the_folder_name_alone(tmp_path, monkeypatch):
    # Windows: %LOCALAPPDATA%\pipx\pipx\venvs\ofscraper
    prefix = _venv(tmp_path, None, "pipx", "pipx", "venvs", "ofscraper")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    assert pg.install_method() == "pipx"


def test_uv_tool_installs_into_its_python(tmp_path, monkeypatch):
    prefix = _venv(tmp_path, "uv-receipt.toml", "uv", "tools", "ofscraper")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "executable", str(prefix / "bin" / "python"))
    monkeypatch.setattr(pg.shutil, "which", lambda name: f"/bin/{name}" if name == "uv" else None)

    plan = pg.install_driver_plan()

    assert plan.method == "uv"
    assert plan.command == ["/bin/uv", "pip", "install", "--python", sys.executable, REQ]


def test_pip_install_uses_pip(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(_venv(tmp_path)))
    monkeypatch.setattr(pg, "_pip_available", lambda: True)

    plan = pg.install_driver_plan()

    assert plan.method == "pip"
    assert plan.command[1:] == ["-u", "-m", "pip", "install", REQ]


def test_a_venv_without_pip_uses_uv(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(_venv(tmp_path)))
    monkeypatch.setattr(pg, "_pip_available", lambda: False)
    monkeypatch.setattr(pg.shutil, "which", lambda name: "/bin/uv" if name == "uv" else None)

    assert pg.install_driver_plan().command[:3] == ["/bin/uv", "pip", "install"]


@pytest.mark.parametrize("marker, method", [("pipx_metadata.json", "pipx"), ("uv-receipt.toml", "uv")])
def test_a_missing_tool_gives_the_command_to_type(tmp_path, monkeypatch, no_tools, marker, method):
    monkeypatch.setattr(sys, "prefix", str(_venv(tmp_path, marker)))

    plan = pg.install_driver_plan()

    assert plan.method == method
    assert plan.command is None
    assert REQ in plan.manual
    assert plan.manual in pg.driver_missing_text()


def test_pipx_outside_path_is_found_where_it_installs(tmp_path, monkeypatch, no_tools):
    prefix = _venv(tmp_path, "pipx_metadata.json", "venvs", "ofscraper")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    exe = "pipx.exe" if sys.platform == "win32" else "pipx"
    tool = tmp_path / "home" / ".local" / "bin" / exe
    tool.parent.mkdir(parents=True)
    tool.write_text("")

    assert pg.install_driver_plan().command[0] == str(tool)


def test_the_tab_shows_a_command_that_can_be_pasted():
    shown = pg.shown_command(["C:/x/Scripts/python.exe", "-u", "-m", "pip", "install", REQ])
    assert shown == f'python -m pip install "{REQ}"'
    assert pg.shown_command(["C:/tools/pipx.exe", "inject", "ofscraper", REQ]) == (
        f'pipx inject ofscraper "{REQ}"'
    )


# --- the patch script keeps the driver ------------------------------------------

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.18.1_gui.py"


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_script_pg_driver", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tool_env(tmp_path, driver=True):
    venv = tmp_path / "tools" / "ofscraper"
    sp = venv / "Lib" / "site-packages"
    (sp / "ofscraper").mkdir(parents=True)
    (sp / "ofscraper" / "__main__.py").write_text("")
    (venv / "pyvenv.cfg").write_text("")
    (venv / "Scripts").mkdir()
    (venv / "Scripts" / "python.exe").write_text("")
    if driver:
        (sp / "psycopg").mkdir()
        (sp / "psycopg_pool").mkdir()
    return venv, sp


def test_patch_script_keeps_the_versions_in_step(patch_mod):
    assert patch_mod.POSTGRES_DRIVER == REQ


def test_patch_script_sees_the_driver_in_a_tool_env(patch_mod, monkeypatch, tmp_path):
    _, sp = _tool_env(tmp_path)
    monkeypatch.setattr(patch_mod, "_find_uv_ofscraper_pkg", lambda: sp / "ofscraper")
    assert patch_mod._postgres_driver_present("uv")
    assert not patch_mod._postgres_driver_present("pip")


def test_uv_reinstall_lists_the_driver_only_when_it_was_there(patch_mod, monkeypatch):
    assert REQ not in patch_mod._gui_dep_names()
    monkeypatch.setattr(patch_mod, "_KEEP_POSTGRES_DRIVER", True)
    assert patch_mod._uv_with_args(patch_mod._gui_dep_names())[-2:] == ["--with", REQ]


@pytest.mark.parametrize("method", ["uv", "pipx"])
def test_a_dropped_driver_is_installed_again(patch_mod, monkeypatch, tmp_path, method):
    venv, sp = _tool_env(tmp_path, driver=False)
    finder = "_find_uv_ofscraper_pkg" if method == "uv" else "_find_pipx_ofscraper_pkg"
    monkeypatch.setattr(patch_mod, finder, lambda: sp / "ofscraper")
    monkeypatch.setattr(patch_mod, "_pipx_venv_name", lambda: "ofscraper")
    ran = []
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda cmd, **kw: ran.append(cmd))

    patch_mod._restore_postgres_driver(method)

    if method == "uv":
        assert ran == [["uv", "pip", "install", "--python", str(venv / "Scripts" / "python.exe"), REQ]]
    else:
        assert ran == [["pipx", "inject", "ofscraper", REQ]]


def test_a_kept_driver_is_left_alone(patch_mod, monkeypatch, tmp_path):
    _, sp = _tool_env(tmp_path)
    monkeypatch.setattr(patch_mod, "_find_uv_ofscraper_pkg", lambda: sp / "ofscraper")
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda *a, **k: pytest.fail("ran an install"))
    patch_mod._restore_postgres_driver("uv")


def test_a_failed_reinstall_only_warns(patch_mod, monkeypatch, tmp_path, capsys):
    _, sp = _tool_env(tmp_path, driver=False)
    monkeypatch.setattr(patch_mod, "_find_pipx_ofscraper_pkg", lambda: sp / "ofscraper")
    monkeypatch.setattr(patch_mod, "_pipx_venv_name", lambda: "ofscraper")

    def fail(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(patch_mod.subprocess, "run", fail)
    patch_mod._restore_postgres_driver("pipx")
    assert "Install driver" in capsys.readouterr().out
