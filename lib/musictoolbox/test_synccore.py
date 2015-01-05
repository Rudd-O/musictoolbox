'''
Created on Aug 11, 2012

@author: rudd-o
'''

import unittest
from StringIO import StringIO
import tempfile
import os
import musictoolbox.synccore as mod
import shutil
from musictoolbox import transcoders

# FIXME: test musictoolbox.synccli

def synthetic_playlists_fixtures():
    p1, p2 = StringIO(), StringIO()
    p1.write('''
    #test playlist
    /home/rudd-o/mp3.mp3
    home/rudd-o/wav.mp3
    ''')
    p2.write('''
    #test playlist 2
    /home/rudd-o/playlist2.mp3
    /home/rudd-o/wav.mp3
    ''')

    p1.seek(0)
    p2.seek(0)

    output = {
              "/home/rudd-o/mp3.mp3":[p1],
              "/home/rudd-o/wav.mp3":[p1, p2],
              "/home/rudd-o/playlist2.mp3":[p2],
              }

    return [p1, p2], output

def mtimes_fixtures():
    t1 = tempfile.NamedTemporaryFile()
    t2 = tempfile.NamedTemporaryFile()
    mt1 = os.stat(t1.name).st_mtime
    mt2 = os.stat(t2.name).st_mtime
    return [t1, t2], [mt1, mt2]

def list_files_recursively_fixtures():
    d = tempfile.mkdtemp()
    files = [os.path.join(d, str(x)) for x in range(10)]
    e = os.path.join(d, "subdir")
    os.mkdir(e)
    giles = [os.path.join(e, str(x)) for x in range(10)]
    [ file(f, "w") for f in files + giles ]
    mtimes = [ os.stat(f).st_mtime for f in files + giles ]
    return d, files + giles, mtimes


class DummyTranscoder(transcoders.Transcoder):

    def would_transcode_to(self, from_):
        if from_ == "mp3": return "mp3"
        raise transcoders.CannotTranscode(from_)


class DummyOggToMp3Transcoder(transcoders.Transcoder):

    def would_transcode_to(self, from_):
        if from_ in ["mp3", "ogg"]: return "mp3"
        raise transcoders.CannotTranscode(from_)


class TestParsePlaylists(unittest.TestCase):

    def test_synthetic_playlists(self):
        sources, output = synthetic_playlists_fixtures()
        files, excs = mod.parse_playlists(sources)
        self.assertEquals(files, output)
        self.assertEquals(excs, [])

    def test_nonexistent_playlists(self):
        sources = ["does not exist"]
        files, excs = mod.parse_playlists(sources)
        self.assertEquals(files, {})
        self.assertTrue(excs[0][0], "does not exist")
        self.assertTrue(isinstance(excs[0][1], IOError))


class TestListFilesRecursively(unittest.TestCase):

    def test_simple_case(self):
        d, files, _ = list_files_recursively_fixtures()
        listed_files = mod.list_files_recursively(d)
        listed_files.sort()
        shutil.rmtree(d)
        self.assertEquals(files, listed_files)


class TestScanMtimes(unittest.TestCase):

    def test_mtimes(self):
        f, t = mtimes_fixtures()
        result = list(mod.scan_mtimes([x.name for x in f]))
        [x.close() for x in f]
        self.assertEquals(result[0][1], t[0])
        self.assertEquals(result[1][1], t[1])


class TestVfatProtect(unittest.TestCase):

    def test_noendingdots(self):
        p = mod.vfatprotect("/some/path/with./dots")
        self.assertNotIn(".", p)
        p = mod.vfatprotect("/some/path/with..../many dots")
        self.assertNotIn(".", p)
        p = mod.vfatprotect("/some/path/with /many spaces")
        self.assertNotIn(" /", p)

    def test_nobadchars(self):
        for f in '?<>\\:*|':
            p = mod.vfatprotect("/path/with%sbadchar" % f)
            self.assertNotIn(f, p)

