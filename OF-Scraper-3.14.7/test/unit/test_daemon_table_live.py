"""A daemon run fills the table live on a desktop; only Docker (Xvfb) holds
the rows back until the run finishes."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6")

import ofscraper.gui.app as gui_app  # noqa: E402
from ofscraper.gui.pages import table_page  # noqa: E402


@pytest.mark.parametrize("docker", [True, False])
def test_defer_follows_docker(monkeypatch, docker):
    monkeypatch.setattr(gui_app, "_is_docker", lambda: docker)
    assert table_page._defer_daemon_table() is docker


@pytest.mark.parametrize("docker", [True, False])
def test_daemon_rerun_defers_only_in_docker(monkeypatch, docker):
    monkeypatch.setattr(gui_app, "_is_docker", lambda: docker)
    page = MagicMock()
    page._running_text.return_value = "Running…"
    table_page.TablePage._on_daemon_run_starting(page, 2)
    assert page.data_table.begin_deferred.called is docker
    page.data_table.clear_all.assert_called_once()
