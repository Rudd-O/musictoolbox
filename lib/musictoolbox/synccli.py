# twisted new devel
#
# split the synchronizer spinning off some of its functionality
# i need a source thingie that allows me to scan sources
# i need a target thingie that allows me to scan
# targets
#
# then the synchronizer can do the twisted part, by scanning the sources and adding deferreds to trigger the events, in a two-step process, prepare(scan all) and then synchronize.  and that way
# only the synchronizer needs to depend on the
# twisted part.
#
# it might also be a good idea to add, for lack of a
# better name, a synchronizer user interface that
# can be plugged using composition into the synchronizer, such that the synchronizer can
# invoke callbacks on that user interface at appropriate times, decoupling all that nonsense
# out of the synchronizer class itself
#
# it still remains to be seen how to provide proper
# granularity for progress reports, without adding dependencies on twisted into these scanners, given that the scan / prepare part and the synchronization part both are unfortunately long-running,  ultimately i want a progressbar for scanning and for transcoding, without embedding twisted code in the scanners or the ui

import sys
import os
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
import glob
from functools import partial
from twisted.internet.defer import Deferred
from twisted.internet.defer import DeferredList
from twisted.internet import reactor
from musictoolbox.synccore import Synchronizer
from musictoolbox.synccore import assert_deferredlist_succeeded
from musictoolbox.transcoders import ConfigurableTranscoder as the_transcoder
import logging


class SynchronizationCLIBackend:
    def __init__(self, s, verbose):
        self.synchronizer = s
        self.verbose = verbose
        self.failures = []

    def scan(self):
        if self.verbose:
            print >> sys.stderr, "Starting scan"

        def on_parse_playlists_done(count):
            def on_scan_source_files_mtimes_done(count):
                if self.verbose:
                    print >> sys.stderr, \
                        "Scanning %s source files mtimes done" % len(count)
            def on_scan_source_files_mtimes_failed(failure):
                print >> sys.stderr, \
                    "Failed to scan source files: %s" % f.value
                self.failures.append(failure)

            if self.verbose:
                print >> sys.stderr, \
                    "Parsing playlists discovered %s source files" % len(count)
            dm = self.synchronizer.scan_source_files_mtimes()
            dm.addCallback(on_scan_source_files_mtimes_done)
            dm.addErrback(on_scan_source_files_mtimes_failed)
            return dm

        def on_parse_playlists_failed(f):
            print >> sys.stderr, \
                "Parsing playlists failed: %s" % f.value
            self.failures.append(f)

        d1 = self.synchronizer.parse_playlists()
        d1.addCallback(on_parse_playlists_done)
        d1.addErrback(on_parse_playlists_failed)

        def on_scan_target_dir_done(p):
            def on_scan_target_dir_mtimes_done(p):
                if self.verbose:
                    print >> sys.stderr, \
                        "Scanning %s target files mtimes done" % len(p)
            def on_scan_target_dir_mtimes_failed(f):
                print >> sys.stderr, \
                    "Scanning target files mtimes failed: %s" % f.value
                self.failures.append(f)

            if self.verbose:
                print >> sys.stderr, "Scanning %s target files done" % len(p)
            dt = self.synchronizer.scan_target_dir_mtimes()
            dt.addCallback(on_scan_target_dir_mtimes_done)
            dt.addErrback(on_scan_target_dir_mtimes_failed)
            return dt

        def on_scan_target_dir_failed(f):
            print >> sys.stderr, \
                "Scanning target directory failed: %s" % f.value
            self.failures.append(f)

        d2 = self.synchronizer.scan_target_dir()
        d2.addCallback(on_scan_target_dir_done)
        d2.addErrback(on_scan_target_dir_failed)

        return DeferredList([d1, d2])

    def preview_synchronization(self):
        if self.verbose:
            print >> sys.stderr, "Computing synchronization"
        ops, errors = self.synchronizer.compute_synchronization()
        for s, t in ops.items():
            print "Source: %r\nTarget: %r\n" % (s, t)
        for s, t in errors.items():
            print "Not transferring: %r\nBecause: %r\n" % (s, t)

    def synchronize(self):
        if self.verbose:
            print >> sys.stderr, "Synchronizing"
        sync_tasks = self.synchronizer.synchronize()
        for s, t in sync_tasks.items():
            t.addCallback(partial(self.sync_task_done, s))
            t.addErrback(partial(self.sync_task_failed, s))
        return DeferredList(sync_tasks.values())

    def sync_task_done(self, src, dst):
        print >> sys.stderr, "Synced: %r\nTarget: %r\n" % (src, dst)

    def sync_task_failed(self, src, failure):
        print >> sys.stderr, "Not synced: %r\nBecause: %s\n" % (src, failure)

    def synchronize_playlists(self):
        '''this method blocks'''
        self.synchronizer.synchronize_playlists()


def run_sync(verbose, dryrun, destpath, playlists):
    failures = []

    t = the_transcoder()
    k = Synchronizer(t)
    k.set_target_dir(destpath)
    [ k.add_playlist(p) for p in playlists ]

    w = SynchronizationCLIBackend(k, verbose=verbose)

    def scan_finished(possible_failures):
        failures.extend([ s[1] for s in possible_failures if not s[0] ])
        failures.extend(w.failures)
        if failures:
            print >> sys.stderr, "Scan failed"
            end()
        elif verbose:
            print >> sys.stderr, "Scan finished"
        if dryrun:
            w.preview_synchronization()
            end()
        else:
            sync = w.synchronize()
            sync.addCallback(sync_finished)

    def sync_finished(possible_failures):
        failures.extend([ s[1] for s in possible_failures if not s[0] ])
        if failures:
            print >> sys.stderr, "Sync failed"
        elif verbose:
            print >> sys.stderr, "Sync finished"
        try:
            w.synchronize_playlists()
            if verbose:
                print >> sys.stderr, "Playlist generation finished"
        except Exception, e:
            print >> sys.stderr, "Playlist generation failed"
            failures.append(e)
        end()

    def end():
        reactor.stop()

    def start():
        scan = w.scan()
        scan.addCallback(scan_finished)

    reactor.callLater(0, start)
    reactor.run()

    return failures if failures else None

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
    parser.add_argument(dest="playlists", help="paths to M3U playlists to synchronize", metavar="playlist", nargs='+')
    parser.add_argument(dest="destpath", help="destination directory", metavar="dir")
    return parser


def main(argv=None):
    '''Command line options.'''

    logging.basicConfig(level=logging.WARNING)

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    parser = get_parser()
    args = parser.parse_args()

    failures = run_sync(verbose=args.verbose,
             dryrun=args.dryrun,
             playlists=args.playlists,
             destpath=args.destpath)

    if failures:
        for failure in failures:
            print >> sys.stderr, failure
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())

# FIXME: handle ctrl-c interrupts properly

