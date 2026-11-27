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

import contextlib

from ofscraper.utils.cache.safe_disk import SafeDisk, SafeJSONDisk
from humanfriendly import InvalidSize, parse_size

import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.config.file as config_file
import ofscraper.utils.config.naming_check as naming_check
import ofscraper.utils.config.utils.wrapper as wrapper
import ofscraper.utils.const as const  # noqa: F401
from ofscraper.utils.config.path_norm import strip_path_quotes  # noqa: F401

# auto_update_config rebuilds config.json from these getters and writes it
# back, so each must return what belongs in the file. Environment fallbacks
# that shouldn't be saved go in settings.merged_settings instead.
#
# _first, _first_set, _value and _truthy_value are the lookups most getters
# share; the reference builder (scripts/reference/build_reference.py) reads
# their arguments to list each key's older names and environment default.


# the paths _lookup() is asked for while this is a set: auto_update_config
# uses it to tell an older name the getters read from a key nothing reads
_reads = None


@contextlib.contextmanager
def _recording_reads():
    global _reads
    _reads = set()
    try:
        yield _reads
    finally:
        _reads = None


def _lookup(config, path):
    """the value at a "key" or "section.key" path; a section that isn't a
    dict, e.g. a hand-edited null, counts as empty"""
    if _reads is not None:
        _reads.add(path)
    section, _, key = path.rpartition(".")
    if not section:
        return config.get(key)
    values = config.get(section)
    return values.get(key) if isinstance(values, dict) else None


def _note_reads(*paths):
    """Record paths a getter reads without _lookup() (the GUI patch's
    settings and their older top-level names), so the config rewrite's notes
    don't call them unread."""
    if _reads is not None:
        _reads.update(paths)


def _first(config, *paths):
    """
    The value at the first path that holds a truthy one, else the value at
    the last path: what ``config.get(a) or config.get(b) or ...`` gives. A
    path is a top-level key or "section.key". Later paths are only read when
    needed, so a broken section after a truthy value isn't touched.
    """
    val = None
    for path in paths:
        val = _lookup(config, path)
        if val:
            break
    return val


def _first_set(config, *paths):
    """
    The value at the first path that isn't None, else None, so a saved
    false, 0 or "" is kept wherever it is. Paths are as for _first(), and
    later ones are only read when needed.
    """
    for path in paths:
        val = _lookup(config, path)
        if val is not None:
            return val
    return None


def _value(config, env_key, *paths):
    """_first_set(), falling back to the env_key default when nothing is set"""
    if config is False:
        return of_env.getattr(env_key)
    val = _first_set(config, *paths)
    return val if val is not None else of_env.getattr(env_key)


def _truthy_value(config, env_key, *paths):
    """
    _first(), falling back to the env_key default when it's falsy: for keys
    where no falsy value is a valid setting, so one means unset
    """
    if config is False:
        return of_env.getattr(env_key)
    return _first(config, *paths) or of_env.getattr(env_key)


@wrapper.config_reader
def get_main_profile(config=None):
    if config is False:
        return of_env.getattr("PROFILE_DEFAULT")
    value = _lookup(config, of_env.getattr("mainProfile"))
    return value or of_env.getattr("PROFILE_DEFAULT")


@wrapper.config_reader
def get_filesize_max(config=None):
    if config is False:
        return of_env.getattr("FILE_SIZE_MAX_DEFAULT")
    try:
        size = _value(
            config,
            "FILE_SIZE_MAX_DEFAULT",
            "file_size_max",
            "download_options.file_size_max",
            "download_options.file_size_limit",
            "content_filter_options.file_size_max",
        )
        return parse_size(str(size))
    except (ValueError, TypeError, InvalidSize):
        # parse_size's InvalidSize isn't a ValueError; an unparsable size,
        # e.g. "", counts as 0
        return 0


@wrapper.config_reader
def get_filesize_min(config=None):
    if config is False:
        return of_env.getattr("FILE_SIZE_MIN_DEFAULT")
    try:
        size = _value(
            config,
            "FILE_SIZE_MIN_DEFAULT",
            "file_size_min",
            "download_options.file_size_min",
            "content_filter_options.file_size_min",
        )
        return parse_size(str(size))
    except (ValueError, TypeError, InvalidSize):
        # parse_size's InvalidSize isn't a ValueError; an unparsable size,
        # e.g. "", counts as 0
        return 0


