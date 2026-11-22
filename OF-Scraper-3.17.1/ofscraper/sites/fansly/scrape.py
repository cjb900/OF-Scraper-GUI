"""Fansly versions of the area fetchers OF-Scraper's post pipeline calls.

Each returns OnlyFans-shaped dicts (see ``normalize``), so the caller wraps
them in ``Post`` and writes them to the database exactly as it does for
OnlyFans.
"""

import contextlib
import logging

import ofscraper.utils.settings as settings
from ofscraper.sites.fansly import api, normalize

log = logging.getLogger("shared")

# the post areas Fansly supports; others are skipped for Fansly profiles
AREAS = ("Profile", "Timeline", "Messages", "Purchased", "Labels")


@contextlib.asynccontextmanager
async def _session(c):
    if c is not None:
        yield c
        return
    import ofscraper.managers.manager as manager

    async with manager.Manager.session.aget_ofsession() as session:
        yield session


def _after():
    """``--after`` as epoch seconds, or None for a full scan."""
    after = getattr(settings.get_settings(), "after", None)
    if not after:
        return None
    return getattr(after, "float_timestamp", None)


async def get_timeline_posts(model_id, username, c=None, post_id=None):
    async with _session(c) as c:
        if post_id:
            posts = await api.posts_by_id(c, post_id)
            return [p for p in posts if str(p["id"]) in {str(x) for x in post_id}]
        report = normalize.ScanReport()
        posts = await api.timeline(c, model_id, after=_after(), report=report)
        try:
            stats = await api.timeline_stats(c, model_id)
        except Exception as e:  # the check is only a report
            log.debug(f"Fansly media counts not read: {e}")
            stats = None
    log.debug(f"Fansly timeline: {len(posts)} posts for {username}")
    log.info(report.summary(username, stats, after=_after()))
    return posts


async def get_messages(model_id, username, c=None, post_id=None):
    async with _session(c) as c:
        group_id = api.group_id_for(await api.groups(c), model_id)
        if not group_id:
            log.info(f"No Fansly conversation with {username}")
            return []
        found = await api.messages(c, group_id, after=_after())
    if post_id:
        found = [m for m in found if str(m["id"]) in {str(x) for x in post_id}]
    log.debug(f"Fansly messages: {len(found)} for {username}")
    return found


async def label_names(c, model_id):
    """The creator's walls as labels, in one batch (``labels.scrape_labels``'s form)."""
    async with _session(c) as c:
        walls, has_main_wall = await api.walls(c, model_id)
        found = normalize.labels(walls, has_main_wall=has_main_wall)
    log.debug(f"Fansly walls as labels: {[x['id'] for x in found]}")
    yield found


async def label_pages(c, label, model_id):
    """One wall's posts, a timeline page at a time, newest first."""
    async with _session(c) as c:
        async with contextlib.aclosing(
            api.timeline_pages(c, model_id, wall_id=label["id"])
        ) as pages:
            async for page in pages:
                yield page


async def get_profile(model_id, username, c=None):
    """The creator's avatar and banner as "Profile" items (read fresh, as
    their links are signed and expire)."""
    async with _session(c) as c:
        accounts = await api.accounts_by_id(c, [model_id])
    account = next(
        (a for a in accounts or [] if str(a.get("id")) == str(model_id)), None
    )
    if not account:
        log.info(f"No Fansly account for {username}: no avatar or banner to download")
        return []
    found = normalize.profile_items(account)
    log.debug(f"Fansly profile: {len(found)} pictures for {username}")
    return found


async def get_paid_posts(model_id, username, c=None):
    async with _session(c) as c:
        found = await api.purchases(c, model_id)
    log.debug(f"Fansly purchases: {len(found)} for {username}")
    return found


def _list_names(names):
    """User list names without OF-Scraper's reserved ones ('main',
    'ofscraper.main'), which mean "no list filter"."""
    try:
        import ofscraper.utils.of_env.of_env as of_env

        reserved = {
            str(of_env.getattr("OFSCRAPER_RESERVED_LIST") or "").lower(),
            str(of_env.getattr("OFSCRAPER_RESERVED_LIST_ALT") or "").lower(),
        }
    except Exception:
        reserved = {"ofscraper.main", "main"}
    out = []
    for n in names or []:
        n = str(n).strip().lower()
        if n and n not in reserved and n not in out:
            out.append(n)
    return out


async def get_models(usernames=None, c=None, userlists=None, blacklists=None):
    """Creators to scrape, as OnlyFans-shaped model dicts.

    With usernames: every value goes to ``account?usernames=``, and the
    all-digit ones (which may be account ids, or all-digit usernames) to
    ``account?ids=`` as well. With user lists (and no usernames): the
    accounts on the user's Fansly lists with those names. Otherwise every
    followed account (``account/<me>/following``, then ``account?ids=``).
    Without usernames, accounts on a black list are left out (as on OnlyFans,
    named creators are never filtered).

    userlists / blacklists default to the run's settings (--ul / --bl, or
    the config's default lists).
    """
    import ofscraper.utils.me as me_util

    usernames = [str(u) for u in (usernames or []) if u and u != "ALL"]
    ids = [u for u in usernames if u.isdigit()]
    if userlists is None or blacklists is None:
        try:
            run = settings.get_settings()
        except Exception:
            run = None
        if userlists is None:
            userlists = getattr(run, "userlist", None)
        if blacklists is None:
            blacklists = getattr(run, "blacklist", None)
    userlists = _list_names(userlists)
    blacklists = _list_names(blacklists)
    async with _session(c) as c:
        blocked = set()
        if blacklists and not usernames:
            blocked_ids, missing = await api.accounts_on_lists(c, blacklists)
            blocked = set(blocked_ids)
            if missing:
                log.warning(f"Fansly black list(s) not found: {', '.join(missing)}")
        if not usernames and userlists:
            list_ids, missing = await api.accounts_on_lists(c, userlists)
            if missing:
                log.warning(
                    f"Fansly list(s) not found in My lists: {', '.join(missing)}. Only lists "
                    "you made are available (not VIP Accounts, Blocked, Muted or DM Allow)."
                )
            log.info(f"Fansly lists {', '.join(userlists)}: {len(list_ids)} accounts")
            accounts = await api.accounts_by_id(c, [i for i in list_ids if i not in blocked])
            return [normalize.model(a) for a in accounts if a.get("id") and a.get("username")]
        if usernames:
            accounts = list(await api.accounts_by_username(c, usernames))
            if ids:
                accounts.extend(await api.accounts_by_id(c, ids))
            # a name and the id of the same creator return it twice
            seen = set()
            accounts = [
                a for a in accounts
                if str(a.get("id")) not in seen and not seen.add(str(a.get("id")))
            ]
        else:
            accounts = await api.accounts_by_id(c, await api.following_ids(c, me_util.get_id()))
    return [
        normalize.model(a) for a in accounts
        if a.get("id") and a.get("username") and str(a.get("id")) not in blocked
    ]
