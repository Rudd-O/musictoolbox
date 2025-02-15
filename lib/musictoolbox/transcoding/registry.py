import collections
import logging
import os
from pathlib import Path
from typing import List, Dict, Tuple, Set, Type, Protocol, Any

from importlib import metadata

import networkx as nx

import pprint

from .interfaces import (
    FileType,
    TranscoderName,
    TranscoderProtocol,
    TranscoderLookupProtocol,
)
from .settings import TranscoderSettings


_LOGGER = logging.getLogger(__name__)


class TranscodingStep(object):
    def __init__(
        self,
        transcoder_db: TranscoderLookupProtocol,
        srctype: FileType,
        dsttype: FileType,
        transcoder_name: TranscoderName,
    ):
        self.srctype = srctype
        self.dsttype = dsttype
        self.transcoder_name = transcoder_name
        self.transcoder_db = transcoder_db

    def __str__(self) -> str:
        return "%s --(%s)--> %s" % (self.srctype, self.transcoder_name, self.dsttype)

    def __repr__(self) -> str:
        return self.__str__()

    def transcode(self, src: Path, dst: Path) -> None:
        transcoder = self.transcoder_db.get_transcoder(self.transcoder_name)
        return transcoder.transcode(src, dst)


class TranscodingPath(object):
    cost: int = -1
    steps: List[TranscodingStep] = []

    def __init__(
        self,
        cost: int,
        transcoder_db: TranscoderLookupProtocol,
        steps_list: List[Tuple[FileType, FileType, TranscoderName]],
    ):
        self.cost = cost
        self.steps = []
        for step in steps_list:
            self.steps.append(TranscodingStep(transcoder_db, *step))

    def __str__(self) -> str:
        return "< %s >" % " | ".join(str(s) for s in self.steps)

    def __repr__(self) -> str:
        return self.__str__()

    def __eq__(self, other: Any) -> bool:
        return str(self) == str(other)

    @property
    def srctype(self) -> FileType:
        return self.steps[0].srctype

    @property
    def dsttype(self) -> FileType:
        return self.steps[-1].dsttype


class TranscodingPathLookupProtocol(Protocol):
    def lookup(self, __arg: Path) -> List[TranscodingPath]:
        pass


class TranscoderRegistry(object):
    loaded_entry_points = False
    transcoder_factories: Set[Type[TranscoderProtocol]] = set()
    transcoders: Dict[TranscoderName, TranscoderProtocol] = {}

    def __init__(self, transcoder_settings: TranscoderSettings):
        if not self.__class__.loaded_entry_points:
            eps = metadata.entry_points()
            codecs = eps.select(group="musictoolbox.transcoding.codecs")
            for ep in codecs:
                try:
                    factory = ep.load()
                    assert 0, factory
                    self.__class__.transcoder_factories.add(factory)
                    self.transcoder_factories.add(factory)
                except Exception as e:
                    _LOGGER.warning(
                        "Loading entry point %s has failed with exception %s", ep, e
                    )
                    continue
            self.__class__.loaded_entry_points = True

        self.transcoder_settings = transcoder_settings
        self.transcoders: Dict[TranscoderName, TranscoderProtocol] = {}
        all_setting_names = self.transcoder_settings.all_names()
        for factory in self.transcoder_factories:
            name = TranscoderName(factory.__name__.lower())
            settings = self.transcoder_settings.for_name(name)
            all_setting_names -= set([name])
            _LOGGER.debug(
                "Initializing transcoder %s%s",
                name,
                (
                    " with user-supplied settings %s" % settings
                    if settings
                    else " without any user-supplied settings"
                ),
            )
            transcoder = factory(settings)
            self.transcoders[name] = transcoder
        if all_setting_names:
            raise ValueError(
                "Settings for unavailable transcoders %s have been specified in configuration"
                % ", ".join("%r" % x for x in all_setting_names),
            )

    def map_pipelines(self, src: Path) -> Tuple[nx.MultiDiGraph, List[TranscodingPath]]:
        logger = _LOGGER.getChild("map_pipelines")
        srctype = FileType.by_name(FileType.from_path(src))
        logger.debug("source type %s" % srctype)
        org_srctype = srctype
        g = nx.MultiDiGraph()

        t2name = dict([(t, tname) for tname, t in self.transcoders.items()])
        logger.debug("transcoder to name:\n%s" % pprint.pformat(t2name))

        types_explored: Dict[FileType, bool] = collections.defaultdict(bool)
        if srctype not in types_explored:
            types_explored[srctype] = False

        logger.debug("types explored status:\n%s" % pprint.pformat(types_explored))
        while any(not f for f in types_explored.values()):
            srctype = [x for x, y in types_explored.items() if not y][0]
            logger.debug("  exploring %s", srctype)
            g.add_node(srctype)
            for tname, t in self.transcoders.items():
                p = Path(os.path.join(src.parent, src.stem + "." + srctype))
                dsttypes = t.can_transcode(p)
                for d in dsttypes:
                    logger.debug("    %s can transcode to %s", t, d)
                    g.add_node(d)
                    g.add_edge(srctype, d, key=t, label=tname)
                    if d not in types_explored:
                        types_explored[d] = False
            types_explored[srctype] = True

        type TStep = Tuple[FileType, FileType, TranscoderProtocol]
        type TPath = List[TStep]
        paths: List[TPath] = []
        copytranscoder = self.transcoders[TranscoderName("copy")]
        copypath: TPath = [
            (
                org_srctype,
                org_srctype,
                copytranscoder,
            )
        ]
        paths.append(copypath)
        for tt in types_explored.keys():
            res = list(nx.all_simple_edge_paths(g, org_srctype, tt))
            logger.debug("  retrieved paths for type %s:", tt)
            for i, pp in enumerate(res):
                if pp != []:
                    logger.debug("  %s. %s", i + 1, pp)
                    paths.append(pp)
                else:
                    logger.debug("  %s. empty path (ignored)", i + 1)

        new_paths: List[
            Tuple[int, List[Tuple[FileType, FileType, TranscoderName]]]
        ] = []
        for path in paths:
            logger.debug("  evaluating path %s", path)
            length = len(path)
            cost = 0
            new_path = []
            append = True
            for step in path:
                s = step[0]
                dest = step[1]
                transcoder: TranscoderProtocol = step[2]
                if length > 1 and transcoder == copytranscoder:
                    append = False
                    break
                cost += transcoder.cost
                new_path.append((s, dest, t2name[transcoder]))
            if append:
                logger.debug(
                    "  appending path %s with cost %s: %s", path, cost, new_path
                )
                new_paths.append((cost, new_path))
            else:
                logger.debug("  not appending path %s with cost %s", path, cost)

        final_paths = [
            TranscodingPath(cost, self, path) for cost, path in list(sorted(new_paths))
        ]
        return g, final_paths

    @classmethod
    def register(cls, transcoder_factory):  # type: (Type[TranscoderRegistry], Type[TranscoderProtocol]) -> Type[TranscoderProtocol]
        cls.transcoder_factories.add(transcoder_factory)
        return transcoder_factory

    def __str__(self) -> str:
        return "<EncoderRegistry: %s>" % ", ".join(self.transcoders.keys())

    def get_transcoder(self, transcoder_name: TranscoderName) -> TranscoderProtocol:
        return self.transcoders[transcoder_name]


register = TranscoderRegistry.register
