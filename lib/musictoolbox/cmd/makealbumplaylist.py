import argparse
import glob
import logging
import os
import sys
import typing

import mutagen

from ..logging import basicConfig


def sort_by_track_number(paths: typing.List[str]) -> typing.List[str]:
    metadatas = [(f, mutagen.File(f)) for f in paths]
    relevant = []
    relevant.extend(
        [(int(m["tracknumber"][0]), f, m) for f, m in metadatas if "tracknumber" in m]
    )
    relevant.extend(
        [
            (int(m["TRCK"].text[0].split("/")[0]), f, m)
            for f, m in metadatas
            if "TRCK" in m
        ]
    )
    relevant.extend(
        [(99, f, m) for f, m in metadatas if f not in [b for _, b, __ in relevant]]
    )
    relevant = list(sorted(relevant))
    return [f for _, f, __ in relevant]


def make_album_playlist(
    playlistpath: str, paths: typing.List[str], dryrun: bool = False
) -> None:
    playlist_dir = os.path.dirname(playlistpath)
    files: typing.List[str] = []
    for p in paths:
        if os.path.isdir(p):
            for spec in ["*.mp3", "*.ogg", "*.mpc", "*.flac"]:
                files.extend(glob.iglob(os.path.join(p, spec)))
        else:
            files.append(p)
    sortedfiles = sort_by_track_number(files)
    relativefiles = [os.path.relpath(f, playlist_dir) for f in sortedfiles]
    if dryrun:
        playlist_fileobj = sys.stdout
    else:
        playlist_fileobj = open(playlistpath, "w")
    playlist_fileobj.write("\n".join(relativefiles))


def get_parser() -> argparse.ArgumentParser:
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = (
        "Creates a playlist from passed directories and files, sorted by track number"
    )

    parser = argparse.ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        dest="dryrun",
        action="store_true",
        help="do nothing except show what will happen [default: %(default)s]",
    )
    parser.add_argument(
        dest="paths", help="files and directories to include in playlist", nargs="+"
    )
    parser.add_argument(
        dest="playlist", help="path to an M3U playlist to write", nargs=1
    )
    return parser


def main() -> int:
    basicConfig(main_module_name=__name__, level=logging.WARNING)

    parser = get_parser()
    args = parser.parse_args()

    make_album_playlist(args.playlist[0], args.paths, dryrun=args.dryrun)
    return 0
