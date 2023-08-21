import argparse
import collections
import itertools
import logging
import collections.abc
import os
import sys
import typing
from musictoolbox.logging import basicConfig
from musictoolbox.cache import FileMetadataCache, OnDiskMetadataCache
from musictoolbox.files import all_files

from mutagen._file import File

_LOGGER = logging.getLogger(__name__)

KEY_ALBUM = "album"
KEY_ALBUMARTIST = "albumartist"
KEY_ARTIST = "artist"
CACHE_VERSION = 3

TM = typing.TypeVar("TM", bound="TrackMetadata")


class TrackMetadata(object):
    album: list[str] | None
    artist: list[str] | None
    albumartist: list[str] | None

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
    def from_file(klass: typing.Type[TM], ff: str) -> TM:
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


def main() -> None:
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

    allfiles = all_files(args.FILE, recursive=True)

    with OnDiskMetadataCache(
        "scanalbumartists.pickle",
        CACHE_VERSION,
        lambda: FileMetadataCache(TrackMetadata.from_file),
    ) as tags:
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
                        tags.update_metadata_for(files_to_fix)
                        dumpfiles("Files fixed")
                    else:
                        dumpfiles("Files to fix")
                        print(
                            f"    Would add the album artist {va_text}"
                            f" among {popular_artists}"
                        )

    sys.exit(0)


if __name__ == "__main__":
    main()
