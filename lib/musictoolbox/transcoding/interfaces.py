from pathlib import Path
from typing import List, Any, Type, Dict, Callable, Union, Protocol  # @UnusedImport


class FileType(str):
    cache = {}  # type: Dict[str, FileType]

    @classmethod
    def by_name(klass, name):  # type: (Type[FileType], str) -> FileType
        if name not in klass.cache:
            klass.cache[name] = FileType(name)
        return klass.cache[name]

    @classmethod
    def from_path(klass, path):  # type: (Type[FileType], Path) -> FileType
        name = path.suffix[1:].lower()
        return klass.by_name(name)


class TranscoderProtocol(Protocol):
    """Interface for transcoders."""

    cost: int = -1

    def __init__(self, settings: Dict[str, Any]):
        pass

    def transcode(self, src: Path, dest: Path) -> None:
        """Transcodes a file src to a file dest."""
        pass

    def can_transcode(self, src: Path) -> List[FileType]:
        pass


class TranscoderName(str):
    pass


class TranscoderLookupProtocol(Protocol):
    def get_transcoder(self, transcoder_name: TranscoderName) -> TranscoderProtocol:
        pass


Postprocessor = Callable[[str, str, Union[None, str], Union[None, str]], None]
