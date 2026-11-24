"""ONLYFANS_GUI_ARGS / FANSLY_GUI_ARGS start each site with its own options
when the tab window opens (Docker: one container scraping both sites)."""

from types import SimpleNamespace

import pytest

from ofscraper.gui import site_context

OF, FS = site_context.ONLYFANS, site_context.FANSLY


def test_reads_both_variables():
    env = {
        "ONLYFANS_GUI_ARGS": "--daemon 60 -ts --username ALL --posts all",
        "FANSLY_GUI_ARGS": " --daemon 120 --username ALL --posts all ",
    }
    assert site_context.startup_site_args(env) == {
        OF: ["--daemon", "60", "-ts", "--username", "ALL", "--posts", "all"],
        FS: ["--daemon", "120", "--username", "ALL", "--posts", "all"],
    }


def test_blank_or_missing_is_not_set():
    assert site_context.startup_site_args({"ONLYFANS_GUI_ARGS": "  ", "FANSLY_GUI_ARGS": ""}) == {}
    assert site_context.startup_site_args({}) == {}


def test_site_options_are_dropped():
    # the tab window sets --gui, --site and --config for each site itself
    env = {"FANSLY_GUI_ARGS": "--gui --site onlyfans --config=/x.json --daemon 5 --config /y.json"}
    assert site_context.startup_site_args(env) == {FS: ["--daemon", "5"]}


def test_quoted_values_stay_together():
    env = {"ONLYFANS_GUI_ARGS": '--username "a b" --posts all'}
    assert site_context.startup_site_args(env)[OF] == ["--username", "a b", "--posts", "all"]


def test_plan_without_per_site_options_is_unchanged():
    # GUI_ARGS (forwarded) goes to the shown site only, as before
    assert site_context.startup_plan(FS, ["--daemon", "5"], {}) == [(FS, ["--daemon", "5"])]
    assert site_context.startup_plan(OF, [], {}) == [(OF, [])]


def test_plan_starts_both_sites_with_their_own_options():
    per_site = {OF: ["--daemon", "60"], FS: ["--daemon", "120"]}
    assert site_context.startup_plan(OF, [], per_site) == [
        (OF, ["--daemon", "60"]),
        (FS, ["--daemon", "120"]),
    ]
    # the shown (last-used) site still starts first
    assert site_context.startup_plan(FS, [], per_site) == [
        (FS, ["--daemon", "120"]),
        (OF, ["--daemon", "60"]),
    ]


def test_plan_ignores_gui_args_when_per_site_options_are_set():
    per_site = {FS: ["--daemon", "120"]}
    # the shown site opens without options; Fansly starts with its own
    assert site_context.startup_plan(OF, ["--daemon", "60"], per_site) == [
        (OF, []),
        (FS, ["--daemon", "120"]),
    ]


def test_window_starts_every_planned_site():
    pytest.importorskip("PyQt6")
    from ofscraper.gui import site_host

    _, host_class = site_host._define_classes()
    started = []

    class Tab:
        def __init__(self, site):
            self.site = site

        def start(self, extra=None):
            started.append((self.site, extra))

    shown = []
    window = SimpleNamespace(
        site_tabs={OF: Tab(OF), FS: Tab(FS)},
        tabs=SimpleNamespace(setCurrentWidget=lambda tab: shown.append(tab.site)),
    )
    window.start_site = lambda site, extra=None: host_class.start_site(window, site, extra)
    host_class.start_sites(window, [(FS, ["--daemon", "120"]), (OF, ["--daemon", "60"])])
    assert started == [(FS, ["--daemon", "120"]), (OF, ["--daemon", "60"])]
    assert shown == [FS]
