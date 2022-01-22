# Music toolbox

This is a small toolbox of utilities written in Python 2 that help users groom their music collection.

## What's in the box

The box contains a number of utilities.  The main one is `syncplaylists`.

### syncplaylists: the playlist synchronizer

`syncplaylists` takes a number of file lists / playlists in the command line,
and a destination directory, then synchronizes all the songs in the playlists
to the destination directory, with optional modifications to the files and their
names as they are copied to the destination directory.  `syncplaylists` preserves
your music collection's directory structure, and allows you to define what
formats you want your music to be transcoded to.

Run `syncplaylists --help` for more information.

`syncplaylists` accepts a simple YAML file in your home directory, by default read
from file `transcoding.yaml` in `$HOME/.config/musictoolbox` (althoug you can change
which file to use with the `-c` command line parameter).  The file must say how you
want things to be transcoded (documentation on the config format is forthcoming):

```
# cat ~/.config/musictoolbox/transcoding.yaml
policies:
- source: ogg
  # Ogg Vorbis and Ogg Opus files to be copied directly
  pipeline: [copy]
- source: *
  # Everything else to transcode to MP3.  MP3 files
  # themselves will be copied since the copy transcoder
  # is the one with the cheapest "cost".
  target: mp3
```

Once you've created the YAML config file, here's the quickstart version of how you
actually *use* the tool:

```
[user@laptop ~/Music]$ syncplaylists -vd Playlists/*.m3u /mnt/usbdrive/Music/
```

That will copy all songs listed in all M3U playlists within your
`~/Music/Playlists` folder directly into `/mnt/usbdrive/Music`, preserving
the directory structure you have.

### genplaylist: the playlist generator

`genplaylist` generates playlists.  Run `genplaylist --help` for more information.


## Requirements / dependencies

This is a list of requirements for most of these utilities to work:

* python3-packaging
* python3-networkx
* python3-pyxdg
* python3-psutil
* python3-mutagen
* ffmpeg
* GStreamer
