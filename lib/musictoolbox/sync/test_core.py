"""
Created on Aug 11, 2012

@author: rudd-o
"""

import collections
import contextlib
import os
from pathlib import Path
import pprint
from queue import Queue
import shutil
import tempfile
import textwrap
import typing
import unittest

from . import core as mod
from ..files import AbsolutePath, Absolutize as A
from ..files import ensure_directories_exist
from ..transcoding import policies, registry, settings, transcoder
from ..transcoding.interfaces import TranscoderName, FileType
from ..transcoding.test_registry import DummyLookup


# FIXME: test musictoolbox.synccli
@contextlib.contextmanager
def synthetic_playlists_fixtures() -> typing.Generator[
    typing.Tuple[
        typing.List[AbsolutePath], typing.Dict[AbsolutePath, typing.List[AbsolutePath]]
    ],
    None,
    None,
]:
    with tempfile.TemporaryDirectory() as d:
        p1, p2 = open(Path(d) / "a.m3u", "w"), open(Path(d) / "b.m3u", "w")
        try:
            p1.write(
                textwrap.dedent(
                    """
                    #test playlist
                    /home/rudd-o/mp3.mp3
                    home/rudd-o/wav.mp3
                    /home/rudd-o/common.mp3
                    """
                )
            )
            p2.write(
                textwrap.dedent(
                    """
                    #test playlist 2
                    /home/rudd-o/playlist2.mp3
                    /home/rudd-o/wav.mp3
                    /home/rudd-o/common.mp3
                    """
                )
            )
        finally:
            p1.close()
            p2.close()

        output = {
            A("/home/rudd-o/mp3.mp3"): [A(p1.name)],
            A(Path(d) / "home/rudd-o/wav.mp3"): [A(p1.name)],
            A("/home/rudd-o/common.mp3"): [A(p1.name), A(p2.name)],
            A("/home/rudd-o/playlist2.mp3"): [A(p2.name)],
            A("/home/rudd-o/wav.mp3"): [A(p2.name)],
        }
        yield [A(p1.name), A(p2.name)], output


@contextlib.contextmanager
def list_files_recursively_fixtures() -> typing.Generator[
    typing.Tuple[str, typing.List[AbsolutePath], typing.List[typing.Union[int, float]]],
    None,
    None,
]:
    with tempfile.TemporaryDirectory() as d:
        files = [os.path.join(d, str(x)) for x in range(10)]
        e = os.path.join(d, "subdir")
        os.mkdir(e)
        giles = [os.path.join(e, str(x)) for x in range(10)]
        for f in files + giles:
            with open(f, "w"):
                pass
        mtimes = [os.stat(f).st_mtime for f in files + giles]
        yield d, [A(x) for x in files + giles], mtimes


class TestParsePlaylists(unittest.TestCase):
    maxDiff = 65536

    def test_synthetic_playlists(self) -> None:
        with synthetic_playlists_fixtures() as (sources, output):
            files, excs = mod.parse_playlists(sources)
            self.assertEqual(files, output)
            self.assertEqual(excs, [])

    def test_nonexistent_playlists(self) -> None:
        sources = [A("does not exist")]
        files, excs = mod.parse_playlists(sources)
        self.assertEqual(files, {})
        self.assertTrue(excs[0][0], "does not exist")
        self.assertTrue(isinstance(excs[0][1], IOError), excs[0][1])


class TestListFilesRecursively(unittest.TestCase):
    maxDiff = 65536

    def test_simple_case(self) -> None:
        with list_files_recursively_fixtures() as (d, files, _):
            listed_files = mod.list_files_recursively(A(d))
            listed_files.sort()
            shutil.rmtree(d)
            self.assertEqual(files, listed_files)