@wrapper.config_reader
def get_min_length(config=None):
    return _value(
        config,
        "MIN_LENGTH_DEFAULT",
        "length_min",
        "download_options.length_min",
        "content_filter_options.length_min",
    )


@wrapper.config_reader
def get_max_length(config=None):
    return _value(
        config,
        "MAX_LENGTH_DEFAULT",
        "length_max",
        "download_options.length_max",
        "content_filter_options.length_max",
    )


@wrapper.config_reader
def get_system_freesize(config=None):
    if config is False:
        return of_env.getattr("SYSTEM_FREEMIN_DEFAULT")
    try:
        size = _value(
            config,
            "SYSTEM_FREEMIN_DEFAULT",
            "system_free_min",
            "download_options.system_free_min",
        )
        return parse_size(str(size))
    except (ValueError, TypeError, InvalidSize):
        # parse_size's InvalidSize isn't a ValueError; an unparsable size,
        # e.g. "", counts as 0
        return 0


@wrapper.config_reader
def get_dirformat(config=None):
    return _truthy_value(
        config, "DIR_FORMAT_DEFAULT", "dir_format", "file_options.dir_format"
    )


@wrapper.config_reader
def get_fileformat(config=None):
    return _truthy_value(
        config, "FILE_FORMAT_DEFAULT", "file_format", "file_options.file_format"
    )


@wrapper.config_reader
def get_textlength(config=None):
    if config is False:
        return of_env.getattr("TEXTLENGTH_DEFAULT")
    try:
        return int(
            _value(
                config, "TEXTLENGTH_DEFAULT", "textlength", "file_options.textlength"
            )
        )
    except (ValueError, TypeError):
        return of_env.getattr("TEXTLENGTH_DEFAULT")


@wrapper.config_reader
def get_date(config=None):
    return _truthy_value(config, "DATE_DEFAULT", "date", "file_options.date")


@wrapper.config_reader
def get_InfiniteLoop(config=None):
    return _value(
        config,
        "INFINITE_LOOP_DEFAULT",
        "infinite_loop_action_mode",
        "advanced_options.infinite_loop_action_mode",
    )


@wrapper.config_reader
def get_incremental_downloads(config=None):
    if config is False:
        return of_env.getattr("INCREMENTAL_DOWNLOADS_DEFAULT")
    val = _first_set(
        config,
        "incremental_downloads",
        "advanced_options.incremental_downloads",
        "advanced_options.enable_auto_after",
    )
    return val if val is not None else of_env.getattr("INCREMENTAL_DOWNLOADS_DEFAULT")


@wrapper.config_reader
def get_default_userlist(config=None):
    if config is False:
        return of_env.getattr("DEFAULT_USER_LIST") or []
    val = _first(config, "default_user_list", "advanced_options.default_user_list")
    return val or of_env.getattr("DEFAULT_USER_LIST") or []


@wrapper.config_reader
def get_default_blacklist(config=None):
    if config is False:
        return of_env.getattr("DEFAULT_BLACK_LIST") or []
    val = _first(config, "default_black_list", "advanced_options.default_black_list")
    return val or of_env.getattr("DEFAULT_BLACK_LIST") or []


@wrapper.config_reader
def get_logs_expire(config=None):
    if not config:
        return 0
    val = _first_set(config, "logs_expire_time", "advanced_options.logs_expire_time")
    try:
        return int(val) if val is not None else 0
    except (ValueError, TypeError):
        return 0


@wrapper.config_reader
def get_ssl_verify(config=None):
    if not config:
        return of_env.getattr("SSL_VALIDATION_DEFAULT")

    # 1. Check for None, not falsiness, so a literal False reaches step 2
    val = _first_set(config, "ssl_verify", "advanced_options.ssl_verify")

    # 2. Legacy Migration: Convert JSON booleans (True/False) to the new default
    if isinstance(val, bool):
        return "custom"

    return val if val is not None else of_env.getattr("SSL_VALIDATION_DEFAULT")


def _sanitize_file_extension(val, default: str) -> str:
    """Strip leading dots; keep alnum only; fall back to *default* if empty."""
    s = "".join(c for c in str(val or "").strip().lstrip(".").lower() if c.isalnum())
    return s or default


def _file_options_dict(config):
    if not isinstance(config, dict):
        return {}
    fo = config.get("file_options")
    return fo if isinstance(fo, dict) else {}


