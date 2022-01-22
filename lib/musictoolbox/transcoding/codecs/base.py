from pathlib import Path
from typing import List, Dict, Any, Optional


from musictoolbox.transcoding.interfaces import FileType


class BinaryTranscoder(object):
    def can_transcode(self, src: Path) -> List[FileType]:
        name = self.__class__.__name__
        if "Using" in name:
            name = name.split("Using")[0]
        parts = [FileType.by_name(x.lower()) for x in name.split("To")]
        if parts[0] == FileType.from_path(src):
            return [parts[1]]
        return []


class NoSettings(object):
    def __init__(self, settings: Optional[Dict[str, Any]]):
        if settings:
            raise ValueError(
                "the %s transcoder takes no settings" % self.__class__.__name__.lower()
            )


class WithEnvironmentVariables(object):
    def __init__(self, settings: Optional[Dict[str, Any]]):
        if not hasattr(self, "settings"):
            self.settings: Dict[str, Any] = {}
        if settings and "environment_variables" in settings:
            if not "environment_variables" in self.settings:
                self.settings["environment_variables"] = {}
            for k, v in settings["environment_variables"].items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise ValueError(
                        "The environment variable %r is not a string or its value %r is not a string"
                        % (k, v)
                    )
                self.settings["environment_variables"][k] = v
        else:
            self.settings["environment_variables"] = {}


class WithSettings(object):
    def __init__(self, settings: Optional[Dict[str, Any]]):
        self.settings = settings or {}
