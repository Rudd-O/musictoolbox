import logging
import os
from queue import Queue
from threading import Thread
import typing

import concurrent.futures as fut

# FIXME: does this belong here?  Why not on the main()?
import signal as _unused_signal  # noqa

from . import algo
from .. import files
from ..files import AbsolutePath, Absolutize
from ..transcoding import registry as reg, transcoder
from ..transcoding.interfaces import Postprocessor
from .interfaces import (
    PathMappingProtocol,
    PathComparisonProtocol,
)


logger = logging.getLogger(__name__)


def parse_playlists(
    sources: typing.List[AbsolutePath],
) -> typing.Tuple[
    typing.Dict[AbsolutePath, typing.List[AbsolutePath]],
    typing.List[typing.Tuple[AbsolutePath, Exception]],
]:
    """
    Take several playlists, and return a dictionary and a list.
    This dictionary is structured as follows:
    - keys: absolute path names mentioned in the playlists
    - values: playlists where the file appeared
    The list is a sequence of (file, Exception) occurred while parsing.
    Symlinked playlists are followed to their targets to extract paths.
    """
    files: typing.Dict[AbsolutePath, typing.List[AbsolutePath]] = {}
    excs: typing.List[typing.Tuple[AbsolutePath, Exception]] = []
    for source in sources:
        try:
            realsource = Absolutize(os.path.realpath(source))
            realsourcedir = realsource.parent
            with open(realsource, "r") as sourcef:
                thisbatch = [
                    Absolutize(os.path.join(realsourcedir, x.strip()))
                    for x in sourcef.readlines()
                    if x.strip() and not x.strip().startswith("#")
                ]
                for path in thisbatch:
                    if path not in files:
                        n: typing.List[AbsolutePath] = []
                        files[path] = n
                    files[path].append(source)
        except Exception as e:
            excs.append((source, e))
    return files, excs


def list_files_recursively(
    directory: AbsolutePath,
) -> typing.List[AbsolutePath]:
    """Return a list of absolute paths from recursively listing a directory"""
    return [
        Absolutize(os.path.join(base, f))
        for base, _, files in os.walk(directory)
        for f in files
    ]


class CallerStopped(Exception):
    pass


SyncQueueItem = typing.Tuple[
    AbsolutePath,
    AbsolutePath,
    typing.Union[
        None,
        Exception,
    ],
]


class SyncPool(Thread):
    def __init__(
        self,
        to_sync: typing.List[
            typing.Tuple[AbsolutePath, AbsolutePath, reg.TranscodingPath]
        ],
        slave: transcoder.SingleItemSyncer,
        max_workers: typing.Optional[int] = None,
    ):
        Thread.__init__(self, daemon=True)
        self.slave = slave
        self.to_sync = to_sync
        self.executor = fut.ThreadPoolExecutor(max_workers=max_workers)
        self.cancelled: typing.List[bool] = []
        self.results: Queue[typing.Union[SyncQueueItem, None]] = Queue()

    def cancel(self) -> None:
        self.cancelled.append(True)
        self.executor.shutdown(wait=True, cancel_futures=True)
        while True:
            # Consume the results that remain.
            r = self.results.get()
            if r is None:
                break

    def run(self) -> None:
        try:
            future_to_url = {
                self.executor.submit(self.slave.sync, s, d, p): (s, d)
                for s, d, p in self.to_sync
            }
            for future in fut.as_completed(future_to_url):
                if self.cancelled:
                    break
                src, dst = future_to_url[future]
                exc: typing.Union[None, Exception] = None
                try:
                    future.result()
                except Exception as e:
                    exc = e
                self.results.put((src, dst, exc))
        finally:
            # FIXME
            # [delete_ignoring_notfound(tmpd) for _, tmpd, d in series]
            self.results.put(None)
            self.executor.shutdown(wait=True, cancel_futures=True)