def _legacy_override_all(config) -> bool:
    """Pre–per-type flag: single override_file_extensions enabled all media types."""
    fo = _file_options_dict(config)
    val = config.get("override_file_extensions") if isinstance(config, dict) else None
    if val is None:
        val = fo.get("override_file_extensions")
    return bool(val)


def _get_per_type_ext_override(config, key: str) -> bool:
    """Per-mediatype override; falls back to legacy global override_file_extensions."""
    _note_reads(key, f"file_options.{key}", "override_file_extensions", "file_options.override_file_extensions")
    if config is False or not isinstance(config, dict):
        return False
    fo = _file_options_dict(config)
    if key in fo or key in config:
        val = config.get(key) if key in config else None
        if val is None:
            val = fo.get(key)
        return bool(val)
    # Any per-type key present ⇒ already migrated; missing type stays off
    siblings = (
        "override_image_extension",
        "override_video_extension",
        "override_audio_extension",
    )
    if any(s in fo or s in config for s in siblings):
        return False
    return _legacy_override_all(config)


@wrapper.config_reader
def get_override_file_extensions(config=None):
    """True if any mediatype extension override is on (incl. legacy global flag)."""
    if config is False:
        return False
    if not isinstance(config, dict):
        return False
    return (
        get_override_image_extension(config=config)
        or get_override_video_extension(config=config)
        or get_override_audio_extension(config=config)
    )


@wrapper.config_reader
def get_override_image_extension(config=None):
    return _get_per_type_ext_override(config, "override_image_extension")


@wrapper.config_reader
def get_override_video_extension(config=None):
    return _get_per_type_ext_override(config, "override_video_extension")


@wrapper.config_reader
def get_override_audio_extension(config=None):
    return _get_per_type_ext_override(config, "override_audio_extension")


@wrapper.config_reader
def get_image_extension(config=None):
    _note_reads("image_extension", "file_options.image_extension")
    if config is False:
        return "jpg"
    if not isinstance(config, dict):
        return "jpg"
    fo = _file_options_dict(config)
    val = config.get("image_extension")
    if val is None:
        val = fo.get("image_extension")
    return _sanitize_file_extension(val, "jpg")


@wrapper.config_reader
def get_video_extension(config=None):
    _note_reads("video_extension", "file_options.video_extension")
    if config is False:
        return "mp4"
    if not isinstance(config, dict):
        return "mp4"
    fo = _file_options_dict(config)
    val = config.get("video_extension")
    if val is None:
        val = fo.get("video_extension")
    return _sanitize_file_extension(val, "mp4")


@wrapper.config_reader
def get_audio_extension(config=None):
    _note_reads("audio_extension", "file_options.audio_extension")
    if config is False:
        return "mp3"
    if not isinstance(config, dict):
        return "mp3"
    fo = _file_options_dict(config)
    val = config.get("audio_extension")
    if val is None:
        val = fo.get("audio_extension")
    return _sanitize_file_extension(val, "mp3")


@wrapper.config_reader
def get_after_action_script(config=None):
    return _value(
        config,
        "AFTER_ACTION_SCRIPT_DEFAULT",
        "after_action_script",
        "advanced_options.after_action_script",
        "script_options.after_action_script",
        "scripts_options.after_action_script",
    )


@wrapper.config_reader
def get_post_script(config=None):
    return _value(
        config,
        "POST_SCRIPT_DEFAULT",
        "post_script",
        "advanced_options.post_script",
        "scripts.post_script",
        "script_options.post_script",
        "scripts_options.post_script",
    )


@wrapper.config_reader
def get_alert_script(config=None):
    return _value(
        config,
        "ALERT_SCRIPT_DEFAULT",
        "alert_script",
        "script_options.alert_script",
    )


@wrapper.config_reader
def get_naming_script(config=None):
    return _value(
        config,
        "NAMING_SCRIPT_DEFAULT",
        "naming_script",
        "advanced_options.naming_script",
        "scripts.naming_script",
        "script_options.naming_script",
        "scripts_options.naming_script",
    )


@wrapper.config_reader
def get_skip_download_script(config=None):
    return _value(
        config,
        "SKIP_DOWNLOAD_SCRIPT_DEFAULT",
        "skip_download_script",
        "advanced_options.skip_download_script",
        "scripts.skip_download_script",
        "script_options.skip_download_script",
        "scripts_options.skip_download_script",
    )