class TestComputeSynchronization(unittest.TestCase):

    def test_simple_case(self):
        m = mod.compute_synchronization({}, "/", {}, "/")
        self.assertEquals(m, ({}, {}, {}))

    def test_identical(self):
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/a":1},
            "/target")
        self.assertEquals(m[0], {})

    def test_older(self):
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/a":0},
            "/target")
        self.assertEquals(m[0], {"/a": "/target/a"})

    def test_absent_target(self):
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {},
            "/target")
        self.assertEquals(m[0], {"/a": "/target/a"})

    def test_absent_source(self):
        m = mod.compute_synchronization(
            {},
            "/",
            {},
            "/target")
        self.assertEquals(m[0], {})

    def test_mapper(self):
        mapper = lambda x, y: x.replace("a", "b")
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/b":1},
            "/target",
            path_mapper=mapper)
        self.assertEquals(m[0], {})
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/b":0},
            "/target",
            path_mapper=mapper)
        self.assertEquals(m[0], {"/a": "/target/b"})

    def test_fat32_windowing(self):
        def fatcompare(s, t):
            x = int(s) - int(t)
            if x >= 2: return 1
            elif x <= -2: return -1
            return 0
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/a":0},
            "/target",
            time_comparator=fatcompare)
        self.assertEquals(m[0], {})
        m = mod.compute_synchronization(
            {"/a":2},
            "/",
            {"/target/a":1},
            "/target",
            time_comparator=fatcompare)
        self.assertEquals(m[0], {})
        m = mod.compute_synchronization(
            {"/a":1},
            "/",
            {"/target/a":2},
            "/target",
            time_comparator=fatcompare)
        self.assertEquals(m[0], {})
        m = mod.compute_synchronization(
            {"/a":4},
            "/",
            {"/target/a":2},
            "/target",
            time_comparator=fatcompare)
        self.assertEquals(m[0], {"/a":"/target/a"})

    def test_complex(self):
        s = {"/source/abc":45, "/source/def":30}
        t = {}
        sp = "/"
        tp = "/target"
        e = {
             "/source/abc":"/target/source/abc",
             "/source/def":"/target/source/def",
        }
        m = mod.compute_synchronization(s, sp, t, tp)
        self.assertEquals(m[0], e)

        sp = "/source"
        e = {
             "/source/abc":"/target/abc",
             "/source/def":"/target/def",
        }
        m = mod.compute_synchronization(s, sp, t, tp)
        self.assertEquals(m[0], e)

        sp = "/source/"
        m = mod.compute_synchronization(s, sp, t, tp)
        self.assertEquals(m[0], e)

        tp = "/target/"
        m = mod.compute_synchronization(s, sp, t, tp)
        self.assertEquals(m[0], e)

        sp = "/source"
        m = mod.compute_synchronization(s, sp, t, tp)
        self.assertEquals(m[0], e)

        sp = "/source/a"
        e = {
             "/source/abc":"/target/../abc",
             "/source/def":"/target/../def",
        }
        self.assertRaises(ValueError,
           lambda: mod.compute_synchronization(s, sp, t, tp))


