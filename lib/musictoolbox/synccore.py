'''
Created on Aug 11, 2012

@author: rudd-o
'''

import logging
import os
import signal
from threading import Thread, Lock
from Queue import Queue
import musictoolbox.old

logger = logging.getLogger(__name__)

# ================== generic utility functions ================

def parse_playlists(sources):
    '''
    Take several playlists, and return a dictionary and a list.
    This dictionary is structured as follows:
    - keys: absolute path names mentioned in the playlists
    - values: playlists where the file appeared
    The list is a sequence of (file, Exception) occurred while parsing.
    '''
    files = {}
    excs = []
    for source in sources:
        try:
            sourcename = source
            if hasattr(source, "read"):
                sourcedir = "/"
            else:
                sourcedir = os.path.dirname(source)
                source = file(source)
            thisbatch = [
                     os.path.abspath(
                         os.path.join(sourcedir, x.strip())
                     )
                     for x in source.readlines()
                     if x.strip() and not x.strip().startswith("#")
            ]
            for path in thisbatch:
                if path not in files: files[path] = []
                files[path].append(sourcename)
        except Exception, e:
            excs.append((source, e))
    return files, excs

def scan_mtimes(filelist):
    '''Take a list of files, and yield tuples (path, mtime or Exception).
    
    The dictionary value for a particular key may contain an
    exception in lieu of an mtime.  This means that scanning
    the key failed.
    '''
    def mtimeorexc(x):
        try:
            return os.stat(f).st_mtime
        except Exception, e:
            return e

    for f in filelist:
        yield f, mtimeorexc(f)

def chunkify(longlist, nchunks):
    return [
          longlist[i::nchunks]
          for i in xrange(nchunks)
          if longlist[i::nchunks]
    ]

def merge_dicts(d):
    '''take a list of dicts and merge it into a single dict'''
    r = {}
    map(r.update, d)
    return r

def get_deferredlist_return_column(x):
    '''take a table of deferredlist's (result, return) outputs and return
    only the return column.'''
    if x: return zip(*x)[1]
    return x

def assert_deferredlist_succeeded(result):
    if result:
        assert all(x is True for x in zip(*result)[0]), "deferredlist failed: %r" % result
    return result

def list_files_recursively(directory):
    '''Return a list of absolute paths from recursively listing a directory'''
    return [
            os.path.abspath(os.path.join(base, f))
            for base, _, files in os.walk(directory)
            for f in files
            ]

def vfatprotect(f):
    for illegal in '?<>\\:*|"^': f = f.replace(illegal, "_")
    while "./" in f: f = f.replace("./", "/")
    while " /" in f: f = f.replace(" /", "/")
    return f

def fatcompare(s, t):
    x = int(s) - int(t)
    if x >= 2: return 1
    elif x <= -2: return -1
    return 0