class Synchronizer(object):
    def __init__(
        self,
        playlists: typing.List[AbsolutePath],
        target_directory: AbsolutePath,
        transcoding_mapper: transcoder.TranscodingMapper,
        exclude_beneath: typing.List[AbsolutePath],
        postprocessor: Postprocessor,
        force_vfat: bool,
    ) -> None:
        self.playlists = playlists
        self.target_directory = target_directory
        self.target_playlist_dir = self.target_directory / "Playlists"

        self.transcoding_mapper = transcoding_mapper
        self.postprocessor: Postprocessor = postprocessor
        self.filesystem_path_mapper = (
            algo.ForceVFATPathMapper(self.target_directory)
            if force_vfat
            else algo.FilesystemPathMapper(self.target_directory)
        )

        self.exclude_beneath = exclude_beneath

    def compute_synchronization(self, unconditional: bool = False) -> algo.SyncRet:
        """Computes synchronization between sources and target."""

        logger.debug("Parsing %s playlists", len(self.playlists))
        source_files, excs = parse_playlists(self.playlists)
        logger.debug("Discovered %s source files", len(source_files))
        if excs:
            for pl, e in excs:
                logger.error("Cannot scan playlist %s: %s", pl, e)
            raise e

        logger.debug("Scanning target directory %s", self.target_directory)
        try:
            target_files = list_files_recursively(self.target_directory)
            logger.debug("Discovered %s target files", len(target_files))
        except Exception as e:
            logger.error("Cannot scan target directory: %s", e)
            raise e

        source_basedir = Absolutize(
            os.path.commonprefix([s.parent for s in source_files])
        )

        class AbsoluteMapperAdapter(object):
            def __init__(self, mapper: transcoder.TranscodingMapper):
                self.mapper = mapper

            def map(self, src: AbsolutePath) -> AbsolutePath:
                return Absolutize(self.mapper.map(src))

        source_mappers: typing.List[PathMappingProtocol] = [
            AbsoluteMapperAdapter(self.transcoding_mapper),
        ]
        target_mappers: typing.List[PathMappingProtocol] = [self.filesystem_path_mapper]
        transcode_pather = self.transcoding_mapper

        comparator: PathComparisonProtocol = algo.ModTimestampComparer()
        if unconditional:
            comparator = algo.SourceAlwaysNewer()

        # Also exclude from deletion all playlists that will be synced.
        exclude_beneath = self.exclude_beneath + [
            self.target_playlist_dir / p.name for p in self.playlists
        ]

        return algo.compute_synchronization(
            list(source_files),
            source_basedir,
            target_files,
            self.target_directory,
            source_mappers,
            target_mappers,
            transcode_pather,
            comparator,
            exclude_beneath,
        )

    def synchronize(
        self,
        sync_plan: algo.SyncRet,
        concurrency: int,
    ) -> typing.Tuple[
        Queue[typing.Union[SyncQueueItem, None]],
        typing.Callable[[], None],
    ]:
        """
        Computes synchronization between sources and target, then
        gets ready to sync using a thread pool, dispatching tasks to it.
        The start of the sync process happens immediately, and synchronization
        happens asynchronously.

        Returns a tuple of Queue with result objects, and a callable that
        can be called to cancel the process.  Once the cancel callable
        returns, the process has stopped.  The result object is a tuple
        with (src, dst, optional Exception).
        """
        to_sync, _, __, ___ = sync_plan
        max_workers: typing.Optional[int] = (
            concurrency if (concurrency and concurrency > 0) else None
        )

        logger.info(
            "Synchronizing %s items with %s threads",
            len(to_sync),
            max_workers if max_workers else "automatic number of",
        )
        slave = transcoder.SingleItemSyncer(self.postprocessor)
        t = SyncPool(to_sync, slave, max_workers=max_workers)
        t.start()

        return t.results, t.cancel

    def synchronize_playlists(
        self, sync_plan: algo.SyncRet, dryrun: bool = False
    ) -> typing.Generator[
        typing.Tuple[AbsolutePath, AbsolutePath, typing.Union[Exception, None]],
        None,
        None,
    ]:
        """
        Once synchronization of files has been done, synchronization of
        playlists is possible.

        The entry conditions for this function are the same as the entry
        conditions of synchronize().

        It yields tuples of (source_path, target_path, optional Exception)
        where the exception will not be None if there was a problem
        synchronizing a particular playlist.

        Symlinked playlists are followed to their target files to compute
        their synchronization.
        """
        # FIXME if adding params to the following call, add them above too
        will_sync_list, wont_sync, already_synced, _ = sync_plan
        will_sync = dict((s, d) for s, d, _ in will_sync_list)

        if not dryrun:
            try:
                files.ensure_directories_exist([self.target_playlist_dir.as_posix()])
            except Exception as e:
                yield (self.target_playlist_dir, self.target_playlist_dir, e)
                return

        for p in self.playlists:
            newp = self.target_playlist_dir / p.name
            oldp, p = p, Absolutize(os.path.realpath(p))
            try:
                pdir = p.parent
                with p.open("r") as pf:
                    pfl = pf.readlines()
                newpfl = []
                for ln in pfl:
                    if ln.startswith("#") or not ln.strip():
                        newpfl.append(ln)
                        continue
                    cr = ln.endswith("\n")
                    orgl = "# was: " + ln.strip() + "\n"
                    newpfl.append(orgl)
                    ln = ln.strip()
                    truel = Absolutize(os.path.join(pdir, ln))
                    if truel in will_sync:
                        ln = will_sync[truel].as_posix()
                        ln = os.path.relpath(ln, self.target_playlist_dir.as_posix())
                    elif truel in already_synced:
                        ln = already_synced[truel].as_posix()
                        ln = os.path.relpath(ln, self.target_playlist_dir.as_posix())
                    elif truel in wont_sync:
                        ln = "# not synced because of %s" % wont_sync[truel]
                    else:
                        assert 0, (ln, truel)
                    if cr:
                        ln += "\n"
                    newpfl.append(ln)
                # Insert provenance comment.
                newpfl.insert(
                    1 if (newpfl and newpfl[0].startswith("#EXTM3U")) else 0,
                    "# from: %s\n" % oldp,
                )
                sync = True
                try:
                    with newp.open("r") as oldpfl:
                        if oldpfl.read() == "".join(newpfl):
                            sync = False
                except FileNotFoundError:
                    pass
                if sync:
                    if not dryrun:
                        with newp.open("w") as newpf:
                            newpf.writelines(newpfl)
                            newpf.flush()
                    yield (oldp, newp, None)
            except Exception as e:
                yield (oldp, newp, e)

    def synchronize_deletions(
        self, sync_plan: algo.SyncRet, dryrun: bool = False
    ) -> typing.Generator[
        typing.Tuple[AbsolutePath, typing.Union[Exception, None]], None, None
    ]:
        """
        Once synchronization of files and playlists has been done, sync
        of deletions is possible.

        The entry conditions for this function are the same as the entry
        conditions of synchronize_playlists().

        It yields tuples of (path, optional Exception) where the exception
        will not be None if there was a problem deleting a particular file.
        """
        _, __, ___, deleting = sync_plan

        for t in deleting:
            try:
                if not dryrun:
                    t.unlink(True)
                yield (t, None)
            except Exception as e:
                yield (t, e)


# =================== end synchronizer code ========================
