"""-ml / --ml / --my-list (Fansly's "My lists") are other names for -ul."""
import click
import pytest
from click.testing import CliRunner

from ofscraper.utils.args.parse.arguments.user_select import user_list_option

pytestmark = pytest.mark.unit


@click.command()
@user_list_option
def _cmd(userlist):
    click.echo(",".join(sorted(userlist)))


@pytest.mark.parametrize(
    "args",
    [
        ["-ul", "Testing"],
        ["--userlist", "testing"],
        ["-ml", "testing"],
        ["--ml", "TESTING"],
        ["--my-list", "testing"],
        ["--my-lists", "testing"],
        ["--mylist", "testing"],
        ["--mylists", "testing"],
    ],
)
def test_every_name_sets_userlist(args):
    result = CliRunner().invoke(_cmd, args)
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "testing"


def test_names_combine():
    result = CliRunner().invoke(_cmd, ["--ml", "a,b", "-ul", "c"])
    assert result.output.strip() == "a,b,c"


def test_double_dash_ul_is_not_an_option():
    # the docs once said --ul; only -ul (one dash) exists
    result = CliRunner().invoke(_cmd, ["--ul", "a"])
    assert result.exit_code != 0
    assert "No such option" in result.output
