from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
import logging
import os
import sys
import textwrap
import typing

from ..tagging import transfer_tags  # type: ignore

from ..files import Absolutize
from ..logging import basicConfig
from ..transcoding import config, policies, registry
from ..transcoding.interfaces import Postprocessor
from ..transcoding.transcoder import TranscodingMapper
from .core import Synchronizer


logger = logging.getLogger(__name__)


class SynchronizationCLI:

    debug = False

    def __init__(
        self,
        destpath: str,
        playlists: typing.List[str],
        dryrun: bool,
        concurrency: int,
        delete: bool,
        exclude_beneath: typing.List[str],
        transcoding_mapper: TranscodingMapper,
        postprocessor: Postprocessor,
        force_vfat: bool,
    ) -> None:
        self.synchronizer = Synchronizer(
            [Absolutize(p) for p in playlists],
            Absolutize(destpath),
            transcoding_mapper,
            [Absolutize(p) for p in exclude_beneath],
            postprocessor,
            force_vfat,
        )
        self.dryrun = dryrun
        self.delete = delete
        self.concurrency = concurrency

    def run(self) -> int:
        """Returns:

        0 if all transcoding / synchronization operations completed.
        2 if scanning experienced a problem.
        4 if a transcoding / synchronization failure took place.
        8 if a problem took place while writing playlists.
        16 if a problem took place while removing files.
        Or a combination of the above.

        Raises Exception in an unexpected failure took place.

        If self.debug == True (see __init__), raises the exceptions
        that the transcoding / sync operations saw.
        """
        try:
            sync_plan = self.synchronizer.compute_synchronization()
        except Exception:
            logger.exception("Error scanning source material")
            return 2

        will_sync, cant_sync, already_synced, will_delete = sync_plan

        for src, dst in already_synced.items():
            logger.info("No need to sync %s — already synced to %s", src, dst)

        for src, dst, _ in will_sync:
            logger.info("Will sync %s to %s", src, dst)

        for src, ex in cant_sync.items():
            logger.info("Cannot sync %s: %s", src, ex)

        if self.delete:
            for fn in will_delete:
                logger.info("Will delete %s", fn)

        problems_syncing = False

        if not self.dryrun:
            q, cancel = self.synchronizer.synchronize(sync_plan, self.concurrency)
            try:
                while True:
                    r = q.get(block=True)
                    if r is None:
                        break
                    s, d, exc = r
                    if exc:
                        problems_syncing = True
                        logger.error("Could not sync file %s: %s", s, exc)
                    else:
                        logger.info("Synced file: %s -> %s", s, d)
            except KeyboardInterrupt:
                cancel()
                raise

        problems_playlisting = False

        for oldp, newp, exc in self.synchronizer.synchronize_playlists(
            sync_plan, self.dryrun
        ):
            if exc:
                problems_playlisting = True
                logger.error("Could not sync playlist %s: %s", newp, exc)
            else:
                if not self.dryrun:
                    logger.info("Synced playlist: %s -> %s", oldp, newp)

        problems_deleting = False

        if self.delete:
            for p, exc in self.synchronizer.synchronize_deletions(
                sync_plan, self.dryrun
            ):
                if exc:
                    problems_deleting = True
                    logger.error("Could not remove file %s: %s", p, exc)
                else:
                    if not self.dryrun:
                        logger.info("Removed file: %s", p)

        retval = 0
        if problems_syncing or cant_sync:
            retval += 4
        if problems_playlisting:
            retval += 8
        if problems_deleting:
            retval += 16
        return retval


def get_parser() -> ArgumentParser:
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = "Synchronizes music to a directory."
    program_shortdesc += (
        "\n\n"
        + textwrap.dedent(
            """
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
    """
        ).strip()
    )

    parser = ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        dest="dryrun",
        action="store_true",
        help="do nothing except show what will happen [default: %(default)s]",
    )
    parser.add_argument(
        "-d",
        "--delete",
        dest="delete",
        action="store_true",
        help="remove all files that are not mentioned in the playlists [default: %(default)s]",
    )
    parser.add_argument(
        "-D",
        "--debug",
        dest="debug",
        action="store_true",
        help="raise exceptions instead of reporting them in a succinct manner [default: %(default)s]",
    )
    parser.add_argument(
        "-e",
        "--exclude",
        dest="exclude",
        action="append",
        default=[],
        help="ignore all files underneath these folders [default: %(default)s]",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="count",
        help="set verbosity level [default: %(default)s]",
    )
    parser.add_argument(
        "-V",
        "--force-vfat",
        dest="force_vfat",
        action="store_true",
        default=False,
        help="assume that the destination folder is stored on a FAT file system, and perform the path name conversions appropriate for the case -- useful to sync files to Android devices or other typical music players [default is to autodetect based on the destination mount point]",
    )
    parser.add_argument(
        "--concurrency",
        metavar="NUMPROCS",
        dest="concurrency",
        type=int,
        default=-1,
        help="number of concurrent processes to run [default: automatic]",
    )
    parser.add_argument(
        dest="playlists",
        help="paths to M3U playlists to synchronize",
        metavar="playlist",
        nargs="+",
    )
    parser.add_argument(
        "-c",
        "--config-file",
        help="path to a configuration file with transcoding policies and settings; highest precedence config will be loaded from %s"
        % config.transcoding_config_default_path(),
        type=str,
        default=None,
    )
    parser.add_argument(
        "-p",
        "--profile-file",
        help="path to a file where cProfile output will be stored",
        type=str,
        default=None,
    )
    parser.add_argument(dest="destpath", help="destination directory", metavar="dir")
    return parser


def run_sync(
    dryrun: bool,
    destpath: str,
    playlists: typing.List[str],
    concurrency: int,
    delete: bool,
    exclude_beneath: typing.List[str],
    configfile: typing.Optional[str] = None,
    profilefile: typing.Optional[str] = None,
    force_vfat: typing.Optional[bool] = False,
) -> int:
    """Runs sync process.  Returns what SynchronizationCLIBackend.run() does."""
    cfg = config.load_transcoding_config(configfile)
    reg = registry.TranscoderRegistry(cfg.settings)
    sel = policies.PolicyBasedPipelineSelector(cfg.policies, allow_fallback=False)
    tm = TranscodingMapper(reg, sel)
    pp = transfer_tags

    def w() -> int:
        return SynchronizationCLI(
            destpath,
            playlists,
            dryrun,
            concurrency,
            delete,
            exclude_beneath,
            tm,
            pp,
            force_vfat or False,
        ).run()

    if profilefile:
        import cProfile

        cProfile.runctx("w()", {}, locals(), filename=profilefile)
        return 0

    ret: int = w()
    return ret


def main(argv: typing.Optional[typing.List[str]] = None) -> None:
    """Command line options."""

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    parser = get_parser()
    args = parser.parse_args()

    if args.debug:
        level = logging.DEBUG
    elif args.verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    basicConfig(__name__, level)

    sys.exit(
        run_sync(
            dryrun=args.dryrun,
            playlists=args.playlists or [],
            concurrency=args.concurrency,
            destpath=args.destpath,
            delete=args.delete,
            exclude_beneath=args.exclude or [],
            configfile=args.config_file,
            profilefile=args.profile_file,
            force_vfat=args.force_vfat,
        )
    )


if __name__ == "__main__":
    main()
