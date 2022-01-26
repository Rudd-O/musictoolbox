import argparse
import logging
import os

from ..logging import basicConfig


def main() -> int:

    basicConfig(main_module_name=__name__, level=logging.DEBUG)
    p = argparse.ArgumentParser(
        description="Copy an M3U playlist, preserving its relative paths or making them absolute."
    )
    p.add_argument("IN", type=str, nargs="+", help="input playlist")
    p.add_argument("OUT", type=str, nargs=1, help="output playlist")
    p.add_argument(
        "-A",
        "--absolute",
        action="store_true",
        help="make paths in output playlist absolute",
    )

    args = p.parse_args()

    for in_file in args.IN:
        new = []
        in_basedir = os.path.dirname(in_file)
        out_file = args.OUT[0]
        if os.path.isdir(out_file):
            out_basedir = out_file
            out_file = os.path.join(out_basedir, os.path.basename(in_file))
        else:
            assert len(args.IN) == 1, (
                "Error: multiple source paths were specified, but destination %r is not a directory."
                % out_file
            )
            out_basedir = os.path.dirname(out_file)

        with open(in_file, "r") as in_:
            for line in in_:
                if line.startswith("#"):
                    new.append(line)
                    continue
                has_newline = line.endswith("\n")
                line = line.rstrip()
                absline = os.path.abspath(os.path.join(in_basedir, line))
                line = absline
                if not args.absolute:
                    relline = os.path.relpath(line, out_basedir)
                    line = relline
                new.append(line + ("\n" if has_newline else ""))

        try:
            with open(out_file, "r") as out_orig:
                orig_text = out_orig.read()
        except Exception:
            orig_text = ""

        new_text = "".join(new)

        if new_text != orig_text:
            with open(out_file, "w") as out_:
                out_.write(new_text)

    return 0
