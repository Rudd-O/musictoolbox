"""
Created on Aug 11, 2012

@author: rudd-o
"""

import collections
import logging
import os
import pathlib
import typing

import psutil  # type: ignore

from ..files import AbsolutePath, Absolutize
from ..transcoding.registry import (
    TranscodingPathLookupProtocol,
    TranscodingPath,
)
from .interfaces import (
    PathMappingProtocol,
    PathComparisonProtocol,
)


logger = logging.getLogger(__name__)


def within(path: AbsolutePath, subpath: AbsolutePath) -> bool:
    """Return True if path equals subpath or subpath is within path."""
    if path == subpath:
        return True
    return subpath.is_relative_to(path)


def delete_ignoring_notfound(f: pathlib.Path) -> None:
    try:
        os.unlink(f.as_posix())
    except FileNotFoundError:
        pass


def vfatprotect(f: str) -> str:
    """Replace illegal characters in VFAT file system paths."""
    for illegal in '?<>\\:*|"^':
        f = f.replace(illegal, "_")
    while "./" in f:
        f = f.replace("./", "/")
    while " /" in f:
        f = f.replace(" /", "/")
    return f


def get_mptypes() -> typing.Dict[str, str]:
    """Return a mapping of mount points and their file system types."""
    return dict([(p.mountpoint, p.fstype) for p in psutil.disk_partitions()])


def get_fstype(
    p: AbsolutePath, mptypes: typing.Dict[str, str]
) -> typing.Tuple[str, AbsolutePath]:
    """Return the file system type corresponding to a path, along with the file system's mount point."""
    assert os.name != "nt"
    for deepest_mountpoint in p.parents:
        if deepest_mountpoint.as_posix() in mptypes:
            break
    return mptypes[deepest_mountpoint.as_posix()], deepest_mountpoint


class FilesystemPathMapper(object):
    def __init__(self, target_dir: AbsolutePath) -> None:  # @UnusedVariable
        self.mptypes = get_mptypes()
        self.paths_seen: typing.Dict[AbsolutePath, AbsolutePath] = {}

    def map(self, path: AbsolutePath) -> AbsolutePath:
        fstype, deepest_mountpoint = get_fstype(path, self.mptypes)
        if fstype not in ("vfat", "ntfs"):
            return path

        head, tail = deepest_mountpoint, path.relative_to(deepest_mountpoint)
        tailstr = pathlib.Path(vfatprotect(tail.as_posix()))
        tailstr_lower = pathlib.Path(tailstr.as_posix().lower())
        normalized_path = Absolutize(head / tailstr)
        normalized_path_lower = Absolutize(head / tailstr_lower)

        if normalized_path_lower not in self.paths_seen:
            self.paths_seen[normalized_path_lower] = normalized_path
        return self.paths_seen[normalized_path_lower]


class ForceVFATPathMapper(FilesystemPathMapper):
    def __init__(self, target_dir: AbsolutePath) -> None:
        FilesystemPathMapper.__init__(self, target_dir)
        self.mptypes = {target_dir.as_posix(): "vfat", "/": self.mptypes["/"]}


def vfatcompare(s: typing.Union[int, float], t: typing.Union[int, float]) -> int:
    """Compare two VFAT timestamps — if they are close enough, return "same"."""
    x = int(s) - int(t)
    if x >= 2:
        return 1
    elif x <= -2:
        return -1
    return 0


class SourceAlwaysNewer(object):
    def compare(self, __arg1: AbsolutePath, __arg2: AbsolutePath) -> int:
        return 1


class ModTimestampComparer(object):
    def __init__(self) -> None:
        self.mptypes = get_mptypes()

    def compare(self, path1: AbsolutePath, path2: AbsolutePath) -> int:
        fstypes = set(get_fstype(p, self.mptypes)[0] for p in [path1, path2])
        if "vfat" in fstypes:
            comparator = vfatcompare
        else:
            comparator = lambda x, y: (1 if x > y else (-1 if x < y else 0))

        try:
            st2 = path2.stat()
        except FileNotFoundError:
            # The target file does not exist, so we always return the
            # source file as newer.
            return 1
        st1 = path1.stat()

        try:
            t1 = st1.st_mtime_ns / 1000000000
            t2 = st2.st_mtime_ns / 1000000000
        except AttributeError:
            t1 = st1.st_mtime
            t2 = st2.st_mtime

        return comparator(t1, t2)


class SyncError(Exception):
    pass


class Conflict(SyncError):
    def __init__(
        self, source: AbsolutePath, target: AbsolutePath, predecessor: AbsolutePath
    ):
        self.source = source
        self.target = target
        self.predecessor = predecessor

    def __str__(self) -> str:
        return (
            "<Conflict: file %s cannot be synced to %s because %s was already synced there>"
            % (self.source, self.target, self.predecessor)
        )

    def __eq__(self, other: typing.Any) -> bool:
        return str(self) == str(other)


