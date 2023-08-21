import logging
import sys

from musictoolbox.logging import basicConfig
from mutagen._file import File


def main() -> None:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    for f in sys.argv[1:]:
        x = File(f)
        unwanted = [k for k in x.keys() if "musicbrainz" in k.lower()]
        if unwanted:
            for a in unwanted:
                del x[a]
            x.save()
    sys.exit(0)
