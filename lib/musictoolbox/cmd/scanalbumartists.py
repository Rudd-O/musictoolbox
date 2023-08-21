import argparse
import io
import collections
import itertools
import logging
import pickle
import collections.abc
import os
import sys
import typing
import xdg.BaseDirectory
import fcntl
import contextlib
from musictoolbox.logging import basicConfig

from mutagen import File

_LOGGER = logging.getLogger(__name__)

KEY_ALBUM = "album"
KEY_ALBUMARTIST = "albumartist"
KEY_ARTIST = "artist"

# ======= mp3gain and soundcheck operations ==========


T = typing.TypeVar("T", bound="TrackMetadata")


class TrackMetadata(object):
    album: list[str] | None
    artist: list[str] | None
    albumartist: list[str] | None
    modtime: float

    def __init__(
        self,
        valid: bool,
        album: list[str],
        artist: list[str],
        albumartist: list[str],
    ) -> None:
        self.valid = valid
        self.album = album
        self.albumartist = albumartist
        self.artist = artist

    @classmethod
    def from_file(klass: typing.Type[T], ff: str) -> T:
        try:
            from_disk_metadata = File(ff, easy=True)
        except Exception as exc:
            _LOGGER.error("Error identifying %s: %s:", ff, exc)
            from_disk_metadata = None
        if from_disk_metadata is None:
            return klass(False, [], [], [])
        return klass(
            True,
            album=from_disk_metadata.get(KEY_ALBUM),
            artist=from_disk_metadata.get(KEY_ARTIST),
            albumartist=from_disk_metadata.get(KEY_ALBUMARTIST),
        )


C = typing.TypeVar("C")


class FileMetadataCache(typing.Generic[C]):
    def __init__(self, cache_item_factory: collections.abc.Callable[[str], C]) -> None:
        self.__factory = cache_item_factory
        self.__store: dict[str, tuple[float, C]] = {}
        self.__dirty = False

    def update_metadata_for(self, allfiles: list[str]) -> None:
        dirty = False
        for ff in allfiles:
            ff = os.path.abspath(ff)
            try:
                modtime = os.stat(ff).st_mtime
            except Exception as exc:
                _LOGGER.error("Error examining %s: %s", ff, exc)
                continue
            if ff in self.__store and self.__store[ff][0] >= modtime:
                if _LOGGER.level <= logging.DEBUG:
                    _LOGGER.debug("No need to update cache for file %s", ff)
                continue
            if _LOGGER.level <= logging.DEBUG:
                _LOGGER.debug("Updated cache for file %s at mod time %s", ff, modtime)
            metadata = self.__factory(ff)
            self.__store[ff] = (modtime, metadata)
            dirty = True
        self.__dirty = dirty

    def __getitem__(self, key: str) -> C:
        key = os.path.abspath(key)
        return self.__store[key][1]

    def has_key(self, key: str) -> bool:
        key = os.path.abspath(key)
        return key in self.__store

    def get(self, key: str) -> C | None:
        key = os.path.abspath(key)
        m = self.__store.get(key)
        if m is None:
            return None
        return m[1]

    def mark_clean(self) -> None:
        self.__dirty = False

    def is_dirty(self) -> bool:
        return self.__dirty


@contextlib.contextmanager
def cached_metadata() -> typing.Generator[FileMetadataCache[TrackMetadata], None, None]:
    f: io.BufferedReader | None = None
    p = xdg.BaseDirectory.save_cache_path("musictoolbox")
    path = os.path.join(p, "scanalbumartists.pickle")

    metadata = FileMetadataCache(TrackMetadata.from_file)
    fsize = 0
    try:
        if _LOGGER.level <= logging.DEBUG:
            _LOGGER.debug("Loading cache from %s", path)
        f = open(path, "a+b")
        fcntl.flock(f, fcntl.LOCK_EX)
        fsize = os.stat(path).st_size
        f.seek(0, 0)
    except Exception as exc:
        if not isinstance(exc, FileNotFoundError):
            _LOGGER.error("Error opening cache from %s: %s", path, exc)

    if f and fsize:
        try:
            metadata = typing.cast(FileMetadataCache[TrackMetadata], pickle.load(f))
        except Exception as exc:
            _LOGGER.error("Error opening cache from %s: %s", path, exc)

    yield metadata

    if f and metadata.is_dirty():
        metadata.mark_clean()
        if _LOGGER.level <= logging.DEBUG:
            _LOGGER.debug("Saving cache to %s", path)
        f.seek(0, 0)
        f.truncate()
        pickle.dump(metadata, f)
        f.flush()
        f.close()


