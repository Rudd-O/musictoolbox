'''
Created on Aug 11, 2012

@author: rudd-o
'''

import os
import multiprocessing
from twisted.internet import reactor, threads
from twisted.internet.defer import DeferredList
from twisted.python.threadpool import ThreadPool
from twisted.internet.threads import deferToThreadPool
from musictoolbox.transcoders import CannotTranscode
from musictoolbox.old import transfer_tags

# ================== generic utility functions ================

def parse_playlists(sources):
    '''
    Take several playlists, and return a dictionary.
    This dictionary is structured as follows:
    - keys: absolute path names mentioned in the playlists
    - values: playlists where the file appeared
    '''
    files = {}
    for source in sources:
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
    return files

def scan_mtimes(filelist):
    '''Take a list of files, and return a dictionary
    with a list of files and their modification times
    
    The dictionary value for a particular key may contain an
    exception in lieu of an mtime.  This means that scanning
    the key failed.
    '''
    def mtimeorexc(x):
        try:
            return os.stat(f).st_mtime
        except (IOError, OSError), e:
            return e

    return dict([ (f, mtimeorexc(f)) for f in filelist ])

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
    path_mapper=lambda x: x,
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
    the source file names into the desired target file names prior to
    performing the comparison.  By default, it is an identity function.
    
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
    target_basedir = targetdir

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

    desired_target_files = [
        os.path.join(
             target_basedir, path_mapper(
                 os.path.relpath(p, start=source_basedir)
             )
        )
        for p in source_files
    ]

    # desired target to original source map
    dt2s_map = dict(zip(desired_target_files, source_files))
    need_to_transfer = dict([
         (s, t) for t, s in dt2s_map.items()
         if t not in target_files
         or time_comparator(source_mtimes[s], target_mtimes[t]) > 0
         or unconditional
    ])

    return need_to_transfer, wont_transfer

#==================================================================


