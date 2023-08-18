import argparse
import logging
import mutagen  # type:ignore
import os
import subprocess

from musictoolbox.logging import basicConfig


def main() -> int:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    p = argparse.ArgumentParser(
        description="Frontend for replaygain (of python-rgain3 fame).  This program"
        " helps you add ReplayGain information to music in an intelligent fashion,"
        " grouping songs by album so album ReplayGain information is calculated"
        " correctly with respect to all other tracks in the album."
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

    args = p.parse_args()

    allfiles = []
    for f in args.FILE:
        if os.path.isdir(f):
            if args.recursive:
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

    files_album: dict[str, str | None] = {}
    for ff in allfiles:
        metadata = mutagen.File(ff, easy=True)
        if metadata is None:
            continue
        try:
            album = metadata.get("album", [None])[0]
        except IndexError:
            album = None
        files_album[ff] = album.lower() if album else None

    album_files: dict[str | None, list[str]] = {}
    for f, alb in files_album.items():
        if alb not in album_files:
            album_files[alb] = []
        album_files[alb].append(f)

    if args.show:
        return subprocess.call(["replaygain", "--show"] + list(files_album.keys()))

    ret = 0
    for album, filegroup in album_files.items():
        if not album:
            batches = [[x] for x in filegroup]
        else:
            batches = [filegroup]
        for batch in batches:
            noalbum = not album or len(batch) < 2
            ret = subprocess.call(
                ["replaygain"]
                + (["--dry-run"] if args.dry_run else [])
                + (["--force"] if args.force else [])
                + (["--no-album"] if noalbum else [])
                + batch
            )
            if ret != 0:
                break

    return ret
