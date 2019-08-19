'''
Transcoders!
'''

import shutil
from musictoolbox import old
import iniparse
from iniparse import INIConfig
import os
import subprocess
try:
    from urllib.request import pathname2url
except ImportError:
    from urllib import pathname2url


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

    def would_transcode_file_to(self, src):
        '''
        src is an existing path.

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

    def transcode(self, src, dst):
        '''Copy source_file into destination_file'''
        shutil.copyfile(src, dst)


# FIXME: this transcoder should at LEAST detect the formats available
# so it wont fail during sync
class LegacyTranscoder(Transcoder):

    def would_transcode_to(self, from_):
        if from_ in "ogg flac mp3 wav mpc": return "mp3"
        if from_ in "mp4 flv": return "mp4"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        old.transcode_file(src, dst)


class FlvMp4WebmToMp3Transcoder(Transcoder):
    '''Transcodes from FLV / MP4 to MP3, avoiding retranscoding if possible.'''

    def would_transcode_to(self, from_):
        if from_ in ["flv", "mp4", "webm", "mkv"]: return "mp3"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        '''Transcode FLV / MP4 to MP3 file'''
        output = subprocess.check_output(
                                        [
                                         "ffprobe",
                                         src
                                         ],
                                         stderr=subprocess.STDOUT,
                                         text=True,
                                         )
        if "Audio: mp3" in output:
            src = "file://" + pathname2url(src)
            subprocess.check_call(
                [
                 "gst-launch-1.0",
                 "giosrc", "location=%s" % src,
                 "!", "flvdemux",
                 "!", "audio/mpeg",
                 "!", "filesink", "location=%s" % dst,
                 ],
                stdin=None,
                stdout=None,
                stderr=None,
                close_fds=True,
            )
        else:
            src = "file://" + pathname2url(src)
            subprocess.check_call(
                [
                 "gst-launch-1.0",
                 "giosrc", "location=%s" % src,
                 "!", "decodebin",
                 "!", "audioconvert",
                 "!", "lamemp3enc", "encoding-engine-quality=2", "quality=0",
                 "!", "filesink", "location=%s" % dst,
                 ],
                stdin=None,
                stdout=None,
                stderr=None,
                close_fds=True,
            )


class ExtractAudioTranscoder(Transcoder):
    '''Simply extracts audio from videos into a file.'''

    def would_transcode_file_to(self, src):
        '''Transcode MP4 to M4A file'''
        output = subprocess.check_output(
                                        [
                                         "ffprobe",
                                         src
                                         ],
                                         stderr=subprocess.STDOUT,
                                         text=True,
                                         )
        if "Audio: mp3" in output:
            return "mp3"
        elif "Audio: aac" in output:
            return "m4a"
        else:
            _, ext = os.path.splitext(src)
            raise CannotTranscode(ext[1:])

    def transcode(self, src, dst):
        subprocess.check_call(
            [
             "ffmpeg",
             "-i", src,
             "-acodec", "copy",
             "-vn",
             dst,
             ],
            stdin=None,
            stdout=None,
            stderr=None,
            close_fds=True,
        )


class FlvMp4WebmToWavTranscoder(Transcoder):
    '''Transcodes from FLV / MP4 to RIFF WAVE 32 bit float.'''

    def would_transcode_to(self, from_):
        if from_ in ["flv", "mp4", "webm", "mkv"]: return "wav"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        '''Transcode FLV / MP4 to RIFF WAVE file'''
        src = "file://" + pathname2url(src)
        subprocess.check_call(
            [
             "gst-launch-1.0",
             "giosrc", "location=%s" % src,
             "!", "decodebin",
             "!", "audioconvert",
             "!", "audio/x-raw,format=F32LE",
             "!", "wavenc",
             "!", "filesink", "location=%s" % dst,
             ],
            stdin=None,
            stdout=None,
            stderr=None,
            close_fds=True,
        )


class AudioToMp3Transcoder(Transcoder):
    '''Transcodes from any audio format to MP3.'''

    def would_transcode_to(self, from_):
        if from_ in ["ogg", "aac", "m4a", "wav", "flac", "mpc"]:
            return "mp3"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        '''Transcode audio file to MP3 file'''
        src = "file://" + pathname2url(src)
        subprocess.check_call(
            [
             "gst-launch-1.0",
             "giosrc", "location=%s" % src,
             "!", "decodebin",
             "!", "audioconvert",
             "!", "lamemp3enc", "encoding-engine-quality=2", "quality=0",
             "!", "filesink", "location=%s" % dst,
             ],
            stdin=None,
            stdout=None,
            stderr=None,
            close_fds=True,
        )


class AudioToWavTranscoder(Transcoder):
    '''Transcodes from any audio format to RIFF WAVE 32 bit float.'''

    def would_transcode_to(self, from_):
        if from_ in ["ogg", "aac", "m4a", "mp3", "flac", "mpc"]:
            return "wav"
        raise CannotTranscode(from_)

    def transcode(self, src, dst):
        '''Transcode audio file to MP3 file'''
        src = "file://" + pathname2url(src)
        subprocess.check_call(
            [
             "gst-launch-1.0",
             "giosrc", "location=%s" % src,
             "!", "decodebin",
             "!", "audioconvert",
             "!", "audio/x-raw,format=F32LE",
             "!", "wavenc",
             "!", "filesink", "location=%s" % dst,
             ],
            stdin=None,
            stdout=None,
            stderr=None,
            close_fds=True,
        )


class ConfigurableTranscoder(Transcoder):
    def __init__(self):
        self.cfg = INIConfig(open(os.path.join(os.path.expanduser("~"),'.syncplaylists.ini')))

    def _lookup_transcoder(self, from_):
        to = getattr(self.cfg.transcoding, from_)
        if isinstance(to, iniparse.config.Undefined):
            to = getattr(self.cfg.transcoding, "*")
        if isinstance(to, iniparse.config.Undefined):
            raise CannotTranscode(from_)

        if to == "copy":
            return CopyTranscoder()

        if to == "extractaudio":
            return ExtractAudioTranscoder()

        known_transcoders = [
                             FlvMp4WebmToMp3Transcoder,
                             AudioToMp3Transcoder,
                             FlvMp4WebmToWavTranscoder,
                             AudioToWavTranscoder,
                             ]

        for t in known_transcoders:
            t = t()
            try:
                can_do = t.would_transcode_to(from_)
            except CannotTranscode:
                continue
            if can_do == to:
                break
        return t

    def would_transcode_to(self, from_):
        return self._lookup_transcoder(from_).would_transcode_to(from_)

    def would_transcode_file_to(self, src):
        from_ = os.path.splitext(src)[1][1:].lower()
        return self._lookup_transcoder(from_).would_transcode_file_to(src)

    def transcode(self, src, dst):
        from_ = os.path.splitext(src)[1][1:].lower()
        transcoder = self._lookup_transcoder(from_)
        return transcoder.transcode(src, dst)
