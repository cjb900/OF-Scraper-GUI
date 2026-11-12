import logging
import os
import pathlib
import platform
import re
from contextlib import contextmanager
from pathlib import Path

import ofscraper.utils.config.data as data
import ofscraper.utils.console as console_
import ofscraper.utils.of_env.of_env as of_env
import ofscraper.utils.paths.common as common_paths
import ofscraper.utils.settings as settings

console = console_.get_shared_console()
homeDir = pathlib.Path.home()
log = logging.getLogger("shared")


@contextmanager
def set_directory(path: Path):
    """Sets the cwd within the context

        Args:``
            path (``Path): The path to the cwd

    Yields:
        None
    """

    origin = Path().absolute()
    Path(str(path)).mkdir(parents=True, exist_ok=True)
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(origin)


def temp_cleanup():
    if not of_env.getattr("BATCH_TEMPFILE_CLEANUP"):
        return
    if not settings.get_settings().auto_resume:
        log.info("Cleaning up temp files\n\n")
        root = data.get_TempDir()
        if root is None:
            return
        for file in filter(
            lambda x: x.is_file()
            and re.search(r"\.part$|^temp_", x.name) is not None,
            pathlib.Path(root).glob("**/*"),
        ):
            file.unlink(missing_ok=True)


def truncate(path):
    path = pathlib.Path(os.path.normpath(path))
    if platform.system() == "Windows":
        return _windows_truncateHelper(path)
    elif platform.system() == "Linux":
        return _linux_truncateHelper(path)
    elif platform.system() == "Darwin":
        return _mac_truncateHelper(path)
    else:
        return pathlib.Path(path)


# Windows' classic limit: 260 UTF-16 characters including the final NUL.
WINDOWS_MAX_PATH_CHARS = 259
# NTFS limit for one file or folder name
WINDOWS_MAX_NAME_CHARS = 255

_long_paths_enabled = None


def windows_long_paths_enabled():
    """True when this Python process may use paths over 260 characters.

    RtlAreLongPathsEnabled checks both the LongPathsEnabled registry setting
    and the program's manifest, so it's only True when long paths really work.
    """
    global _long_paths_enabled
    if _long_paths_enabled is None:
        try:
            import ctypes

            fn = ctypes.windll.ntdll.RtlAreLongPathsEnabled
            fn.restype = ctypes.c_ubyte
            _long_paths_enabled = bool(fn())
        except Exception:
            _long_paths_enabled = False
        log.debug(f"Windows long paths enabled: {_long_paths_enabled}")
    return _long_paths_enabled


def windows_path_length(text):
    """Length as Windows counts it: UTF-16 code units (an emoji counts 2)."""
    return len(str(text).encode("utf-16-le")) // 2


def _windows_max_path_chars():
    # OFSC_WINDOWS_MAX_PATH_BYTES (2 bytes per character) can only lower it
    configured = of_env.getattr("WINDOWS_MAX_PATH_BYTES") // 2
    return min(WINDOWS_MAX_PATH_CHARS, configured)


def _windows_truncateHelper(path):
    path = pathlib.Path(os.path.normpath(path))
    if windows_long_paths_enabled():
        # only the name itself is limited
        budget = WINDOWS_MAX_NAME_CHARS
    else:
        # the folder and its separator count against the whole-path limit
        budget = min(
            WINDOWS_MAX_NAME_CHARS,
            _windows_max_path_chars() - windows_path_length(path.parent) - 1,
        )
    name = path.name
    if windows_path_length(name) <= budget:
        return path

    match = re.search(r"_[0-9]+\.[a-z4]*$", name, re.IGNORECASE) or re.search(
        r"\.[a-z4]*$", name, re.IGNORECASE
    )
    ext = match.group(0) if match else ""
    stem = name[: len(name) - len(ext)]
    room = budget - windows_path_length(ext)
    if room <= 0:
        log.warning(
            f"The folder path is too long for Windows to add a file name: {path.parent}. "
            "Shorten the save location or folder format, or turn on Windows long paths."
        )
        return path
    low, high = 0, len(stem)
    while low < high:
        mid = (low + high + 1) // 2
        if windows_path_length(stem[:mid]) <= room:
            low = mid
        else:
            high = mid - 1
    stem = stem[:low]
    if not ext:
        # Windows drops trailing spaces and dots from a name
        stem = stem.rstrip(" .")
    final_path = pathlib.Path(path.parent, f"{stem}{ext}")
    log.debug(
        f"path: {path} shortened to {windows_path_length(final_path)} characters"
    )
    return final_path


