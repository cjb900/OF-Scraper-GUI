"""Update now: download and check the patch script, then run it after the GUI exits."""

import os
import pathlib
import subprocess
import sys

import pytest

from ofscraper.gui.utils import self_update as su
from ofscraper.gui.utils import version_check as vc

GOOD = 'import sys\nPATCH_ID = "20261116_gui_3_17_1_v441"\nZIP_B64 = "AAAA"\nprint("patched")\n'
URL = "https://raw.githubusercontent.com/cjb900/OF-Scraper-GUI/testing/patch_ofscraper_3.17.1_gui.py"


@pytest.fixture
def updates(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "updates_dir", lambda: tmp_path / "gui_updates")
    return tmp_path / "gui_updates"


def fake_download(monkeypatch, body: bytes, status=200):
    import httpx

    class Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def stream(self, method, url):
            client = self

            class Resp:
                def __enter__(self):
                    return self

                def __exit__(self, *a):
                    return False

                def raise_for_status(self):
                    if status >= 400:
                        raise httpx.HTTPStatusError("bad", request=None, response=None)

                def iter_bytes(self):
                    yield body[: len(body) // 2]
                    yield body[len(body) // 2:]

            return Resp()

    monkeypatch.setattr(httpx, "Client", Client)


# --- checking the download ---------------------------------------------------------------


def test_verify_accepts_the_expected_patch(tmp_path):
    p = tmp_path / "patch_ofscraper_3.17.1_gui.py"
    p.write_text(GOOD)
    assert su.verify_patch(p, 441) == "20261116_gui_3_17_1_v441"


@pytest.mark.parametrize("text, why", [
    (GOOD.replace("v441", "v440"), "not v441"),
    ("<html>rate limited</html>", "complete patch script"),
    ("x = 1\n", "isn't a GUI patch script"),
    (GOOD[: len(GOOD) // 2], "complete patch script"),
])
def test_verify_rejects(tmp_path, text, why):
    p = tmp_path / "patch_ofscraper_3.17.1_gui.py"
    p.write_text(text)
    with pytest.raises(su.UpdateFailed, match=why):
        su.verify_patch(p, 441)


def test_download_saves_a_verified_script(updates, monkeypatch):
    fake_download(monkeypatch, GOOD.encode())
    path = su.download_patch(URL, 441)
    assert path == updates / "patch_ofscraper_3.17.1_gui.py"
    assert path.read_text() == GOOD
    assert not list(updates.glob("*.part"))


def test_a_bad_download_leaves_nothing(updates, monkeypatch):
    fake_download(monkeypatch, b"<html>not found</html>")
    with pytest.raises(su.UpdateFailed):
        su.download_patch(URL, 441)
    assert not list(updates.glob("*"))


def test_only_patch_scripts_are_downloaded(updates):
    with pytest.raises(su.UpdateFailed, match="unexpected download name"):
        su.download_patch("https://example.com/evil.py", 441)


def test_release_download_link_is_the_newest_patch():
    release = {"assets": [
        {"name": "patch_ofscraper_3.14.7_gui.py", "browser_download_url": "u147"},
        {"name": "patch_ofscraper_3.17.1_gui.py", "browser_download_url": "u171"},
        {"name": "notes.txt", "browser_download_url": "x"},
    ]}
    assert vc.release_patch_url(release) == "u171"
    assert vc.release_patch_url({"assets": []}) is None


# --- the Python that runs it -----------------------------------------------------------------


def test_pip_install_uses_this_python(monkeypatch):
    monkeypatch.setattr(sys, "base_prefix", sys.prefix)
    assert su.patch_python() == [sys.executable]


def test_venv_uses_its_base_python(monkeypatch, tmp_path):
    base = tmp_path / "python3"
    base.write_text("")
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "venv"))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "base"))
    monkeypatch.setattr(sys, "_base_executable", str(base), raising=False)
    assert su.patch_python() == [str(base)]


def test_a_python_inside_the_venv_is_never_used(monkeypatch, tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    inside = venv / "bin" / "python3"
    inside.write_text("")
    monkeypatch.setattr(sys, "prefix", str(venv))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "base"))
    monkeypatch.setattr(sys, "_base_executable", str(inside), raising=False)
    monkeypatch.setattr(su.platform, "system", lambda: "Linux")
    monkeypatch.setattr(su.shutil, "which", lambda name: str(inside))
    assert su.patch_python() == []


# --- the console ----------------------------------------------------------------------------


def test_first_available_terminal(monkeypatch):
    found = {"konsole": "/usr/bin/konsole", "xterm": "/usr/bin/xterm"}
    monkeypatch.setattr(su.shutil, "which", lambda name: found.get(name))
    assert su.terminal_command(["py", "x"]) == ["/usr/bin/konsole", "-e", "py", "x"]
    monkeypatch.setattr(su.shutil, "which", lambda name: None)
    assert su.terminal_command(["py"]) is None


@pytest.mark.parametrize("system", ["Windows", "Linux"])
def test_launch_opens_a_console_that_waits(monkeypatch, tmp_path, system):
    script = tmp_path / "patch_ofscraper_3.17.1_gui.py"
    script.write_text(GOOD)
    calls = []
    monkeypatch.setattr(su, "patch_python", lambda: ["/py"])
    monkeypatch.setattr(su.platform, "system", lambda: system)
    monkeypatch.setattr(su.shutil, "which", lambda name: "/usr/bin/xterm" if name == "xterm" else None)
    monkeypatch.setattr(su.subprocess, "Popen", lambda cmd, **kw: calls.append((cmd, kw)))
    su.launch_after_exit(script, wait_pid=4242)
    cmd, kw = calls[0]
    helper = str(tmp_path / "run_gui_update.py")
    assert cmd[-5:] == ["/py", helper, "4242", "/py", str(script)]
    assert (tmp_path / "run_gui_update.py").read_text() == su.HELPER
    if system == "Windows":
        assert kw["creationflags"] & 0x10  # a new console window
    else:
        assert cmd[:2] == ["/usr/bin/xterm", "-e"] and kw["start_new_session"]


def test_no_terminal_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(su, "patch_python", lambda: ["/py"])
    monkeypatch.setattr(su.platform, "system", lambda: "Linux")
    monkeypatch.setattr(su.shutil, "which", lambda name: None)
    with pytest.raises(su.UpdateFailed, match="terminal"):
        su.launch_after_exit(tmp_path / "p.py", wait_pid=1)


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX pid")
def test_helper_runs_the_patch_once_the_gui_is_gone(tmp_path):
    # a process that has already exited stands in for the closed GUI
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    marker = tmp_path / "ran"
    patch = tmp_path / "patch.py"
    patch.write_text(f"open({str(marker)!r}, 'w').write('yes')\n")
    helper = tmp_path / "run_gui_update.py"
    helper.write_text(su.HELPER)
    out = subprocess.run(
        [sys.executable, str(helper), str(done.pid), sys.executable, str(patch)],
        input="\n", capture_output=True, text=True, timeout=30,
    )
    assert marker.read_text() == "yes"
    assert "The patch script finished." in out.stdout
