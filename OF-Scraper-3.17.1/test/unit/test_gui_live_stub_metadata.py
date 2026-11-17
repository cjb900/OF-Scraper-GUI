"""Metadata mode in the GUI: 3.17.1's stop_live_screen asks the live display
for its renderable; the GUI's stand-in must answer (c10)."""

import sys

sys.argv = sys.argv[:1]
import ofscraper.main.open.load  # noqa: E402,F401

import pytest  # noqa: E402

pytest.importorskip("PyQt6")

import ofscraper.gui.utils.workflow as workflow  # noqa: E402


def test_null_live_has_a_renderable():
    live = workflow._NullLive()
    assert live.get_renderable() is None
    live.update("panel")
    assert live.get_renderable() == "panel"


def test_stop_live_screen_runs_with_the_gui_stub(monkeypatch):
    import ofscraper.utils.live.screens as screens

    monkeypatch.setattr(screens, "clear_tasks_by_name", lambda *a, **k: None)
    workflow._install_gui_live_stubs()
    try:
        screens.get_live().start()  # a previous run left it "started"
        ran = []
        with screens.stop_live_screen(clear="all"):
            ran.append(True)
        assert ran == [True]
    finally:
        workflow._uninstall_gui_live_stubs()


class Page:
    def __init__(self, failed):
        self._wf = type("W", (), {"_last_run_failed": failed})()

    def window(self):
        return type("M", (), {"workflow": self._wf})()


@pytest.mark.parametrize("cancelling, failed, status", [
    (False, False, "ok"),
    (False, True, "error"),
    (True, True, "cancelled"),
])
def test_a_failed_run_is_recorded_as_an_error(cancelling, failed, status):
    from ofscraper.gui.pages.table_page import TablePage

    assert TablePage._run_status(Page(failed), cancelling) == status
