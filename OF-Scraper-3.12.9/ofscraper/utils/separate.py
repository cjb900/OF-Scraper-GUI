r"""
                                                             
 _______  _______         _______  _______  _______  _______  _______  _______  _______ 
(  ___  )(  ____ \       (  ____ \(  ____ \(  ____ )(  ___  )(  ____ )(  ____ \(  ____ )
| (   ) || (    \/       | (    \/| (    \/| (    )|| (   ) || (    )|| (    \/| (    )|
| |   | || (__     _____ | (_____ | |      | (____)|| (___) || (____)|| (__    | (____)|
| |   | ||  __)   (_____)(_____  )| |      |     __)|  ___  ||  _____)|  __)   |     __)
| |   | || (                   ) || |      | (\ (   | (   ) || (      | (      | (\ (   
| (___) || )             /\____) || (____/\| ) \ \__| )   ( || )      | (____/\| ) \ \__
(_______)|/              \_______)(_______/|/   \__/|/     \||/       (_______/|/   \__/
                                                                                      
"""

import logging

import ofscraper.utils.cache as cache
import ofscraper.utils.constants as constants
import ofscraper.utils.me as me_util

log = logging.getLogger("shared")


def separate_by_id(data: list, media_ids: list) -> list:
    media_ids = set(media_ids)
    return list(filter(lambda x: x.id not in media_ids, data))


def seperate_avatars(data, downloaded_media_ids=None):
    return list(
        filter(
            lambda x: seperate_avatar_helper(x, downloaded_media_ids) is False,
            data,
        )
    )


def _media_marked_downloaded(mid, downloaded_media_ids) -> bool:
    if not downloaded_media_ids:
        return False
    if mid in downloaded_media_ids:
        return True
    if str(mid) in downloaded_media_ids:
        return True
    return False


def seperate_avatar_helper(ele, downloaded_media_ids=None):
    # Skip profile avatar/header only when cache agrees it was finished *and*
    # the DB still marks that media as downloaded. Otherwise drop stale cache
    # entries (e.g. DB wiped/restored) so the GUI does not show “not downloaded”
    # rows that are never queued.
    if ele.postid and ele.responsetype == "profile":
        value = cache.get(ele.postid, default=False)
        if (
            value
            and downloaded_media_ids is not None
            and not _media_marked_downloaded(ele.id, downloaded_media_ids)
        ):
            try:
                cache.delete(ele.postid)
            except Exception:
                pass
            log.debug(
                "Cleared stale profile download cache for postid=%s media_id=%s "
                "(cached done but not marked downloaded in DB)",
                ele.postid,
                ele.id,
            )
            return False
        return value
    return False


def seperate_by_self(data):
    my_id = me_util.get_id()
    if constants.getattr("FILTER_SELF_MEDIA"):
        return list(filter(lambda x: x.post.fromuser != my_id, data))
