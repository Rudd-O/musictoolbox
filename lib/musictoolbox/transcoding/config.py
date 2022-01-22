import io
import logging
import os
from typing import TextIO, Optional, List

import xdg.BaseDirectory  # type: ignore
import yaml  # type: ignore

from .interfaces import TranscoderName, FileType
from .policies import (
    TranscoderPolicies,
    TranscoderPolicy,
)
from .settings import TranscoderSettings


# Sample policy file:
sample_policy_file = """
policies:
- source: abc
  target: def
settings:
#  copy: {}
# The copy transcoder supports no settings.
#  another:
#     abc: def
"""


logger = logging.getLogger(__name__)


class TranscoderConfiguration(object):

    policies: TranscoderPolicies = TranscoderPolicies([])
    settings: TranscoderSettings = TranscoderSettings({})

    def __str__(self) -> str:
        return "<TranscoderConfiguration policies: %s  settings: %s>" % (
            self.policies,
            self.settings,
        )


DefaultTranscoderConfiguration = TranscoderConfiguration()


class TranscoderConfigurationLoader(yaml.SafeLoader):  # type: ignore
    def construct_transcoder_policy(
        self, node: yaml.MappingNode
    ) -> Optional[TranscoderPolicy]:
        if not node.tag.endswith(":map"):
            raise ValueError(
                "a transcoder policy must be a dictionary of policy settings"
            )
        source: Optional[FileType] = None
        target: Optional[FileType] = None
        transcode_to: Optional[FileType] = None
        pipeline: List[TranscoderName] = []
        for key, val in node.value:
            if key.value == "source":
                v = self.construct_scalar(val)
                if not isinstance(v, str):
                    raise ValueError(
                        "a transcoder source must be a file type in string form"
                    )
                source = FileType.by_name(v)
            elif key.value == "target":
                v = self.construct_scalar(val)
                if not isinstance(v, str):
                    raise ValueError(
                        "a transcoder target must be a file type in string form"
                    )
                target = FileType.by_name(v)
            elif key.value == "transcode_to":
                v = self.construct_scalar(val)
                if not isinstance(v, str):
                    raise ValueError(
                        "a transcoder transcode_to value must be a file type in string form"
                    )
                transcode_to = FileType.by_name(v)
            elif key.value == "pipeline":
                v: list[str] = self.construct_sequence(val)  # type: ignore
                if not isinstance(v, list):
                    raise ValueError(
                        "a transcoder pipeline must be a list of transcoder names"
                    )
                pipeline = [TranscoderName(x) for x in v]
            else:
                raise ValueError(
                    "transcoder policies do not know setting %r" % key.value
                )
        if source or target or transcode_to or pipeline:
            return TranscoderPolicy(
                source=source,
                target=target,
                transcode_to=transcode_to,
                pipeline=pipeline,
            )
        return None

    def construct_transcoder_policies(
        self, node: yaml.SequenceNode
    ) -> TranscoderPolicies:
        if not node.tag.endswith(":seq"):
            raise ValueError("transcoder policies must be a list of policies")
        ps = []
        for v in node.value:
            vv = self.construct_transcoder_policy(v)
            if vv is not None:
                ps.append(vv)
        return TranscoderPolicies(ps)

    def construct_transcoder_settings(
        self, node: yaml.MappingNode
    ) -> TranscoderSettings:
        if not node.tag.endswith(":map"):
            raise ValueError(
                "transcoder settings must be a dictionary of {transcoder name: settings{}}"
            )
        v = yaml.SafeLoader.construct_mapping(self, node, deep=True)
        return TranscoderSettings(v)

    def construct_document(self, node):  # type: ignore
        cfg = TranscoderConfiguration()
        for unused_n, (key, val) in enumerate(node.value):
            if key.value == "policies":
                cfg.policies = self.construct_transcoder_policies(val)
            elif key.value == "settings":
                cfg.settings = self.construct_transcoder_settings(val)
            else:
                raise ValueError("%r is not permitted in the configuration" % key.value)
        return cfg

    @classmethod
    def from_file(cls, fobject: TextIO) -> TranscoderConfiguration:
        p = yaml.load(fobject, Loader=cls)
        if p is None:
            return DefaultTranscoderConfiguration
        assert isinstance(p, TranscoderConfiguration), p
        return p


def transcoding_config_default_filename() -> str:
    return os.path.join("musictoolbox", "transcoding.yaml")


def transcoding_config_default_path() -> str:
    return os.path.join(
        xdg.BaseDirectory.xdg_config_home, transcoding_config_default_filename()
    )


def load_transcoding_config(p: Optional[str] = None) -> TranscoderConfiguration:
    """
    Config file none-> load first found config.
    Config file empty string -> do not load any config.
    """
    if p == "":
        logger.debug(
            "User specified empty config file; explicitly skipping any config file and using defaults"
        )
        return DefaultTranscoderConfiguration

    logger.debug("Specified configuration file: %s", p)
    p = p or xdg.BaseDirectory.load_first_config(transcoding_config_default_filename())
    logger.debug("Actually discovered configuration file: %s", p)
    if p:
        logger.debug("Configuration file %s exists; loading it", p)
        with open(p, "r") as f:
            cfg = TranscoderConfigurationLoader.from_file(f)
            logger.debug("Loaded configuration: %s", cfg)
            return cfg

    logger.debug("No configuration file %s; using defaults", p)
    return DefaultTranscoderConfiguration


if __name__ == "__main__":
    with io.StringIO(sample_policy_file) as f:
        cfg = TranscoderConfigurationLoader.from_file(f)
        print(cfg)
