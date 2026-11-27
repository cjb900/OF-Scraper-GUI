"""Every scraper file changed from stock 3.18.1 is shipped by the GUI patch.

A changed file that isn't on FILES stays stock on patched installs; a new
file that isn't on it makes the files that import it fail to load.
"""

import ast
import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
# the commit that added the unmodified 3.18.1 source
STOCK_MESSAGE = "OF-Scraper-3.18.1 released"


def _git(*args):
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available")
    if out.returncode != 0:
        pytest.skip(f"git {args[0]} failed: {out.stderr.strip()}")
    return out.stdout


def _changed_files():
    stock = _git("log", "--format=%H", "--fixed-strings", f"--grep={STOCK_MESSAGE}", "-1").strip()
    if not stock:
        pytest.skip("the stock 3.18.1 commit is not in this checkout")
    out = _git("diff", "--name-only", "--diff-filter=d", stock, "HEAD", "--", "ofscraper")
    return [line.split("/ofscraper/", 1)[1] for line in out.split() if "/ofscraper/" in line]


def _patch_files():
    text = (ROOT / "patch_ofscraper_3.18.1_gui.py").read_text(encoding="utf-8")
    return ast.literal_eval(re.search(r"^FILES = (\[.*\])$", text, re.M).group(1))


def test_every_changed_scraper_file_is_on_the_patch_list():
    files = set(_patch_files())
    missing = [f for f in _changed_files() if f not in files]
    assert missing == []


def test_file_count_matches_the_list():
    text = (ROOT / "patch_ofscraper_3.18.1_gui.py").read_text(encoding="utf-8")
    count = int(re.search(r"^FILE_COUNT = (\d+)$", text, re.M).group(1))
    assert count == len(_patch_files())


def test_every_listed_file_exists_except_keydive():
    # gui/scripts/drm_keydive.py is added to the source tree before a rebuild
    missing = [
        f for f in _patch_files()
        if f != "gui/scripts/drm_keydive.py" and not (ROOT / "ofscraper" / f).is_file()
    ]
    assert missing == []