def syncplaylists_fixtures(
    dd: AbsolutePath,
    fake_songs: typing.List[str],
    fake_playlists: typing.List[typing.List[str]],
) -> typing.List[AbsolutePath]:
    pls: typing.List[AbsolutePath] = []
    for n, c in enumerate(fake_playlists):
        fn = dd / ("%s.m3u" % n)
        pls.append(fn)
        with fn.open("w") as f:
            f.write("\n".join(c))
    for s in fake_songs:
        ss = dd / s
        ensure_directories_exist([ss.parent.as_posix()])
        with ss.open("w") as f:
            f.write("Not a real file")
    return pls


def donothing_postpro(
    unused1: str,
    unused2: str,
    unused3: typing.Optional[str] = None,
    unused4: typing.Optional[str] = None,
) -> None:
    pass


def consume(
    q: Queue[typing.Union[mod.SyncQueueItem, None]]
) -> typing.List[mod.SyncQueueItem]:
    res: typing.List[mod.SyncQueueItem] = []
    while True:
        v = q.get()
        if v is None:
            break
        res.append(v)
    return res


def copypath(ft: str) -> registry.TranscodingPath:
    return registry.TranscodingPath(
        1,
        DummyLookup(),
        [(FileType.by_name(ft), FileType.by_name(ft), TranscoderName("copy"))],
    )


