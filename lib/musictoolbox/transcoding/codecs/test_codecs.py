from pathlib import Path
from typing import Union, List
import unittest

from . import gstreamerffmpeg as mod


class TestGst(unittest.TestCase):
    def test_same_pipeline_as_before(self) -> None:
        src, dst, f = Path("a"), Path("b"), "gst-launch-1.0"
        in_ = [
            "decodebin",
            "audioconvert",
            "audio/x-raw,format=F32LE",
            "wavenc",
        ]
        exp_ = [
            f,
            "-f",
            "giosrc",
            "location=file://%s" % src.absolute().as_posix(),
            "!",
            "decodebin",
            "!",
            "audioconvert",
            "!",
            "audio/x-raw,format=F32LE",
            "!",
            "wavenc",
            "!",
            "filesink",
            "location=%s" % dst.absolute().as_posix(),
        ]
        self.assertListEqual(exp_, mod.gst(src, dst, *in_, force_gst_command=f))

    def test_element_with_parameters(self) -> None:
        src, dst, f = Path("a"), Path("b"), "gst-launch-1.0"
        in_: List[Union[str, List[str]]] = [
            "decodebin",
            "audioconvert",
            [
                "lamemp3enc",
                "encoding-engine-quality=2",
                "quality=0",
            ],
            "xingmux",
        ]
        exp_ = [
            f,
            "-f",
            "giosrc",
            "location=file://%s" % src.absolute().as_posix(),
            "!",
            "decodebin",
            "!",
            "audioconvert",
            "!",
            "lamemp3enc",
            "encoding-engine-quality=2",
            "quality=0",
            "!",
            "xingmux",
            "!",
            "filesink",
            "location=%s" % dst.absolute().as_posix(),
        ]
        self.assertListEqual(exp_, mod.gst(src, dst, *in_, force_gst_command=f))

    def test_candidate_sort_largest_version_wins(self) -> None:
        in_ = [
            "/usr/bin/gst-launch-0.10",
            "/usr/bin/gst-launch-1.0",
            "/usr/bin/gst-launch-1.1",
        ]
        exp = [
            "/usr/bin/gst-launch-1.1",
            "/usr/bin/gst-launch-1.0",
            "/usr/bin/gst-launch-0.10",
        ]
        res = mod.sort_gst_candidates(in_)
        self.assertListEqual(exp, res)

    def test_candidate_sort_unversioned_wins(self) -> None:
        in_ = [
            "/usr/bin/gst-launch",
            "/usr/bin/gst-launch-1.0",
            "/usr/bin/gst-launch-1.1",
        ]
        exp = [
            "/usr/bin/gst-launch",
            "/usr/bin/gst-launch-1.1",
            "/usr/bin/gst-launch-1.0",
        ]
        res = mod.sort_gst_candidates(in_)
        self.assertListEqual(exp, res)