def compute_synchronization(
    sources, sourcedir,
    targets, targetdir,
    path_mapper=lambda x, y: x,
    time_comparator=lambda x, y: 1 if x > y else 0 if x == y else -1,
    unconditional=False,
    ):
    '''
    Compute a synchronization schedule based on a dictionary of
    {source_filename:mtime} and a dictionary of {target_filename:mtime}.
    Paths must be absolute or the behavior of this function is undefined.
    All paths must be contained in their respective specified directories.
    mtime in the source dictionary can be an exception, in which case it will
    be presumed that the source file in question cannot be transferred.

    The synchronization aims to discover the target file names based on
    the source file names, and then automatically figure out which files
    need to be transferred, based on their absence in the remote site,
    or their modification date.

    This function accepts a path mapping callable that will transform
    a partial source file name, and the full path to the source file name,
    into the desired partial target file name prior to performing the
    date comparison.  By default, it is an identity function x, y => x.

    This function also accepts a time comparator function that will
    be used to perform the comparison between source and target
    modification times.  The comparator is the standard 1 0 -1 comparator
    that takes x,y where it returns 1 if x > y, 0 if x and y are identical,
    and -1 if x < y.  The comparator gets passed the source mtime as the
    first parameter, and the target mtime as the second parameter.
    FAT file system users may want to pass a custom comparator that takes
    into consideration the time resolution of FAT32 file systems
    (greater than 2 seconds). 

    Return two dictionaries:
        1. a dictionary {s:t} where s is the source file name, and
           t is the desired target file name after transfer.
        2. a dictionary {s:e} where s is the source file name, and
           e is the exception explaining why it cannot be synced
    '''

    wont_transfer = dict([
        (k, v) for k, v in sources.items()
        if isinstance(v, Exception)
    ])
    source_mtimes = dict([
        (k, v) for k, v in sources.items()
        if not isinstance(v, Exception)
    ])
    source_files = source_mtimes.keys()
    source_basedir = sourcedir
    target_mtimes = targets
    target_files = target_mtimes.keys()
    target_basedir = os.path.abspath(targetdir)

    test = source_basedir + os.path.sep \
           if source_basedir[-len(os.path.sep)] != os.path.sep \
           else source_basedir
    for k in source_files:
        if not k.startswith(test):
            raise ValueError, \
                "source path %r not within source dir %r" % (k, source_basedir)

    test = target_basedir + os.path.sep \
           if target_basedir[-len(os.path.sep)] != os.path.sep \
           else target_basedir
    for k in target_files:
        if not k.startswith(test):
            raise ValueError, \
                "target path %r not within target dir %r" % (k, target_basedir)

    desired_target_files = []
    new_source_files = []
    for p in source_files:
        try:
            desired_target_files.append(os.path.join(
                target_basedir, path_mapper(
                    os.path.relpath(p, start=source_basedir), p
                )
            ))
            new_source_files.append(p)
        except Exception, e:
            wont_transfer[p] = e
    source_files = new_source_files

    # desired target to original source map
    dt2s_map = dict(zip(desired_target_files, source_files))
    need_to_transfer = dict([
         (s, t) for t, s in dt2s_map.items()
         if t not in target_files
         or time_comparator(source_mtimes[s], target_mtimes[t]) > 0
         or unconditional
    ])

    return need_to_transfer, wont_transfer


_dir_lock = Lock()


def ensure_directories_exist(dirs):
    with _dir_lock:
        for t in dirs:
            if not t:
                continue
            if not os.path.exists(t):
                os.makedirs(t)

#==================================================================


#===================== synchronizer code ==========================

class SynchronizerSlave(Thread):
    def __init__(self, work, outqueue, transcoder, postprocessor):
        Thread.__init__(self)
        self.work = work
        self.outqueue = outqueue
        self.stopped = False
        self.transcoder = transcoder
        self.postprocessor = postprocessor

    def run(self):
        for src, dst in self.work:
            if self.stopped: break
            try:
                self._synchronize_wrapper(src, dst)
                self.outqueue.put((src, dst))
            except BaseException, e:
                self.outqueue.put((src, e))
        self.outqueue.put(None)

    def _synchronize_wrapper(self, s, d):
        # adapt the transcoder interface to return the source file
        # because the transcoder returns old and new formats
        target_dir, target_file = os.path.dirname(d), os.path.basename(d)
        tempf = 'tmp-' + target_file
        try:
            ensure_directories_exist([target_dir])
        except BaseException:
            try:
                os.rmdir(target_dir)
            except Exception:
                pass
            raise

        tempdest = os.path.join(target_dir, tempf)
        try:
            newext = self.transcoder.transcode(s, tempdest)
            self.postprocessor(s, tempdest, target_format=newext)
        except BaseException:
            try:
                os.unlink(tempdest)
            except Exception:
                pass
            raise
        if (os.stat(tempdest).st_size == 0
            and
            os.stat(s).st_size != 0):
            os.unlink(tempdest)
            raise AssertionError, ("we expected the transcoded file to be "
                                   "larger than 0 bytes")
        if newext is not None:
            dpath, _ = os.path.splitext(d)
            d = dpath + "." + newext
        os.rename(tempdest, d)
        return d

    def stop(self):
        self.stopped = True