@wrapper.config_reader
def get_after_download_script(config=None):
    return _value(
        config,
        "AFTER_DOWNLOAD_SCRIPT_DEFAULT",
        "after_download_script",
        "advanced_options.after_download_script",
        "scripts.after_download_script",
        "script_options.after_download_script",
        "scripts_options.after_download_script",
    )


@wrapper.config_reader
def get_env_files(config=None):
    # This must remain "safe" to avoid chicken-and-egg loops
    if config is False:
        return []
    val = _first(
        config,
        "env_files",
        "advanced_options.env_files",
        "scripts.env_files",
        "script_options.env_files",
    )
    return val or []


# config.json can't hold comments, so this note is a key of its own, for
# anyone who looks for the database setting in the file. It isn't read as a
# setting: whatever the file holds there is replaced by the note
DATABASE_URL_NOTE = (
    "Not set in this file. To use PostgreSQL, set the OFSC_DATABASE_URL"
    " environment variable, or put it in a file listed in env_files (it holds"
    " a password). See POSTGRESQL.md."
)


@wrapper.config_reader
def get_database_url_note(config=None):
    return DATABASE_URL_NOTE


@wrapper.config_reader
def get_metadata(config=None):
    if config is False:
        return of_env.getattr("METADATA_DEFAULT")
    if "metadata" not in config:
        return of_env.getattr("METADATA_DEFAULT")
    return _lookup(config, "metadata")


@wrapper.config_reader
def get_download_limit(config=None):
    if config is False:
        return of_env.getattr("DOWNLOAD_LIMIT_DEFAULT")
    try:
        limit = _value(
            config,
            "DOWNLOAD_LIMIT_DEFAULT",
            "download_limit",
            "performance_options.download_limit",
        )
        return parse_size(str(limit))
    except (ValueError, TypeError, InvalidSize):
        # parse_size's InvalidSize isn't a ValueError; an unparsable size,
        # e.g. "", counts as 0
        return 0


@wrapper.config_reader
def get_ffmpeg(config=None):
    if config is False:
        return of_env.getattr("FFMPEG_DEFAULT")
    val = strip_path_quotes(_first_set(config, "ffmpeg", "binary_options.ffmpeg"))
    # "" is kept as-is so a config rewrite doesn't save OFSC_FFMPEG_DEFAULT
    # into the file; settings applies that fallback at runtime
    return val if val is not None else of_env.getattr("FFMPEG_DEFAULT")


@wrapper.config_reader
def get_discord(config=None):
    return _value(config, "DISCORD_DEFAULT", "discord")


@wrapper.config_reader
def get_discord_avatars(config=None):
    """Post creator avatars to Discord (they show as large pictures); off
    unless "discord_avatars" is true."""
    if config is False:
        return False
    value = _first_set(config, "discord_avatars")
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


@wrapper.config_reader
def get_filter(config=None):
    # config=False goes through _value() too, so the default is normalised
    final_filter = _value(
        config,
        "FILTER_DEFAULT",
        "filter",
        "download_options.filter",
        "content_filter_options.filter",
    )
    if isinstance(final_filter, str):
        return [x.capitalize().strip() for x in final_filter.split(",")]
    elif isinstance(final_filter, list):
        # an entry that isn't a media type name is left out
        return [x.capitalize() for x in final_filter if isinstance(x, str)]
    return []


@wrapper.config_reader
def responsetype(config=None):
    return _truthy_value(config, "RESPONSE_TYPE_DEFAULT", "responsetype")


@wrapper.config_reader
def get_timeline_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]
    if config is False:
        return default
    val = _first(
        config, "timeline", "post", "responsetype.timeline", "responsetype.post"
    )
    return val or default


@wrapper.config_reader
def get_post_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["timeline"]
    if config is False:
        return default
    val = _first(
        config, "post", "timeline", "responsetype.post", "responsetype.timeline"
    )
    return val or default


@wrapper.config_reader
def get_archived_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["archived"]
    if config is False:
        return default
    return _first(config, "archived", "responsetype.archived") or default


@wrapper.config_reader
def get_stories_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["stories"]
    if config is False:
        return default
    return _first(config, "stories", "responsetype.stories") or default


