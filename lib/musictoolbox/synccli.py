import sys
import os
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
from musictoolbox.synccore import Synchronizer
from musictoolbox.transcoders import ConfigurableTranscoder as the_transcoder
import logging


logger = logging.getLogger(__name__)

class SynchronizationCLIBackend:
    def __init__(self,
                 transcoder,
                 destpath,
                 playlists,
                 dryrun,
                 concurrency):
        self.synchronizer = Synchronizer(transcoder)
        self.synchronizer.set_target_dir(destpath)
        [ self.synchronizer.add_playlist(p) for p in playlists ]
        self.dryrun = dryrun
        self.concurrency = concurrency

    def run(self):
        """Returns:

        0 if all transcoding / synchronization operations completed.
        4 if a transcoding / synchronization failure took place.
        8 if a problem took place while writing playlists.
        Or a combination of the above.

        Raises Exception in an unexpected failure took place.
        """
        failures = self.synchronizer.scan()
        if failures:
            print >> sys.stderr, "Problems encountered during scanning:\n"
            for s, t in failures:
                print >> sys.stderr, \
                    "Could not scan: %r\nBecause: %r\n" % (s, t)
            print >> sys.stderr

        if self.dryrun:
            ops, errors = self.synchronizer.compute_synchronization()
            for s, t in ops.items():
                print "Source: %r\nTarget: %r\n" % (s, t)
            for s, t in errors.items():
                print "Not transferring: %r\nBecause: %r\n" % (s, t)
            if errors:
                return 8
            return 0

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

        playlist_failures = self.synchronizer.synchronize_playlists()
        if playlist_failures:
            print >> sys.stderr, "Problems while writing playlists:\n"
            for s, t in playlist_failures:
                print >> sys.stderr, \
                    "Could not write: %r\nBecause: %r\n" % (s, t)
            print >> sys.stderr

        exitval = 0
        if errors:
            exitval += 4
        if playlist_failures:
            exitval += 8
        return exitval


def run_sync(dryrun, destpath, playlists, concurrency):
    """Runs sync process.  Returns what SynchronizatoinCLIBackend.run() does."""
    transcoder = the_transcoder()
    w = SynchronizationCLIBackend(transcoder,
                                  destpath,
                                  playlists,
                                  dryrun,
                                  concurrency)
    return w.run()


# cmd line stuff

def get_parser():
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = "Synchronizes music to a directory"

    parser = ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=RawDescriptionHelpFormatter
    )
    parser.add_argument("-n", "--dry-run", dest="dryrun", action="store_true", help="do nothing except show what will happen [default: %(default)s]")
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
        destpath=args.destpath
    )


if __name__ == "__main__":
    sys.exit(main())

# FIXME: handle ctrl-c interrupts properly

