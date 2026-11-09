"""Every scraper file changed from stock 3.14.7 is shipped by the GUI patch.

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
STOCK = "932e9e1"  # "OF-Scraper-3.14.7 released"


def _changed_files():
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=d", STOCK, "HEAD", "--", "ofscraper"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git is not available")
    if out.returncode != 0:
        pytest.skip("stock 3.14.7 commit is not in this checkout")
    return [line.split("/ofscraper/", 1)[1] for line in out.stdout.split() if "/ofscraper/" in line]


def test_every_changed_scraper_file_is_on_the_patch_list():
    text = (ROOT / "patch_ofscraper_3.14.7_gui.py").read_text(encoding="utf-8")
    files = set(ast.literal_eval(re.search(r"^FILES = (\[.*\])$", text, re.M).group(1)))
    # plugins ship separately (Available Plugins), not with the patch
    missing = [f for f in _changed_files() if not f.startswith("plugins/") and f not in files]
    assert missing == []
