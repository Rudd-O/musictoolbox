from __future__ import print_function

import logging
import typing

from mutagen.apev2 import APEv2
from mutagen.id3 import ID3
from mutagen import File

logger = logging.getLogger(__name__)


# ======= mp3gain and soundcheck operations ==========

REPLAYGAIN_TAGS = (
    "replaygain_track_gain",
    "replaygain_track_peak",
    "replaygain_album_gain",
    "replaygain_album_peak",
    "replaygain_reference_loudness",
    "RVA2",
)


def printpairs(toprint: list[tuple[str, typing.Any]]) -> None:
    key_tpl = "%%%ds" % max(len(x[0]) for x in toprint)
    for key, tag in toprint:
        print(key_tpl % key, "  ", repr(tag))


def viewmp3norm(files: list[str]) -> None:
    while files:
        file = files.pop(0)

        print()
        print(file)

        try:
            tags = File(file)
        except Exception as e:
            print("No known tags", e)
            tags = None
        try:
            apetags = APEv2(file)
        except Exception as e:
            print("No APE tags", e)
            apetags = None

        toprint: list[tuple[str, typing.Any]] = []
        for key, tag in list(apetags.items()):
            toprint.append((key, tag))
        if toprint:
            print("===APE tags====")
            printpairs(toprint)

        toprint = []
        if tags:
            toprint = []
            for key, tag in list(tags.items()):
                try:
                    if any(
                        [x in tag.desc.lower() or x in key for x in REPLAYGAIN_TAGS]
                    ):
                        toprint.append((key, tag))
                except AttributeError:
                    continue
        if toprint:
            print("===Other tags===")
            printpairs(toprint)


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

        toprint: list[tuple[str, typing.Any]] = []
        if apetags:
            print("===APE tags====")
            for key, tag in list(apetags.items()):
                toprint.append((key, tag))
            printpairs(toprint)

        toprint = []
        if tags:
            print("===ID3 tags===")
            for key, tag in list(tags.items()):
                toprint.append((key, tag))
            printpairs(toprint)


# algorithm begins here
