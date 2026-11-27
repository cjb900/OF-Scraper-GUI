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


def test_idle_interrupt_shuts_down_without_task_done_error(monkeypatch):
    runs = []
    jobs = InterruptWhenIdle()
    _stub_daemon(monkeypatch, jobs, lambda: runs.append(1))

    with pytest.raises(KeyboardInterrupt):
        scraper.daemon_process()
    assert runs == [1]
    assert jobs.unfinished_tasks == 0


def test_stop_is_written_to_the_log(monkeypatch, caplog):
    # so a stop shows up in the log files, not only on the console / docker logs
    jobs = InterruptWhenIdle()
    _stub_daemon(monkeypatch, jobs, lambda: None)

    with caplog.at_level(logging.WARNING, logger="shared"):
        with pytest.raises(KeyboardInterrupt):
            scraper.daemon_process()
    assert "Stop requested: shutting down the daemon" in caplog.text


def test_interrupt_during_a_job_still_marks_it_done(monkeypatch):
    def runner():
        raise KeyboardInterrupt

    jobs = queue.Queue()
    _stub_daemon(monkeypatch, jobs, runner)

    with pytest.raises(KeyboardInterrupt):
        scraper.daemon_process()
    assert jobs.unfinished_tasks == 0


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGTERM cannot be delivered in-process on Windows"
)
def test_sigterm_while_idle_exits_with_keyboard_interrupt():
    # the real daemon loop and SIGTERM handler; only auth and scraping are stubbed
    script = textwrap.dedent(
        """
        import os, signal, threading
        from types import SimpleNamespace
        import ofscraper.main.open.load  # import order, as in conftest
        import ofscraper.commands.scraper.scraper as scraper

        ran = threading.Event()
        def runner():
            ran.set()
            threading.Timer(0.3, os.kill, (os.getpid(), signal.SIGTERM)).start()

        scraper.checkers.check_auth = lambda: None
        scraper.scraperManager = lambda: SimpleNamespace(runner=runner)
        scraper.settings.get_settings = lambda: SimpleNamespace(output_level="NORMAL")
        scraper.manager.Manager = SimpleNamespace(
            current_model_manager=SimpleNamespace(sync_models=lambda: None)
        )
        scraper.actions.select_areas = lambda: None
        scraper.set_schedule = lambda *args, **kwargs: None
        try:
            scraper.daemon_process()
        except KeyboardInterrupt:
            print("interrupted" if ran.is_set() else "interrupted before the first run")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "interrupted"
