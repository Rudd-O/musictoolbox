import logging
import sys
import typing

from musictoolbox.logging import basicConfig
from mutagen.apev2 import APEv2, APENoHeaderError


def detect_broken_ape_tags() -> None:
    files: typing.List[str] = sys.argv[1:]
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    while files:
        f = files.pop(0)
        try:
            APEv2(f)
        except APENoHeaderError:
            pass
        except KeyError:
            print(f)
        except Exception as e:
            print("while processing %r: %s" % (f, e), file=sys.stderr)


def detect_missing_ape_tags() -> None:
    files: typing.List[str] = sys.argv[1:]
    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    while files:
        f = files.pop(0)
        try:
            APEv2(f)
        except APENoHeaderError:
            print(f)
        except KeyError:
            pass
        except Exception as e:
            print("while processing %r: %s" % (f, e), file=sys.stderr)