class TestSynchronizer(unittest.TestCase):

    def setUp(self):
        t = DummyTranscoder()
        self.k = mod.Synchronizer(t)

    def test_parse_playlists(self):
        sources, output = synthetic_playlists_fixtures()
        [ self.k.add_playlist(p) for p in sources ]
        self.k._parse_playlists()
        filelist = self.k.source_files
        self.assertTrue(lambda: len(filelist))
        self.assertEquals(self.k.playlists, sources)
        self.assertEquals(self.k.source_files, output)

    def test_scan_source_files_mtimes(self):
        f, t = mtimes_fixtures()
        p1 = StringIO(f[0].name + "\n" + f[1].name)
        p2 = StringIO(f[1].name)
        [ self.k.add_playlist(p) for p in [p1, p2] ]

        try:
            self.k._parse_playlists()
            self.k._scan_source_files_mtimes()
            self.assertTrue(f[0].name in self.k.source_files)
            self.assertTrue(f[1].name in self.k.source_files)
            self.assertTrue(f[0].name in self.k.source_files_mtimes)
            self.assertTrue(f[1].name in self.k.source_files_mtimes)
            self.assertEquals(self.k.source_files_mtimes[f[0].name], t[0])
            self.assertEquals(self.k.source_files_mtimes[f[1].name], t[1])
        finally:
            [x.close() for x in f]

    def test_scan_source_files_mtimes_nofiles(self):
        self.k._parse_playlists()
        self.assertTrue(lambda: len(self.k.source_files) == 0)
        self.assertTrue(lambda: len(self.k.source_files_mtimes) == 0)

    def test_scan_target_dir(self):
        directory, files, _ = list_files_recursively_fixtures()
        self.k.set_target_dir(directory)
        try:
            self.k._scan_target_dir()
            for f in files: self.assertIn(f, self.k.target_files)
        finally:
            shutil.rmtree(directory)

    def test_scan_target_dir_mtimes(self):
        directory, files, mtimes = list_files_recursively_fixtures()
        self.k.set_target_dir(directory)
        try:
            self.k._scan_target_dir()
            self.k._scan_target_dir_mtimes()
            for f in files:
                self.assertIn(f, self.k.target_files)
                self.assertIn(f, self.k.target_files_mtimes)
                expected_mtimes = dict(zip(files, mtimes))
                self.assertEquals(self.k.target_files_mtimes, expected_mtimes)
        finally:
            shutil.rmtree(directory)

    def test_compute_synchronization(self):
        self.k.set_target_dir("/target")
        self.k.scan_done = True  # simulate scanning done
        self.k.source_files_mtimes = {"/source/a.mp3":5}
        self.k.target_files_mtimes = {"/target/a.mp3":1}
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {"/source/a.mp3": "/target/a.mp3"})

        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {})

        self.k.source_files_mtimes = {"/source/a.ogg":7}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {})

        self.k.set_transcoder(DummyOggToMp3Transcoder())
        self.k.scan_done = True  # simulate scanning done
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {"/source/a.ogg":"/target/a.mp3"})

        self.k.source_files_mtimes = {"/source/a.MP3":4}
        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {})

        self.k.source_files_mtimes = {"/source/a.MP3":7}
        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {'/source/a.MP3': '/target/a.mp3'})

        self.k.source_files_mtimes = {"/source/a.MP3":7, "/source/a.mp3":8}
        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {'/source/a.mp3': '/target/a.mp3',
                                '/source/a.MP3': '/target/a.mp3'})
        ops = self.k.compute_synchronization()[2]
        self.assertEquals(ops, {})

        self.k.source_files_mtimes = {"/source/a.MP3":7}
        self.k.target_files_mtimes = {"/target/a.MP3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {'/source/a.MP3': '/target/a.MP3'})

        self.k.source_files_mtimes = {"/source/a.Ogg":4}
        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {})
        ops = self.k.compute_synchronization()[2]  # the skipped files
        self.assertEquals(ops, {"/source/a.Ogg":"/target/a.mp3"})

        self.k.source_files_mtimes = {"/source/a.OgG":9}
        self.k.target_files_mtimes = {"/target/a.mp3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {'/source/a.OgG': '/target/a.mp3'})

        self.k.source_files_mtimes = {"/source/a.OgG":9}
        self.k.target_files_mtimes = {"/target/a.MP3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()[0]
        self.assertEquals(ops, {'/source/a.OgG': '/target/a.MP3'})

        e = Exception()
        self.k.source_files_mtimes = {"/source/a.OgG":e,
                                    "/source/a.mP3":8}
        self.k.target_files_mtimes = {"/target/a.MP3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()
        self.assertEquals(ops[0], {'/source/a.mP3': '/target/a.MP3'})
        self.assertEquals(ops[1], {'/source/a.OgG': e})

        self.k.source_files_mtimes = {"/invalidsource/a.OgG":e,
                                    "/source/a.mP3":8}
        self.k.target_files_mtimes = {"/target/a.MP3":4}
        self.k.compute_sync_cache = None
        ops = self.k.compute_synchronization()
        self.assertEquals(ops[0], {'/source/a.mP3': '/target/a.MP3'})
        self.assertEquals(ops[1], {'/invalidsource/a.OgG': e})

    def test_synchronize(self):
        old = mod.SynchronizerSlave._synchronize_wrapper
        def compute_synchronization():
            return {"a":"b"}, {}, {}
        def _synchronize_wrapper(self, src, dst):
            return dst
        self.k.compute_synchronization = compute_synchronization
        mod.SynchronizerSlave._synchronize_wrapper = _synchronize_wrapper
        self.k._ensure_directories_exist = lambda _: None
        try:
            sync_tasks = self.k.synchronize()
            number = 0
            for f, result in sync_tasks:
                self.assertEquals(f, "a")
                self.assertEquals(result, "b")
                number += 1
            self.assertEquals(number, 1)
        finally:
            mod.SynchronizerSlave._synchronize_wrapper = old

    def test_bad_synchronize(self):
        self.fired = []
        def compute_synchronization():
            return {"a":"b", "c":"d"}, {}, {}
        def transcode(src, dst):
            raise Exception, "m"
        self.k.compute_synchronization = compute_synchronization
        self.k.transcoder.transcode = transcode
        self.k._ensure_directories_exist = lambda _: None

        sync_tasks = list(self.k.synchronize())
        results = [ x[1] for x in sync_tasks ]
        assert all(isinstance(x, Exception) for x in results)
