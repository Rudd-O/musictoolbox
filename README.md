Music toolbox
=============

This is a small toolbox of utilities written in Python 2 that help users groom their music collection.

What's in the box
-----------------

`syncplaylists` takes a number of file lists / playlists in the command line,
and a destination directory, then synchronizes all the songs in the playlists
to the destination directory, with optional modifications to the files and their
names as they are copied to the destination directory.  `syncplaylists` preserves
your music collection's directory structure.

`syncplaylists` requires a simple INI file in your home directory (name it
`.syncplaylists.ini`) which must say how you want things to be transcoded:

```
# cat .syncplaylists.ini
[transcoding]
mp3=copy
m4a=copy
ogg=copy
flac=copy
*=mp3
opus=copy
```

Once you've created the INI file, here's the quickstart version of how you
actually *use* the tool:

```
[user@laptop ~/Music]$ syncplaylists -vd Playlists/*.m3u /mnt/usbdrive/Music/
```

That will copy all songs listed in all M3U playlists within your
`~/Music/Playlists` folder directly into `/mnt/usbdrive/Music`, preserving
the directory structure you have.

Run `syncplaylists --help` or see `get_parser()` in file `synccli.py` for more
information.

`genplaylist` generates playlists.  Run `genplaylist --help` or see
`get_parser()` in file `genplaylist` for more information.

Requirements
------------

This is a non-exhaustive list of requirements for most of these utilities to work:

  - python-setuptools
  - ffmpeg
  - python-mutagen
  - mp3gain
  - madplay
  - mplayer
  - mppenc
  - vorbis-tools
  - flac

