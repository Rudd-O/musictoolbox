Music toolbox
=============

This is a small toolbox of utilities written in Python 2 that help users groom their music collection.

What's in the box
-----------------

- `syncplaylists`: taking a number of playlists in the command line, and a destination directory, it synchronizes all the songs in the playlists (preserving the path structure) to the destination directory.  It has the ability to transcode the files to the preferred formats of your target device as well.  Run `syncplaylists --help` for more information.

`syncplaylists will read an INI file named ~/.syncplaylists.ini to determine how to transcode.  Add the following to it:

    [transcoding]
    mp3=copy
    *=mp3

and you should be done.  More documentation coming.

Requirements
------------

This is a non-exhaustive list of requirements for most of these utilities to work:

  - python-setuptools
  - python-twisted
  - ffmpeg
  - python-mutagen
  - mp3gain
  - madplay
  - mplayer
  - mppenc
  - vorbis-tools
  - flac

