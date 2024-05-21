import collections
import logging
import os
import re
import sys
import typing

from difflib import SequenceMatcher as SM
from musictoolbox.logging import basicConfig

TOKENIZER = re.compile("[^0-9a-zA-Z]+")


def scan(
    tree_path: str
) -> tuple[
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, list[str]],
]:
    filename_to_fullpath: dict[str, list[str]] = collections.defaultdict(list)
    filename_basedir_to_fullpath: dict[str, list[str]] = collections.defaultdict(list)

    for base, dirs, files in os.walk(tree_path):
        for fn in files:
            name_without_ext, ext = os.path.splitext(fn)
            if ext in [".mood", ".nfo"]:
                continue
            fullpath = os.path.join(base, fn)
            filename_to_fullpath[name_without_ext].append(fullpath)
            filename_basedir = os.path.join(os.path.basename(base), name_without_ext)
            filename_basedir_to_fullpath[filename_basedir].append(fullpath)

    filename_tokenized_to_fullpath = {
        TOKENIZER.sub(" ", k).lower(): v for k, v in filename_to_fullpath.items()
    }
    filename_basedir_tokenized_to_fullpath = {
        TOKENIZER.sub(" ", k).lower(): v
        for k, v in filename_basedir_to_fullpath.items()
    }
    return (
        filename_to_fullpath,
        filename_basedir_to_fullpath,
        filename_tokenized_to_fullpath,
        filename_basedir_tokenized_to_fullpath,
    )


def find_choices(
    nonexistent_path: str,
    filename_to_fullpath: dict[str, list[str]],
    filename_basedir_to_fullpath: dict[str, list[str]],
    filename_tokenized_to_fullpath: dict[str, list[str]],
    filename_basedir_tokenized_to_fullpath: dict[str, list[str]],
) -> list[str]:
    name_without_ext = os.path.splitext(os.path.basename(nonexistent_path))[0]
    filename_basedir = os.path.join(
        os.path.basename(os.path.dirname(nonexistent_path)), name_without_ext
    )
    exact_filename_matches = filename_to_fullpath.get(name_without_ext, [])
    exact_filename_basedir_matches = filename_basedir_to_fullpath.get(
        name_without_ext, []
    )

    # assert 0, exact_filename_matches + exact_filename_basedir_matches

    filename_basedir_tokenized = TOKENIZER.sub(" ", filename_basedir).lower()
    fuzzy_filename_basedir_matches = [
        p
        for similitude, paths in reversed(
            sorted(
                s
                for s in [
                    (
                        SM(
                            None, filename_basedir_tokenized, haystack_tokenized
                        ).ratio(),
                        paths,
                    )
                    for haystack_tokenized, paths in filename_basedir_tokenized_to_fullpath.items()
                ]
            )
        )
        for p in paths
    ][:10]

    name_tokenized = TOKENIZER.sub(" ", name_without_ext).lower()
    fuzzy_filename_matches = [
        p
        for similitude, paths in reversed(
            sorted(
                s
                for s in [
                    (SM(None, name_tokenized, haystack_tokenized).ratio(), paths)
                    for haystack_tokenized, paths in filename_tokenized_to_fullpath.items()
                ]
            )
        )
        for p in paths
        if p not in fuzzy_filename_basedir_matches
    ][:10]

    return (
        exact_filename_basedir_matches
        + exact_filename_matches
        + fuzzy_filename_basedir_matches
        + fuzzy_filename_matches
    )


def main() -> None:
    basicConfig(main_module_name=__name__, level=logging.DEBUG)

    replacements: typing.Dict[str, str] = {}

    try:
        (
            filename_to_fullpath,
            filename_basedir_to_fullpath,
            filename_tokenized_to_fullpath,
            filename_basedir_tokenized_to_fullpath,
        ) = scan(os.path.abspath(sys.argv[1]))
    except IndexError:
        assert 0, (
            "error: the first path to this program must be the root"
            " folder of your music collection, and any subsequent"
            " paths should be M3U playlists"
        )

    for fn in sys.argv[2:]:
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
                if fullpath in replacements:
                    newlines.append(replacements[fullpath])
                    didchange = True
                else:
                    print("%r does not exist, searching for alternatives" % line)
                    choices = find_choices(
                        line,
                        filename_to_fullpath,
                        filename_basedir_to_fullpath,
                        filename_tokenized_to_fullpath,
                        filename_basedir_tokenized_to_fullpath,
                    )
                    print("Choices:\n")
                    for n, choice in enumerate(choices):
                        print("{:>2}: {}".format(n + 1, choice))

                    print(
                        "\nEnter a number or a full new path to replace the old one, or leave empty for no replacement:"
                    )

                    newline = sys.stdin.readline().strip()

                    if not newline:
                        print("Skipping replacement of %r" % line)
                        newlines.append(line)
                        continue

                    try:
                        choice_int = int(newline)
                        newline = choices[choice_int - 1]
                    except Exception:
                        pass

                    if os.path.abspath(newline) == newline:
                        newline = os.path.relpath(newline, d)

                    print(f"Replacement selected: {newline}")
                    replacements[fullpath] = newline
                    newlines.append(newline)

                    didchange = True
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