def _mac_truncateHelper(path):
    path = pathlib.Path(os.path.normpath(path))
    if len(str(path)) <= of_env.getattr("MAC_MAX_PATH"):
        return path
    dir = path.parent
    match = re.search(r"_[0-9]+\.[a-z4]*$", path.name, re.IGNORECASE) or re.search(
        r"\.[a-z4]*$", path.name, re.IGNORECASE
    )
    ext = match.group(0) if match else ""
    file = re.sub(ext, "", path.name)
    maxlength = of_env.getattr("MAC_MAX_PATH") - len(ext)
    newFile = f"{file[:maxlength]}{ext}"
    final = pathlib.Path(dir, newFile)
    log.debug(f"path: {final} path size: {len(str(final))}")
    log.debug(f"path: {final} filename size: {len(str(final.name))}")
    return pathlib.Path(dir, newFile)


def _linux_truncateHelper(path):
    path = pathlib.Path(os.path.normpath(path))
    dir = path.parent
    match = re.search(r"_[0-9]+\.[a-z4]*$", path.name, re.IGNORECASE) or re.search(
        r"\.[a-z4]*$", path.name, re.IGNORECASE
    )
    ext = match.group(0) if match else ""
    file = re.sub(ext, "", path.name)
    max_bytes = of_env.getattr("LINUX_MAX_FILE_NAME_BYTES") - get_string_byte_size_unix(
        ext
    )
    low, high = 0, len(file)
    while low < high:
        mid = (low + high) // 2
        if get_string_byte_size_unix(file[:mid]) <= max_bytes:
            low = mid + 1
        else:
            high = mid
    newFile = f"{file[:high]}{ext}"
    log.debug(f"path: {path} filename bytesize: {get_string_byte_size_unix(newFile)}")
    return pathlib.Path(dir, newFile)


def get_string_byte_size_unix(text):
    """
    This function estimates the byte size of a string considering ASCII characters.

    Args:
        text: The string to analyze.

    Returns:
        The estimated byte size of the string.
    """
    total_size = 0
    text = str(text)
    normal_char_size = of_env.getattr("NORMAL_CHAR_SIZE_UNIX")
    special_char_size = of_env.getattr("SPECIAL_CHAR_SIZE_UNIX")
    utf = of_env.getattr("UTF")

    if utf:
        return len(text.encode(utf))
    for char in text:
        try:
            if ord(char) < 128:
                total_size += normal_char_size  # 2 bytes for ASCII characters
            else:
                total_size += special_char_size
        except ValueError:
            total_size += (
                special_char_size  # 4 bytes for non-ASCII characters (assumption)
            )
    return total_size


def get_string_byte_size_windows(text):
    """
    This function estimates the byte size of a string considering ASCII characters.

    Args:
        text: The string to analyze.

    Returns:
        The estimated byte size of the string.
    """
    total_size = 0
    text = str(text)
    normal_char_size = of_env.getattr("NORMAL_CHAR_SIZE_WINDOWS")
    special_char_size = of_env.getattr("SPECIAL_CHAR_SIZE_WINDOWS")
    utf = of_env.getattr("UTF")
    if utf:
        return len(text.encode(utf))
    for char in text:
        try:
            if ord(char) < 128:
                total_size += normal_char_size  # 2 bytes for ASCII characters
            else:
                total_size += special_char_size
        except ValueError:
            total_size += (
                special_char_size  # 4 bytes for non-ASCII characters (assumption)
            )
    return total_size


def cleanDB():
    try:
        pathlib.Path(common_paths.get_profile_path() / "db.lock").unlink(
            missing_ok=True
        )
    except PermissionError:
        None


def speed_file():
    return pathlib.Path(common_paths.get_profile_path() / "speed.zip")
