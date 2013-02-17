'''
Transcoders!
'''

import shutil
from musictoolbox import old


class CannotTranscode(Exception):
    def __init__(self, source_format):
        self.source_format = source_format

    def __str__(self):
        return "<CannotTranscode from=%s>" % (
                                             self.source_format,
                                           )

    def __repr__(self):
        return "<CannotTranscode from=%r>" % (
                                             self.source_format,
                                           )


class Transcoder:

    def would_transcode_to(self, from_):
        '''
        from_ is a file extension (without the leading dot)
        representing the source file format.  The extension passed by
        the caller must be lowercased by the caller.
        
        This method must return the target format as a file extension,
        or raise CannotTranscode(sfmt) if it cannot transcode the file
        in question.
        '''
        raise NotImplementedError

    def transcode(self, source_file, destination_file):
        '''Transcode source_file into destination_file.  Destination_file
        will be overwritten.
        
        The return value is None.  This function is pure side effects.
        
        This function blocks while the transcoding is happening.
        It does not return a deferred.
        '''
        raise NotImplementedError


class AbsentMindedTranscoder(Transcoder):
    '''Doesn't do anything.'''

    def would_transcode_to(self, from_):
        return from_

    def transcode(self, src, dst):
        pass


class CopyTranscoder(Transcoder):
    '''Implementation of a transcoder that just copies files blindly.'''
    def would_transcode_to(self, from_):
        return from_

    def transcode(self, source_file, destination_file):
        '''Copy source_file into destination_file'''
        shutil.copyfile(source_file, destination_file)


# FIXME: this transcoder should at LEAST detect the formats available
# so it wont fail during sync
class LegacyTranscoder(Transcoder):
    def would_transcode_to(self, from_):
        if from_ in "ogg flac mp3 wav mpc": return "mp3"
        if from_ in "mp4 flv": return "mp4"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        old.transcode_file(src, dst)
