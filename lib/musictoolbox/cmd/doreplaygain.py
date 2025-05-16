import argparse
import collections
import itertools
import logging
import subprocess
import sys
import typing
import concurrent.futures
import os

from musictoolbox.cache import FileMetadataCache, OnDiskMetadataCache
from musictoolbox.files import all_files
from musictoolbox.logging import basicConfig
from mutagen._file import File
from rgain3.lib.albumid import get_album_id # type: ignore
from rgain3.lib import rgio, GainData # type: ignore


_LOGGER = logging.getLogger(__name__)
_MAPPER = rgio.BaseFormatsMap()

CACHE_VERSION = 6

TM = typing.TypeVar("TM", bound="AlbumIdentifier")


class AlbumIdentifier(object):
    identifier: str
    albumgain: GainData | None
    trackgain: GainData | None

    def __init__(
        self,
        valid: bool,
        identifier: str,
        albumgain: GainData | None,
        trackgain: GainData | None,
    ) -> None:
        self.valid = valid
        self.identifier = identifier
        self.albumgain = albumgain
        self.trackgain = trackgain

    @classmethod
    def from_file(klass: typing.Type[TM], ff: str) -> TM:
        from_disk_metadata = None
        try:
            from_disk_metadata = File(ff)
        except Exception as exc:
            _LOGGER.error("Error identifying %s: %s:", ff, exc)
            return klass(False, "", None, None)
        if from_disk_metadata is None:
            return klass(False, "", None, None)
        album_id = get_album_id(from_disk_metadata)
        try:
            trackgain, albumgain = _MAPPER.read_gain(ff)
        except Exception as exc:
            # The file is not supported.  We return invalid.
            _LOGGER.error("Cannot read ReplayGain from %s: %s>", ff, exc)
            return klass(False, "", None, None)
        return klass(
            True,
            identifier=album_id,
            trackgain=trackgain,
            albumgain=albumgain,
        )


def main() -> None:
    p = argparse.ArgumentParser(
        description="Collection-wide frontend for replaygain (of python-rgain3 fame).",
        epilog="This program"
        " helps you add ReplayGain information to music in an intelligent fashion,"
        " grouping songs by album so album ReplayGain information is calculated"
        " correctly with respect to all other tracks in the album."
        "\n\n"
        "This program is similar to the rgain3 program `collectiongain` but it"
        " decides which files to group as an album in a different way, and will not"
        " operate recursively by default."
        "\n\n"
        "To ensure optimum operation, use the program scanalbumartists prior to"
        " running this program, to ensure all your album artist tags are consistent.",
    )
    p.add_argument("FILE", type=str, nargs="+", help="file to operate on")
    p.add_argument(
        "--show",
        action="store_true",
        help="only show the ReplayGain information for files",
    )
    p.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="if folders are specified, operate recursively",
    )
    p.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="do not actually modify files",
    )
    p.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="force recalculation even if files already contain that information",
    )
    p.add_argument(
        "-p",
        "--parallelism",
        type=int,
        help="how many replaygain processes to run at once (default %(default)s)",
        default=os.cpu_count(),
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose operation",
    )

    args = p.parse_args()
    basicConfig(
        main_module_name=__name__, level=logging.DEBUG if args.verbose else logging.INFO
    )

    allfiles = all_files(args.FILE, recursive=args.recursive)

    with OnDiskMetadataCache(
        "doreplaygain.pickle",
        CACHE_VERSION,
        lambda: FileMetadataCache(AlbumIdentifier.from_file),
    ) as tags:
        tags.update_metadata_for(allfiles)

        album_files: dict[str, list[str]] = collections.defaultdict(list)

        for f in allfiles:
            id_ = tags.get(f)
            if not id_ or not id_.valid:
                continue
            album_files[id_.identifier].append(f)

        ret = 0

        if args.show:
            if not album_files:
                sys.exit(0)
            for album, files in album_files.items():
                if album is None:
                    _LOGGER.info(f"* For singles {album}:")
                else:
                    _LOGGER.info(f"* For album {album}:")
                r = subprocess.call(["replaygain", "--show"] + files)
                if r != 0:
                    ret = r
            sys.exit(0)

        t = concurrent.futures.ThreadPoolExecutor(max_workers=args.parallelism)
        future_to_result = {}

        for album, filegroup in album_files.items():
            if not album:
                batches = [[x] for x in filegroup]
            else:
                batches = [filegroup]
            for batch in batches:
                process = False
                noalbum = not album or len(batch) < 2
                need_trackgain = [x for x in batch if tags[x].trackgain is None]
                __ = {}
                if noalbum:
                    # If the file in the batch and has RG, ignore the batch
                    # unless explicitly instructed not to.
                    if need_trackgain or args.force:
                        _LOGGER.info(
                            "Processing %s files — %s%s",
                            len(batch),
                            "one or more need track gain"
                            if need_trackgain
                            else "forced"
                            if args.force
                            else "?",
                            " (dry-run)" if args.dry_run else "",
                        )
                        for f in need_trackgain:
                            _LOGGER.debug("* Track gain missing: %s", f)
                            __[f] = True
                        for f in [x for x in batch if x not in __]:
                            _LOGGER.debug("* Other in batch:     %s", f)
                        process = True
                else:
                    need_albumgain = [x for x in batch if tags[x].albumgain is None]
                    # If all of the files file in the batch have equal album RG
                    # ignore the batch unless explicitly instructed not to.
                    mismatched_albumgains = any(
                        z != w
                        for z, w in itertools.pairwise(tags[x].albumgain for x in batch)
                    )
                    if (
                        mismatched_albumgains
                        or need_albumgain
                        or need_trackgain
                        or args.force
                    ):
                        _LOGGER.info(
                            "Processing %s files — %s%s",
                            len(batch),
                            "mismatch in album gain"
                            if mismatched_albumgains
                            else "one or more need album gain"
                            if need_albumgain
                            else "one or more need track gain"
                            if need_trackgain
                            else "forced"
                            if args.force
                            else "?",
                            " (dry-run)" if args.dry_run else "",
                        )
                        for f in need_albumgain:
                            _LOGGER.debug("* Album gain missing: %s", f)
                            __[f] = True
                        for f in [x for x in need_trackgain if x not in __]:
                            _LOGGER.debug("* Track gain missing: %s", f)
                            __[f] = True
                        for f in [x for x in batch if x not in __]:
                            _LOGGER.debug("* Other in batch:     %s", f)
                        process = True
                if not process:
                    continue
                future_to_result[
                    t.submit(
                        subprocess.call,
                        ["replaygain"]
                        + (["--dry-run"] if args.dry_run else [])
                        + ["--force"]
                        + (["--no-album"] if noalbum else [])
                        + batch,
                    )
                ] = batch

        try:
            for future in concurrent.futures.as_completed(future_to_result):
                batch = future_to_result[future]
                ret = future.result()
                if ret == 0:
                    tags.update_metadata_for(batch)
                else:
                    _LOGGER.error("Batch %s failed", batch)
                    for future in future_to_result:
                        future.cancel()
                    break
        except BaseException:
            for future in future_to_result:
                future.cancel()
            raise

    sys.exit(ret)
