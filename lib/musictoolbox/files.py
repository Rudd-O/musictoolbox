import os
import typing
import contextlib
from pathlib import Path
from threading import Lock


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


def all_files(paths: list[str], recursive: bool = True) -> list[str]:
    allfiles: list[str] = []
    for f in paths:
        if os.path.isdir(f):
            if recursive:
                files = [
                    os.path.join(root, x) for root, _, fs in os.walk(f) for x in fs
                ]
            else:
                files = [
                    os.path.join(f, x)
                    for x in os.listdir(f)
                    if not os.path.isdir(os.path.join(f, x))
                ]
        else:
            files = [f]
        allfiles.extend(files)
    return allfiles
