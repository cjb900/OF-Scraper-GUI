"""The GUI's own reads and writes of a creator's rows, through the scraper's
database functions, for when PostgreSQL is on (POSTGRESQL.md, "GUI patch").

With PostgreSQL off the GUI keeps reading each user_data.db itself, as it
always has; these are used only while ``postgres_setup.enabled()``. The
scraper's functions pick the database (the current site's schema) and only
return that creator's rows.
"""

from __future__ import annotations

import contextlib
import logging

log = logging.getLogger("shared")

# every row of these belongs to one creator (as postgres_import's DATA_TABLES);
# profiles and models (a creator's names) are left
CREATOR_TABLES = ("medias", "posts", "messages", "stories", "others", "products", "labels")


def read_creator_media(model_id, username):
    """(media rows, {post_id: {"price", "text"}}) for one creator, or None
    when the database has nothing for them yet."""
    from ofscraper.db.operations_.media import get_all_medias_sync, get_post_info
    from ofscraper.db.operations_.wrapper import DatabaseMissing

    try:
        rows = get_all_medias_sync(model_id=model_id, username=username, read_only=True)
        info = get_post_info(model_id=model_id, username=username, read_only=True)
    except DatabaseMissing:
        return None
    # as the GUI's own read gave them: 0 and "" for an empty price and text
    post_info = {
        post_id: {"price": value.get("price") or 0, "text": value.get("text") or ""}
        for post_id, value in (info or {}).items()
    }
    return [dict(row) for row in rows or []], post_info


def newest_posted_at(model_id, username):
    """The newest non-empty posted_at among the creator's media, as
    MAX(posted_at) gives it in a user_data.db. None when there is none."""
    found = read_creator_media(model_id, username)
    if not found:
        return None
    dates = [str(row.get("posted_at")) for row in found[0] if row.get("posted_at")]
    return max(dates) if dates else None


def downloaded_files(model_id, username):
    """[(directory, filename)] of the creator's downloaded media that have a
    recorded file."""
    from ofscraper.db.operations_.media import get_media_post_files_downloaded
    from ofscraper.db.operations_.wrapper import DatabaseMissing

    try:
        files = get_media_post_files_downloaded(
            model_id=model_id, username=username, read_only=True
        )
    except DatabaseMissing:
        return []
    return sorted({(d, f) for d, f in (files or {}).values() if d and f})


def _creator_rows_deleter():
    from ofscraper.db.operations_ import wrapper

    @wrapper.operation_wrapper
    def delete_creator_rows(model_id=None, username=None, conn=None, **kwargs):
        backend = wrapper.backend_of(conn)
        removed = 0
        with contextlib.closing(conn.cursor()) as cur:
            for table in CREATOR_TABLES:
                if not backend.table_exists(cur, table):
                    continue
                cur.execute(f"DELETE FROM {table} WHERE model_id = ?", [int(model_id)])
                removed += max(cur.rowcount or 0, 0)
        conn.commit()
        return removed

    return delete_creator_rows


def delete_creator_rows(model_id, username):
    """Purge's "Delete model DB" with PostgreSQL on: remove the creator's
    rows from the current site's tables in one transaction, as deleting
    their user_data.db does. The names they were seen under (profiles,
    models) stay. Returns how many rows were removed."""
    return _creator_rows_deleter()(model_id=model_id, username=username)


def _directory_mover():
    from ofscraper.db.operations_ import wrapper

    @wrapper.operation_wrapper
    def move_directories(moves=None, relocate=None, conn=None, **kwargs):
        backend = wrapper.backend_of(conn)
        changed = 0
        with contextlib.closing(conn.cursor()) as cur:
            if not backend.table_exists(cur, "medias"):
                return 0
            cur.execute("SELECT DISTINCT directory FROM medias WHERE directory IS NOT NULL")
            for (directory,) in [tuple(row) for row in cur.fetchall()]:
                new = relocate(directory, moves)
                if new and new != directory:
                    cur.execute(
                        "UPDATE medias SET directory = ? WHERE directory = ?",
                        [new, directory],
                    )
                    changed += max(cur.rowcount or 0, 0)
        conn.commit()
        return changed

    return move_directories


def move_download_paths(moves, relocate):
    """The OnlyFans folder move with PostgreSQL on: point the recorded
    download folders (medias.directory) at the moved folders, for every
    creator of the current site. ``relocate(directory, moves)`` gives the
    new folder or None. Returns how many rows changed."""
    return _directory_mover()(moves=moves, relocate=relocate)
