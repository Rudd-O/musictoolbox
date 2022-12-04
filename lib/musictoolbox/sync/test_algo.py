import collections
import os
from pathlib import Path
import tempfile
import typing
import unittest

from . import algo as mod
from ..files import AbsolutePath, Absolutize
from ..transcoding.registry import TranscodingPath
from ..transcoding.test_registry import DummyLookup


def ab(
    iterable: typing.Union[typing.Dict[str, str], typing.List[str], str]
) -> typing.Union[
    typing.Dict[AbsolutePath, AbsolutePath],
    typing.List[AbsolutePath],
    AbsolutePath,
]:
    if isinstance(iterable, list):
        return [Absolutize(x) for x in iterable]
    elif isinstance(iterable, dict):
        return dict(
            (
                Absolutize(x),
                Absolutize(y),
            )
            for x, y in iterable.items()
        )
    elif isinstance(iterable, str):
        return Absolutize(iterable)
    else:
        assert 0, "not reached: %s" % type(iterable)


def abp(x: str) -> AbsolutePath:
    return typing.cast(AbsolutePath, ab(x))


def abd(x: typing.Dict[str, str]) -> typing.Dict[AbsolutePath, AbsolutePath]:
    return typing.cast(typing.Dict[AbsolutePath, AbsolutePath], ab(x))


def abl(x: typing.List[str]) -> typing.List[AbsolutePath]:
    return typing.cast(typing.List[AbsolutePath], ab(x))


