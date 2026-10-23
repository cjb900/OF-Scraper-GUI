from pytest_check import check

import ofscraper.utils.args.accessors.read as args_
from ofscraper.utils.of_env.values.test.test_constants import *
from ofscraper.utils.separate import separate_by_id


def test_args(mocker):
    args = args_.getargs([])
    assert (args) == args_.retriveArgs()


def test_args_change(mocker):
    args = args_.getargs([])
    args.renewal = "test"
    args_.changeargs(args)
    for key in vars(args).keys():
        with check:
            assert (vars(args)[key]) == vars(args_.retriveArgs())[key]
