import logging
import os
from pathlib import Path
import shutil
import tempfile
from threading import Lock
import typing

from networkx import MultiDiGraph  # type: ignore

from . import policies as pol, registry as reg
from .. import files
from .interfaces import (
    Postprocessor,
    FileType,
    TranscoderName,
)


logger = logging.getLogger(__name__)


class NoPipeline(Exception):
    def __init__(self, source: Path):
        self.source = source

    def __str__(self) -> str:
        return (
            "<Transcoding: file %s cannot be transcoded by any codec pipeline according to configuration>"
            % (self.source,)
        )


class TranscodingMapper(object):
    def __init__(
        self,
        transcoder_registry: reg.TranscoderRegistry,
        pipeline_selector: pol.PolicyBasedPipelineSelector,
    ):
        self.transcoder_registry = transcoder_registry
        self.pipeline_selector = pipeline_selector
        self.pipeline_cache: typing.Dict[Path, typing.List[reg.TranscodingPath]] = {}
        self.pipeline_cache_lock = Lock()

    def _feed_cache(self, path: Path) -> typing.List[reg.TranscodingPath]:
        with self.pipeline_cache_lock:
            if path in self.pipeline_cache:
                return self.pipeline_cache[path]

        _, all_paths = self.transcoder_registry.map_pipelines(path)
        transcoding_paths = self.pipeline_selector.select_pipelines(all_paths, path)
        with self.pipeline_cache_lock:
            self.pipeline_cache[path] = transcoding_paths
        return transcoding_paths

    def map(self, path: Path) -> Path:
        transcoding_paths = self._feed_cache(path)
        if not transcoding_paths:
            raise NoPipeline(path)
        transcoding_path = transcoding_paths[0]
        parent, stem = path.parent, path.stem
        newext = transcoding_path.dsttype
        dst = parent / (stem + "." + newext)
        return dst

    def lookup(self, path: Path) -> typing.List[reg.TranscodingPath]:
        return self._feed_cache(path)

    def lookup_with_graph(
        self,
        path: Path,
        dsttype: typing.Optional[FileType] = None,
        pipeline: typing.Optional[typing.List[TranscoderName]] = None,
    ) -> typing.Tuple[MultiDiGraph, typing.List[reg.TranscodingPath]]:
        logger.debug(
            "Selecting appropriate pipelines for path:%s dsttype:%s pipeline:%s",
            path,
            dsttype,
            pipeline,
        )
        graph, paths = self.transcoder_registry.map_pipelines(path)
        transcoding_paths = self.pipeline_selector.select_pipelines(
            paths, path, dsttype, pipeline
        )
        return graph, transcoding_paths


class SingleItemSyncer(object):
    def __init__(self, postprocessor: Postprocessor):
        self.postprocessor = postprocessor

    def sync(self, src: Path, dst: Path, transcoding_path: reg.TranscodingPath) -> None:
        logger.debug("Beginning to transcode from %s", src)
        files.ensure_directories_exist([dst.parent.as_posix()])
        in_fn = src.as_posix()
        with files.remover() as tmpfiles:
            for step in transcoding_path.steps:
                prefix = ".tmp-" + step.transcoder_name + dst.stem
                suffix = "." + step.dsttype
                prefix = files.shorten_to_name_max(
                    dst.parent.as_posix(),
                    prefix,
                    8 + len(suffix),
                )
                out_f = tempfile.NamedTemporaryFile(
                    prefix=prefix,
                    dir=dst.parent.as_posix(),
                    suffix=suffix,
                    delete=False,
                )
                out_fn = out_f.name
                tmpfiles.append(out_fn)
                out_f.close()
                logger.debug("Pipeline step: %s", step)
                step.transcode(Path(in_fn), Path(out_fn))
                shutil.copymode(in_fn, out_fn)
                in_fn = out_fn
            self.postprocessor(
                src.as_posix(),
                in_fn,
                transcoding_path.srctype,
                transcoding_path.dsttype,
            )
            os.rename(in_fn, dst)
        logger.debug("Done transcoding to %s", dst)
