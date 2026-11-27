import pytest

pytestmark = pytest.mark.unit

import ofscraper.gui.utils.host_callbacks as host_callbacks


@pytest.fixture(autouse=True)
def no_host():
    host_callbacks.set_host(None)
    yield
    host_callbacks.set_host(None)


def test_ensure_gui_host_installs_the_gui_host():
    # it assigned _current_host without `global`, so every call raised
    # UnboundLocalError and get_host() stayed the no-op host
    host = host_callbacks.ensure_gui_host()
    assert isinstance(host, host_callbacks.GuiHostCallbacks)
    assert host_callbacks.get_host() is host


def test_ensure_gui_host_reuses_the_installed_host():
    first = host_callbacks.ensure_gui_host()
    assert host_callbacks.ensure_gui_host() is first
