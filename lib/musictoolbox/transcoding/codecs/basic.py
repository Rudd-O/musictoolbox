from pathlib import Path
import shutil
from typing import List

from . import base
from .. import registry
from ..interfaces import FileType


@registry.register
class Copy(base.NoSettings):
    """Copies files without changing format."""

    cost = 1

    def transcode(self, src: Path, dst: Path) -> None:
        shutil.copyfile(src, dst)

    def can_transcode(self, src: Path) -> List[FileType]:
        return [FileType.from_path(src)]
