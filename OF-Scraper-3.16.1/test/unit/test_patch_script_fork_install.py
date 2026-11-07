"""The 3.16.1 patch script installs and accepts OF-Scraper-Community 3.16.1."""

import collections
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.16.1_gui.py"
_URL = "git+https://github.com/cloakedkeys/OF-Scraper-Community@3.16.1"
_V = collections.namedtuple("version_info", "major minor micro releaselevel serial")


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_316_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "version,ok",
    [
        ("3.16.1", True),
        ("3.16.1+g8e8cb81", True),  # a git install of the tag
        ("3.16.1.post2+gdeadbee", True),
        ("3.16.0", False),
        ("3.16.2", False),
        ("3.14.7", False),  # upstream from PyPI
        (None, False),
        ("garbage", False),
    ],
)
def test_target_version(patch_mod, version, ok):
    assert patch_mod._is_target_version(version) is ok


def _answers(monkeypatch, patch_mod, *answers):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))


def test_git_build_of_the_tag_is_accepted_without_questions(patch_mod, monkeypatch):
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.16.1+g8e8cb81")
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("should not ask"))
    assert patch_mod._check_and_offer_upgrade("uv") is True


def test_newer_version_asks_before_patching(patch_mod, monkeypatch, capsys):
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.16.2")
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda *a, **k: pytest.fail("no install"))
    _answers(monkeypatch, patch_mod, "no")
    assert patch_mod._check_and_offer_upgrade("pip") is False
    assert "can undo newer fixes" in capsys.readouterr().out
    _answers(monkeypatch, patch_mod, "yes")
    assert patch_mod._check_and_offer_upgrade("pip") is True


def test_upstream_version_offers_the_fork(patch_mod, monkeypatch, capsys):
    installs = []
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.14.7")
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda m, **k: installs.append(m) or True)
    _answers(monkeypatch, patch_mod, "yes")
    assert patch_mod._check_and_offer_upgrade("pipx") is True
    assert installs == ["pipx"]
    out = capsys.readouterr().out
    assert "older upstream OF-Scraper" in out and "OF-Scraper-Community 3.16.1" in out


def test_install_stops_without_git(patch_mod, monkeypatch, capsys):
    monkeypatch.setattr(patch_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda *a, **k: pytest.fail("ran a command"))
    assert patch_mod._install_ofscraper("pip") is False
    assert "git was not found" in capsys.readouterr().out


@pytest.mark.parametrize(
    "ver,supported", [((3, 10), False), ((3, 11), True), ((3, 13), True), ((3, 15), True), ((3, 16), False)]
)
def test_python_range(patch_mod, monkeypatch, ver, supported):
    monkeypatch.setattr(patch_mod.sys, "version_info", _V(*ver, 0, "final", 0))
    assert patch_mod._python_supported() is supported
    # uv is only pointed at another Python when this one is unsupported
    assert patch_mod._uv_python_arg() == ([] if supported else ["--python", "3.12"])


def test_supported_new_python_installs_with_this_python(patch_mod, monkeypatch):
    runs = []
    monkeypatch.setattr(patch_mod.sys, "version_info", _V(3, 14, 0, "final", 0))
    monkeypatch.setattr(patch_mod, "_git_missing", lambda: False)
    monkeypatch.setattr(patch_mod, "_find_older_python", lambda: pytest.fail("looked for 3.11/3.12"))
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda cmd, *a, **k: runs.append(cmd))
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.16.1")
    assert patch_mod._install_ofscraper("pipx") is True
    assert runs == [["pipx", "install", "--force", _URL]]


def test_pipx_list_json_is_read(patch_mod, monkeypatch):
    # the 3.14.7 script used json without importing it, so this always gave None
    data = {"venvs": {"ofscraper": {"metadata": {"main_package": {"package_version": "3.16.1"}}}}}
    monkeypatch.setattr(
        patch_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=json.dumps(data), stderr=""),
    )
    assert patch_mod._pipx_list_json() == data
    assert patch_mod._get_installed_ofscraper_version("pipx") == "3.16.1"


def test_root_and_tree_copies_match():
    root_copy = Path(__file__).resolve().parents[3] / "patch_ofscraper_3.16.1_gui.py"
    if not root_copy.exists():
        pytest.skip("only the tree copy is present")
    assert root_copy.read_bytes() == _SCRIPT.read_bytes()


def test_zip_matches_the_tree(patch_mod):
    # every file in the patch is the tree's current file (rebuild_patch_zip.py was run)
    import base64
    import io
    import zipfile

    root = _SCRIPT.parent / "ofscraper"
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(patch_mod.ZIP_B64)))
    assert sorted(zf.namelist()) == sorted(patch_mod.FILES)
    assert patch_mod.FILE_COUNT == len(patch_mod.FILES)

    def norm(b):  # a Windows checkout may have CRLF line endings
        return b.replace(b"\r\n", b"\n")

    stale = [n for n in zf.namelist() if norm(zf.read(n)) != norm((root / n).read_bytes())]
    assert stale == [], "run rebuild_patch_zip.py"
