import sys
import os
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from musictoolbox.synccore import Synchronizer
from musictoolbox.transcoders import ConfigurableTranscoder as the_transcoder
import logging
import textwrap


logger = logging.getLogger(__name__)

class SynchronizationCLIBackend:
    def __init__(self,
                 transcoder,
                 destpath,
                 playlists,
                 dryrun,
                 concurrency,
                 delete,
                 exclude_beneath):
        self.synchronizer = Synchronizer(transcoder)
        self.synchronizer.set_target_dir(destpath)
        self.synchronizer.set_exclude_beneath(exclude_beneath or [])
        [ self.synchronizer.add_playlist(p) for p in playlists ]
        self.dryrun = dryrun
        self.concurrency = concurrency
        self.delete = delete

    def run(self):
        """Returns:

        0 if all transcoding / synchronization operations completed.
        2 if scanning experienced a problem.
        4 if a transcoding / synchronization failure took place.
        8 if a problem took place while writing playlists.
        Or a combination of the above.

        Raises Exception in an unexpected failure took place.
        """
        exitval = 0
        failures = self.synchronizer.scan()
        if failures:
            print >> sys.stderr, "Problems encountered during scanning:\n"
            for s, t in failures:
                print >> sys.stderr, \
                    "Could not scan: %r\nBecause: %r\n" % (s, t)
            print >> sys.stderr
            exitval += 2

        if self.dryrun:
            ops, errors, _, deleting = self.synchronizer.compute_synchronization()
            for s, t in ops.items():
                print "Source: %r\nTarget: %r\n" % (s, t)
            for s, t in errors.items():
                print "Not transferring: %r\nBecause: %r\n" % (s, t)
            if self.delete:
                for t in deleting:
                    print "Deleting: %r\n" % (t,)
            written_playlists, playlist_failures = self.synchronizer.synchronize_playlists(dryrun=True)
            for w in written_playlists:
                print "Would write target playlist %r\n" % w
            for s, t in playlist_failures:
                print >> sys.stderr, \
                    "Could not write: %r\nBecause: %r\n" % (s, t)

            if errors:
                exitval += 8
            if playlist_failures:
                exitval += 8

            return exitval

        sync_tasks = self.synchronizer.synchronize(concurrency=self.concurrency)
        errors = None
        for s, t in sync_tasks:
            if isinstance(t, Exception):
                print >> sys.stderr, \
                    "Not synced: %r\nBecause: %s\n" % (s, t)
                errors = True
            else:
                print >> sys.stderr, \
                    "Synced: %r\nTarget: %r\n" % (s, t)
        if errors:
            exitval += 4

        written_playlists, playlist_failures = self.synchronizer.synchronize_playlists()
        for p in written_playlists:
            print >> sys.stderr, \
                "Written: %r\n" % (p, )
        if playlist_failures:
            print >> sys.stderr, "Problems while writing playlists:\n"
            for s, t in playlist_failures:
                print >> sys.stderr, \
                    "Could not write: %r\nBecause: %r\n" % (s, t)
            print >> sys.stderr
            exitval += 8

        if self.delete:
            deletion_failures = self.synchronizer.synchronize_deletions()
            if deletion_failures:
                print >> sys.stderr, "Problems while deleting files:\n"
                for s, t in deletion_failures:
                    print >> sys.stderr, \
                        "Could not delete: %r\nBecause: %r\n" % (s, t)
                print >> sys.stderr
                exitval += 8

        return exitval


def run_sync(dryrun, destpath, playlists, concurrency, delete, exclude_beneath):
    """Runs sync process.  Returns what SynchronizatoinCLIBackend.run() does."""
    transcoder = the_transcoder()
    w = SynchronizationCLIBackend(transcoder,
                                  destpath,
                                  playlists,
                                  dryrun,
                                  concurrency,
                                  delete,
                                  exclude_beneath)
    return w.run()


# cmd line stuff

def get_parser():
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = "Synchronizes music to a directory."
    program_shortdesc += "\n\n" + textwrap.dedent("""
This program takes a number of file lists / playlists in the command line,
and a destination directory, then synchronizes all the songs in the playlists
to the destination directory, with optional modifications to the files and their
names as they are copied to the destination directory, for example preserving
the path structure except for changing characters incompatible with VFAT
volumes to underscores.

For example, suppose you have two playlists `a.m3u` and `b.m3u` (perhaps
generated with the companion `genplaylist` program) that contain the
respective following song lists:

1. /shared/Music/Ace of Base/Everytime it rains.mp3
2. /shared/Music/Scatman John/Scatman.mp3

1. /shared/Music/Dr. Alban/It's my life (12" mix).mp3

If you run `syncplaylists a.m3u b.m3u "/mounteddrive/Travel Music"`, the
resulting directory structure in `/mounteddrive/Travel Music` will look
like this:

1. /mounteddrive/Travel Music/Ace of Base/Everytime it rains.mp3
2. /mounteddrive/Travel Music/Scatman John/Scatman.mp3
3. /mounteddrive/Travel Music/Music/Dr. Alban/It's my life (12_ mix).mp3
4. /mounteddrive/Travel Music/Playlists/a.m3u
5. /mounteddrive/Travel Music/Playlists/b.m3u

with the paths in the brand new playlists `a.m3u` and `b.m3u` transmuted
so that the song paths are relative to the location of the playlists.  This way
your media player can automatically use the playlists you specified to play
music for you.

`syncplaylists` also has the ability to transcode the files to the preferred
formats of your target device as well.  `syncplaylists will read an INI file
named `~/.syncplaylists.ini` to determine how to transcode.  For example,
if you wanted to transcode all non-MP3 files to MP3, you could add the
following configuration to the file:

    [transcoding]
    mp3=copy
    *=mp3

and then `syncplaylists` will do a best-effort attempt to transcode the files
in your playlists to MP3, except for the MP3 files themselves which would just
get copied as per the `copy` action specified in the configuration file.
    """).strip()

    parser = ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument("-n", "--dry-run", dest="dryrun", action="store_true", help="do nothing except show what will happen [default: %(default)s]")
    parser.add_argument("-d", "--delete", dest="delete", action="store_true", help="remove all files that are not mentioned in the playlists [default: %(default)s]")
    parser.add_argument("-e", "--exclude", dest="exclude", action="append", help="ignore all files underneath these paths or that match the specific path [default: %(default)s]")
    parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
    parser.add_argument("-c", "--concurrency", metavar="NUMPROCS", dest="concurrency", type=int, default=4, help="number of concurrent processes to run [default: %(default)s]")
    parser.add_argument(dest="playlists", help="paths to M3U playlists to synchronize", metavar="playlist", nargs='+')
    parser.add_argument(dest="destpath", help="destination directory", metavar="dir")
    return parser


def main(argv=None):
    '''Command line options.'''

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    parser = get_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.WARNING)

    return run_sync(
        dryrun=args.dryrun,
        playlists=args.playlists,
        concurrency=args.concurrency,
        destpath=args.destpath,
        delete=args.delete,
        exclude_beneath=args.exclude,
    )


if __name__ == "__main__":
    sys.exit(main())
