"""The 3.16.4 patch script installs and accepts ofscraper-community 3.16.4 from PyPI,
and says what to do when it finds upstream's ofscraper instead."""

import collections
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "patch_ofscraper_3.16.4_gui.py"
_SPEC = "ofscraper-community==3.16.4"
_V = collections.namedtuple("version_info", "major minor micro releaselevel serial")


@pytest.fixture
def patch_mod():
    spec = importlib.util.spec_from_file_location("_patch_3164_under_test", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "version,ok",
    [
        ("3.16.4", True),
        ("3.16.4+g686f28c", True),  # a git install of the tag
        ("3.16.4.post2+gdeadbee", True),
        ("3.16.1", False),
        ("3.16.5", False),
        ("3.14.7", False),  # upstream from PyPI
        (None, False),
        ("garbage", False),
    ],
)
def test_target_version(patch_mod, version, ok):
    assert patch_mod._is_target_version(version) is ok


def test_install_spec_is_the_pypi_package(patch_mod):
    assert patch_mod._install_spec() == _SPEC


def _answers(monkeypatch, *answers):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(replies))


def _installed(monkeypatch, patch_mod, dist, version):
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_dist", lambda m=None: (dist, version))
    monkeypatch.setattr(patch_mod, "_pip_dists", lambda: [(dist, version)] if dist else [])


@pytest.mark.parametrize("dist", ["ofscraper-community", None])
def test_target_is_accepted_without_questions(patch_mod, monkeypatch, dist):
    _installed(monkeypatch, patch_mod, dist, "3.16.4")
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("should not ask"))
    assert patch_mod._check_and_offer_upgrade("uv") is True


def test_newer_version_asks_before_patching(patch_mod, monkeypatch, capsys):
    _installed(monkeypatch, patch_mod, "ofscraper-community", "3.16.5")
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda *a, **k: pytest.fail("no install"))
    _answers(monkeypatch, "no")
    assert patch_mod._check_and_offer_upgrade("pip") is False
    assert "can undo newer fixes" in capsys.readouterr().out
    _answers(monkeypatch, "yes")
    assert patch_mod._check_and_offer_upgrade("pip") is True


def test_older_community_version_offers_the_pypi_install(patch_mod, monkeypatch, capsys):
    installs = []
    _installed(monkeypatch, patch_mod, "ofscraper-community", "3.16.3")
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda m, **k: installs.append(m) or True)
    _answers(monkeypatch, "yes")
    assert patch_mod._check_and_offer_upgrade("pipx") is True
    assert installs == ["pipx"]
    assert "pipx install ofscraper-community==3.16.4" in capsys.readouterr().out


@pytest.mark.parametrize(
    "method, uninstall, install",
    [
        ("pip", "pip uninstall ofscraper", "pip install ofscraper-community==3.16.4"),
        ("pipx", "pipx uninstall ofscraper", "pipx install ofscraper-community==3.16.4"),
        ("uv", "uv tool uninstall ofscraper", "uv tool install ofscraper-community==3.16.4"),
    ],
)
def test_upstream_ofscraper_says_what_to_install(patch_mod, monkeypatch, capsys, method, uninstall, install):
    _installed(monkeypatch, patch_mod, "ofscraper", "3.14.7")
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda *a, **k: pytest.fail("no install"))
    _answers(monkeypatch, "no")
    assert patch_mod._check_and_offer_upgrade(method) is False
    out = capsys.readouterr().out
    assert "older upstream OF-Scraper" in out
    assert "'ofscraper-community'" in out
    assert uninstall in out and install in out


def test_old_git_install_of_the_fork_is_switched_too(patch_mod, monkeypatch, capsys):
    # git installs of 3.16.1 and older were named "ofscraper"
    _installed(monkeypatch, patch_mod, "ofscraper", "3.16.1+g8e8cb81")
    _answers(monkeypatch, "no")
    assert patch_mod._check_and_offer_upgrade("pip") is False
    assert "old package name" in capsys.readouterr().out


@pytest.mark.parametrize(
    "method, uninstall",
    [
        ("pip", [sys.executable, "-m", "pip", "uninstall", "-y", "ofscraper"]),
        ("pipx", ["pipx", "uninstall", "ofscraper"]),
        ("uv", ["uv", "tool", "uninstall", "ofscraper"]),
    ],
)
def test_switch_uninstalls_upstream_then_installs(patch_mod, monkeypatch, method, uninstall):
    runs, installs = [], []
    _installed(monkeypatch, patch_mod, "ofscraper", "3.14.7")
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda cmd, *a, **k: runs.append(cmd))
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda m, **k: installs.append(m) or True)
    _answers(monkeypatch, "yes")
    assert patch_mod._check_and_offer_upgrade(method) is True
    assert runs == [uninstall]
    assert installs == [method]


def test_command_only_version_before_3_16_is_treated_as_upstream(patch_mod, monkeypatch, capsys):
    # only `ofscraper --version` answered, so the package name is unknown
    _installed(monkeypatch, patch_mod, None, "3.14.7")
    _answers(monkeypatch, "no")
    assert patch_mod._check_and_offer_upgrade("pip") is False
    assert "pip uninstall ofscraper" in capsys.readouterr().out


