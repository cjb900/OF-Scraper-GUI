import logging
import os
import pathlib
import platform
import shutil
from collections.abc import Iterable

import ofscraper.commands.scraper.actions.utils.globals as common_globals
import ofscraper.utils.dates as dates
import ofscraper.utils.paths.common as common_paths
from ofscraper.commands.scraper.actions.utils.log import get_medialog

try:
    from win32_setctime import setctime  # pylint: disable=import-error
except ModuleNotFoundError:
    pass


def moveHelper(temp, path_to_file, ele, log_=None):
    if not path_to_file.exists():
        shutil.move(temp, path_to_file)
    elif (
        pathlib.Path(temp).absolute().stat().st_size
        >= pathlib.Path(path_to_file).absolute().stat().st_size
    ):
        shutil.move(temp, path_to_file)
    else:
        pathlib.Path(temp).unlink(missing_ok=True)
        log_ = log_ or logging.getLogger("shared")
        log_.debug(f"{get_medialog(ele)} smaller then previous file")
    # set variables based on parent process


def _resolve(path):
    path = pathlib.Path(path)
    try:
        return path.resolve()
    except OSError:
        # some network/virtual drives (e.g. WinError 1005 on mapped Windows
        # volumes) can't be resolved; the directory set is only used to
        # date folders afterwards, so an absolute path is enough
        return path.absolute()


def _resolve_dir(path):
    path = _resolve(path)
    return path if path.is_dir() else path.parent


def addGlobalDir(path):
    paths = (
        [path]
        if isinstance(path, (str, os.PathLike)) or not isinstance(path, Iterable)
        else path
    )
    common_globals.dirSet.update(map(_resolve_dir, paths))


def addLocalDir(path):
    paths = [path] if not isinstance(path, list) else path
    common_globals.dirSet.update(map(_resolve_dir, paths))


def set_time(path, timestamp):
    if platform.system() == "Windows":
        setctime(path, timestamp)
    os.utime(path, (timestamp, timestamp))


def setDirectoriesDate(log=None):
    log = log or common_globals.log
    log.info("Setting Date for modified directories")
    output = set()
    # resolved the same way as dirSet so is_relative_to compares like with like
    # (resolve() can turn a mapped drive letter into a UNC path)
    rootDir = _resolve(common_paths.get_save_location())
    log.debug(f"Original DirSet {list(common_globals.dirSet)}")
    log.debug(f"rootDir {rootDir}")

    for ele in common_globals.dirSet:
        output.add(ele)
        try:
            while not os.path.samefile(ele, rootDir) and not os.path.samefile(
                ele.parent, rootDir
            ):
                if ele.parent in output:
                    # We already added all subsequent paths in this tree
                    break
                if not pathlib.PurePath(ele.parent).is_relative_to(rootDir):
                    # Don't descend if the parent path is outside rootDir such as
                    # when a symlink was used somewhere in the path
                    break
                common_globals.log.debug(f"Setting Dates ele:{ele} rootDir:{rootDir}")
                output.add(ele.parent)
                ele = ele.parent
        except OSError as E:
            # samefile stats both paths, which fails on the same drives
            log.debug(f"could not walk up from {ele}: {E}")
    log.debug(f"Directories list {output}")
    for ele in output:
        try:
            set_time(ele, dates.get_current_time())
        except OSError as E:
            log.debug(f"could not set date on {ele}: {E}")
