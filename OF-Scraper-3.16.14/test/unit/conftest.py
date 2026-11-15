"""Unit tests for the GUI patch: the GUI and the patch's own changes to ofscraper.

test/conftest.py (upstream's) runs first: it clears sys.argv and imports the
app in an order that avoids circular imports.
"""
from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: GUI patch unit tests")


@pytest.fixture(autouse=True)
def _parse_args_can_run_again(monkeypatch):
    """parse_args registers the subcommands on each call, and cloup 4 refuses
    a second registration. In the app it runs once per process; here several
    tests parse arguments, so a name that's already registered is skipped."""
    import ofscraper.utils.args.main as args_main

    program = args_main.main.program
    original = program.add_command

    def add_command(cmd, name=None, *args, **kwargs):
        if (name or cmd.name) in program.commands:
            return None
        return original(cmd, name, *args, **kwargs)

    monkeypatch.setattr(program, "add_command", add_command)
    yield
