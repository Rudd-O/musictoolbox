import argparse
import collections
import errno
import fnmatch
import os
import stat
import sys
import tempfile
import textwrap
import urllib.parse


def get_parser() -> argparse.ArgumentParser:
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = "Generates file lists / M3U playlists from a directory."
    program_shortdesc += (
        "\n\n"
        + textwrap.dedent(
            """
This program takes a number of paths in the command line, and a destination
file name, then saves the list of files within those paths to the destination
file, overwriting whatever was in the file previously.  Each path is only added
once to the destination file list / playlist.

The list of files in the file list / playlist created by `genplaylist` will
always be relative to the directory that contains the file list / playlist,
except for the case when a file has non-printable characters, in which case
a proper URL with the non-printable characters escaped will be saved to the
file list / playlist instead.

Only path entries that test positive for the `os.path.isfile()` test
(that means no special devices, no broken symlinks, no directories) will be
included in the output file list.  Unreadable files will be added, but
unlistable directories will be skipped without displaying any errors.
    """
        ).strip()
    )
    parser = argparse.ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--include",
        help="include only files matching this pattern; "
        "this option can be specified multiple times",
        metavar="pattern",
        action="append",
    )
    parser.add_argument(
        "-x",
        "--exclude",
        help="exclude files matching this pattern, as well as "
        "files within directories matching this pattern; "
        "this option can be specified multiple times",
        metavar="pattern",
        action="append",
    )
    parser.add_argument(
        dest="paths",
        help="paths to directories or files to list",
        metavar="path",
        nargs="+",
    )
    parser.add_argument(
        dest="playlist", help="destination playlist name", metavar="playlist"
    )
    return parser


def get_umask() -> int:
    umask = os.umask(0o77)
    os.umask(umask)
    return umask


class OutputWriter(object):
    """Writes to a regular file or a special file, varying its behavior
    depending on the type of file."""

    def __init__(self, filename: str) -> None:
        self.name = filename

        try:
            mode = os.stat(filename).st_mode
            if stat.S_ISBLK(mode) or stat.S_ISCHR(mode) or stat.S_ISFIFO(mode):
                self.fobject = open(filename, "w")
        except OSError:
            pass

        if not self.fobject:
            directory, prefix = os.path.split(filename)
            if not directory:
                directory = os.path.curdir
            if not prefix:
                raise OSError(
                    errno.EISDIR,
                    os.strerror(errno.EISDIR) + ": " + repr(filename),
                )
            t = tempfile.NamedTemporaryFile(
                mode="w+",
                prefix=prefix,
                dir=directory,
                delete=False,
            )
            t.close()
            self.fobject = open(t.name, "w")

    def write(self, text: str) -> None:
        self.fobject.write(text)

    def flush(self) -> None:
        self.fobject.flush()

    def close(self) -> None:
        try:
            if self.name != self.fobject.name:
                try:
                    oldmode = os.stat(self.name).st_mode
                    os.chmod(self.fobject.name, oldmode)
                except OSError as e:
                    if e.errno != errno.ENOENT:
                        raise
                    umask = get_umask()
                    newmode = ~umask & 0o666
                    os.chmod(self.fobject.name, newmode)
                os.rename(self.fobject.name, self.name)
        finally:
            try:
                self.fobject.close()
            except OSError as e:
                if e.errno != errno.ENOENT:
                    raise


def main() -> None:
    parser = get_parser()
    args = parser.parse_args()
    playlist = args.playlist
    excludes = args.exclude
    includes = args.include
    playlistdir = os.path.dirname(playlist)
    playlistfile = OutputWriter(playlist)
    playlistcontents = collections.OrderedDict()
    for path in args.paths:
        for basepath, dirs, files in os.walk(path, topdown=True):
            for d in dirs[:]:
                # Do not walk any directories that match exclusion patterns.
                if excludes and any(fnmatch.fnmatch(d, pat) for pat in excludes):
                    dirs.remove(d)
            for filename in files:
                # If includes were specified, do not include files that do
                # not match the inclusion patterns.
                if includes and not any(
                    fnmatch.fnmatch(filename, pat) for pat in includes
                ):
                    continue
                # Do not include any files that match exclusion patterns.
                if excludes and any(fnmatch.fnmatch(filename, pat) for pat in excludes):
                    continue
                joined = os.path.join(basepath, filename)
                if not os.path.isfile(joined):
                    continue
                if any(ord(x) < 32 for x in joined):
                    joined = os.path.abspath(joined)
                    p = "file://" + "".join(
                        x if x >= 32 and x < 128 else urllib.parse.quote(x)
                        for x in joined
                    )
                else:
                    p = os.path.relpath(joined, playlistdir)
                if p in playlistcontents:
                    continue
                playlistfile.write(p + "\n")
                playlistcontents[p] = True
    playlistfile.flush()
    playlistfile.close()

    sys.exit(0)
