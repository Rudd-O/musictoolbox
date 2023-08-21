#!/usr/bin/python3
# type: ignore

# FIXME:
# make tag transfer into something like the encoder registry
# but simpler -- either direct transfers with shortcut functions,
# or loaders that load generic info, and writers of that generic
# info for known formats.
#
# IOW: this must be rewritten completely.

from __future__ import print_function

import logging
import os
import typing

import mutagen.apev2  # atype: ignore
import mutagen.flac  # atype: ignore
import mutagen.id3  # atype: ignore
import mutagen.musepack  # atype: ignore
import mutagen.oggvorbis  # atype: ignore

from .util import transform_keys

logger = logging.getLogger(__name__)


def copy_generic_tag_values_to_id3(i, o):
    """copies tag values from i to o, transforming to fit the ID3 spec"""
    tag_transformation_map = {
        "album": "TALB",
        "artist": "TPE1",
        "comment": "COMM",
        "description": "COMM",
        "date": "TDRC",
        "year": "TDRC",
        "title": "TIT2",
        "tracknumber": "TRCK",
        "track": "TRCK",
        "genre": "TCON",
        "replaygain_album_gain": lambda x: mutagen.id3.TXXX(
            desc="replaygain_album_gain", encoding=1, text=x
        ),
        "replaygain_album_peak": lambda x: mutagen.id3.TXXX(
            desc="replaygain_album_peak", encoding=1, text=x
        ),
        "replaygain_track_gain": lambda x: mutagen.id3.TXXX(
            desc="replaygain_track_gain", encoding=1, text=x
        ),
        "replaygain_track_peak": lambda x: mutagen.id3.TXXX(
            desc="replaygain_track_peak", encoding=1, text=x
        ),
    }

    def iterate(k, v):
        if k in tag_transformation_map:
            if type(v) not in (tuple, list):
                v = [v]
            constructor = tag_transformation_map[k]
            if callable(constructor):
                newvalues = [constructor(str(value)) for value in v]
            else:
                constructor = getattr(mutagen.id3, constructor)
                newvalues = [constructor(text=str(value), encoding=3) for value in v]
            list(map(o.add, newvalues))
            return newvalues

    transform_keys(str.lower, i)
    for k, v in list(i.items()):
        iterate(k, v)


def transfer_tags_any_mp3(origin, destination, tag_reader):

    try:
        i = tag_reader(origin)
    except Exception:
        logger.exception("Could not open tag of %s", origin)
        return

    try:
        o = mutagen.id3.ID3(filename=destination)
    except mutagen.id3.ID3NoHeaderError:
        o = mutagen.id3.ID3()

    copy_generic_tag_values_to_id3(i, o)
    o.save(filename=destination, v1=2)


def transfer_tags_mp3(origin, destination):

    # First we'll try to copy any APEv2 tags from origin to destination.
    # It is not an error if that does not happen.
    try:
        i = mutagen.apev2.APEv2()
        i.load(origin)
        i.save(destination)
    except mutagen.apev2.APENoHeaderError:
        pass
    except Exception:
        logger.exception(
            "Though %s exists, an error blocked opening the APEv2 tag", origin
        )

    try:
        i = mutagen.id3.ID3()
        i.load(origin)
        i.save(destination, v1=2)
    except mutagen.id3.ID3NoHeaderError:
        pass  # no ID3 tag, we skip it
    except Exception:
        logger.exception(
            "Though %s exists, an error blocked opening the ID3 tag: %s", origin
        )


# FIXME: IMPLEMENT TRANSFER OF TAGS FROM VIDEOS
tag_transfer_functions = {
    "mp3:mp3": lambda x, y, _, __: transfer_tags_mp3(x, y),
    "mp3:aac": lambda x, y, _, __: transfer_tags_mp3(x, y),
    "ogg:mp3": lambda x, y, _, __: transfer_tags_any_mp3(x, y, mutagen.oggvorbis.Open),
    "flac:mp3": lambda x, y, _, __: transfer_tags_any_mp3(x, y, mutagen.flac.Open),
    "mpc:mp3": lambda x, y, _, __: transfer_tags_any_mp3(x, y, mutagen.musepack.Open),
}


def transfer_tags(
    origin: str,
    destination: str,
    source_format: typing.Optional[str] = None,
    target_format: typing.Optional[str] = None,
) -> None:
    if not source_format:
        source_format = os.path.splitext(origin)[1][1:].lower()
    if not target_format:
        target_format = os.path.splitext(destination)[1][1:].lower()
    m = "%s:%s" % (source_format, target_format)
    if m in tag_transfer_functions:
        logger.debug("Using %s for tag transfer function", m)
        transfer_function = tag_transfer_functions[m]
        transfer_function(origin, destination, source_format, target_format)
    else:
        logger.debug("No tag transfer function for %s", m)
    return