class TestSynchronizer(unittest.TestCase):
    maxDiff = 65535

    def setUp(self) -> None:
        self.td = A(tempfile.mkdtemp(suffix=self.__class__.__name__))

    def tearDown(self) -> None:
        shutil.rmtree(self.td)

    def _makeStack(
        self,
        playlists: typing.List[AbsolutePath],
        target_dir: AbsolutePath,
        forced_policy: typing.Optional[policies.TranscoderPolicy] = None,
        allow_fallback: bool = True,
        force_vfat: bool = False,
    ) -> mod.Synchronizer:
        ts = settings.TranscoderSettings({})
        tr = registry.TranscoderRegistry(ts)
        pipeline = [TranscoderName("copy")]
        policy = (
            forced_policy
            if forced_policy
            else policies.TranscoderPolicy(
                source=None, target=None, transcode_to=None, pipeline=pipeline
            )
        )
        ps = policies.PolicyBasedPipelineSelector(
            policies.TranscoderPolicies([policy]), allow_fallback
        )
        tm = transcoder.TranscodingMapper(tr, ps)
        s = mod.Synchronizer(
            playlists, target_dir, tm, [], donothing_postpro, force_vfat
        )
        return s

    def test_basic(self) -> None:
        in_ = (
            self.td,
            [
                "Albums/Good/A-Ha/Take on me.mp3",
                "Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg",
            ],
            [
                ["Albums/Good/A-Ha/Take on me.mp3"],
                [
                    "Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg",
                    "Albums/Good/A-Ha/Take on me.mp3",
                ],
            ],
        )
        want = [
            (
                self.td / "Albums/Good/A-Ha/Take on me.mp3",
                self.td / "output/Good/A-Ha/Take on me.mp3",
                copypath("mp3"),
            ),
            (
                self.td / "Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg",
                self.td / "output/Bad/Ace of Base/What you gonna tell your dad?.ogg",
                copypath("ogg"),
            ),
        ]
        playlists = syncplaylists_fixtures(*in_)
        s = self._makeStack(playlists, self.td / "output")
        got = s.compute_synchronization()
        self.assertEqual(want, got[0])

        q, unused_cancel = s.synchronize(got, 1)
        res = consume(q)
        for _, _, d in res:
            assert not isinstance(d, Exception)
        for _, v, __ in want:
            assert os.path.exists(v), v

    def test_vfat(self) -> None:
        in_ = (
            self.td,
            ["Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg"],
            [["Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg"]],
        )
        want = [
            (
                self.td / "Albums/Bad/Ace of Base/What you gonna tell your dad?.ogg",
                self.td / "output/What you gonna tell your dad_.ogg",
                copypath("ogg"),
            ),
        ]
        playlists = syncplaylists_fixtures(*in_)
        s = self._makeStack(playlists, self.td / "output", force_vfat=True)
        got = s.compute_synchronization()
        self.assertEqual(want, got[0])

        q, unused_cancel = s.synchronize(got, 1)
        res = consume(q)
        for _, _, d in res:
            assert not isinstance(d, Exception)
        for _, v, __ in want:
            assert os.path.exists(v), v

    def test_playlist_does_not_exist(self) -> None:
        s = self._makeStack([self.td / "notexist.m3u"], self.td)
        self.assertRaises(FileNotFoundError, s.compute_synchronization)

    def test_no_matching_pipeline(self) -> None:
        in_ = (
            self.td,
            [
                "Albums/Good/A-Ha/Take on me.aardvark",
            ],
            [
                ["Albums/Good/A-Ha/Take on me.aardvark"],
            ],
        )
        want = collections.OrderedDict(
            [
                (
                    self.td / "Albums/Good/A-Ha/Take on me.aardvark",
                    transcoder.NoPipeline(
                        self.td / "Albums/Good/A-Ha/Take on me.aardvark"
                    ),
                ),
            ]
        )
        playlists = syncplaylists_fixtures(*in_)
        s = self._makeStack(
            playlists,
            self.td,
            forced_policy=policies.TranscoderPolicy(
                source=FileType.by_name("aardvark"),
                target=None,
                transcode_to=None,
                pipeline=[TranscoderName("extractaudio")],
            ),
            allow_fallback=False,
        )
        got = s.compute_synchronization()
        self.assertEqual(got[0], [])

        gots, wants = pprint.pformat(got[1]), pprint.pformat(want)
        assert gots == wants

    def test_uppercase_extension(self) -> None:
        in_ = (
            self.td,
            ["Albums/Good/A-Ha/Take on me.OGG"],
            [["Albums/Good/A-Ha/Take on me.OGG"]],
        )
        want = [
            (
                self.td / "Albums/Good/A-Ha/Take on me.OGG",
                self.td / "Take on me.ogg",
                copypath("ogg"),
            ),
        ]
        playlists = syncplaylists_fixtures(*in_)
        s = self._makeStack(playlists, self.td)
        got = s.compute_synchronization()
        self.assertEqual(got[0], want)

    def test_sync_playlists_base(self) -> None:
        in_ = (
            self.td,
            ["Albums/Good/A-Ha/Take on me.OGG"],
            [["Albums/Good/A-Ha/Take on me.OGG"]],
        )
        wantp = """# from: %s\n# was: %s\n%s""" % (
            self.td / "0.m3u",
            "Albums/Good/A-Ha/Take on me.OGG",
            "../Take on me.ogg",
        )
        playlists = syncplaylists_fixtures(*in_)
        s = self._makeStack(playlists, self.td)
        plan = s.compute_synchronization()
        plsync = list(s.synchronize_playlists(plan))
        assert plsync == [(self.td / "0.m3u", self.td / "Playlists/0.m3u", None)]
        with (self.td / "Playlists/0.m3u").open("r") as f:
            gotp = f.read()
        self.assertMultiLineEqual(wantp, gotp)

    def test_synchronize_deletions(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            dp = Path(d)
            (dp / "output").mkdir()
            with (dp / "playlist.m3u").open("w") as f:
                f.write("a.mp3")

            with (dp / "a.mp3").open("w") as f:
                f.write("x")

            with (dp / "output/b.mp3").open("w") as f:
                f.write("x")

            (dp / "output/Playlists").mkdir()
            with (dp / "output/Playlists/x.m3u").open("w") as f:
                f.write("x")

            s = self._makeStack([A(dp / "playlist.m3u")], A(dp / "output"))
            plan = s.compute_synchronization()
            want = [
                (A(dp / "output/b.mp3"), None),
                (A(dp / "output/Playlists/x.m3u"), None),
            ]
            got = list(s.synchronize_deletions(plan))
            self.assertListEqual(want, got)