class TestFilesystemPathMapper(unittest.TestCase):
    def test_base_case(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        # Verify that the path is returned exactly the same
        # when it refers to a file in a case-sensitive mount point.
        in_ = abp("/a/b/c/D")
        want = abp("/a/b/c/D")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

        # Verify that another path is returned exactly the same
        # when it refers to a file in a case-sensitive mount point.
        in_ = abp("/a/b/c/d")
        want = abp("/a/b/c/d")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

    def test_vfat_case(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        # Verify that the path is returned exactly the same
        # when it refers to a file in a case-sensitive mount point.
        in_ = abp("/mnt/d/x/D")
        want = abp("/mnt/d/x/D")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

        # Verify that another path is returned exactly the same
        # when it refers to a file in a case-sensitive mount point.
        in_ = abp("/mnt/d/X/d")
        want = abp("/mnt/d/x/D")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

    def test_vfat_illegal(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        # Verify that the path is returned changed
        # but only for the parts that correspond to the VFAT mountpoint.
        in_ = abp("/mnt/d/Can we sing this song tonight?.mp3")
        want = abp("/mnt/d/Can we sing this song tonight_.mp3")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

        # Verify that the path is returned as previously seen
        # but only for the parts that correspond to the VFAT mountpoint.
        in_ = abp("/mnt/d/can we sing this song tonight?.mp3")
        want = abp("/mnt/d/Can we sing this song tonight_.mp3")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"

        # Verify that parts not corresponding to the mount point
        # are not transmogrified.
        in_ = abp("/mnt/?/Can we sing this song tonight?.mp3")
        want = abp("/mnt/?/Can we sing this song tonight?.mp3")
        got = c.map(in_)
        assert got == want, f"got: {got}, want: {want}"


class TestVfatProtect(unittest.TestCase):
    def test_noendingdots(self) -> None:
        p = mod.vfatprotect("/some/path/with./dots")
        self.assertNotIn(".", p)
        p = mod.vfatprotect("/some/path/with..../many dots")
        self.assertNotIn(".", p)
        p = mod.vfatprotect("/some/path/with /many spaces")
        self.assertNotIn(" /", p)

    def test_nobadchars(self) -> None:
        for f in "?<>\\:*|":
            p = mod.vfatprotect("/path/with%sbadchar" % f)
            self.assertNotIn(f, p)


class AlwaysN(object):
    def __init__(self, ret: int) -> None:
        self.ret = ret

    def compare(self, _: Path, __: Path) -> int:
        return self.ret


DummyTranscodingPath = TranscodingPath(0, DummyLookup(), [])


class _DummyTranscodingPather(object):
    def lookup(self, __arg: Path) -> typing.List[TranscodingPath]:
        return [DummyTranscodingPath]


AlwaysNewer = AlwaysN(1)
AlwaysEqual = AlwaysN(0)
AlwaysOlder = AlwaysN(-1)
DummyTranscodingPather = _DummyTranscodingPather()


class TestComputeSynchronization(unittest.TestCase):
    maxDiff = 65536

    def test_simple_case(self) -> None:
        got = mod.compute_synchronization(
            [],
            abp("/"),
            [],
            abp("/"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysNewer,
        )
        want: mod.SyncRet = ([], {}, {}, [])
        self.assertEqual(got, want)

    def test_identical_and_older(self) -> None:
        got = mod.compute_synchronization(
            abl(["/a"]),
            abp("/"),
            abl(["/target/a"]),
            abp("/target"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysEqual,
        )
        want: mod.SyncRet = ([], {}, abd({"/a": "/target/a"}), [])
        self.assertEqual(got, want)

        got = mod.compute_synchronization(
            abl(["/a"]),
            abp("/"),
            abl(["/target/a"]),
            abp("/target"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysOlder,
        )
        self.assertEqual(got, want)

    def test_source_is_newer_than_target(self) -> None:
        got = mod.compute_synchronization(
            abl(["/a"]),
            abp("/"),
            abl(["/target/a"]),
            abp("/target"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysNewer,
        )
        want: mod.SyncRet = (
            [
                (abp("/a"), abp("/target/a"), DummyTranscodingPath),
            ],
            {},
            {},
            [],
        )
        self.assertEqual(got, want)

    def test_absent_target(self) -> None:
        got = mod.compute_synchronization(
            abl(["/a"]),
            abp("/"),
            [],
            abp("/target"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysNewer,
        )
        want: mod.SyncRet = (
            [
                (abp("/a"), abp("/target/a"), DummyTranscodingPath),
            ],
            {},
            {},
            [],
        )
        self.assertEqual(got, want)

    def test_absent_source(self) -> None:
        got = mod.compute_synchronization(
            [],
            abp("/"),
            abl(["/target/a"]),
            abp("/target"),
            [],
            [],
            DummyTranscodingPather,
            AlwaysEqual,
        )
        want: mod.SyncRet = ([], {}, {}, abl(["/target/a"]))
        self.assertEqual(got, want)

    def test_mapper(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        got = mod.compute_synchronization(
            abl(["/basedir/a"]),
            abp("/basedir"),
            abl(["/mnt/d/target/a"]),
            abp("/mnt/d/target"),
            [],
            [c],
            DummyTranscodingPather,
            AlwaysNewer,
        )
        want: mod.SyncRet = (
            [
                (
                    abp("/basedir/a"),
                    abp("/mnt/d/target/a"),
                    DummyTranscodingPath,
                ),
            ],
            {},
            {},
            [],
        )
        self.assertEqual(got, want)

    def test_mapper_conflicts(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        got = mod.compute_synchronization(
            abl(["/basedir/a", "/basedir/A"]),
            abp("/basedir"),
            abl(["/mnt/d/target/a"]),
            abp("/mnt/d/target"),
            [],
            [c],
            DummyTranscodingPather,
            AlwaysNewer,
        )
        want: mod.SyncRet = (
            [
                (
                    abp("/basedir/a"),
                    abp("/mnt/d/target/a"),
                    DummyTranscodingPath,
                ),
            ],
            collections.OrderedDict(
                {
                    abp("/basedir/A"): mod.Conflict(
                        abp("/basedir/A"),
                        abp("/mnt/d/target/a"),
                        abp("/basedir/a"),
                    )
                }
            ),
            {},
            [],
        )
        assert got[1] == want[1]

    def test_complex(self) -> None:
        c = mod.FilesystemPathMapper(abp("/mnt/d"))
        c.mptypes = {"/mnt/d": "vfat", "/": "ext4"}

        class C(object):
            def compare(self, p1: Path, unused_p2: Path) -> int:
                if p1.name == "newerintgt":
                    return -1
                return 1

        got = mod.compute_synchronization(
            abl(
                [
                    "/basedir/needsupdate",
                    "/basedir/differentname",
                    "/basedir/newerintgt",
                    "/basedir/absentintgt",
                ]
            ),
            abp("/basedir"),
            abl(
                [
                    "/mnt/d/target/needsupdate",
                    "/mnt/d/target/DifferentName",
                    "/mnt/d/target/absentinsource",
                ]
            ),
            abp("/mnt/d/target"),
            [],
            [c],
            DummyTranscodingPather,
            C(),
        )
        want: mod.SyncRet = (
            [
                (
                    abp("/basedir/needsupdate"),
                    abp("/mnt/d/target/needsupdate"),
                    DummyTranscodingPath,
                ),
                (
                    abp("/basedir/differentname"),
                    abp("/mnt/d/target/DifferentName"),
                    DummyTranscodingPath,
                ),
                (
                    abp("/basedir/absentintgt"),
                    abp("/mnt/d/target/absentintgt"),
                    DummyTranscodingPath,
                ),
            ],
            {},
            abd(
                {
                    "/basedir/newerintgt": "/mnt/d/target/newerintgt",
                }
            ),
            [abp("/mnt/d/target/absentinsource")],
        )
        self.assertEqual(got, want)


class TestModTimestampComparer(unittest.TestCase):
    def test_regular(self) -> None:
        c = mod.ModTimestampComparer()
        with tempfile.TemporaryDirectory() as d:
            f1 = Absolutize(d) / "f1"
            f2 = Absolutize(d) / "f2"
            with open(f1, "w") as f1o:
                f1o.write("x")
            with open(f2, "w") as f2o:
                f2o.write("y")

            os.utime(f1, (f2.stat().st_mtime + 1, f2.stat().st_mtime + 1))
            assert c.compare(f1, f2) == 1

            os.utime(f1, (f2.stat().st_mtime - 1, f2.stat().st_mtime - 1))
            assert c.compare(f1, f2) == -1

            os.utime(f1, (f2.stat().st_mtime, f2.stat().st_mtime))
            assert c.compare(f1, f2) == 0

    def test_vfat(self) -> None:
        c = mod.ModTimestampComparer()
        with tempfile.TemporaryDirectory() as d:
            c.mptypes[d] = "vfat"
            f1 = Absolutize(d) / "f1"
            f2 = Absolutize(d) / "f2"
            with open(f1, "w") as f1o:
                f1o.write("x")
            with open(f2, "w") as f2o:
                f2o.write("y")

            os.utime(f1, (f2.stat().st_mtime + 1, f2.stat().st_mtime + 1))
            assert c.compare(f1, f2) == 0

            os.utime(f1, (f2.stat().st_mtime - 1, f2.stat().st_mtime - 1))
            assert c.compare(f1, f2) == 0

            os.utime(f1, (f2.stat().st_mtime, f2.stat().st_mtime))
            assert c.compare(f1, f2) == 0


class TestWithin(unittest.TestCase):
    def test_same_matches(self) -> None:
        assert mod.within(Absolutize("/a"), Absolutize("/a/"))

    def test_subpath_matches(self) -> None:
        assert mod.within(Absolutize("/a"), Absolutize("/a/bcd"))

    def test_non_subpaths_do_not_match(self) -> None:
        assert not mod.within(Absolutize("/a"), Absolutize("/bcd"))
        assert not mod.within(Absolutize("/a"), Absolutize("/a/../bcd"))
