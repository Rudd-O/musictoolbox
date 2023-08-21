import logging
import os
import sys
import typing

from musictoolbox.logging import basicConfig


def main() -> None:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)

    replacements: typing.Dict[str, str] = {}

    for fn in sys.argv[1:]:

        didchange = False

        f = open(fn, "r")
        d = os.path.dirname(fn)
        lines = [x.strip() for x in f.readlines() if x.strip()]

        newlines = []
        for line in lines:
            fullpath = os.path.join(d, line)
            if line.startswith("#"):
                newlines.append(line)
            elif not os.path.exists(fullpath):
                didchange = True
                if fullpath in replacements:
                    newlines.append(replacements[fullpath])
                else:
                    print("%r does not exist" % line)
                    print("Enter new path to replace old one")
                    newline = sys.stdin.readline().strip()
                    if not newline:
                        print("Skipping replacement of %r" % line)
                    newlines.append(newline)
                    replacements[fullpath] = newline
            else:
                newlines.append(line)

        if didchange:
            f = open(fn + ".new", "w")
            f.write("\n".join(newlines))
            f.flush()
            f.close()
            os.rename(fn, fn + "~")
            os.rename(fn + ".new", fn)

    sys.exit(0)
