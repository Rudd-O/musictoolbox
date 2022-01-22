import collections
import logging
import os
from pathlib import Path
from typing import List, Dict, Tuple, Set, Type, Protocol, Any

import pkg_resources  # type: ignore

import networkx as nx  # type: ignore

from .interfaces import (
    FileType,
    TranscoderName,
    TranscoderProtocol,
    TranscoderLookupProtocol,
)
from .settings import TranscoderSettings


logger = logging.getLogger(__name__)


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
        # FIXME: the following import should be done with a zope interfaces registry,
        # and the Zope component architecture, since  the classes have already been
        # registered as TranscoderProtocol.
        from . import codecs  # @UnusedImport

        if not self.__class__.loaded_entry_points:
            for ep in pkg_resources.iter_entry_points(
                group="musictoolbox.transcoding.codecs"
            ):
                try:
                    factory = ep.load()
                    self.__class__.transcoder_factories.add(factory)
                    self.transcoder_factories.add(factory)
                except pkg_resources.DistributionNotFound as e:
                    logger.debug(
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
            logger.debug(
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
        srctype = FileType.by_name(FileType.from_path(src))
        org_srctype = srctype
        g = nx.MultiDiGraph()

        t2name = dict([(t, tname) for tname, t in self.transcoders.items()])

        types_explored: Dict[FileType, bool] = collections.defaultdict(bool)
        if srctype not in types_explored:
            types_explored[srctype] = False
        while any(not f for f in types_explored.values()):
            srctype = [x for x, y in types_explored.items() if not y][0]
            g.add_node(srctype)
            for tname, t in self.transcoders.items():
                p = Path(os.path.join(src.parent, src.stem + "." + srctype))
                dsttypes = t.can_transcode(p)
                for d in dsttypes:
                    g.add_node(d)
                    g.add_edge(srctype, d, key=t, label=tname)
                    if d not in types_explored:
                        types_explored[d] = False
            types_explored[srctype] = True

        paths = []
        copytranscoder = self.transcoders[TranscoderName("copy")]
        copypath: List[Tuple[FileType, FileType, TranscoderProtocol]] = [
            (
                org_srctype,
                org_srctype,
                copytranscoder,
            )
        ]
        paths.append(copypath)
        for tt in types_explored.keys():
            paths += list(nx.all_simple_edge_paths(g, org_srctype, tt))

        new_paths: List[
            Tuple[int, List[Tuple[FileType, FileType, TranscoderName]]]
        ] = []
        for path in paths:
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
                new_paths.append((cost, new_path))

        final_paths = [
            TranscodingPath(cost, self, path) for cost, path in list(sorted(new_paths))
        ]
        return g, final_paths

    @classmethod
    def register(
        cls, transcoder_factory
    ):  # type: (Type[TranscoderRegistry], Type[TranscoderProtocol]) -> Type[TranscoderProtocol]
        cls.transcoder_factories.add(transcoder_factory)
        return transcoder_factory

    def __str__(self) -> str:
        return "<EncoderRegistry: %s>" % ", ".join(self.transcoders.keys())

    def get_transcoder(self, transcoder_name: TranscoderName) -> TranscoderProtocol:
        return self.transcoders[transcoder_name]


register = TranscoderRegistry.register
