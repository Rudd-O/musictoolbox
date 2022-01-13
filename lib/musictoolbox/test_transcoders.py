import os
import unittest

import musictoolbox.transcoders as mod


class TestGst(unittest.TestCase):
    def test_same_pipeline_as_before(self):
        src, dst, f = "a", "b", "gst-launch-1.0"
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
            "location=%s" % src,
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
            "location=%s" % dst,
        ]
        self.assertListEqual(exp_, mod.gst(src, dst, *in_, force_gst_command=f))

    def test_element_with_parameters(self):
        src, dst, f = "a", "b", "gst-launch-1.0"
        in_ = [
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
            "location=%s" % src,
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
            "location=%s" % dst,
        ]
        self.assertListEqual(exp_, mod.gst(src, dst, *in_, force_gst_command=f))

    def test_candidate_sort_largest_version_wins(self):
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

    def test_candidate_sort_unversioned_wins(self):
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
