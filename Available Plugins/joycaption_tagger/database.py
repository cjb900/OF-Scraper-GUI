import json
import os
import datetime
from pathlib import Path

from peewee import SqliteDatabase, Model, CharField, DateTimeField, TextField, BooleanField

# The database file will be initialized later when the plugin knows its data directory.
# thread_safe: scraper downloads invoke the plugin from a worker thread; GUI reads on the main thread.
db = SqliteDatabase(None, pragmas={"journal_mode": "wal"}, thread_safe=True)


def canonical_media_path(file_path) -> str:
    """Normalize paths for SQLite + os.path.exists (important on Windows)."""
    try:
        p = Path(file_path)
        if p.exists():
            return os.path.normpath(str(p.resolve()))
    except OSError:
        pass
    return os.path.normpath(str(Path(file_path)))


def resolve_media_path_for_tagging(file_path) -> str | None:
    """
    Resolve to an existing absolute file path for PIL/tagging after download.
    Falls back to save directory when OF-Scraper passes a relative final path.
    """
    if file_path is None:
        return None
    p = Path(str(file_path)).expanduser()
    try:
        if p.is_file():
            return os.path.normpath(str(p.resolve()))
    except OSError:
        pass
    try:
        import ofscraper.utils.paths.common as common_paths

        root = Path(common_paths.get_save_location())
        alt = (root / p) if not p.is_absolute() else p
        if alt.is_file():
            return os.path.normpath(str(alt.resolve()))
    except Exception:
        pass
    try:
        if p.exists() and p.is_file():
            return os.path.normpath(str(p.resolve()))
    except OSError:
        pass
    return None

class BaseModel(Model):
    class Meta:
        database = db

class MediaItem(BaseModel):
    file_path = CharField(unique=True, max_length=1024)
    tags_json = TextField(default="[]")
    model_used = CharField(max_length=50)
    created_at = DateTimeField(default=datetime.datetime.now)
    copied_to_smart_folder = BooleanField(default=False)

    def set_tags(self, tags_list):
        self.tags_json = json.dumps(tags_list)

    def get_tags(self):
        try:
            return json.loads(self.tags_json)
        except json.JSONDecodeError:
            return []


class MediaEmbedding(BaseModel):
    """
    Stores an OpenCLIP embedding vector for semantic (Immich-like) search.
    Embeddings are stored as JSON arrays of floats to keep this lightweight.
    """

    file_path = CharField(unique=True, max_length=1024)
    model_used = CharField(max_length=64)
    embedding_json = TextField(default="[]")
    created_at = DateTimeField(default=datetime.datetime.now)

    def set_embedding(self, embedding):
        self.embedding_json = json.dumps(embedding)

    def get_embedding(self):
        try:
            return json.loads(self.embedding_json)
        except json.JSONDecodeError:
            return []


def normalize_tag_pairs(tags):
    """
    Flatten stored tag payloads to [(name, score), ...] for UI and smart-folder logic.

    Handles:
    - list[{"label", "score"}] (WD14 / CLIP-style list)
    - dict[str, float] (flat tag -> score)
    - dict[str, dict[...]] or dict[str, list[...]] (nested WD14 / bucketed exports)
    """
    if tags is None:
        return []
    if isinstance(tags, list):
        pairs = []
        for t in tags:
            if not isinstance(t, dict) or "label" not in t:
                continue
            try:
                score = float(t.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            pairs.append((str(t["label"]), score))
        return pairs
    if isinstance(tags, dict):
        pairs = []
        for _k, v in tags.items():
            if isinstance(v, (int, float)):
                try:
                    pairs.append((str(_k), float(v)))
                except (TypeError, ValueError):
                    pairs.append((str(_k), 0.0))
            elif isinstance(v, dict):
                for sk, sv in v.items():
                    if isinstance(sv, (int, float)):
                        try:
                            pairs.append((str(sk), float(sv)))
                        except (TypeError, ValueError):
                            pairs.append((str(sk), 0.0))
                    elif isinstance(sv, dict) and "score" in sv:
                        try:
                            pairs.append((str(sk), float(sv["score"])))
                        except (TypeError, ValueError):
                            pairs.append((str(sk), 0.0))
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "label" in item:
                        try:
                            pairs.append((str(item["label"]), float(item.get("score", 0))))
                        except (TypeError, ValueError):
                            pairs.append((str(item["label"]), 0.0))
                    elif isinstance(item, str):
                        pairs.append((item, 0.0))
        return pairs
    return []


def init_db(db_path: str):
    """Initialize the database connection and create tables."""
    db.init(db_path)
    db.connect()
    db.create_tables([MediaItem, MediaEmbedding], safe=True)