@wrapper.config_reader
def get_highlights_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["highlights"]
    if config is False:
        return default
    return _first(config, "highlights", "responsetype.highlights") or default


@wrapper.config_reader
def get_paid_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["paid"]
    if config is False:
        return default
    return _first(config, "paid", "responsetype.paid") or default


@wrapper.config_reader
def get_messages_progress_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["message"]
    if config is False:
        return default
    return _first(config, "message", "responsetype.message") or default


@wrapper.config_reader
def get_profile_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["profile"]
    if config is False:
        return default
    return _first(config, "profile", "responsetype.profile") or default


@wrapper.config_reader
def get_pinned_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["pinned"]
    if config is False:
        return default
    return _first(config, "pinned", "responsetype.pinned") or default


@wrapper.config_reader
def get_streams_responsetype(config=None):
    default = of_env.getattr("RESPONSE_TYPE_DEFAULT")["streams"]
    if config is False:
        return default
    return _first(config, "streams", "responsetype.streams") or default


@wrapper.config_reader
def get_spacereplacer(config=None):
    return _truthy_value(
        config,
        "SPACE_REPLACER_DEFAULT",
        "space_replacer",
        "file_options.space_replacer",
        "file_options.space-replacer",
    )


@wrapper.config_reader
def get_private_key(config=None):
    if not config:
        return None
    return strip_path_quotes(_first(config, "private-key", "cdm_options.private-key"))


@wrapper.config_reader
def get_client_id(config=None):
    if not config:
        return None
    return strip_path_quotes(_first(config, "client-id", "cdm_options.client-id"))


@wrapper.config_reader
def get_key_mode(config=None):
    if config is False:
        return of_env.getattr("KEY_DEFAULT")
    final_value = _truthy_value(
        config, "KEY_DEFAULT", "key-mode-default", "cdm_options.key-mode-default"
    )
    return (
        final_value.lower()
        if isinstance(final_value, str)
        and final_value.lower() in of_env.getattr("KEY_OPTIONS")
        else of_env.getattr("KEY_DEFAULT")
    )


@wrapper.config_reader
def get_dynamic(config=None):
    if config is False:
        return of_env.getattr("DYNAMIC_RULE_DEFAULT")
    final_value = _truthy_value(
        config,
        "DYNAMIC_RULE_DEFAULT",
        "dynamic-mode-default",
        "advanced_options.dynamic-mode-default",
    )
    return (
        final_value.lower()
        if isinstance(final_value, str)
        and final_value.lower() in of_env.getattr("DYNAMIC_OPTIONS_ALL")
        else of_env.getattr("DYNAMIC_RULE_DEFAULT")
    )


@wrapper.config_reader
def get_dynamic_configured(config=None):
    # the raw value, before get_dynamic() checks it; not written to the file
    if config is False:
        return None
    return _first(
        config, "dynamic-mode-default", "advanced_options.dynamic-mode-default"
    )


@wrapper.config_reader
def get_api_path(config=None):
    """OnlyFans API path prefix (default ``/api2/v2``)."""
    _note_reads("api_path", "advanced_options.api_path")
    from ofscraper.utils.api_path import DEFAULT_API_PATH, normalize_api_path

    if config is False:
        return DEFAULT_API_PATH
    value = config.get("api_path")
    if value is None and isinstance(config.get("advanced_options"), dict):
        value = config.get("advanced_options", {}).get("api_path")
    return normalize_api_path(value)


@wrapper.config_reader
def get_dynamic_rules_manual(config=None):
    """Manual signing-rules JSON text (Dynamic Mode ``manual``)."""
    _note_reads("dynamic_rules_manual", "advanced_options.dynamic_rules_manual")
    from ofscraper.utils.dynamic_rules_manual import normalize_manual_rules_json

    if config is False:
        return ""
    value = config.get("dynamic_rules_manual")
    if value is None and isinstance(config.get("advanced_options"), dict):
        value = config.get("advanced_options", {}).get("dynamic_rules_manual")
    if value is None:
        return ""
    return normalize_manual_rules_json(value)


@wrapper.config_reader
def get_dynamic_rules_url(config=None):
    """Custom signing-rules JSON URL (Dynamic Mode ``generic``)."""
    _note_reads("dynamic_rules_url", "advanced_options.dynamic_rules_url")
    from ofscraper.utils.dynamic_rules_url import normalize_dynamic_rules_url

    if config is False:
        return ""
    value = config.get("dynamic_rules_url")
    if value is None and isinstance(config.get("advanced_options"), dict):
        value = config.get("advanced_options", {}).get("dynamic_rules_url")
    return normalize_dynamic_rules_url(value)