@pytest.mark.parametrize("detected, expected", [("pip", "pip"), ("unknown", "pipx")])
def test_windows_cli_on_path_only_means_pipx_when_nothing_else_was_found(
    patch_mod, monkeypatch, detected, expected
):
    # a pip or venv install also puts ofscraper on PATH; it used to be taken for pipx
    seen = []
    monkeypatch.setattr(patch_mod.platform, "system", lambda: "Windows")
    monkeypatch.setattr(patch_mod.sys, "version_info", _V(3, 12, 0, "final", 0))
    monkeypatch.setattr(patch_mod, "_detect_install_method", lambda: detected)
    monkeypatch.setattr(patch_mod, "_pipx_text_mentions_package", lambda *a: False)
    monkeypatch.setattr(patch_mod, "_windows_ofscraper_cli_version", lambda: "3.16.4")
    monkeypatch.setattr(patch_mod, "_check_and_offer_upgrade", lambda m: seen.append(m) or True)
    monkeypatch.setattr(patch_mod, "_install_gui_deps", lambda m, **k: True)
    monkeypatch.setattr(patch_mod, "apply", lambda **k: 0)
    monkeypatch.setattr(sys, "argv", ["patch", "-y"])
    assert patch_mod.main() == 0
    assert seen == [expected]


def test_switch_stops_when_the_uninstall_fails(patch_mod, monkeypatch):
    _installed(monkeypatch, patch_mod, "ofscraper", "3.14.7")

    def fail(cmd, *a, **k):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(patch_mod.subprocess, "run", fail)
    monkeypatch.setattr(patch_mod, "_install_ofscraper", lambda *a, **k: pytest.fail("no install"))
    _answers(monkeypatch, "yes")
    assert patch_mod._check_and_offer_upgrade("pip") is False


def test_both_packages_in_one_python_warns(patch_mod, monkeypatch, capsys):
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_dist", lambda m=None: ("ofscraper-community", "3.16.4"))
    monkeypatch.setattr(
        patch_mod, "_pip_dists", lambda: [("ofscraper-community", "3.16.4"), ("ofscraper", "3.14.7")]
    )
    assert patch_mod._check_and_offer_upgrade("pip") is True
    assert "pip uninstall -y ofscraper ofscraper-community" in capsys.readouterr().out


def test_dist_info_names_are_read(patch_mod, tmp_path):
    sp = tmp_path / "site-packages"
    (sp / "ofscraper").mkdir(parents=True)
    di = sp / "ofscraper_community-3.16.4.dist-info"
    di.mkdir()
    (di / "METADATA").write_text("Metadata-Version: 2.4\nName: ofscraper-community\nVersion: 3.16.4\n")
    assert patch_mod._read_dist_info(sp / "ofscraper") == ("ofscraper-community", "3.16.4")
    up = sp / "ofscraper-3.14.7.dist-info"
    up.mkdir()
    (up / "METADATA").write_text("Metadata-Version: 2.1\nName: ofscraper\nVersion: 3.14.7\n")
    assert patch_mod._read_dist_infos(sp / "ofscraper") == [
        ("ofscraper-community", "3.16.4"),
        ("ofscraper", "3.14.7"),
    ]


def test_pip_dists_reads_both_names(patch_mod, monkeypatch):
    import importlib.metadata as meta

    versions = {"ofscraper-community": "3.16.4"}

    def version(name):
        if name in versions:
            return versions[name]
        raise meta.PackageNotFoundError(name)

    monkeypatch.setattr(meta, "version", version)
    assert patch_mod._pip_dists() == [("ofscraper-community", "3.16.4")]
    versions = {"ofscraper": "3.14.7"}
    assert patch_mod._pip_dists() == [("ofscraper", "3.14.7")]


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
    monkeypatch.setattr(patch_mod, "_find_older_python", lambda: pytest.fail("looked for 3.11/3.12"))
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda cmd, *a, **k: runs.append(cmd))
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.16.4")
    assert patch_mod._install_ofscraper("pipx") is True
    assert runs == [["pipx", "install", "--force", _SPEC]]


def test_install_does_not_need_git(patch_mod, monkeypatch):
    runs = []
    monkeypatch.setattr(patch_mod.sys, "version_info", _V(3, 12, 0, "final", 0))
    monkeypatch.setattr(patch_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(patch_mod.subprocess, "run", lambda cmd, *a, **k: runs.append(cmd))
    monkeypatch.setattr(patch_mod, "_get_installed_ofscraper_version", lambda m=None: "3.16.4")
    assert patch_mod._install_ofscraper("pip") is True
    assert runs == [[sys.executable, "-m", "pip", "install", "--upgrade", "--force-reinstall", _SPEC]]


@pytest.mark.parametrize("venv", ["ofscraper-community", "ofscraper"])
def test_pipx_list_json_is_read(patch_mod, monkeypatch, venv):
    package = "ofscraper-community" if venv == "ofscraper-community" else "ofscraper"
    data = {"venvs": {venv: {"metadata": {"main_package": {"package": package, "package_version": "3.16.4"}}}}}
    monkeypatch.setattr(
        patch_mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=json.dumps(data), stderr=""),
    )
    assert patch_mod._pipx_list_json() == data
    assert patch_mod._get_installed_ofscraper_dist("pipx") == (package, "3.16.4")
    assert patch_mod._get_installed_ofscraper_version("pipx") == "3.16.4"
    assert patch_mod._pipx_venv_name() == venv


def test_root_and_tree_copies_match():
    root_copy = Path(__file__).resolve().parents[3] / "patch_ofscraper_3.16.4_gui.py"
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
