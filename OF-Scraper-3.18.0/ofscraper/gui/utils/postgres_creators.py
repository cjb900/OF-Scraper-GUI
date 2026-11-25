"""Merge DBs > Creators: what PostgreSQL holds for each creator, and deleting
one creator's rows, as deleting their user_data.db did with SQLite files.

Reads go through upstream's read-only Reader and the delete through its
Writer (ofscraper/db/postgres.py): a connection of their own to the address
handed in, naming the site's schema, so the scraper's pool, settings and
current site aren't used. A delete is one transaction: a creator whose rows
another program (a scrape) is changing is refused with nothing deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# every row of these belongs to one creator (model_id)
DATA_TABLES = ("medias", "posts", "messages", "stories", "others", "products", "labels")
# where the creator's names are: models (model_id) and profiles (user_id)
NAME_TABLES = ("models", "profiles")


@dataclass
class Creator:
    model_id: int
    username: str = ""  # the name seen last; "" when none was saved
    media: int = 0  # distinct media ids
    downloaded: int = 0  # distinct media ids with a downloaded row
    size: int = 0  # bytes of the downloaded rows' files
    posts: int = 0
    messages: int = 0
    stories: int = 0
    other: int = 0  # others + products
    newest_post: str = ""  # newest posted_at among the media, ISO
    last_seen: str = ""  # when the newest name was last seen, ISO

    @property
    def missing(self) -> int:
        return max(self.media - self.downloaded, 0)


@dataclass
class Details:
    names: list = field(default_factory=list)  # [(username, first_seen, last_seen)], newest first
    # [(area, media type, media, downloaded, size)]
    breakdown: list = field(default_factory=list)


def _reader(url):
    import ofscraper.db.postgres as postgres

    return postgres.Reader(url)


def _schema(site):
    import ofscraper.db.postgres as postgres

    return postgres.schema_name(site)


def _tables(reader, schema) -> set:
    return {
        row[0]
        for row in reader.rows(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = ?",
            [schema],
        )
    }


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _text(value) -> str:
    return "" if value is None else str(value)


def list_creators(url, site) -> list[Creator]:
    """Every creator the site's schema has rows or a name for, with their
    counts. [] when the site has nothing in this database yet."""
    schema = _schema(site)
    reader = _reader(url)
    try:
        tables = _tables(reader, schema)
        found: dict[int, Creator] = {}

        def creator(model_id):
            model_id = _int(model_id)
            if model_id not in found:
                found[model_id] = Creator(model_id)
            return found[model_id]

        if "medias" in tables:
            for row in reader.rows(
                f"SELECT model_id, COUNT(DISTINCT media_id),"
                f" COUNT(DISTINCT media_id) FILTER (WHERE downloaded),"
                f" COALESCE(SUM(size) FILTER (WHERE downloaded), 0),"
                f" MAX(posted_at)"
                f" FROM {schema}.medias GROUP BY model_id"
            ):
                item = creator(row[0])
                item.media, item.downloaded, item.size = _int(row[1]), _int(row[2]), _int(row[3])
                item.newest_post = _text(row[4])
        for table, attr in (("posts", "posts"), ("messages", "messages"), ("stories", "stories"),
                            ("others", "other"), ("products", "other")):
            if table not in tables:
                continue
            for model_id, count in reader.rows(
                f"SELECT model_id, COUNT(*) FROM {schema}.{table} GROUP BY model_id"
            ):
                item = creator(model_id)
                setattr(item, attr, getattr(item, attr) + _int(count))
        if "labels" in tables:
            for (model_id,) in reader.rows(f"SELECT DISTINCT model_id FROM {schema}.labels"):
                creator(model_id)
        if "models" in tables:
            for (model_id,) in reader.rows(f"SELECT model_id FROM {schema}.models"):
                creator(model_id)
        if "profiles" in tables:
            # the newest name per creator: last seen last, then the newest row
            for user_id, username, last_seen in reader.rows(
                f"SELECT DISTINCT ON (user_id) user_id, username, last_seen_at"
                f" FROM {schema}.profiles"
                f" ORDER BY user_id, last_seen_at DESC NULLS LAST, id DESC"
            ):
                item = creator(user_id)
                item.username = _text(username)
                item.last_seen = _text(last_seen)
        return sorted(found.values(), key=lambda c: (c.username.lower() or "￿", c.model_id))
    finally:
        reader.close()


def creator_details(url, site, model_id) -> Details:
    """A creator's names and media counts by area (api_type) and type."""
    schema = _schema(site)
    model_id = int(model_id)
    reader = _reader(url)
    try:
        tables = _tables(reader, schema)
        details = Details()
        if "profiles" in tables:
            details.names = [
                (_text(name), _text(first), _text(last))
                for name, first, last in reader.rows(
                    f"SELECT username, first_seen_at, last_seen_at FROM {schema}.profiles"
                    f" WHERE user_id = ? ORDER BY last_seen_at DESC NULLS LAST, id DESC",
                    [model_id],
                )
            ]
        if "medias" in tables:
            details.breakdown = [
                (_text(area) or "(none)", _text(kind) or "(none)", _int(media), _int(done), _int(size))
                for area, kind, media, done, size in reader.rows(
                    f"SELECT api_type, media_type, COUNT(DISTINCT media_id),"
                    f" COUNT(DISTINCT media_id) FILTER (WHERE downloaded),"
                    f" COALESCE(SUM(size) FILTER (WHERE downloaded), 0)"
                    f" FROM {schema}.medias WHERE model_id = ?"
                    f" GROUP BY api_type, media_type ORDER BY api_type, media_type",
                    [model_id],
                )
            ]
        return details
    finally:
        reader.close()


def delete_creators(url, site, model_ids, forget_names=True) -> dict:
    """Delete the creators' rows from the site's schema, all in one
    transaction: everything or (on any error) nothing. With forget_names,
    their names (models, profiles) go too, as with deleting a user_data.db;
    without, they stay listed with no rows. Returns {table: rows deleted}.

    Raises upstream's ChangedMeanwhile when a scrape is changing the same
    rows, PostgresUnavailable for anything else; nothing is deleted then."""
    import ofscraper.db.postgres as postgres

    schema = _schema(site)
    ids = sorted({int(x) for x in model_ids})
    removed: dict[str, int] = {}
    if not ids:
        return removed
    writer = postgres.Writer(url)
    try:
        tables = _tables(writer, schema)
        targets = [(t, "model_id") for t in DATA_TABLES]
        if forget_names:
            targets += [("models", "model_id"), ("profiles", "user_id")]
        marks = ", ".join("?" for _ in ids)
        for table, column in targets:
            if table not in tables:
                continue
            count = writer.change(f"DELETE FROM {schema}.{table} WHERE {column} IN ({marks})", ids)
            removed[table] = max(_int(count), 0)
        writer.commit()
        return removed
    finally:
        writer.close()
