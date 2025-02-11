from pathlib import Path
from typing import List, Tuple
import unittest

from . import config as cfg
from . import registry as reg
from . import settings as set
from .codecs.base import NoSettings
from .interfaces import FileType, TranscoderName, TranscoderProtocol


class DummyTranscoder(NoSettings):
    cost = 0

    def transcode(self, src: Path, dst: Path) -> None:  # @UnusedVariable
        return None

    def can_transcode(self, src: Path) -> List[FileType]:  # @UnusedVariable
        return []


class DummyLookup(object):
    def get_transcoder(
        self,
        transcoder_name: TranscoderName,  # @UnusedVariable
    ) -> TranscoderProtocol:
        return DummyTranscoder({})


def mp(cost: int, steps: List[Tuple[str, str, str]]) -> reg.TranscodingPath:
    return reg.TranscodingPath(
        cost,
        DummyLookup(),
        [
            (FileType.by_name(x[0]), FileType.by_name(x[1]), TranscoderName(x[2]))
            for x in steps
        ],
    )


class TestTranscoderRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.r = reg.TranscoderRegistry(cfg.DefaultTranscoderConfiguration.settings)

    def test_basic_map(self) -> None:
        have = "a.mp3"
        exp = [
            mp(1, [("mp3", "mp3", "copy")]),
            mp(10, [("mp3", "wav", "audiotowav")]),
            mp(20, [("mp3", "wav", "audiotowav"), ("wav", "opus", "wavtoopus")]),
            mp(20, [("mp3", "wav", "audiotowav"), ("wav", "ogg", "wavtoogg")]),
        ]
        unused_graph, got = self.r.map_pipelines(Path(have))
        self.assertListEqual([str(s) for s in exp], [str(s) for s in got])

    def test_copy_is_first(self) -> None:
        have = "a.mp3"
        exp = [mp(1, [("mp3", "mp3", "copy")])]
        unused_graph, got = self.r.map_pipelines(Path(have))
        self.assertListEqual([str(s) for s in exp[0:1]], [str(s) for s in got[0:1]])

    def test_transcoder_settings_for_unknown_transcoder(self) -> None:
        c = set.TranscoderSettings({"unknown": {"a": "b"}})
        self.assertRaises(ValueError, reg.TranscoderRegistry, c)
