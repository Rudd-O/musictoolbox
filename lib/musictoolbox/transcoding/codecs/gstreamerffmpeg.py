import glob
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Union, Optional, Any, Callable, List, Tuple, Dict

import packaging.version

from . import base
from .. import registry
from ..interfaces import FileType


try:
    from shlex import quote
except ImportError:
    from pipes import quote

try:
    from urllib.request import pathname2url
except ImportError:
    from urllib import pathname2url  # type:ignore


logger = logging.getLogger(__name__)


_gst_command = None


def sort_gst_candidates(candidates: List[str]) -> List[str]:
    """Sort GStreamer launch candidates, highest versions first."""
    version_re = re.compile(".*-([0-9]+($|[.][0-9]+)+)")

    def getver(
        v: str,
    ) -> None | packaging.version._BaseVersion:
        try:
            return packaging.version.parse(v)
        except packaging.version.InvalidVersion:
            return None

    withversions = [
        (
            version_re.match(name).groups()[0]  # type:ignore
            if (version_re.match(name) is not None and version_re.match(name))
            else "10000000",
            name,
        )
        for name in candidates
    ]
    withversions = [(getver(v), x) for v, x in withversions if getver(v)]
    return [x[1] for x in reversed(sorted(withversions))]


def gst(
    src: Path,
    dst: Path,
    *elements: Union[str, List[str]],
    force_gst_command: Optional[str] = None
) -> List[str]:
    if force_gst_command:
        prog = force_gst_command
    else:
        global _gst_command
        if _gst_command is None:
            prog = "gst-launch-1.0"
            for p in os.environ.get("PATH", "").split(os.path.pathsep):
                opts = sort_gst_candidates(
                    glob.glob(os.path.join(glob.escape(p), "gst-launch*"))
                )
                for opt in opts:
                    if os.access(opt, os.X_OK):
                        prog = opt
                        break
                else:
                    continue
                break
            _gst_command = prog
        prog = _gst_command

    cmd = [prog, "-f"]
    srcs = "file://" + pathname2url(src.absolute().as_posix())
    cmd += ["giosrc", "location=%s" % srcs]
    for element in elements:
        cmd.append("!")
        if isinstance(element, str):
            cmd.append(element)
        elif isinstance(element, list):
            for e in element:
                if isinstance(e, str):
                    cmd.append(e)
                else:
                    assert 0
        else:
            assert 0
    cmd.append("!")
    cmd += [
        "filesink",
        "location=%s" % dst.absolute().as_posix(),
    ]
    return cmd


def get_output(cmd: List[str]) -> str:
    logger.debug("Getting output from %s", " ".join(quote(s) for s in cmd))
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)


def run(cmd: List[str], env: Dict[str, str] = {}) -> None:
    logger.debug("Running %s", " ".join(quote(s) for s in cmd))
    newenv = dict(os.environ.items())
    for k, v in env.items():
        newenv[k] = v
    output = subprocess.check_output(
        cmd,
        stdin=None,
        stderr=subprocess.STDOUT,
        close_fds=True,
        env=newenv,
    )
    if "gst-launch" in cmd[0] and b"Got EOS from element" not in output:
        # Artificially raise an error here, as there was a problem with
        # the pipeline not finishing.  Notorious for being necessary
        # when gst-launch is interrupted, and it still returns zero.
        raise subprocess.CalledProcessError(255, cmd, "", output)


@registry.register
class FlvMp4WebmToMp3(base.WithEnvironmentVariables):
    """Transcodes from FLV / MP4 to MP3, avoiding retranscoding if possible."""

    cost = 20

    def can_transcode(self, src: Path) -> List[FileType]:
        return (
            [FileType.by_name("mp3")]
            if FileType.from_path(src) in ["flv", "mp4", "webm", "mkv"]
            else []
        )

    def transcode(self, src: Path, dst: Path) -> None:
        """Transcode FLV / MP4 to MP3 file"""
        output = get_output(["ffprobe", src.as_posix()])
        if "Audio: mp3" in output:
            cmd = gst(src, dst, "flvdemux", "audio/mpeg")
        else:
            cmd = gst(
                src,
                dst,
                "decodebin",
                "audioconvert",
                [
                    "lamemp3enc",
                    "encoding-engine-quality=2",
                    "quality=0",
                ],
            )
        cmd.append("xingmux")
        run(cmd, env=self.settings["environment_variables"])


