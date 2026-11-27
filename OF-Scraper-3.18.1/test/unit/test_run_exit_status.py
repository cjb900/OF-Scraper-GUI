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




@pytest.mark.parametrize("gui", [True, False])
def test_an_unreachable_database_stops_the_cli_but_not_the_gui(monkeypatch, caplog, gui):
    # 3.18.1 checks PostgreSQL before any work; the GUI is where the address
    # is fixed or PostgreSQL turned off, so it has to open
    from types import SimpleNamespace

    import ofscraper.db.postgres as postgres
    import ofscraper.utils.settings as settings

    def unreachable():
        raise postgres.PostgresUnavailable("Can't use the PostgreSQL database at x: the server can't be reached.")

    monkeypatch.setattr(postgres, "enabled", lambda: True)
    monkeypatch.setattr(postgres, "POSTGRES", SimpleNamespace(check=unreachable))
    monkeypatch.setattr(settings, "get_args", lambda *a, **k: SimpleNamespace(gui=gui))
    from ofscraper.gui import site_context

    monkeypatch.setattr(site_context, "is_child", lambda: True)  # a site's window
    if gui:
        with caplog.at_level(logging.WARNING, logger="shared"):
            run.check_database()
        assert "The GUI opens anyway" in caplog.text
    else:
        with pytest.raises(postgres.PostgresUnavailable):
            run.check_database()


def test_the_tab_window_doesnt_check_the_database(monkeypatch):
    from types import SimpleNamespace

    import ofscraper.db.postgres as postgres
    import ofscraper.utils.settings as settings
    from ofscraper.gui import site_context

    monkeypatch.setattr(settings, "get_args", lambda *a, **k: SimpleNamespace(gui=True))
    monkeypatch.setattr(site_context, "is_child", lambda: False)
    monkeypatch.setattr(site_context, "tabs_enabled", lambda: True)
    monkeypatch.setattr(postgres, "enabled", lambda: pytest.fail("checked the database"))
    run.check_database()
