import logging
from pathlib import Path
from typing import List, Optional

from . import registry
from .interfaces import FileType, TranscoderName


logger = logging.getLogger(__name__)


def select_pipelines(
    transcoding_paths: List[registry.TranscodingPath],
    src: Path,
    dsttypes: List[FileType],
    pipeline: Optional[List[TranscoderName]] = None,
) -> List[registry.TranscodingPath]:
    srctype = FileType.by_name(FileType.from_path(src))
    # First, we filter all the paths whose source type does not match the requested source type.
    transcoding_paths = [
        p for p in transcoding_paths if (p.steps[0].srctype == srctype)
    ]
    # Then, we filter all the paths whose intermediate or final destination type do not match
    # the requested destination type.
    if dsttypes:
        matches = []
        for p in transcoding_paths:
            chain = [step.srctype for step in p.steps] + [p.steps[-1].dsttype]
            if dsttypes[-1] == chain[-1]:
                # Final step matches.
                if len(dsttypes) == 1:
                    matches.append(p)
                else:
                    if dsttypes[0] in chain[:-1]:
                        matches.append(p)
        transcoding_paths = matches
    # Then, if the user requested a specific pipeline, we filter for it here.
    if pipeline is not None and len(pipeline) > 0:
        transcoding_paths = [
            p
            for p in transcoding_paths
            if len(p.steps) == len(pipeline)
            and all(
                transcoder_name == step.transcoder_name
                for transcoder_name, step in zip(pipeline, p.steps)
            )
        ]
    return transcoding_paths


class TranscoderPolicy(object):
    def __init__(
        self,
        source: Optional[FileType],
        target: Optional[FileType],
        transcode_to: Optional[FileType],
        pipeline: Optional[List[TranscoderName]],
    ):
        self.source = source
        self.target = target
        self.transcode_to = transcode_to
        self.pipeline = pipeline if pipeline else []

    def match(
        self,
        srctype: Optional[FileType] = None,
        dsttype: Optional[FileType] = None,
    ) -> bool:
        wildcard = FileType.by_name("*")
        match_src = (
            not self.source
            or self.source == wildcard
            or not srctype
            or self.source == srctype
        )
        match_dst = (
            not self.target
            or self.target == wildcard
            or not dsttype
            or self.target == dsttype
            or self.transcode_to == dsttype
        )
        return match_src and match_dst

    def __str__(self) -> str:
        parts = []
        if self.source:
            parts.append("source: %s" % self.source)
        if self.target:
            parts.append("target: %s" % self.target)
        if self.pipeline:
            parts.append("pipeline: %s" % " | ".join(self.pipeline))
        if self.transcode_to:
            parts.append("transcode_to: %s" % self.transcode_to)
        return "[" + ", ".join(parts) + "]"


FallbackPolicy = TranscoderPolicy(FileType.by_name("*"), None, None, [])


class TranscoderPolicies(object):
    def __init__(self, policies: List[TranscoderPolicy]):
        self.policies = policies

    def get_policies_for(
        self,
        srctype: Optional[FileType] = None,
        dsttype: Optional[FileType] = None,
    ) -> List[TranscoderPolicy]:
        t = [p for p in self.policies if p.match(srctype, dsttype)]
        return t

    def __str__(self) -> str:
        return "<" + ", ".join("%s" % p for p in self.policies) + ">"


class PolicyBasedPipelineSelector(object):
    def __init__(self, policies: TranscoderPolicies, allow_fallback: bool = True):
        self.policies = policies
        self.allow_fallback = allow_fallback

    def select_pipelines(
        self,
        transcoding_paths: List[registry.TranscodingPath],
        src: Path,
        dsttype: Optional[FileType] = None,
        pipeline: Optional[List[TranscoderName]] = None,
    ) -> List[registry.TranscodingPath]:
        srctype = FileType.from_path(src)
        # Get all policies applicable for the combo of srctype and possibly dsttype.
        policies = self.policies.get_policies_for(srctype, dsttype)
        if self.allow_fallback:
            # Add a fallback policy that allows the system to fall back in case
            # none of the matching policies actually produce at least pipeline.
            policies += [FallbackPolicy]
        for policy in policies:
            # Destination type selection for pipeline lookup.
            # Legend:
            #
            # transcode_to:
            #   The policy specified a specific final format to transcode to.
            #   This is useful when the user knows a particular file format
            #   would normally transcode to another one, but wants to
            #   further transcode from that other one to a final format.
            # target:
            #   The policy specified a target format, usually as match.
            if policy.transcode_to and policy.target:
                dsttypes = [policy.target, policy.transcode_to]
            elif policy.transcode_to:
                dsttypes = [policy.transcode_to]
            elif policy.target:
                dsttypes = [policy.target]
            else:
                dsttypes = []

            limit_to_pipeline = (
                pipeline if pipeline else (policy.pipeline if policy.pipeline else None)
            )
            transcoding_paths_for_policy = select_pipelines(
                transcoding_paths, src, dsttypes, limit_to_pipeline
            )
            if transcoding_paths_for_policy:
                return transcoding_paths_for_policy
        return []


def NoPolicyPipelineSelector() -> PolicyBasedPipelineSelector:
    return PolicyBasedPipelineSelector(TranscoderPolicies([]))
