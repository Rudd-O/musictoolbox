from typing import Dict, Any, Set

from musictoolbox.transcoding.interfaces import TranscoderName


class TranscoderSettings(object):
    def __init__(self, settings_dict: Dict[str, Dict[str, Any]]):
        x = (
            dict((x.lower(), y) for x, y in settings_dict.items())
            if settings_dict
            else {}
        )
        self.settings: Dict[str, Any] = x

    def all_names(self) -> Set[TranscoderName]:
        return set(TranscoderName(x) for x in self.settings.keys())

    def for_name(self, name: TranscoderName) -> Dict[str, Any]:
        deff: Dict[str, Any] = {}
        if name in self.settings:
            return self.settings[name]  # type: ignore
        return deff

    def __str__(self) -> str:
        return "<TranscoderSettings settings: %s>" % str(self.settings)
