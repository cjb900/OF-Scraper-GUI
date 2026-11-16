"""A normal scrape after a check-mode run doesn't inherit check mode's options."""

from types import SimpleNamespace

from ofscraper.gui.utils import workflow


def launch_args(**kw):
    base = dict(force_all=False, force=False, check_area=[], check_usernames=[], url=[],
                after=None, no_cache=False, no_api_cache=False, discord_level="OFF",
                allow_dupe_downloads=True, keep_message_purchased_dupes=False, quality=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_check_mode_options_are_put_back():
    args = launch_args()
    snap = workflow.launch_snapshot(args)
    # what a Check posts run with "Fetch fresh data" leaves behind
    args.force_all, args.force, args.after = True, True, 0
    args.check_area, args.check_usernames, args.url = ["Timeline"], ["model"], ["model"]
    workflow.restore_check_mode_args(args, snap)
    assert args.force_all is False and args.force is False
    assert args.check_area == [] and args.check_usernames == [] and args.url == []


def test_launch_values_are_kept():
    # a --force-all launch from the command line stays forced
    args = launch_args(force_all=True, url=["https://onlyfans.com/1/model"])
    snap = workflow.launch_snapshot(args)
    args.force_all, args.url = False, []
    workflow.restore_check_mode_args(args, snap)
    assert args.force_all is True and args.url == ["https://onlyfans.com/1/model"]


def test_snapshot_lists_are_copies():
    args = launch_args(check_area=["Timeline"])
    snap = workflow.launch_snapshot(args)
    args.check_area.append("Labels")
    assert snap["check_area"] == ["Timeline"]


def test_baseline_comes_from_the_launch_not_from_check_mode():
    snap = workflow.launch_snapshot(launch_args(after=None))
    # after a check-mode run "after" is 0 (scan from the start); the baseline
    # must still be the launch value
    assert snap["after"] is None
