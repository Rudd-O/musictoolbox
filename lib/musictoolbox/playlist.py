import mutagen
import glob
import os
import sys

def sort_by_track_number(paths):
    metadatas = [ (f,mutagen.File(f)) for f in paths ]
    relevant = [ (m["tracknumber"][0],f,m) for f,m in metadatas ]
    relevant = list(sorted(relevant))
    return [ f for x,f,w in relevant ]

def make_album_playlist(playlistpath, *paths):
    playlist_dir = os.path.dirname(playlistpath)
    playlist_fileobj = file(playlistpath, 'wb')
    files  = []
    for p in paths:
        if os.path.isdir(p):
            for spec in ['*.mp3', '*.ogg', '*.mpc', '*.flac']:
                files.extend(glob.iglob(os.path.join(p,spec)))
        else:
            files.append(p)
    sortedfiles = sort_by_track_number(files)
    relativefiles = [ os.path.relpath(f, playlist_dir) for f in sortedfiles ]
    playlist_fileobj.write("\n".join(relativefiles))

def main():
    parms = sys.argv[1:]
    paths = parms[:-1]
    playlistpath = parms[-1]
    make_album_playlist(playlistpath, *paths)
    return 0

if __name__ == "__main__":
    sys.exit(main())
