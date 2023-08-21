from __future__ import print_function

import logging
import typing
import sys

from musictoolbox.logging import basicConfig
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3
from mutagen._file import File

logger = logging.getLogger(__name__)


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


def viewmp3norm() -> None:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    files: list[str] = sys.argv[1:]
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
        if apetags:
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


def viewtags() -> None:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    files: list[str] = sys.argv[1:]
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
