import contextlib
import logging
import os
from pathlib import Path
from threading import Lock
import typing


logger = logging.getLogger(__name__)


AbsolutePath = typing.NewType("AbsolutePath", Path)


def Absolutize(p: typing.Union[Path, str]) -> AbsolutePath:
    if isinstance(p, Path):
        p = p.as_posix()
    pp: AbsolutePath = Path(os.path.abspath(p))  # type: ignore
    return pp


_dir_lock = Lock()


def ensure_directories_exist(dirs: typing.List[str]) -> None:
    global _dir_lock
    with _dir_lock:
        for t in dirs:
            if not t:
                continue
            if not os.path.exists(t):
                os.makedirs(t)


def ensure_files_gone(files: typing.List[str]) -> None:
    for t in files:
        if not t:
            continue
        try:
            os.unlink(t)
        except FileNotFoundError:
            pass


@contextlib.contextmanager
def remover() -> typing.Generator[typing.List[str], None, None]:
    """
    Yields an empty list of files.  At the end of the context,
    removes all files in the list of files.
    """
    files: typing.List[str] = []
    try:
        yield files
    finally:
        ensure_files_gone(files)


def shorten_to_name_max(directory: str, name: str, strip_extra_chars: int) -> str:
    pathconf_directory = os.path.abspath(directory)
    while not os.path.isdir(pathconf_directory):
        pathconf_directory = os.path.dirname(pathconf_directory)
    maxfilenamelen = os.pathconf(pathconf_directory, "PC_NAME_MAX")
    name = name[: maxfilenamelen - strip_extra_chars]
    return name
