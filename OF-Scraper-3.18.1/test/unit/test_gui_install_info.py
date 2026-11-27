"""About shows the Python ofscraper runs on and how it was installed
(gui/utils/install_info.py, shared with Manage DBs > PostgreSQL > Install
driver)."""

import re
import sys

import pytest

from ofscraper.gui.utils import install_info


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake environment folder as sys.prefix, not frozen, not in Docker."""
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(install_info, "in_docker", lambda: False)

    def make(*parts, marker=None, venv=True):
        prefix = tmp_path.joinpath(*parts)
        prefix.mkdir(parents=True)
        if marker:
            (prefix / marker).write_text("")
        monkeypatch.setattr(sys, "prefix", str(prefix))
        monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "base") if venv else str(prefix))
        return prefix

    return make


def test_pipx(env):
    env("pipx", "venvs", "ofscraper", marker="pipx_metadata.json")
    assert install_info.install_label() == "pipx"


def test_pipx_on_windows_by_its_folder(env):
    env("AppData", "Local", "pipx", "pipx", "venvs", "ofscraper")
    assert install_info.install_label() == "pipx"


def test_uv_tool(env):
    env("uv", "tools", "ofscraper", marker="uv-receipt.toml")
    assert install_info.install_label() == "uv (uv tool)"


def test_pip_in_a_venv_and_system_pip(env):
    env("myvenv")
    assert install_info.install_label() == "pip (in a virtual environment)"


def test_system_pip(env):
    env("usr", venv=False)
    assert install_info.install_label() == "pip"


def test_docker_image(env, monkeypatch):
    env("opt", "venv")
    monkeypatch.setattr(install_info, "in_docker", lambda: True)
    assert install_info.install_label() == "pip (in a virtual environment), Docker image"


def test_standalone_download(env, monkeypatch):
    env("bundle")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert install_info.install_label() == "Standalone download"


def test_python_version_names_the_running_python():
    said = install_info.python_version()
    assert said.startswith(".".join(map(str, sys.version_info[:3])))
    assert re.search(r"\((32|64)-bit\)$", said)


def test_about_shows_both_rows(monkeypatch):
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    if not isinstance(app, QtWidgets.QApplication):
        pytest.skip("a QCoreApplication from another test is already running")
    from ofscraper.gui.dialogs import about_dialog

    monkeypatch.setattr(install_info, "install_label", lambda: "pipx")
    monkeypatch.setattr(install_info, "python_version", lambda: "3.12.13 (64-bit)")
    monkeypatch.setattr(install_info, "environment_path", lambda: "/x/venvs/ofscraper")
    dialog = about_dialog.AboutDialog()
    labels = [w.text() for w in dialog.findChildren(QtWidgets.QLabel)]
    at = labels.index("Python:")
    assert labels[at + 1] == "3.12.13 (64-bit)"
    at = labels.index("Installed with:")
    assert labels[at + 1] == "pipx"
    shown = dialog.findChildren(QtWidgets.QLabel)[at + 1]
    assert shown.toolTip() == "Environment: /x/venvs/ofscraper"
    assert labels.index("Operating system:") < labels.index("Python:") < labels.index("FFmpeg:")
