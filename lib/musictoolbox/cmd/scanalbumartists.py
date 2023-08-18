import argparse
import collections
import itertools
import logging
import os
import sys
import typing
from musictoolbox.logging import basicConfig

from mutagen import File

_LOGGER = logging.getLogger(__name__)

KEY_ALBUM = "album"
KEY_ALBUMARTIST = "albumartist"
KEY_ARTIST = "artist"

# ======= mp3gain and soundcheck operations ==========


def main() -> int:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
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
        help="content of the various artists album artist tag",
        default="Various artists",
    )
    args = p.parse_args()

    allfiles: list[str] = []
    for f in args.FILE:
        if os.path.isdir(f):
            files = [os.path.join(root, x) for root, _, fs in os.walk(f) for x in fs]
        else:
            files = [f]
        allfiles.extend(files)

    tags: dict[str, typing.Any] = {}
    for ff in allfiles:
        try:
            metadata = File(ff, easy=True)
        except Exception as exc:
            print(f"Error identifying {ff}: {exc}", file=sys.stderr)
            continue
        if metadata is None:
            continue
        tags[ff] = metadata

    album_tree: dict[
        str, dict[str | None, dict[str | None, dict[str | None, list[str]]]]
    ] = collections.defaultdict(
        lambda: collections.defaultdict(
            lambda: collections.defaultdict(lambda: collections.defaultdict(list))
        )
    )

    for fn, tag in tags.items():
        folder = os.path.dirname(fn)
        album = tag.get(KEY_ALBUM)
        artist = tag.get(KEY_ARTIST)
        albumartist = tag.get(KEY_ALBUMARTIST)
        if not album:
            continue
        if album:
            album = album[0]
        if artist:
            artist = artist[0]
        if albumartist:
            albumartist = albumartist[0]
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

                if args.fix:
                    va_text = args.various_artists_tag
                    for f in files_to_fix:
                        tag = tags[f]
                        tag[KEY_ALBUMARTIST] = [va_text]
                        tag.save()
                    dumpfiles("Files fixed")
                else:
                    dumpfiles("Files to fix")

            # for albumartist, artistdata in albumartists_data.items():
            #    print(f"    {albumartist}:")
            #    for artist, files in artistdata.items():
            #        print(f"      {artist}:")
            #        for f in files:
            #            print(f"        {f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
