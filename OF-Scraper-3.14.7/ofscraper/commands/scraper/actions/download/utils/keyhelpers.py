import asyncio
import logging
import pathlib
import re
import struct
import traceback
from functools import partial

from pywidevine.cdm import Cdm
from pywidevine.device import Device
from pywidevine.pssh import PSSH

import ofscraper.commands.scraper.actions.utils.globals as common_globals
import ofscraper.utils.cache.cache as cache
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.settings as settings
from ofscraper.commands.scraper.actions.utils.retries import (
    get_cmd_download_req_retries,
)
from ofscraper.commands.scraper.actions.utils.log import get_medialog
from ofscraper.utils.system.subprocess import async_run
from ofscraper.utils.system.ffmpeg import get_ffmpeg
import ofscraper.managers.manager as manager

log = None

# Remote key modes that share the minimal CDRM payload (no session cookies).
_REMOTE_CDRM_MODES = frozenset({"cdrm", "cdrm2", "keydb"})


def setLog(input_):
    global log
    log = input_


class CdmFilesMissing(Exception):
    """Manual key mode can't work without the CDM files; retrying won't help."""

    no_retry = True


_cdm_problem_logged = False


def manual_cdm_problem(client_id=None, private_key=None):
    """Return a plain message when manual key mode can't load its CDM files, else None.

    A blank path would otherwise become Path("") == "." and fail with
    "Is a directory: '.'" for every DRM video.
    """
    if client_id is None and private_key is None:
        s = settings.get_settings()
        client_id, private_key = s.client_id, s.private_key
    problems = []
    for label, value in (("client-id", client_id), ("private-key", private_key)):
        value = str(value or "").strip()
        if not value:
            problems.append(f"{label} is not set")
        elif not pathlib.Path(value).is_file():
            problems.append(f"{label} file not found: {value}")
    if not problems:
        return None
    return (
        "Key Mode is manual but the CDM files can't be used ("
        + "; ".join(problems)
        + "). Set client-id and private-key under cdm_options in config.json "
        "(GUI: Configuration → CDM / DRM Key Creation), or choose another Key Mode. "
        "DRM videos are skipped until then."
    )


async def has_cached_key(ele):
    if not of_env.getattr("USE_WIV_CACHE_KEY"):
        return False
    return bool(
        await asyncio.get_event_loop().run_in_executor(
            common_globals.thread, partial(cache.get, ele.license)
        )
    )


async def check_manual_cdm(ele):
    """Raise CdmFilesMissing before a DRM download that could never be decrypted."""
    global _cdm_problem_logged
    keymode = str(settings.get_settings().key_mode or "manual").lower().strip()
    if keymode != "manual":
        return
    problem = manual_cdm_problem()
    if not problem or await has_cached_key(ele):
        return
    if not _cdm_problem_logged:
        _cdm_problem_logged = True
        logging.getLogger("shared").error(problem)
    raise CdmFilesMissing(problem)


def strip_pssh(path):
    """
    Turn pssh boxes in a decrypted file into same-sized 'free' boxes.

    ffmpeg 8+ copies the source's pssh (DRM init data) into the decrypted
    output; 7.x dropped it. The media is identical either way, but a clear
    file still carrying pssh can look protected to some players. Renaming
    keeps every offset valid, so nothing else in the file changes.
    Returns the number of boxes changed.
    """
    changed = 0
    with open(path, "r+b") as f:
        f.seek(0, 2)
        file_end = f.tell()

        def walk(start, end, depth):
            nonlocal changed
            pos = start
            while pos + 8 <= end:
                f.seek(pos)
                size, typ = struct.unpack(">I4s", f.read(8))
                header = 8
                if size == 1:
                    size = struct.unpack(">Q", f.read(8))[0]
                    header = 16
                elif size == 0:
                    size = end - pos
                if size < header or pos + size > end:
                    return
                if typ == b"pssh":
                    f.seek(pos + 4)
                    f.write(b"free")
                    changed += 1
                elif depth == 0 and typ in (b"moov", b"moof"):
                    walk(pos + header, pos + size, depth + 1)
                pos += size

        walk(0, file_end, 0)
    return changed


