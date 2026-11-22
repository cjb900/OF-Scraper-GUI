"""Fansly REST calls used to list creators, posts, messages and purchases.

Every call goes through an OF-Scraper session (``c.requests_async``), which
adds the Fansly headers for ``apiv3.fansly.com``. Responses come wrapped in
``{"success": true, "response": ...}``; these helpers return the payload.
"""

import logging

from ofscraper.sites.fansly import constants, normalize
from ofscraper.sites.fansly.me import unwrap

log = logging.getLogger("shared")

ACCOUNT_IDS_BATCH = 5
ACCOUNT_MEDIA_BATCH = 150
FOLLOWING_LIMIT = 50
GROUPS_LIMIT = 20
MESSAGES_LIMIT = 25
# safety stop for cursor paging that never runs dry
MAX_PAGES = 10000


def _ids(values):
    # comma-separated lists are sent with literal commas, like the web app
    return ",".join(str(v) for v in values)


async def get_json(c, path):
    async with c.requests_async(url=constants.api_url(path)) as r:
        return unwrap(await r.json_())


# ------------------------------------------------------------------ accounts


async def accounts_by_username(c, usernames):
    usernames = [u for u in usernames if u]
    if not usernames:
        return []
    return list(await get_json(c, f"account?usernames={_ids(usernames)}") or [])


async def accounts_by_id(c, ids):
    out = []
    ids = [str(i) for i in ids]
    for start in range(0, len(ids), ACCOUNT_IDS_BATCH):
        batch = ids[start : start + ACCOUNT_IDS_BATCH]
        out.extend(await get_json(c, f"account?ids={_ids(batch)}") or [])
    return out


async def following_ids(c, my_account_id, limit=None):
    """Account ids the signed-in account follows (offset paging)."""
    limit = limit or FOLLOWING_LIMIT
    out = []
    offset = 0
    previous = None
    for _ in range(MAX_PAGES):
        page = await get_json(
            c,
            f"account/{my_account_id}/following?before=0&after=0&limit={limit}&offset={offset}",
        )
        page = page or []
        ids = [str(x["accountId"]) for x in page if x.get("accountId")]
        # a server that ignores offset returns the same page again
        if ids and ids == previous:
            break
        previous = ids
        out.extend(ids)
        if len(page) < limit:
            break
        offset += limit
    return out


# ------------------------------------------------------------------ lists

LIST_ITEMS_LIMIT = 50


async def my_lists(c):
    """The signed-in account's own lists: [{id, label, itemCount, ...}].

    Fansly's built-in lists (VIP, Blocked, Muted, DM Allow) aren't in this
    reply; only lists the user made.
    """
    return list(await get_json(c, "lists/account?itemId=") or [])


async def list_account_ids(c, list_id, item_count=None, limit=None):
    """Account ids on one list (lists/itemsnew; each item's id is an account id).

    Pages past the first by the last item's sortId (``before=``). Paging stops
    when a page is short, brings no new ids, or item_count ids are found, so a
    server that ignores the cursor can't loop.
    """
    limit = limit or LIST_ITEMS_LIMIT
    out = []
    seen = set()
    cursor = None
    for _ in range(MAX_PAGES):
        path = f"lists/itemsnew?listId={list_id}&limit={limit}&sortMode=3"
        if cursor:
            path += f"&before={cursor}"
        page = await get_json(c, path) or []
        new = [str(x["id"]) for x in page if x.get("id") and str(x["id"]) not in seen]
        seen.update(new)
        out.extend(new)
        if not new or len(page) < limit:
            break
        if item_count is not None and len(out) >= int(item_count):
            break
        cursor = page[-1].get("sortId") or page[-1].get("id")
    if item_count is not None and len(out) < int(item_count):
        log.warning(
            f"Fansly list {list_id}: got {len(out)} of {item_count} accounts"
        )
    return out


async def accounts_on_lists(c, names):
    """Account ids on the user's lists whose label matches one of names
    (case-insensitive), and the labels that weren't found."""
    wanted = {str(n).strip().lower() for n in names if str(n).strip()}
    lists = [x for x in await my_lists(c) if str(x.get("label") or "").lower() in wanted]
    found = {str(x.get("label") or "").lower() for x in lists}
    ids = []
    for lst in lists:
        for i in await list_account_ids(c, lst["id"], lst.get("itemCount")):
            if i not in ids:
                ids.append(i)
    return ids, sorted(wanted - found)


# ------------------------------------------------------------------ media backfill


async def account_media(c, ids):
    """Full accountMedia objects by accountMedia id, 150 per call."""
    out = []
    ids = [str(i) for i in ids]
    for start in range(0, len(ids), ACCOUNT_MEDIA_BATCH):
        batch = ids[start : start + ACCOUNT_MEDIA_BATCH]
        out.extend(await get_json(c, f"account/media?ids={_ids(batch)}") or [])
    return out


