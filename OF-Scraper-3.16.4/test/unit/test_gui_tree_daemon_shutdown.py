# GUI tree tests from the 3.14.7 tree's test/unit/test_daemon_shutdown.py that the fork's test/test_daemon_shutdown.py does not have
import sys

# ofscraper parses sys.argv when settings are first read, so hide pytest's
# own command-line flags from it, then import the app's entry module first
# (importing a leaf module first hits a circular import).
sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import logging
import queue
import subprocess
import sys
import textwrap
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

import ofscraper.commands.scraper.scraper as scraper


class InterruptWhenIdle(queue.Queue):
    # a signal arriving while the main thread waits for the next job
    def get(self, *args, **kwargs):
        if self.empty():
            raise KeyboardInterrupt
        return super().get(*args, **kwargs)


def _stub_daemon(monkeypatch, jobs, runner):
    monkeypatch.setattr(scraper, "jobqueue", jobs)
    monkeypatch.setattr(scraper.exit, "sigterm_as_keyboard_interrupt", lambda: None)
    monkeypatch.setattr(scraper.checkers, "check_auth", lambda: None)
    monkeypatch.setattr(scraper, "scraperManager", lambda: SimpleNamespace(runner=runner))
    monkeypatch.setattr(
        scraper.settings, "get_settings", lambda: SimpleNamespace(output_level="NORMAL")
    )
    monkeypatch.setattr(
        scraper.manager,
        "Manager",
        SimpleNamespace(current_model_manager=SimpleNamespace(sync_models=lambda: None)),
    )
    monkeypatch.setattr(scraper.actions, "select_areas", lambda: None)
    monkeypatch.setattr(scraper, "set_schedule", lambda *args, **kwargs: None)


def test_stop_is_written_to_the_log(monkeypatch, caplog):
    # so a stop shows up in the log files, not only on the console / docker logs
    jobs = InterruptWhenIdle()
    _stub_daemon(monkeypatch, jobs, lambda: None)
    # other tests may have built the real "shared" logger, which doesn't
    # propagate, so caplog would see nothing
    monkeypatch.setattr(logging.getLogger("shared"), "propagate", True)

    with caplog.at_level(logging.WARNING, logger="shared"):
        with pytest.raises(KeyboardInterrupt):
            scraper.daemon_process()
    assert "Stop requested: shutting down the daemon" in caplog.text