class Synchronizer(object):

    playlists = None
    target_dir = None

    source_files = None
    source_files_mtimes = None

    _target_files = None
    def _get_target_files(self):
        return self._target_files
    def _set_target_files(self, target_files):
        self._target_files = target_files
        # as a concession to the _fatmapper method which needs to
        # recall the proper casing of already-existing paths
        # we create a cache of such beasts so we can look up the proper
        # casing on any existing file
        self.target_lower_to_canonical_map = dict([
             (
              os.path.relpath(p, start=self.target_dir).lower(),
              os.path.relpath(p, start=self.target_dir)
             )
             for p in target_files
        ])
    target_files = property(
                            _get_target_files,
                            _set_target_files
                            )

    _target_files_mtimes = None
    def _get_target_files_mtimes(self):
        return self._target_files_mtimes
    def _set_target_files_mtimes(self, target_files_mtimes):
        # since test code manually sets the files_mtimes without setting
        # the files list, we refresh the files list using the keys
        # of this lookup
        self._target_files_mtimes = target_files_mtimes
        self.target_files = target_files_mtimes.keys()
    target_files_mtimes = property(
                                   _get_target_files_mtimes,
                                   _set_target_files_mtimes
                                   )

    def __init__(self, transcoder):
        '''
        Class instance initializer.
        
        transcoder must be a Transcoder instance that Synchronizer
        can query to determine the target formats available and what
        formats the files will be transcoded to.
        '''
        self.playlists = []
        self.target_dir = None
        self.source_files = {}
        self.source_files_mtimes = {}
        self.target_files = []
        self.target_files_mtimes = {}
        self.transcoder = transcoder

    def set_transcoder(self, transcoder):
        '''Change to a different transcoder'''
        self.transcoder = transcoder

    def set_target_dir(self, target_dir):
        self.target_dir = target_dir

    def add_playlist(self, playlist):
        self.playlists.append(playlist)

    def scan(self):
        """Scan all files needed to compute synchronization.

        Returns a list of (path, Exception)."""
        excs = []

        logger.info("Parsing %s playlists", len(self.playlists))
        excs.extend(self.parse_playlists())
        logger.info("Discovered %s source files",
                    len(self.source_files))

        logger.info("Scanning target directory %s", self.target_dir)
        excs.extend(self.scan_target_dir())
        logger.info("Discovered %s target files", len(self.target_files))

        logger.info("Scanning %s source files mtimes",
                    len(self.source_files))
        excs.extend(self.scan_source_files_mtimes())
        logger.info("Scanned %s source files mtimes",
                    len(self.source_files_mtimes))

        logger.info("Scanning %s target files mtimes",
                    len(self.target_files))
        excs.extend(self.scan_target_dir_mtimes())
        logger.info("Scanned %s target files mtimes",
                    len(self.target_files_mtimes))

        return excs

    def parse_playlists(self):
        '''
        scan the playlists known to the synchronizer and obtain a list
        of files.

        when done, update self.source_files with the files discovered
        from the playlists, then return exceptions that happened during
        parsing, as a list of tuples (file, exception).

        It is not an error to call this method before having used
        add_playlist(), but it will produce no result.

        This operation blocks.
        '''
        self.source_files, excs = parse_playlists(self.playlists)
        return excs

    def __generic_scan_mtimes_of_file_list(self, filenames):
        '''
        scan files in file_list for their modification
        times. do the scan in parallel for maximum performance.
        Returns dictionary {filename: mtime or Exception}.
        
        This operation blocks.
        '''
        chunks = chunkify(filenames, 8)
        # FIXME TODO hardcoded 8

        class MtimeScanner(Thread):
            def __init__(self, queue, files):
                Thread.__init__(self)
                self.queue = queue
                self.files = files
            def run(self):
                for ret in scan_mtimes(self.files):
                    self.queue.put(ret)
                self.queue.put(None)

        queue = Queue()
        threads = [ MtimeScanner(queue, c) for c in chunks ]
        [ t.start() for t in threads ]
        donecount = 0
        resultdict = {}
        while donecount < len(chunks):
            val = queue.get()
            if val is None:
                donecount += 1
            else:
                resultdict[val[0]] = val[1]
        [ t.join() for t in threads ]
        return resultdict

    def scan_source_files_mtimes(self):
        '''
        scan all the files in source_files for their modification
        times. do the scan in parallel for maximum performance.
        
        this function must be called after self.parse_playlists()
        
        when done, update self.source_files_mtimes with the modification
        times of all files in self.source_files. 
        
        It is not an error to call this method before having used
        scan_source_files(), but it will produce no result.
        
        This operation blocks.
        '''
        filenames = self.source_files.keys()
        files_mtimes = self.__generic_scan_mtimes_of_file_list(filenames)
        self.source_files_mtimes = files_mtimes
        return [ x for x in self.source_files_mtimes.items()
                if isinstance(x[1], Exception) ]

    def scan_target_dir(self):
        '''
        scan the target dir known to the synchronizer.  the scan is
        done in a serialized manner.
        
        when done, update self.target_files with a list of all known files
        in self.target_dir.
        
        It is an error to call this method before set_target_dir()
        
        This operation blocks.
        '''
        try:
            d = list_files_recursively(self.target_dir)
            self.target_files = d
            return []
        except Exception, e:
            return [(self.target_dir, e)]

    def scan_target_dir_mtimes(self):
        '''
        scan all the files in target_files for their modification
        times. do the scan in parallel for maximum performance.
        
        this function must be called after self.scan_target_dir()
        
        when done, update self.target_files_mtimes with the modification
        times of all files in self.target_files. 
        
        It is not an error to call this method before having used
        scan_target_dir(), but it will produce no result.
        
        This operation blocks.
        '''
        filenames = self.target_files
        files_mtimes = self.__generic_scan_mtimes_of_file_list(filenames)
        self.target_files_mtimes = files_mtimes
        return [ x for x in self.target_files_mtimes.items()
                if isinstance(x[1], Exception) ]

    def _fatmapper(self, path, originalpath):
        # the mapper function needs to take FAT32 into account, and needs
        # to know which file formats the targets will be, so it will ask
        # the transcoder about that
        # since FAT32 is case-insensitive but case-preserving, we look
        # up the path in a cache, to select the preferred path
        base, ext = os.path.splitext(path)
        # if the file has an extension
        if ext:
            # split the extension and the dot proper
            dot, ext = ext[0], ext[1:]
            # look the lowercased extension up
            try:
                newext = self.transcoder.would_transcode_to(ext.lower())
            except NotImplementedError:
                newext = self.transcoder.would_transcode_file_to(originalpath)

            # if something came back from the lookup:
            if newext:
                # if the extension is the same, just use the original
                if newext.lower() == ext.lower(): newext = ext
                # and reconstitute the dotted extension
                ext = dot + newext
        path = base + ext
        path = vfatprotect(path)
        if path.lower() in self.target_lower_to_canonical_map:
            path = self.target_lower_to_canonical_map[path.lower()]
        return path

    # now for the comparison function, which works properly on FAT32
    def _fatcompare(self, s, t):
        return fatcompare(s, t)

    def compute_synchronization(self, unconditional=False):
        '''Computes synchronization between sources and target.
        
        You must have already parsed the playlists, scanned the target
        directory, and scanned the mtimes of all sources and targets.
        
        This function does not block.  It returns a pair of dictionaries
        where the first dictionary is a manifest of synchronization operations
        {source:target} that must be executed to bring the target up-to-date
        with respect to the source, and the second dictionary is a manifest
        of {source:reason} where source is a source path name and reason
        is an exception explaining why it won't be transferred.
        
        This function has a preference for FAT32 target file systems. In
        an ideal world, it would detect the file system capabilities of
        the target file system.
        '''
        # let's generate the source basedir
        # due to a problem in os.path.commonprefix
        # where two paths /a/bbb/ccc/ddd.mp3
        # and             /a/bbb/cc catch/cadillac.mp3
        # return /a/bbb/cc instead of /a/bbb/
        # we check that the commonprefix is terminated by a slash
        # and if not, we eat up the end of the string until a slash
        # appears, or the string disappears (in which case => /)
        source_basedir = os.path.commonprefix([
            k for k, v in self.source_files_mtimes.items()
            if not isinstance(v, Exception)
        ])

        while source_basedir and source_basedir[-1] != os.path.sep:
            source_basedir = source_basedir[:-len(os.path.sep)]
        if not source_basedir: source_basedir = os.path.sep

        # now we filter source files according to whether they can
        # be transcoded or not, since we won't be transferring the ones
        # that cannot be transcoded
        # we lowercase the extension in order to look it up properly
        # because the transcoder may not understand uppercase ones

        source_files_mtimes = dict(self.source_files_mtimes.items())

        need_to_transfer, wont_transfer = compute_synchronization(
            source_files_mtimes,
            source_basedir,
            self.target_files_mtimes,
            self.target_dir,
            path_mapper=self._fatmapper,
            time_comparator=self._fatcompare,
            unconditional=unconditional,
        )
        return need_to_transfer, wont_transfer

    def synchronize(self, concurrency=1):
        '''
        Computes synchronization between sources and target, then
        gets ready to sync using a thread pool, dispatching tasks to it.
        The start of the sync process happens immediately.

        The entry conditions for this function are the same as the conditions
        for the self.compute_synchronization function. You must wait until
        a synchronization is done to synchronize again.

        This function blocks.  As it processes files in its plan, it returns
        a tuple (source_file:destination_file or Exception).
        '''
        queue = Queue()
        will_sync, _ = self.compute_synchronization()
        if not will_sync.items():
            return

        chunks = chunkify(will_sync.items(), concurrency)
        threads = [ SynchronizerSlave(chunk,
                                      queue,
                                      self.transcoder,
                                      musictoolbox.old.transfer_tags)
                    for chunk in chunks ]
        [ t.start() for t in threads ]
        ended = 0
        logger.info("Synchronizing with %s threads for %s work items",
                    len(threads), len(will_sync.items()))

        try:
            while ended < len(chunks):
                val = queue.get()
                if val is None:
                    ended += 1
                    logger.info("Thread %s is done", ended)
                else:
                    yield val
        finally:
            logger.info("Stopping and joining all %s threads", len(threads))
            [ t.stop() for t in threads ]
            [ t.join() for t in threads ]
            logger.info("Ended synchronization")

    def synchronize_playlists(self):
        '''
        Once synchronization of files has been done, synchronization of
        playlists is possible.

        The entry conditions for this function are the same as the entry
        conditions of synchronize().

        It returns a list of (target path, Exception).

        This function blocks with impunity.
        '''
        # FIXME if adding params to the following call, add them above too
        will_sync, wont_sync = self.compute_synchronization(unconditional=True)

        target_playlist_dir = os.path.join(self.target_dir, "Playlists")
        try:
            ensure_directories_exist([target_playlist_dir])
        except Exception, e:
            return [(target_playlist_dir, e)]

        excs = []
        for p in self.playlists:
            newp = os.path.join(target_playlist_dir, os.path.basename(p))
            try:
                pdir = os.path.dirname(p)
                pf = open(p)
                pfl = pf.readlines()
                newpfl = []
                for l in pfl:
                    if not l.startswith("#"):
                        oldl = "# was: " + l
                        l = l.strip()
                        truel = os.path.abspath(os.path.join(pdir, l))
                        if truel in will_sync:
                            l = will_sync[truel]
                            l = os.path.relpath(l, target_playlist_dir)
                        elif truel in wont_sync:
                            l = "# not synced because of %s" % wont_sync[truel]
                        elif not l:
                            oldl = ""
                        else:
                            assert 0, l
                        l = l + "\n"
                        l = oldl + l
                    newpfl.append(l)
                newpf = open(newp, "wb")
                newpf.writelines(newpfl)
                newpf.flush()
                newpf.close()
                pf.close()
            except Exception, e:
                excs.append((newp, e))
        return excs

#=================== end synchronizer code ========================