async def missing_media(c, response, report=None):
    """accountMedia the response names but doesn't embed (bundles show only 5)."""
    missing = normalize.missing_account_media_ids(response)
    if not missing:
        return []
    log.debug(f"fetching {len(missing)} Fansly media the response left out")
    found = await account_media(c, missing)
    if len(found) < len(missing):
        log.debug(f"Fansly returned {len(found)} of the {len(missing)} media asked for")
    if report is not None:
        report.backfill_asked += len(missing)
        report.backfill_returned += len(found)
    return found


# ------------------------------------------------------------------ posts


async def timeline(c, account_id, wall_id="", after=None, report=None):
    """All timeline post dicts, newest first."""
    return [
        post
        async for page in timeline_pages(
            c, account_id, wall_id=wall_id, after=after, report=report
        )
        for post in page
    ]


async def timeline_pages(c, account_id, wall_id="", after=None, report=None):
    """Timeline post dicts one page at a time, newest first.

    ``before`` is the id of the last post of the previous page; paging stops
    on an empty page, or once a page reaches posts older than ``after``
    (epoch seconds). With ``wall_id``, only that wall's posts.
    """
    before = "0"
    for _ in range(MAX_PAGES):
        response = await get_json(
            c,
            f"timelinenew/{account_id}?before={before}&after=0&wallId={wall_id}&contentSearch=",
        )
        response = response or {}
        page = response.get("posts") or []
        if not page:
            return
        yield normalize.posts(
            response, await missing_media(c, response, report), report=report
        )
        last = str(page[-1]["id"])
        if last == before:
            return
        before = last
        oldest = normalize.to_seconds(page[-1].get("createdAt"))
        if after is not None and oldest is not None and oldest < after:
            return


async def timeline_stats(c, account_id):
    """The media counts Fansly shows on the profile, or None."""
    accounts = await accounts_by_id(c, [account_id])
    return (accounts[0] if accounts else {}).get("timelineStats") or None


async def walls(c, account_id):
    """The walls (profile tabs) of one account, from ``account?ids=``, and the
    account's ``hasMainWall`` (None when it isn't given)."""
    accounts = await accounts_by_id(c, [account_id])
    account = accounts[0] if accounts else {}
    return list(account.get("walls") or []), account.get("hasMainWall")


async def posts_by_id(c, post_ids):
    response = await get_json(c, f"post?ids={_ids(post_ids)}") or {}
    return normalize.posts(response, await missing_media(c, response))


# ------------------------------------------------------------------ messages


async def groups(c, limit=None):
    """Every page of ``messaging/groups`` (limit/offset paging)."""
    limit = limit or GROUPS_LIMIT
    pages = []
    offset = 0
    previous = None
    for _ in range(MAX_PAGES):
        page = await get_json(
            c,
            "messaging/groups?sortOrder=1&flags=0&subscriptionTierId=&listIds="
            f"&search=&limit={limit}&offset={offset}",
        )
        page = page or {}
        data = page.get("data") or []
        ids = [str(x.get("groupId")) for x in data]
        # a server that ignores offset returns the same page again
        if ids and ids == previous:
            break
        previous = ids
        pages.append(page)
        if len(data) < limit:
            break
        offset += limit
    return pages


def group_id_for(pages, account_id):
    """The conversation with one creator, from ``messaging/groups`` pages."""
    account_id = str(account_id)
    for page in pages:
        for summary in page.get("data") or []:
            if str(summary.get("partnerAccountId")) == account_id and summary.get("groupId"):
                return str(summary["groupId"])
        for group in (page.get("aggregationData") or {}).get("groups") or []:
            users = {str(u.get("userId")) for u in group.get("users") or []}
            if account_id in users and group.get("id"):
                return str(group["id"])
    return None


async def messages(c, group_id, after=None):
    """All message dicts of one conversation, newest first (``before`` cursor)."""
    out = []
    before = None
    for _ in range(MAX_PAGES):
        path = f"message?groupId={group_id}&limit={MESSAGES_LIMIT}"
        if before:
            path += f"&before={before}"
        response = await get_json(c, path) or {}
        page = response.get("messages") or []
        if not page:
            break
        out.extend(normalize.messages(response, await missing_media(c, response)))
        last = str(page[-1]["id"])
        if last == before:
            break
        before = last
        oldest = normalize.to_seconds(page[-1].get("createdAt"))
        if after is not None and oldest is not None and oldest < after:
            break
    return out


# ------------------------------------------------------------------ purchases


async def purchases(c, account_id):
    """Purchased media of one creator (``account/media/orders/``), one post each."""
    response = await get_json(c, "account/media/orders/?limit=9999&offset=0") or {}
    return normalize.purchases(response, account_id, await missing_media(c, response))