@registry.register
class ExtractAudio(object):
    """Extracts audio from videos into a suitably-encapsulated file."""

    cost = 3

    def __init__(self, settings: Optional[Dict[str, Any]]):
        self.settings = settings or {}
        defaults: List[Tuple[str, Callable[[Any], bool], Any]] = [
            (
                "source_extensions",
                lambda v: isinstance(v, list),
                ["flv", "mp4", "webm", "mkv", "wmv", "m4v"],
            ),
        ]
        for k, t, v in defaults:
            if k not in self.settings:
                self.settings[k] = self.settings.get(k, v)
                if not t(self.settings[k]):
                    raise ValueError("Invalid setting %s: %s" % (k, v))

    def can_transcode(self, src: Path) -> List[FileType]:
        if not src.is_file():
            # Optimization.  Cannot inspect for transcoding what does not exist.
            return []

        if (
            FileType.from_path(src) in self.settings["source_extensions"]
        ) or "*" in self.settings["source_extensions"]:
            pass
        else:
            # Skip this file.  As configured, it is not supported by this encoder.
            return []

        try:
            output = get_output(
                [
                    "ffprobe",
                    "-loglevel",
                    "warning",
                    "-hide_banner",
                    "-show_streams",
                    "-select_streams",
                    "a",
                    "--",
                    src.as_posix(),
                ]
            )
        except subprocess.CalledProcessError:
            # Cannot detect file.
            return []
        types: List[FileType] = []
        if "codec_name=mp3" in output:
            types.append(FileType.by_name("mp3"))
        if "codec_name=aac" in output:
            types.append(FileType.by_name("m4a"))
        if "codec_name=opus" in output:
            types.append(FileType.by_name("opus"))
        if "codec_name=vorbis" in output:
            types.append(FileType.by_name("ogg"))
        if "codec_name=wmav" in output:
            types.append(FileType.by_name("wma"))
        return types

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = [
            "ffmpeg",
            "-loglevel",
            "quiet",
            "-y",
            "-i",
            src.as_posix(),
            "-acodec",
            "copy",
            "-vn",
            dst.as_posix(),
        ]
        run(cmd)


@registry.register
class FlvMp4WebmToWav(base.WithEnvironmentVariables):
    """Transcodes from FLV / MP4 to RIFF WAVE 32 bit float."""

    cost = 10

    def can_transcode(self, src: Path) -> List[FileType]:
        return (
            [FileType.by_name("wav")]
            if FileType.from_path(src) in ["flv", "mp4", "webm", "mkv"]
            else []
        )

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = gst(
            src,
            dst,
            "decodebin",
            "audioconvert",
            "audio/x-raw,format=F32LE",
            "wavenc",
        )
        run(cmd, env=self.settings["environment_variables"])


@registry.register
class AudioToMp3(base.WithEnvironmentVariables):
    """Transcodes from any audio format to MP3."""

    cost = 10

    def can_transcode(self, src: Path) -> List[FileType]:
        return (
            [FileType.by_name("mp3")]
            if FileType.from_path(src)
            in ["ogg", "aac", "m4a", "wav", "flac", "mpc", "wma"]
            else []
        )

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = gst(
            src,
            dst,
            "decodebin",
            "audioconvert",
            [
                "lamemp3enc",
                "encoding-engine-quality=2",
                "quality=0",
            ],
            "xingmux",
        )
        run(cmd, env=self.settings["environment_variables"])


@registry.register
class AudioToWav(base.NoSettings):
    """Transcodes from any audio format to RIFF WAVE 32 bit float."""

    cost = 10

    def can_transcode(self, src: Path) -> List[FileType]:
        return (
            [FileType.by_name("wav")]
            if FileType.from_path(src)
            in ["ogg", "aac", "m4a", "flac", "mpc", "mp3", "wma", "opus"]
            else []
        )

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = gst(
            src,
            dst,
            "decodebin",
            "audioconvert",
            "audio/x-raw,format=F32LE",
            "wavenc",
        )
        run(cmd)


@registry.register
class WavToOgg(base.NoSettings, base.BinaryTranscoder):
    """Transcodes from any audio format to Ogg Vorbis."""

    cost = 10

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = gst(
            src,
            dst,
            "wavparse",
            "audioconvert",
            [
                "vorbisenc",
                "quality=0.49",
            ],
            "oggmux",
        )
        run(cmd)


@registry.register
class WavToOpus(base.NoSettings, base.BinaryTranscoder):
    """Transcodes from any audio format to Ogg Opus."""

    cost = 9

    def transcode(self, src: Path, dst: Path) -> None:
        cmd = gst(
            src,
            dst,
            "wavparse",
            "audioconvert",
            ["audioresample", "quality=10", "sinc-filter-mode=full"],
            "opusenc",
            "oggmux",
        )
        run(cmd)
