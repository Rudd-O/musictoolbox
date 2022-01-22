from __future__ import print_function

import logging
import typing

from mutagen.apev2 import APEv2  # type:ignore
from mutagen.id3 import ID3  # type:ignore

logger = logging.getLogger(__name__)


# ======= mp3gain and soundcheck operations ==========

REPLAYGAIN_TAGS = (
    "replaygain_track_gain",
    "replaygain_track_peak",
    "replaygain_album_gain",
    "replaygain_album_peak",
)


def viewmp3norm(files: typing.List[str]) -> None:
    while files:
        file = files.pop(0)

        print()
        print(file)

        try:
            tags = ID3(file)
        except Exception as e:
            print("No ID3 tags", e)
            tags = None
        try:
            apetags = APEv2(file)
        except Exception as e:
            print("No APE tags", e)
            apetags = None

        if apetags:
            print("===APE tags====")
            for key, tag in list(apetags.items()):
                print("%30s" % key, "  ", repr(tag))

        if tags:
            print("===RVA2 tags===")
            for key, tag in list(tags.items()):
                try:
                    if tag.desc.lower() in [x[0] for x in REPLAYGAIN_TAGS]:
                        print("%30s" % key, "  ", repr(tag))
                except AttributeError:
                    continue


def viewtags(files: typing.List[str]) -> None:
    while files:
        file = files.pop(0)

        print()
        print(file)

        try:
            tags = ID3(file)
        except Exception as e:
            print("No ID3 tags", e)
            tags = None
        try:
            apetags = APEv2(file)
        except Exception as e:
            print("No APE tags", e)
            apetags = None

        if apetags:
            print("===APE tags====")
            for key, tag in list(apetags.items()):
                print("%30s" % key, "  ", repr(tag))

        if tags:
            print("===ID3 tags===")
            for key, tag in list(tags.items()):
                print("%30s" % key, "  ", repr(tag))


# algorithm begins here