#===================== synchronizer code ==========================

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

    def parse_playlists(self):
        '''
        scan the playlists known to the synchronizer and obtain a list
        of files.
        
        when done, update self.source_files with the files discovered
        from the playlists. 
        
        It is not an error to call this method before having used
        add_playlist(), but it will produce no result.
        
        this operation blocks -- as such, it returns a deferred
        '''

        d = threads.deferToThread(lambda: parse_playlists(self.playlists))
        def done(files):
            self.source_files = files
            return files
        d.addCallback(done)
        return d

    def __generic_scan_mtimes_of_file_list(self, filenames):
        '''
        scan files in file_list for their modification
        times. do the scan in parallel for maximum performance.
        
        this operation blocks -- as such, it returns a deferred
        '''
        chunks = chunkify(filenames, 8)
        # FIXME TODO hardcoded 8

        deferreds = [
             threads.deferToThread(scan_mtimes, c)
             for c in chunks
        ]

        d = DeferredList(deferreds)
        d.addCallback(assert_deferredlist_succeeded)
        d.addCallback(get_deferredlist_return_column)
        d.addCallback(merge_dicts)
        return d

    def scan_source_files_mtimes(self):
        '''
        scan all the files in source_files for their modification
        times. do the scan in parallel for maximum performance.
        
        this function must be called after self.parse_playlists()
        
        when done, update self.source_files_mtimes with the modification
        times of all files in self.source_files. 
        
        It is not an error to call this method before having used
        scan_source_files(), but it will produce no result.
        
        this operation blocks -- as such, it returns a deferred
        '''
        filenames = self.source_files.keys()
        d = self.__generic_scan_mtimes_of_file_list(filenames)
        def done(files_mtimes):
            self.source_files_mtimes = files_mtimes
            return files_mtimes
        d.addCallback(done)
        return d

    def scan_target_dir(self):
        '''
        scan the target dir known to the synchronizer.  the scan is
        done in a serialized manner.
        
        when done, update self.target_files with a list of all known files
        in self.target_dir.
        
        It is an error to call this method before set_target_dir()
        
        this operation blocks -- as such, it returns a deferred
        '''

        d = threads.deferToThread(list_files_recursively, self.target_dir)
        def done(files):
            self.target_files = files
            return files
        d.addCallback(done)
        return d

    def scan_target_dir_mtimes(self):
        '''
        scan all the files in target_files for their modification
        times. do the scan in parallel for maximum performance.
        
        this function must be called after self.scan_target_dir()
        
        when done, update self.target_files_mtimes with the modification
        times of all files in self.target_files. 
        
        It is not an error to call this method before having used
        scan_target_dir(), but it will produce no result.
        
        this operation blocks -- as such, it returns a deferred
        '''
        filenames = self.target_files
        d = self.__generic_scan_mtimes_of_file_list(filenames)
        def done(files_mtimes):
            self.target_files_mtimes = files_mtimes
            return files_mtimes
        d.addCallback(done)
        return d

    def _fatmapper(self, path):
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
            newext = self.transcoder.would_transcode_to(ext.lower())
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
        source_basedir = os.path.commonprefix(self.source_files_mtimes.keys())

        while source_basedir and source_basedir[-1] != os.path.sep:
            source_basedir = source_basedir[:-len(os.path.sep)]
        if not source_basedir: source_basedir = os.path.sep

        # now we filter source files according to whether they can
        # be transcoded or not, since we won't be transferring the ones
        # that cannot be transcoded
        # we lowercase the extension in order to look it up properly
        # because the transcoder may not understand uppercase ones

        source_files_mtimes = dict(self.source_files_mtimes.items())
        for f in source_files_mtimes.keys():
            try:
                ext = os.path.splitext(f)[1][1:].lower()
                self.transcoder.would_transcode_to(ext)
            except CannotTranscode, e:
                source_files_mtimes[f] = e

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

    def ensure_directories_exist(self, dirs):
        for t in dirs:
            if not t:
                continue
            if not os.path.exists(t):
                os.makedirs(t)

    def synchronize(self, concurrency=1):
        '''
        Computes synchronization between sources and target, then
        gets ready to sync using a thread pool, dispatching tasks to it.
        The start of the sync process happens immediately.
        
        The entry conditions for this function are the same as the conditions
        for the self.compute_synchronization function. You must wait until
        a synchronization is done to synchronize again.
        
        This function does not block.  It returns one thing only:
              a dictionary {source_file:deferred), one per dispatched task:
              each deferred fires when the particular task associated to the
              source_file is done, sending the destination path as the result
              to its callback.
              if the sync is cancelled while in progress or otherwise fails,
              the errback will fire instead, receiving a failure instance.
        '''
        def transcode(s, d):
            # adapt the transcoder interface to return the source file
            # because the transcoder returns old and new formats
            tempp, tempf = os.path.dirname(d), os.path.basename(d)
            tempf = 'tmp-' + tempf
            tempd = os.path.join(tempp, tempf)
            try:
                self.transcoder.transcode(s, tempd)
                transfer_tags(s, tempd)
            except Exception, e:
                try:
                    os.unlink(tempd)
                except Exception:
                    pass
                raise e
            if os.stat(tempd).st_size == 0:
                os.unlink(tempd)
                raise AssertionError, ("we expected the transcoded file to be "
                                       "larger than 0 bytes")
            os.rename(tempd, d)
            return d

        # FIXME if adding params to the following call, add them below too
        will_sync, _ = self.compute_synchronization()

        # create the directories
        target_dirs = set([ os.path.dirname(m) for m in will_sync.values()])
        self.ensure_directories_exist(target_dirs)

        # dispatch execution of transcoders
        self.sync_pool = ThreadPool(maxthreads=concurrency,
                                    minthreads=concurrency)
        self.sync_tasks = {}
        for src, dst in will_sync.items():
            self.sync_tasks[src] = \
                deferToThreadPool(
                  reactor,
                  self.sync_pool,
                  transcode,
                  src,
                  dst,
                )
        def sync_done(result):
            self.src_to_dst_map = will_sync
            self.sync_pool.stop()

        self.sync_pool.start()
        sync_done_trigger = DeferredList(self.sync_tasks.values())
        sync_done_trigger.addCallback(sync_done)
        return self.sync_tasks

        # FIXME: make sure that all the deferreds heave fired with
        # completion information
        # and those which weren't done, fire with a Cancelled exception
        # otherwise the DeferredList will forever be not completed

    def synchronize_playlists(self):
        '''
        Once synchronization of files has been done, synchronization of
        playlists is possible.

        The entry conditions for this function are the same as the entry
        conditions of synchronize().

        This function blocks with impunity.
        '''
        # FIXME if adding params to the following call, add them above too
        will_sync, wont_sync = self.compute_synchronization(unconditional=True)

        target_playlist_dir = os.path.join(self.target_dir, "Playlists")
        self.ensure_directories_exist([target_playlist_dir])

        for p in self.playlists:
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
            newp = os.path.join(target_playlist_dir, os.path.basename(p))
            newpf = open(newp, "wb")
            newpf.writelines(newpfl)
            newpf.flush()
            newpf.close()
            pf.close()


        # FIXME: make sure that all the deferreds heave fired with
        # completion information
        # and those which weren't done, fire with a Cancelled exception
        # otherwise the DeferredList will forever be not completed


#=====================================================
