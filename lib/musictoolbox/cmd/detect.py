import sys
import typing
from mutagen.apev2 import APEv2, APENoHeaderError


def detect_broken_ape_tags(files: typing.List[str]) -> None:
    while files:
        f = files.pop(0)
        try:
            APEv2(f)
        except APENoHeaderError:
            pass
        except KeyError as e:
            print(f)
        except Exception as e:
            print("while processing %r: %s" % (f, e), file=sys.stderr)


def detect_missing_ape_tags(files: typing.List[str]) -> None:
    while files:
        f = files.pop(0)
        try:
            APEv2(f)
        except APENoHeaderError:
            print(f)
        except KeyError as e:
            pass
        except Exception as e:
            print("while processing %r: %s" % (f, e), file=sys.stderr)
