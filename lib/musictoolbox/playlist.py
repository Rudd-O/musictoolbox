import mutagen
import glob
import os
import sys
import logging
import argparse

def sort_by_track_number(paths):
    metadatas = [ (f,mutagen.File(f)) for f in paths ]
    relevant = [ (m["tracknumber"][0],f,m) for f,m in metadatas ]
    relevant = list(sorted(relevant))
    return [ f for x,f,w in relevant ]

def make_album_playlist(playlistpath, paths, dryrun=False):
    playlist_dir = os.path.dirname(playlistpath)
    files  = []
    for p in paths:
        if os.path.isdir(p):
            for spec in ['*.mp3', '*.ogg', '*.mpc', '*.flac']:
                files.extend(glob.iglob(os.path.join(p,spec)))
        else:
            files.append(p)
    sortedfiles = sort_by_track_number(files)
    relativefiles = [ os.path.relpath(f, playlist_dir) for f in sortedfiles ]
    if dryrun:
        playlist_fileobj = sys.stdout
    else:
        playlist_fileobj = file(playlistpath, 'wb')
    playlist_fileobj.write("\n".join(relativefiles))

def get_parser():
    program_name = os.path.basename(sys.argv[0])
    program_shortdesc = "Creates a playlist from passed directories and files, sorted by track number"

    parser = argparse.ArgumentParser(
        prog=program_name,
        description=program_shortdesc,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-n", "--dry-run", dest="dryrun", action="store_true", help="do nothing except show what will happen [default: %(default)s]")
    parser.add_argument(dest="paths", help="files and directories to include in playlist", nargs='+')
    parser.add_argument(dest="playlist", help="path to an M3U playlist to write", nargs=1)
    return parser

def main(argv=None):
    logging.basicConfig(level=logging.WARNING)

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    parser = get_parser()
    args = parser.parse_args()

    make_album_playlist(args.playlist[0], args.paths, dryrun=args.dryrun)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