async def un_encrypt(item, c, ele, input_=None):
    try:
        setLog(input_ or common_globals.log)
        key = None
        keymode = str(settings.get_settings().key_mode or "manual").lower().strip()
        past_key = (
            await asyncio.get_event_loop().run_in_executor(
                common_globals.thread, partial(cache.get, ele.license)
            )
            if of_env.getattr("USE_WIV_CACHE_KEY")
            else None
        )
        if past_key:
            key = past_key
            log.debug(f"{get_medialog(ele)} got key from cache (present)")
        elif keymode == "manual":
            key = await key_helper_manual(c, item["pssh"], ele.license, ele.id)
        elif keymode in _REMOTE_CDRM_MODES:
            key = await key_helper_cdrm(c, item["pssh"], ele.license, ele.id)
        if not key:
            raise Exception(f"{get_medialog(ele)} Could not get key")
        key = key.strip()
        log.debug(f"{get_medialog(ele)} retrieved new key (present)")
        newpath = pathlib.Path(
            re.sub(
                r"\.part$", f".{item['ext']}", str(item["path"]), flags=re.IGNORECASE
            )
        )
        ffmpeg_key = get_ffmpeg_key(key)
        log.debug(f"{get_medialog(ele)} got ffmpeg key (present)")
        log.debug(
            f"{get_medialog(ele)}  renaming {pathlib.Path(item['path']).absolute()} -> {newpath}"
        )
        r = await async_run(
            [
                get_ffmpeg(),
                "-decryption_key",
                ffmpeg_key,
                "-i",
                str(item["path"]),
                "-codec",
                "copy",
                str(newpath),
                "-y",
            ],
            level=of_env.getattr("FFMPEG_SUBPROCESS_LEVEL"),
            name="ffmpeg",
        )
        if not pathlib.Path(newpath).exists():
            log.debug(f"{get_medialog(ele)} ffmpeg {r.stderr.decode()}")
            log.debug(f"{get_medialog(ele)} ffmpeg {r.stdout.decode()}")
            await asyncio.get_event_loop().run_in_executor(
                common_globals.thread,
                partial(
                    cache.set, ele.license, None, expire=of_env.getattr("KEY_EXPIRY")
                ),
            )
            raise Exception(f"{get_medialog(ele)} ffmpeg decryption failed")
        else:
            log.debug(f"{get_medialog(ele)} ffmpeg  decrypt success {newpath}")
            try:
                if n := strip_pssh(newpath):
                    log.debug(f"{get_medialog(ele)} removed {n} pssh box(es) from {newpath}")
            except Exception as E:  # cleanup is optional; never fail a good decrypt
                log.debug(f"{get_medialog(ele)} could not strip pssh from {newpath}: {E}")
            pathlib.Path(item["path"]).unlink(missing_ok=True)
            item["path"] = newpath
            await asyncio.get_event_loop().run_in_executor(
                common_globals.thread,
                partial(
                    cache.set, ele.license, key, expire=of_env.getattr("KEY_EXPIRY")
                ),
            )
            return item
    except Exception as E:
        raise E


def get_ffmpeg_key(key):
    return key.split(":")[1]


async def key_helper_cdrm(c, pssh, licence_url, id):
    """Post only pssh + license URL to the remote helper — never cookies / sign / x-bc."""
    key = None
    log.debug(f"ID:{id} using cdrm auto key helper (minimal payload; no session cookies)")
    try:
        log.debug(f"ID:{id} pssh: {pssh is not None}")
        log.debug(f"ID:{id} licence url present: {bool(licence_url)}")
        # Intentionally omit cookie / sign / x-bc. Remote helpers that require
        # those headers are unsupported; use Key Mode "manual" + local CDM.
        json_data = {
            "licurl": licence_url,
            "pssh": pssh,
        }
        async with c.requests_async(
            url=of_env.getattr("CDRM"),
            method="post",
            json=json_data,
            retries=get_cmd_download_req_retries(),
            wait_min=of_env.getattr("OF_MIN_WAIT_API"),
            wait_max=of_env.getattr("OF_MAX_WAIT_API"),
            total_timeout=of_env.getattr("CDM_TIMEOUT"),
            skip_expection_check=True,
        ) as r:
            data = await r.json_()
            # Do not log full response — may contain content keys.
            log.debug(f"ID:{id} cdrm response keys: {list(data) if isinstance(data, dict) else type(data).__name__}")
            key = data["message"]
        return key
    except Exception as E:
        log.traceback_(E)
        log.traceback_(traceback.format_exc())
        raise Exception(
            f"ID:{id} remote key helper failed without session cookies. "
            "Switch Key Mode to manual and use local CDM files "
            "(Configuration → CDM / DRM Key Creation)."
        ) from E


async def key_helper_manual(c, pssh, licence_url, id):
    key = None
    log.debug(f"ID:{id} using manual key helper")
    try:
        log.debug(f"ID:{id} pssh: {pssh is not None}")
        log.debug(f"ID:{id} licence: {licence_url}")

        # prepare pssh
        pssh_obj = PSSH(pssh)

        # load device
        if problem := manual_cdm_problem():
            raise CdmFilesMissing(problem)
        private_key = pathlib.Path(settings.get_settings().private_key).read_bytes()
        client_id = pathlib.Path(settings.get_settings().client_id).read_bytes()
        device = Device(
            security_level=3,
            private_key=private_key,
            client_id=client_id,
            type_="ANDROID",
            flags=None,
        )

        # load cdm
        cdm = Cdm.from_device(device)

        # open cdm session
        session_id = cdm.open()

        keys = None
        challenge = cdm.get_license_challenge(session_id, pssh_obj)
        from ofscraper.utils.host_allowlist import ensure_allowed_download_url

        licence_url = ensure_allowed_download_url(licence_url, kind="drm-license")
        async with manager.Manager.session.get_cdm_session_manual() as c:
            async with c.requests_async(
                url=licence_url,
                method="post",
                data=challenge,
                retries=get_cmd_download_req_retries(),
                wait_min=of_env.getattr("OF_MIN_WAIT_API"),
                wait_max=of_env.getattr("OF_MAX_WAIT_API"),
                total_timeout=of_env.getattr("CDM_TIMEOUT"),
            ) as r:
                data = await r.read_()
                cdm.parse_license(session_id, (data))
                keys = cdm.get_keys(session_id)
                cdm.close(session_id)
            keyobject = list(filter(lambda x: x.type == "CONTENT", keys))[0]

        key = "{}:{}".format(keyobject.kid.hex, keyobject.key.hex())
        return key
    except Exception as E:
        log.traceback_(E)
        log.traceback_(traceback.format_exc())
        raise E
