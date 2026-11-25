import atexit
import os
import shutil
import sys
import tempfile

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it.
sys.argv = sys.argv[:1]

# Give every test session (one per xdist worker) its own empty home folder,
# set before ofscraper is imported, so no test can read or write the real
# ~/.config/ofscraper and every run starts like a fresh install. The app finds
# its config folder with Path.home() (HOME, or USERPROFILE on Windows) plus
# OFSC_CONFIG_DIR, so a user's own OFSC_CONFIG_DIR is dropped too.
_scratch_home = tempfile.mkdtemp(
    prefix=f"ofs-test-home-{os.environ.get('PYTEST_XDIST_WORKER', 'main')}-"
)
os.environ["HOME"] = _scratch_home
os.environ["USERPROFILE"] = _scratch_home
os.environ.pop("OFSC_CONFIG_DIR", None)
atexit.register(shutil.rmtree, _scratch_home, ignore_errors=True)

# The app's entry module imports ofscraper's packages in an order that avoids
# their circular imports; importing a leaf module first fails.
import ofscraper.main.open.load  # noqa: E402,F401


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _subcommand_registry_restored():
    """parse_args registers the subcommands, and cloup refuses a second
    registration. A test that parses for real (with global_args.args
    monkeypatched back afterwards) used to leave them registered, so the next
    real parse in that worker failed with 'command "manual" already exists'.
    Put the registry back after every test."""
    import ofscraper.utils.args.main as args_main

    program = args_main.main.program
    before = dict(program.commands)
    sections = list(getattr(program, "_user_sections", []))
    if getattr(program, "_default_section", None) is not None:
        sections.append(program._default_section)
    saved = [(s, dict(s.commands)) for s in sections]
    yield
    program.commands.clear()
    program.commands.update(before)
    for section, cmds in saved:
        section.commands.clear()
        section.commands.update(cmds)


@pytest.fixture(autouse=True)
def _database_url_not_kept():
    """of_env caches the environment it loaded. A PostgreSQL live test that
    loads it while OFSC_DATABASE_URL is set left the address cached after the
    variable was removed, so later tests in that worker used PostgreSQL. Drop
    such a cache after each test; the next read loads it again."""
    yield
    import ofscraper.utils.of_env as of_env_pkg

    cached = of_env_pkg._cached_settings or {}
    if cached.get("OFSC_DATABASE_URL") and not os.environ.get("OFSC_DATABASE_URL"):
        of_env_pkg._cached_settings = None