SyncRet = typing.Tuple[
    typing.List[typing.Tuple[AbsolutePath, AbsolutePath, TranscodingPath]],
    typing.Dict[AbsolutePath, Exception],
    typing.Dict[AbsolutePath, AbsolutePath],
    typing.List[AbsolutePath],
]


def compute_synchronization(
    source_files: typing.List[AbsolutePath],
    source_basedir: AbsolutePath,
    target_files: typing.List[AbsolutePath],
    target_basedir: AbsolutePath,
    source_mappers: typing.List[PathMappingProtocol],
    target_mappers: typing.List[PathMappingProtocol],
    transcode_pather: TranscodingPathLookupProtocol,
    comparator: PathComparisonProtocol,
    exclude_beneath: typing.Optional[typing.List[AbsolutePath]] = None,
) -> SyncRet:
    """
    Compute a synchronization schedule based on a dictionary of
    {source_filename:mtime} and a dictionary of {target_filename:mtime}.
    Paths must be absolute or the behavior of this function is undefined.
    All paths must be contained in their respective specified directories.
    mtime in the source dictionary can be an exception, in which case it will
    be presumed that the source file in question cannot be transferred.

    The synchronization aims to discover the target file names based on
    the source file names, and then automatically figure out which files
    need to be transferred, based on their absence in the remote site,
    or their modification date.

    This function accepts a path mapping callable that will transform
    a partial source file name, and the full path to the source file name,
    into the desired partial target file name prior to performing the
    date comparison.  By default, it is an identity function x, y => x.

    This function also accepts a time comparator function that will
    be used to perform the comparison between source and target
    modification times.  The comparator is the standard 1 0 -1 comparator
    that takes x,y where it returns 1 if x > y, 0 if x and y are identical,
    and -1 if x < y.  The comparator gets passed the source mtime as the
    first parameter, and the target mtime as the second parameter.
    FAT file system users may want to pass a custom comparator that takes
    into consideration the time resolution of FAT32 file systems
    (greater than 2 seconds).

    Return four values in a tuple:
        1. A dictionary {s:t} where s is the source file name, and
           t is the desired target file name after transfer.
        2. A dictionary {s:e} where s is the source file name, and
           e is the exception explaining why it cannot be synced,
        3. A dictionary {s:e} of files that will be skipped, with their
           corresponding would-be targets that already were transferred,
        4. A list of files that will be deleted from the destination.
    """
    exclude_beneath = exclude_beneath or []

    will_transfer: typing.List[
        typing.Tuple[AbsolutePath, AbsolutePath, TranscodingPath]
    ] = []
    cant_transfer = collections.OrderedDict()
    already_transferred = collections.OrderedDict()
    deleting = collections.OrderedDict()

    def multimap(
        f: AbsolutePath, mappers: typing.List[PathMappingProtocol]
    ) -> AbsolutePath:
        for mapper in mappers:
            f = Absolutize(mapper.map(f))
        return f

    for t in target_files:
        if any(within(exclude_root, t) for exclude_root in exclude_beneath):
            # Do not delete any files within the exclude dirs.
            pass
        else:
            # This file does not reside in the exclude dir.
            # We default to deleting it, until such time that we later
            # decide it must be kept back.
            deleting[t] = True
        # Warm up the target mappers so that paths with different casing
        # will not have a problem later on being discovered.
        multimap(t, target_mappers)

    already_processed: typing.Dict[AbsolutePath, bool] = {}
    already_foreseen: typing.Dict[AbsolutePath, AbsolutePath] = {}

    for src in source_files:
        if not within(source_basedir, src):
            raise ValueError(
                "source path %r not within source dir %r" % (src, source_basedir)
            )

        if src in already_processed:
            continue
        already_processed[src] = True

        try:
            src_mapped = multimap(src, source_mappers)
            tpath = transcode_pather.lookup(src)[0]
        except Exception as e:
            cant_transfer[src] = e
            continue

        rel = src_mapped.relative_to(source_basedir)
        absp = target_basedir / rel

        tgt = multimap(absp, target_mappers)

        if any(within(exclude_root, tgt) for exclude_root in exclude_beneath):
            # Do not sync any files within the exclude dirs.
            continue

        try:
            if tgt in already_foreseen:
                raise Conflict(src, tgt, already_foreseen[tgt])
            if comparator.compare(src, tgt) > 0:
                will_transfer.append((src, tgt, tpath))
                already_foreseen[tgt] = src
            else:
                already_transferred[src] = tgt
        except Exception as e:
            cant_transfer[src] = e
        deleting[tgt] = False

    return (
        will_transfer,
        cant_transfer,
        already_transferred,
        [d for d, y in deleting.items() if y],
    )
