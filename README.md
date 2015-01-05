Music toolbox
=============

This is a small toolbox of utilities written in Python 2 that help users groom their music collection.

What's in the box
-----------------

`genplaylist` generates playlists.  Run `genplaylist --help` or see
`get_parser()` in file `genplaylist` for more information.  More documentation
will be forthcoming very soon.

`syncplaylists` takes a number of file lists / playlists in the command line,
and a destination directory, then synchronizes all the songs in the playlists
to the destination directory, with optional modifications to the files and their
names as they are copied to the destination directory.  Run
`syncplaylists --help` or see `get_parser()` in file `synccli.py` for more
information.  More documentation will be forthcoming very soon.

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