def main() -> int:
    p = argparse.ArgumentParser(
        description="Determine which albums exist and if they are properly tagged."
    )
    p.add_argument("FILE", type=str, nargs="+", help="file to operate on")
    p.add_argument(
        "-f",
        "--fix",
        action="store_true",
        help="add a various artists album artist tag to files that need it",
    )
    p.add_argument(
        "-t",
        "--various-artists-tag",
        help="content of the various artists album artist tag;"
        " if this is set to auto, then the album artist is deduced"
        " from the most popular artist among the album",
        default="Various artists",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose operation",
    )
    args = p.parse_args()

    basicConfig(
        main_module_name=__name__,
        level=(logging.DEBUG if args.verbose else logging.INFO),
    )

    allfiles: list[str] = []
    for f in args.FILE:
        if os.path.isdir(f):
            files = [os.path.join(root, x) for root, _, fs in os.walk(f) for x in fs]
        else:
            files = [f]
        allfiles.extend(files)

    with cached_metadata() as tags:
        tags.update_metadata_for(allfiles)

        album_tree: dict[
            str, dict[str | None, dict[str | None, dict[str | None, list[str]]]]
        ] = collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(lambda: collections.defaultdict(list))
            )
        )

        for fn in allfiles:
            tag = tags.get(fn)
            if not tag:
                continue

            folder = os.path.dirname(fn)
            album = tag.album[0] if tag.album else None
            if not album:
                continue
            artist = tag.artist[0] if tag.artist else None
            albumartist = tag.albumartist[0] if tag.albumartist else None
            try:
                album_tree[folder][album][albumartist][artist].append(fn)
            except Exception:
                assert 0, (folder, album, albumartist, artist, fn)

        for folder, data in sorted(album_tree.items()):
            for album, albumartists_data in data.items():
                problems = []
                if None in albumartists_data and len(albumartists_data[None]) > 1:
                    problems.append(
                        "This album has more than one artist but no album artist"
                    )
                if len(albumartists_data) > 1:
                    problems.append("This album has more than one album artist")
                if problems:
                    print(f"{folder}:")
                    print(f"  {album}:")
                    for problem in problems:
                        print(f"    {problem}")
                    files_to_fix = [
                        f
                        for _, artistdata in albumartists_data.items()
                        for _, artist_files in artistdata.items()
                        for f in artist_files
                    ]

                    def dumpfiles(header: str) -> None:
                        print(f"    {header}:")
                        for f in files_to_fix:
                            print(f"      {f}")

                    va_text = args.various_artists_tag
                    if va_text == "auto":
                        artists = [
                            "" if a is None else a
                            for _, artistdata in albumartists_data.items()
                            for a, artist_files in artistdata.items()
                            for _ in artist_files
                        ]
                        popular_artists = sorted(
                            [
                                (x, len(list(y)))
                                for x, y in itertools.groupby(sorted(artists))
                            ],
                            key=lambda g: -g[1],
                        )
                        va_text = popular_artists[0][0]
                        if (
                            len(popular_artists) > 1
                            and popular_artists[0][1] == popular_artists[1][1]
                        ):
                            va_text = None
                    if va_text is None:
                        dumpfiles("Cannot determine album artist, skipping these files")
                        continue

                    if args.fix:
                        print(
                            f"    Adding album artist {va_text} among {popular_artists}"
                        )
                        for f in files_to_fix:
                            savetag = File(f, easy=True)
                            savetag[KEY_ALBUMARTIST] = [va_text]
                            savetag.save()
                        dumpfiles("Files fixed")
                    else:
                        dumpfiles("Files to fix")
                        print(
                            f"    Would add the album artist {va_text}"
                            f" among {popular_artists}"
                        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
