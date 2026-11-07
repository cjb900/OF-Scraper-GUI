import atexit
import os
import shutil
import sys
import tempfile

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it.
sys.argv = sys.argv[:1]

# ofscraper keeps its config, profiles and databases under the home folder.
# Point that at a throwaway folder so tests see the default config and never
# read or rewrite the real ~/.config/ofscraper of whoever runs them.
_test_home = tempfile.mkdtemp(prefix="ofscraper-test-home-")
os.environ["HOME"] = _test_home
os.environ["USERPROFILE"] = _test_home
atexit.register(shutil.rmtree, _test_home, ignore_errors=True)

# The app's entry module imports ofscraper's packages in an order that avoids
# their circular imports; importing a leaf module first fails.
import ofscraper.main.open.load  # noqa: E402,F401
