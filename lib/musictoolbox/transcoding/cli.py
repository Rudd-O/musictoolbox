import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Optional

from networkx import drawing, MultiDiGraph  # type: ignore

from . import config, policies, transcoder, registry
from ..logging import basicConfig

# FIXME type comment
from ..tagging import transfer_tags  # type: ignore
from .interfaces import FileType, TranscoderName


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Transcodes a media file into another format.",
    )
    p.add_argument("src", help="source file name", type=str)
    p.add_argument("dst", help="destination file name", type=str)
    meg = p.add_mutually_exclusive_group()
    meg.add_argument(
        "-l",
        "--plot",
        help="only plot the available transcoder pipelines",
        action="store_true",
        default=False,
    )
    meg.add_argument(
        "-n",
        "--dry-run",
        help="only display what would be done",
        action="store_true",
        default=False,
    )
    p.add_argument(
        "-p",
        "--pipeline",
        help="comma-separated name of transcoder pipeline steps that overrides the configuration file; possible steps for a (src, dst) pair of files displayed with -n",
        type=str,
        default="",
    )
    p.add_argument(
        "-c",
        "--config-file",
        help="path to a configuration file with transcoding policies and settings; highest precedence config will be loaded from %s; empty string config file will prevent loading any config"
        % config.transcoding_config_default_path(),
        type=str,
        default=None,
    )
    p.add_argument(
        "-d",
        "--debug",
        help="enable debug logging",
        action="store_true",
        default=False,
    )
    return p


def plot_transcoder_pipelines(graph: MultiDiGraph) -> None:
    with tempfile.NamedTemporaryFile() as f:
        drawing.nx_pydot.write_dot(graph, f.name)
        f.seek(0, 0)
        out = subprocess.check_output(["dot", "-Tpng"], stdin=f)
        f.seek(0, 0)
        f.truncate()
        f.write(out)
        f.flush()
        subprocess.check_call(["eog", f.name])


def main() -> Optional[int]:
    p = parser()
    opts = p.parse_args()
    basicConfig(__name__, logging.DEBUG if opts.debug else logging.INFO)

    c = config.load_transcoding_config(opts.config_file)
    r = registry.TranscoderRegistry(c.settings)
    src, dst = Path(opts.src), Path(opts.dst) if opts.dst else None

    pipeline = (
        [TranscoderName(n) for n in opts.pipeline.split(",")] if opts.pipeline else []
    )
    selector = (
        policies.NoPolicyPipelineSelector()
        if pipeline
        else policies.PolicyBasedPipelineSelector(c.policies)
    )
    mapper = transcoder.TranscodingMapper(r, selector)

    dsttype = FileType.by_name(FileType.from_path(dst)) if dst else None
    graph, selected_paths = mapper.lookup_with_graph(
        src, dsttype=dsttype, pipeline=pipeline
    )

    if opts.plot:
        plot_transcoder_pipelines(graph)
        return 0
    elif opts.dry_run:
        for nn, path in enumerate(selected_paths):
            print(
                "Transcoder pipeline %swith cost %s:"
                % ("(selected) " if nn == 0 else "", path.cost)
            )
            for n, step in enumerate(path.steps):
                print("%3d. %s" % (n + 1, step))
            print()
        if not selected_paths:
            print(
                "No transcoder pipelines found for the involved file formats the constraints from configuration or parameters."
            )
        return 4
    elif not dst:
        print(
            "The destination file name cannot be empty if --plot or --dry-run weren't requested.",
            file=sys.stderr,
        )
        return os.EX_USAGE
    elif not selected_paths:
        print(
            "Cannot transcode %s -- no transcoding pipelines found for the involved file formats from configuration or parameters."
            % src,
            file=sys.stderr,
        )
        return 4

    syncer = transcoder.SingleItemSyncer(transfer_tags)
    syncer.sync(src, dst, selected_paths[0])
    return 0