@wrapper.config_reader
def get_media_host_suffixes(config=None):
    """Extra media/DRM CDN host suffixes (comma-separated)."""
    _note_reads("media_host_suffixes", "advanced_options.media_host_suffixes")
    from ofscraper.utils.media_host_suffixes import normalize_media_host_suffixes

    if config is False:
        return ""
    value = config.get("media_host_suffixes")
    if value is None and isinstance(config.get("advanced_options"), dict):
        value = config.get("advanced_options", {}).get("media_host_suffixes")
    return normalize_media_host_suffixes(value)


@wrapper.config_reader
def get_api_endpoint_overrides(config=None):
    """Per-endpoint URL overrides (dict of of_env key → URL template)."""
    _note_reads("api_endpoint_overrides", "advanced_options.api_endpoint_overrides")
    from ofscraper.utils.api_endpoint_overrides import normalize_endpoint_overrides_dict

    if config is False:
        return {}
    value = config.get("api_endpoint_overrides")
    if value is None and isinstance(config.get("advanced_options"), dict):
        value = config.get("advanced_options", {}).get("api_endpoint_overrides")
    return normalize_endpoint_overrides_dict(value)


@wrapper.config_reader
def get_part_file_clean(config=None):
    if config is False:
        return of_env.getattr("RESUME_DEFAULT")
    val = _first_set(config, "auto_resume", "download_options.auto_resume")
    if val is not None:
        return val
    legacy_val = _lookup(config, "partfileclean")
    if legacy_val is not None:
        return legacy_val is False
    return of_env.getattr("RESUME_DEFAULT")


@wrapper.config_reader
def get_download_semaphores(config=None):
    if config is False:
        return of_env.getattr("DOWNLOAD_SEM_DEFAULT")
    try:
        final_sem = int(
            _truthy_value(
                config,
                "DOWNLOAD_SEM_DEFAULT",
                "download_sems",
                "performance_options.download_sems",
            )
        )
        # the download pool needs at least one worker
        if final_sem < 1:
            return int(of_env.getattr("DOWNLOAD_SEM_DEFAULT"))
        return final_sem
    except (ValueError, TypeError):
        return int(of_env.getattr("DOWNLOAD_SEM_DEFAULT"))


@wrapper.config_reader
def get_show_downloadprogress(config=None):
    return _value(
        config, "PROGRESS_DEFAULT", "downloadbars", "advanced_options.downloadbars"
    )


@wrapper.config_reader
def get_cache_mode(config=None):
    # diskcache's disks, reading only plain data back (CVE-2025-69872)
    if cache_mode_helper(config=config) == "json":
        return SafeJSONDisk
    else:
        return SafeDisk


def cache_mode_helper(config=None):
    if config is False:
        return of_env.getattr("CACHEDEFAULT")
    if config is None:
        config = config_file.open_config()
    final_data = _truthy_value(
        config, "CACHEDEFAULT", "cache-mode", "advanced_options.cache-mode"
    )
    modes = {"sqlite", "json", "disabled", "api_disabled"}
    if isinstance(final_data, str) and final_data in modes:
        return final_data
    else:
        return of_env.getattr("CACHEDEFAULT")


@wrapper.config_reader
def get_rotate_logs(config=None):
    return _value(
        config, "ROTATE_DEFAULT", "rotate_logs", "advanced_options.rotate_logs"
    )


@wrapper.config_reader
def get_sanitizeDB(config=None):
    return _value(
        config, "SANITIZE_DB_DEFAULT", "sanitize_text", "advanced_options.sanitize_text"
    )


@wrapper.config_reader
def get_textType(config=None):
    if config is False:
        return of_env.getattr("TEXT_TYPE_DEFAULT")
    final_value = _truthy_value(
        config,
        "TEXT_TYPE_DEFAULT",
        "text_type_default",
        "file_options.text_type_default",
    )
    # "Word" is word; anything else falls back, and the startup rewrite of
    # config.json then replaces it
    return naming_check.text_type(final_value) or of_env.getattr("TEXT_TYPE_DEFAULT")


