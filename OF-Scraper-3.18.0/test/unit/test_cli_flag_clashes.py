"""No two options of one CLI command share a flag: click silently lets one win."""
import collections

import pytest

pytestmark = pytest.mark.unit

import ofscraper.utils.args.main as args_main  # noqa: E402
from ofscraper.utils.args.parse.commands.main import program  # noqa: E402

@pytest.fixture(scope="module")
def cli():
    # what parse_args() does before parsing
    added = []
    for name, cmd in {
        "manual": args_main.manual.manual,
        "msg_check": args_main.message.message_check,
        "story_check": args_main.story.story_check,
        "paid_check": args_main.paid.paid_check,
        "post_check": args_main.post.post_check,
        "metadata": args_main.metadata.metadata,
        "db": args_main.db.db,
    }.items():
        if name not in program.commands:  # another test may have added them
            program.add_command(cmd, name)
            added.append(name)
    yield program
    # take them out again: a later parse_args() adds them itself, and cloup
    # refuses a name that's already there ('command "manual" already exists')
    sections = list(getattr(program, "_user_sections", []))
    if getattr(program, "_default_section", None) is not None:
        sections.append(program._default_section)
    for name in added:
        program.commands.pop(name, None)
        for section in sections:
            section.commands.pop(name, None)


def _clashes(cmd, path="ofscraper"):
    flags = collections.defaultdict(list)
    for p in cmd.params:
        for flag in [*p.opts, *p.secondary_opts]:
            flags[flag].append(p.name)
    found = {(path, f): names for f, names in flags.items() if len(names) > 1}
    for name, sub in getattr(cmd, "commands", {}).items():
        found.update(_clashes(sub, f"{path} {name}"))
    return found


def test_no_command_has_a_flag_twice(cli):
    found = _clashes(cli)
    assert "metadata" in cli.commands
    assert found == {}


def _metadata_params(cli, *argv):
    cmd = cli.commands["metadata"]
    return cmd.make_context("metadata", ["-md", "update", *argv]).params


def test_promo_skip_and_post_script_flags(cli):
    def params(*argv):
        return cli.make_context("ofscraper", list(argv)).params

    assert params("-psk")["promo"] is False
    assert params("--promo-skip")["promo"] is False
    assert params("-po")["promo"] is True
    p = params("-ps", "after.sh")  # -ps is --post-script
    assert p["post_script"] == "after.sh" and p["promo"] is None
