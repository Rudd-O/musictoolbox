from pathlib import Path
import unittest

from musictoolbox.transcoding.interfaces import FileType, TranscoderName
from musictoolbox.transcoding.policies import select_pipelines, TranscoderPolicy
from musictoolbox.transcoding.test_registry import mp


bn = FileType.by_name


class TestSelectPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.pipelines = [
            mp(1, [("mp3", "mp3", "copy")]),
            mp(2, [("mp3", "ogg", "mp3toogg")]),
            mp(3, [("mp3", "wav", "mp3towav"), ("wav", "ogg", "wavtoogg")]),
        ]

    def test_copy_selected(self) -> None:
        res = select_pipelines(
            self.pipelines,
            Path("a.mp3"),
            pipeline=[TranscoderName("copy")],
            dsttypes=[],
        )
        if not res:
            assert 0, "expected at least one pipeline"
        p = res[0]
        self.assertEqual([x.transcoder_name for x in p.steps], [TranscoderName("copy")])

    def test_cheaper_selected(self) -> None:
        res = select_pipelines(
            self.pipelines, Path("a.mp3"), dsttypes=[FileType.by_name("ogg")]
        )
        if not res:
            assert 0, "expected at least one pipeline"
        p = res[0]
        self.assertEqual(
            [x.transcoder_name for x in p.steps], [TranscoderName("mp3toogg")]
        )

    def test_pipeline_preference_respected(self) -> None:
        res = select_pipelines(
            self.pipelines,
            Path("a.mp3"),
            dsttypes=[FileType.by_name("ogg")],
            pipeline=[TranscoderName("mp3towav"), TranscoderName("wavtoogg")],
        )
        if not res:
            assert 0, "expected at least one pipeline"
        p = res[0]
        self.assertEqual(
            [x.transcoder_name for x in p.steps],
            [TranscoderName("mp3towav"), TranscoderName("wavtoogg")],
        )

    def test_pipeline_with_transcode_to(self) -> None:
        res = select_pipelines(
            self.pipelines,
            Path("a.mp3"),
            dsttypes=[FileType.by_name("wav"), FileType.by_name("ogg")],
            pipeline=[TranscoderName("mp3towav"), TranscoderName("wavtoogg")],
        )
        if not res:
            assert 0, "expected at least one pipeline"
        p = res[0]
        self.assertEqual(
            [x.transcoder_name for x in p.steps],
            [TranscoderName("mp3towav"), TranscoderName("wavtoogg")],
        )

    def test_no_pipeline_if_none_fit(self) -> None:
        res = select_pipelines(
            self.pipelines,
            Path("a.mp3"),
            dsttypes=[FileType.by_name("mp4")],
        )
        if res:
            assert 0, "expected no pipelines, got %s" % res


class TestTranscoderPolicy(unittest.TestCase):
    def test_one(self) -> None:
        p = TranscoderPolicy(bn("mp3"), bn("mov"), None, None)
        assert p.match(bn("mp3"))
        assert p.match(dsttype=bn("mov"))
        assert p.match(srctype=bn("mp3"), dsttype=bn("mov"))

    def test_only_target_policy(self) -> None:
        p = TranscoderPolicy(None, bn("mov"), None, None)
        assert p.match(bn("mp3"))
        assert p.match(dsttype=bn("mov"))
        assert not p.match(dsttype=bn("mp4"))
        assert p.match(srctype=bn("mp3"), dsttype=bn("mov"))
