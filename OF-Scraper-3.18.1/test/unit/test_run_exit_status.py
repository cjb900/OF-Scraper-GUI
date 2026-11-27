import logging

import pytest

import ofscraper.main.open.run as run


def _fail():
    raise RuntimeError("simulated failure")


def test_failed_run_exits_with_status_1_and_logs_the_error(monkeypatch):
    monkeypatch.setattr(run, "start_manager", _fail)
    monkeypatch.setattr(run.exit_manager, "shutdown", lambda: None)
    records = []
    handler = logging.Handler(level=logging.ERROR)
    handler.emit = records.append
    logger = logging.getLogger("shared")
    logger.addHandler(handler)
    try:
        with pytest.raises(SystemExit) as exit_info:
            run.main()
    finally:
        logger.removeHandler(handler)
    assert exit_info.value.code == 1
    assert any("simulated failure" in r.getMessage() for r in records)


def test_successful_run_exits_0(monkeypatch):
    # 3.18.1: run.main() always ends with the run's exit status
    monkeypatch.setattr(run, "start_manager", lambda: None)
    monkeypatch.setattr(run, "check_dry_run", lambda: None)
    monkeypatch.setattr(run, "check_database", lambda: None)
    with pytest.raises(SystemExit) as exit_info:
        run.main()
    assert exit_info.value.code == 0


def test_closing_the_gui_exits_0_after_a_partial_scrape(monkeypatch):
    # a GUI scrape with failed files records PARTIAL (4); closing the window
    # then showed "stopped unexpectedly (exit code 4)" in the tab window
    import ofscraper.main.close.exit_status as exit_status
    import ofscraper.managers.manager as manager_mod

    def gui_session():
        exit_status.record(exit_status.PARTIAL)
        manager_mod._gui_closed()

    monkeypatch.setattr(run, "start_manager", gui_session)
    monkeypatch.setattr(run, "check_dry_run", lambda: None)
    monkeypatch.setattr(run, "check_database", lambda: None)
    with pytest.raises(SystemExit) as exit_info:
        run.main()
    assert exit_info.value.code == 0