@wrapper.config_reader
def get_TempDir(config=None):
    if config is False:
        return of_env.getattr("TEMP_FOLDER_DEFAULT")
    val = _first_set(config, "temp_dir", "advanced_options.temp_dir")
    return strip_path_quotes(val) if val is not None else of_env.getattr("TEMP_FOLDER_DEFAULT")


@wrapper.config_reader
def get_filename_collision(config=None):
    return _value(
        config,
        "FILENAME_COLLISION_DEFAULT",
        "filename_collision",
        "file_options.filename_collision",
    )


@wrapper.config_reader
def get_truncation(config=None):
    return _value(
        config,
        "TRUNCATION_DEFAULT",
        "truncation_default",
        "file_options.truncation_default",
    )


@wrapper.config_reader
def get_max_post_count(config=None):
    if config is False:
        return of_env.getattr("MAX_COUNT_DEFAULT")
    try:
        return int(
            _value(
                config,
                "MAX_COUNT_DEFAULT",
                "max_post_count",
                "download_options.max_post_count",
            )
        )
    except (ValueError, TypeError):
        return of_env.getattr("MAX_COUNT_DEFAULT")


@wrapper.config_reader
def get_hash(config=None):
    return _value(
        config,
        "HASHED_DEFAULT",
        "remove_hash_match",
        "advanced_options.remove_hash_match",
    )


@wrapper.config_reader
def get_block_ads(config=None):
    return _value(
        config, "BLOCKED_ADS_DEFAULT", "block_ads", "content_filter_options.block_ads"
    )


@wrapper.config_reader
def get_skip_unavailable_content(config=None):
    return _value(
        config,
        "SKIP_UNAVAILABLE_DEFAULT",
        "skip_unavailable_content",
        "advanced_options.skip_unavailable_content",
    )


@wrapper.config_reader
def get_verify_all_integrity(config=None):
    return _value(
        config,
        "VERIFY_ALL_INTEGRITY",
        "verify_all_integrity",
        "download_options.verify_all_integrity",
    )


@wrapper.config_reader
def get_drm_duration_match_threshold(config=None):
    """Minimum actual/expected duration ratio for DRM (and optional) integrity checks.

    Default 0.98 (98%). Values > 1 are treated as percents (e.g. 98 → 0.98).
    """
    _note_reads("drm_duration_match_threshold", "download_options.drm_duration_match_threshold")
    default = 0.98
    if config is False:
        return default
    raw = config.get("drm_duration_match_threshold")
    if raw is None and isinstance(config.get("download_options"), dict):
        raw = config.get("download_options", {}).get("drm_duration_match_threshold")
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if value <= 0:
        return default
    if value > 1.0 and value <= 100:
        value = value / 100.0
    if value > 1.0:
        return default
    return value


@wrapper.config_reader
def get_live_save_location(config=None):
    if not config:
        return ""
    val = _lookup(config, "live_options.save_location")
    return strip_path_quotes(val) if isinstance(val, str) else ""


@wrapper.config_reader
def get_live_dirformat(config=None):
    if not config:
        return ""
    val = _lookup(config, "live_options.dir_format")
    return val if isinstance(val, str) else ""


@wrapper.config_reader
def get_live_fileformat(config=None):
    if not config:
        return ""
    val = _lookup(config, "live_options.file_format")
    return val if isinstance(val, str) else ""


TYPE_OPTION_FIELDS = ("save_location", "dir_format", "file_format")


@wrapper.config_reader
def get_type_options(config=None):
    """{type: {field: value}} with only the fields an entry takes; an entry
    that isn't an object is left out. What it reads is recorded, as
    _lookup records, for the notes on what the rewrite of config.json drops."""
    if not config:
        return {}
    raw = config.get("type_options")
    if not isinstance(raw, dict):
        return {}
    cleaned = {}
    for name, section in raw.items():
        if not isinstance(section, dict):
            continue
        entry = {field: section[field] for field in TYPE_OPTION_FIELDS if isinstance(section.get(field), str)}
        if "save_location" in entry:
            entry["save_location"] = strip_path_quotes(entry["save_location"])
        if _reads is not None:
            # a field it takes is read even when it holds something else,
            # which the rewrite then names as such
            _reads.add(f"type_options.{name}")
            _reads.update(f"type_options.{name}.{field}" for field in TYPE_OPTION_FIELDS if field in section)
        cleaned[str(name)] = entry
    return cleaned
