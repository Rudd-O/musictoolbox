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
