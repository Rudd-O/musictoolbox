#!/usr/bin/env python

import sys
import os
import glob
import subprocess
import string
import signal
import logging
import select
import tempfile
import urllib
import urlparse
import threading
import Queue
import multiprocessing
import time

import mutagen
from mutagen.apev2 import APEv2
from mutagen.id3 import ID3, TXXX
import mutagen.flac
import mutagen.apev2
import mutagen.id3
import mutagen.easyid3
import mutagen.mp3
import mutagen.oggvorbis
import mutagen.musepack




def log(fmt,*args):
	if not args: sys.stderr.write(fmt + "\n")
	else: sys.stderr.write(fmt%args + "\n")
	sys.stderr.flush()

def fixopen(*args,**kwargs):
	# workaround some of my FLAC files have ID3 tags
	# and that causes problems for mutagen
	filename = args[0]
	if filename.lower().endswith(".flac"): return mutagen.flac.Open(*args,**kwargs)
	else:						  return mutagen.File(*args,**kwargs)

def command_available(cmd):
    try: subprocess.call([cmd],stdout=file(os.devnull),stderr=file(os.devnull))
    except OSError, e:
        if e.errno == 2: return False
        raise
    except subprocess.CalledProcessError, e:
        if e.returncode == 127: return False
    return True

# ======= mp3gain and soundcheck operations ==========

def transform_keys(f,d):
	for k,v in d.items():
		if f(k) != k:
			del d[k]
			d[f(k)] = v
	return d

def convert_gain_from_mp3gain_to_txxx(gain):
	assert type(gain) in (str,unicode)
	if gain[-3:] == " dB": gain = gain[:-3]
	try: gain = float(gain)
	except ValueError: raise ValueError, "invalid gain value %r"%gain
	return "%.2f dB" % gain

def convert_peak_from_mp3gain_to_txxx(peak):
	assert type(peak) in (str,unicode)
	try: peak = float(peak)
	except ValueError: raise ValueError, "invalid peak value %r"%peak
	return "%.6f" % peak

def convert_gain_from_txxx_to_mp3gain(gain):
	assert type(gain) in (str,unicode)
	if gain[-3:] == " dB": gain = gain[:-3]
	try: gain = float(gain)
	except ValueError: raise ValueError, "invalid gain value %r"%gain
	if gain >= 0.0: return "+%f dB" % gain
	return "%f dB" % gain

REPLAYGAIN_TAGS = (
	("replaygain_track_gain", convert_gain_from_mp3gain_to_txxx,convert_gain_from_txxx_to_mp3gain),
	("replaygain_track_peak", convert_peak_from_mp3gain_to_txxx,lambda x: x),
	("replaygain_album_gain", convert_gain_from_mp3gain_to_txxx,convert_gain_from_txxx_to_mp3gain),
	("replaygain_album_peak", convert_peak_from_mp3gain_to_txxx,lambda x: x),
)

def viewmp3norm(files):
	while files:
		file = files.pop(0)

		print 
		print file

		try: tags = ID3(file)
		except Exception,e:
			print "No ID3 tags",e
			tags = None
		try: apetags = APEv2(file)
		except Exception,e:
			print "No APE tags",e
			apetags = None

		if apetags:
			print "===APE tags===="
			for key,tag in apetags.items():
				print "%30s"%key,"  ",repr(tag)

		if tags:
			print "===RVA2 tags==="
			for key,tag in tags.items():
				try:
					if tag.desc.lower() in [ x[0] for x in REPLAYGAIN_TAGS ]:
						print "%30s"%key,"  ",repr(tag)
				except AttributeError: continue

def detect_broken_ape_tags(files):
	while files:
		f = files.pop(0)
		try:
			apetags = APEv2(f)
		except mutagen.apev2.APENoHeaderError:
			pass
		except KeyError, e:
			print f
		except Exception, e:
			print >> sys.stderr, "while processing %r: %s" % (f, e)


def detect_missing_ape_tags(files):
	while files:
		f = files.pop(0)
		try:
			apetags = APEv2(f)
		except mutagen.apev2.APENoHeaderError:
			print f
		except KeyError, e:
			pass
		except Exception, e:
			print >> sys.stderr, "while processing %r: %s" % (f, e)


def viewtags(files):
	while files:
		file = files.pop(0)

		print 
		print file

		try: tags = ID3(file)
		except Exception,e:
			print "No ID3 tags",e
			tags = None
		try: apetags = APEv2(file)
		except Exception,e:
			print "No APE tags",e
			apetags = None

		if apetags:
			print "===APE tags===="
			for key,tag in apetags.items():
				print "%30s"%key,"  ",repr(tag)

		if tags:
			print "===ID3 tags==="
			for key,tag in tags.items():
				print "%30s"%key,"  ",repr(tag)


def get_mp3gain_tags(filename):
	"""Helper function
	returns None or a 4-tuple in the order of the above tuple.  some of the values may be None
	"""
	try: i = mutagen.apev2.APEv2(filename)
	except mutagen.apev2.APENoHeaderError: return
	vals = []
	transform_keys(str.lower,i)
	for t in [ x[0] for x in REPLAYGAIN_TAGS ]:
		try: vals.append(i[t])
		except KeyError: vals.append(None)
	def f(s):
		if s: return unicode(s)
		else: return None
	if any(vals): return [ f(s) for s in vals ]

def get_txxx_tags(filename):
	"""Helper function"""
	try: i = mutagen.id3.ID3(filename)
	except mutagen.id3.ID3NoHeaderError: return
	vals = []
	for t in [ "TXXX:%s"%x[0] for x in REPLAYGAIN_TAGS ]:
		try: vals.append(str(i[t]))
		except KeyError: vals.append(None)
	if any(vals): return [str(s) for s in vals]

def decimalToASCIIHex (number):
	return "%08X"%number

def gain2sc (gain,base):
	result = round((10 ** (-gain / 10.0)) * base);
	if (result > 65534): result = 65534
	return decimalToASCIIHex(result)

def replaygain_to_soundcheck(gain):
	if type(gain) in (str,unicode): gain = float(gain)
	soundcheck = [ gain2sc(gain, 1000), gain2sc(gain, 1000), gain2sc(gain, 2500), gain2sc(gain, 2500) ]
	soundcheck.append("00024CA8")
	soundcheck.append("00024CA8")
	soundcheck.append("00007FFF")
	soundcheck.append("00007FFF")
	soundcheck.append("00024CA8")
	soundcheck.append("00024CA8")
	return " "+" ".join(soundcheck)

def write_soundcheck_tag(filename,text):
	metadata = mutagen.id3.Open(filename)
	metadata["COMM:iTunNORM:'eng'"] = mutagen.id3.COMM(
			encoding=3,
			lang="eng",
			desc="iTunNORM",
			text=[unicode(text)])
	metadata.save()

def recalc_soundcheck(filename,mp3gain_values):
	type = config_soundcheck_uses
	assert len(mp3gain_values) == 4
	tg,tp,ag,ap = mp3gain_values
	if type is MP3GAIN_ALBUM:	   	values = [ag,tg]
	elif type is MP3GAIN_TRACK:	values = [tg,ag]
	values = [ v for v in values if v is not None ]
	if not values: return
	value = float(values[0].split()[0])
	debug("Recalculating Soundcheck values")
	tagcontent = replaygain_to_soundcheck(value)
	write_soundcheck_tag(filename,tagcontent)

def mp3gain_to_txxx(filename):
	i = mutagen.apev2.APEv2(filename)
	try: o = mutagen.id3.ID3(filename)
	except mutagen.id3.ID3NoHeaderError: o = mutagen.id3.ID3()
	changed = False
	for name,f,g in REPLAYGAIN_TAGS:
		if name.lower() in i: name = name.lower()
		elif name.upper() in i: name = name.upper()
		else: continue
		o[name] = mutagen.id3.TXXX(desc=name.lower(),encoding=1,text=f(unicode(i[name])))
		changed = True
	if changed: o.save(filename)

def txxx_to_mp3gain(filename):
	i = mutagen.id3.ID3(filename)
	try: o = mutagen.apev2.APEv2(filename)
	except mutagen.apev2.APENoHeaderError: o = mutagen.apev2.APEv2()
	changed = False
	for name,f,g in REPLAYGAIN_TAGS:
		try:
			o[name.upper()] = g(unicode(i["TXXX:%s"%name])) ; changed = True
		except KeyError: pass
	if changed: o.save(filename)

def cohere_replaygain_tags(filename):
	debug("Cohering replaygain tags for %r",filename)
	if type(filename) is list:
		for x in filename: cohere_replaygain_tags(x)
		return
	
	mp3gain_tags = get_mp3gain_tags(filename)
	txxx_tags = get_txxx_tags(filename)
	if mp3gain_tags:
		debug("Transforming mp3gain ReplayGain info into TXXX")
		mp3gain_to_txxx(filename) # needs to be done because mp3gain may
							# have altered its values with a volume adjustment, rendering 
							# the content of the TXXX tags invalid
	elif txxx_tags and not mp3gain_tags:
		debug("Transforming TXXX ReplayGain info into mp3gain")
		txxx_to_mp3gain(filename)
	else: return
	mp3gain_values = get_mp3gain_tags(filename)
	recalc_soundcheck(filename,mp3gain_values)

def apply_mp3gain(filename,apply=False):
	debug("Applying replaygain tags for %r with level %s",filename,apply)
	assert apply in (MP3GAIN_ALBUM,MP3GAIN_TRACK,False)
	try: tg,tp,ag,ap = get_mp3gain_tags(filename)
	except TypeError: tg,tp,ag,ap = [None,None,None,None]
	cmd = ["mp3gain","-T","-f"]
	if apply is MP3GAIN_ALBUM:
		if ag: cmd.extend(["-a","-c"])
		else: cmd.extend(["-r","-c"])
	elif apply is MP3GAIN_TRACK: cmd.extend(["-r","-c"])
	else: pass
	cmd = cmd + [filename]
	if len(cmd) == 4: debug("Computing mp3gain ReplayGain with %s"," ".join(cmd))
	else: debug("Applying mp3gain ReplayGain with %s"," ".join(cmd))
	subprocess.check_call(cmd,stdout=file("/dev/null","w"),stderr=subprocess.STDOUT)
	cohere_replaygain_tags(filename)

# ======= / mp3gain and soundcheck operations ==========


calc_commands = {
	".ogg1"  : "vorbisgain",
	".ogg"   : "vorbisgain -a",
	".flac1" : "metaflac --add-replay-gain",
	".flac"  : "metaflac --add-replay-gain",
	".mp31"  : ["mp3gain -p -t -f",cohere_replaygain_tags],
	".mp3"   : ["mp3gain -p -t -f",cohere_replaygain_tags],
}

undo_commands = {
	".ogg1"  : "vorbisgain -c",
	".ogg"   : "vorbisgain -c",
	".flac1" : "metaflac --remove-replay-gain",
	".flac"  : "metaflac --remove-replay-gain",
	".mp31"  : ["mp3gain -u", "mp3gain -s d"],
	".mp3"   : ["mp3gain -u", "mp3gain -s d"],
}

def mediafilesindir(directory):
	newfiles = []
	for globspec in [ "*%s"%k for k in calc_commands.keys() if not k.endswith("1") ]:
		newfiles.extend( glob.iglob(os.path.join(directory,globspec)) )
	return newfiles

def getalbum(filename):
	metadata = fixopen(filename)
	if not metadata.keys(): return None

	try: album = unicode(metadata["TALB"]).lower()
	except KeyError:
		try: album = unicode(metadata["album"]).lower() # if keyerror, no tiene album
		except KeyError: album = ''
	# just in case
	if not album.strip(): return None
	return album.strip()

def askdir(directory,album):
	samealbum = set()
	files = mediafilesindir(directory)
	for f in files:
		f = os.path.realpath(f)
		if getalbum(f) == album: samealbum.add(f)
	return samealbum

def askotherfiles(files,album):
	samealbum = set()
	for f in files:
		f = os.path.realpath(f)
		if getalbum(f) == album: samealbum.add(f)
	return samealbum

def alreadyhasreplay(f,album=False):
	try:
		if f.lower().endswith(".mp3"): metadata = mutagen.apev2.Open(f)
		else: metadata = fixopen(f)
	except (mutagen.apev2.APENoHeaderError,KeyError):
		return False
	if album:
		if metadata.has_key("replaygain_album_gain"): return True
		if metadata.has_key("REPLAYGAIN_ALBUM_GAIN"): return True
	else:
		if metadata.has_key("replaygain_track_gain"): return True
		if metadata.has_key("REPLAYGAIN_TRACK_GAIN"): return True
	return False

def alreadyhasrva2(f,album=False):
	try: metadata = mutagen.id3.Open(f)
	except mutagen.id3.ID3NoHeaderError: return False
	for value in metadata.values():
		try:
			if album and value.desc == "replaygain_album_gain": return True
			elif value.desc == "replaygain_track_gain": return True
		except AttributeError: continue
	return False

# algorithm begins here

def doreplaygain(args,options):
	filenames = [ unicode(os.path.realpath(os.path.abspath(f)),"utf-8") for f in args ]
	for f in filenames[:]:
		if os.path.isdir(f):
			filenames.extend(mediafilesindir(f))
			filenames.remove(f)
	filenames = list(set(filenames))

	while filenames:
		filename = filenames.pop(0)
		if not options.quiet: log( "Doing %s",repr(filename) )
		# initialize our list with it
		files = set([filename])
		album = getalbum(filename)
		if album:
			# add other files from the same directory with the same album
			filesfromdir = askdir(os.path.dirname(filename),album)
			l = len(files)
			files = files | set( [ f for f in filesfromdir ] )
			if not options.quiet: log ( "Found %s new files from the same album in the directory", (len(files)-l) )

			# add other files from the same directory with the same album
			filesfromargs = askotherfiles(filenames,album)
			l = len(files)
			files = files | set( [ f for f in filesfromargs ] )
			if not options.quiet: log ( "Found %s new files from command line arguments", (len(files)-l) )

		# group them by file type :-(
		fileswithexts = [ (os.path.splitext(f)[1].lower(),f) for f in files ]
		groups = {}
		for extension in set([ s[0] for s in fileswithexts ]):
			groups[extension] = [ f[1] for f in fileswithexts if f[0] == extension ]

		for extension,files in groups.items():
			for f in files: assert type(f) is unicode
			if len(files) == 1:
				album = False
				extension = extension + "1"
			else:
				album = True

			if \
			not options.redo \
			and all( [ alreadyhasreplay(f,album=album) for f in files ] ) \
			and ( "mp3" not in extension or all( [ alreadyhasrva2(f,album=album) for f in files ] ) ):

				if not options.quiet: log( "All (%s) files already have replaygain (album %s), we skip them", len(files),album )

			else:

				# just some verbose code
				withoutape = [ x for x in files if not alreadyhasreplay(x,album=album)]
				if withoutape:
					if not options.quiet: log( "These files do not already have ReplayGain (album %s):"%album)
					for x in withoutape:
						if not options.quiet: log( "     %s",repr(x) )
				if "mp3" in extension:
					withoutrva2 = [ x for x in files if not alreadyhasrva2(x,album=album)]
					if withoutrva2:
						if not options.quiet: log( "These files do not already have RVA2 (album %s):"%album)
						for x in withoutrva2:
							if not options.quiet: log( "     %s",repr(x))
				# / end verbose code
				
				def run_command(command,files):
					if callable(command):
						if options.dryrun: log ( str(command) + "(" + repr(files) + ")" )
						else: command(files)
					else:
						command = command.split()
						command = command + files
						if options.dryrun: command = ["echo"] + command
						subprocess.check_call(command,stderr=subprocess.STDOUT)
				
				if options.redo:
					commands = undo_commands[extension]
					if type(commands) is not list: commands = [commands]
					for command in commands: run_command(command,files)
				
				commands = calc_commands[extension]
				if type(commands) is not list: commands = [commands]
				for command in commands: run_command(command,files)

			for f in files:
				if f in filenames: filenames.remove(f)


# ======= configuration and constants ==========

# Re-encode, even if the source and target formats are the same
# Otherwise, just the following transformations are applied
config_reencode_same_format = False

# Apply MP3 gain process to input and output MP3 files
# Prevents clipping of files with loud volume during decodes
# and also makes every song sound similar in loudness
# Choose whether track or album gain is used, or False if not.
MP3GAIN_TRACK =	1
MP3GAIN_ALBUM =	2
# config_apply_mp3gain = MP3GAIN_ALBUM
# mobile player now supports replaygain
config_apply_mp3gain = False

# Compute replaygain if the file has no replaygain information
# Unfortunately, if replaygain is missing from the transcoded file
# we can only compute the track replaygain, not the album one
# So it's better to computing replaygain on your collection before transcoding
config_compute_missing_replaygain = True

# If any format of ReplayGain information is found in your tracks, then the transcoding process
# will write all other missing formats (TXXX(desc), mp3gain, Soundcheck) during the transcode
# This lets you set the type of ReplayGain that will be used to compute Soundcheck
config_soundcheck_uses = MP3GAIN_ALBUM

# ======= / configuration and constants ==========

def debug(*args): return logging.getLogger("transcoder").debug(*args)
def err(*args): return logging.getLogger("transcoder").exception(*args)
def info(*args): return logging.getLogger().info(*args)
def warning(*args): return logging.getLogger().warn(*args)

# ======= encoding / decoding functions ==========

def maketempcopy(uri):
	"""Create a temporary copy of the contents of the specified URI
	return a path to a temporary file that must be deleted by the caller"""
	extension = os.path.splitext(uri)[1]
	dir = None
	if os.access('/dev/shm',os.W_OK) and not uri.lower().endswith("mpc"): dir = "/dev/shm"
	tmp_fd, tmp_path = tempfile.mkstemp(prefix="transcode-",suffix=extension,dir=dir)
	try:
		tmp_file = os.fdopen(tmp_fd,"w")
		tmp_file.write(urllib.urlopen(uri).read(-1))
		tmp_file.flush()
		tmp_file.close()
	except Exception:
		os.unlink(tmp_path)
		raise
	return tmp_path

class TranscoderException(Exception): pass
class NoDecoderException(TranscoderException): pass
class NoEncoderException(TranscoderException): pass

# this shit requires an URGENT rewrite using zope interfaces and adapters, like MP3File needs to be adapted to something FLACFile, and policies to arrange that (may need a private adapter registry then!).

# decoders take the in file and the out file as parameters
decoders = {}
def detect_decoders():
    global decoders
    if command_available("madplay"):
        decoders["mp3"] = lambda i,o: ["madplay","--no-tty-control","--output=wav:%s"%o,i]
    if command_available("ogg123"):
        decoders["ogg"] = lambda i,o: ["ogg123","-d","wav","-f",o,i]
    if command_available("flac"):
        decoders["flac"] = lambda i,o: ["flac","-d","-o",o,i]
    if command_available("mppdec"):
        decoders["mpc"] = lambda i,o: ["mppdec",i,o]
    if command_available("mplayer"):
        decoders["mpc"] = lambda i,o: ["mplayer","-vo","null","-ao","pcm:file=%s"%o,i]
    if command_available("mplayer"):
        decoders['m4a'] = lambda i,o: ["mplayer","-vo","null","-ao","pcm:file=%s"%o,i]
    decoders["wav"] = lambda i,o: ["cp",i,o]
    decoders["flv"] = lambda i,o: ["cp",i,o]
    decoders["mp4"] = lambda i,o: ["cp",i,o]
detect_decoders()

def decode(input,source_format):
	"""receives a path to a file, presumed to be in a temporary directory
	returns a path to a new temporary file that needs to be deleted by the caller"""
	output = input + ".wav"
	decoder = decoders[source_format](input,output)
	debug("Decoding with %s"," ".join(decoder))
	try:	subprocess.check_call(decoder,stdout=file("/dev/null","w"),stderr=subprocess.STDOUT)
	except Exception:
		if os.path.exists(output): os.unlink(output)
		raise
	return output

# encoders take the in file and the out file as parameters
encoders = {}
def detect_encoders():
    global encoders
    if command_available("lame"):
        encoders["mp3"] = lambda i,o: "lame -q 0 --noreplaygain --nohist --vbr-new".split(" ") + [i,o]
    if command_available("aacplusenc"):
        encoders["aac"] = lambda i,o: ["aacplusenc",i,o,"58"]
    if command_available("ffmpeg"):
        encoders["mp4"] = lambda i,o: ["ffmpeg","-acodec","copy","-vcodec","h264","-vf","scale=800:-1","-i",i,o]
detect_encoders()

def encode(input,target_format):
	"""receives a path to a file, presumed to be in a temporary directory
	returns a path to a new temporary file that needs to be deleted by the caller"""
	output = input + "." + target_format
	encoder = encoders[target_format](input,output)
	debug("Encoding with %s"," ".join(encoder))
	try:	subprocess.check_call(encoder,stdout=file("/dev/null","w"),stderr=subprocess.STDOUT)
	except Exception:
		if os.path.exists(output): os.unlink(output)
		raise
	return output

# ======= / encoding / decoding functions ==========

# ======= tag transfer functions ==========

def copy_tag_values(i,o,filter):
	"""copies tag values from i to o, if filter is true"""
	def m(k,v):
		if filter(k,v): o[unicode(k)] = v
	for k,v in i.items():
		m(k,v)

def copy_generic_tag_values_to_id3(i,o):
	"""copies tag values from i to o, transforming to fit the ID3 spec"""
	tag_transformation_map = {
		"album":"TALB",
		"artist":"TPE1",
		"comment":"COMM",
		"description":"COMM",
		"date":"TDRC",
		"year":"TDRC",
		"title":"TIT2",
		"tracknumber":"TRCK",
		"track":"TRCK",
		"genre":"TCON",
		"replaygain_album_gain":lambda x: mutagen.id3.TXXX(desc="replaygain_album_gain",encoding=1,text=x),
		"replaygain_album_peak":lambda x: mutagen.id3.TXXX(desc="replaygain_album_peak",encoding=1,text=x),
		"replaygain_track_gain":lambda x: mutagen.id3.TXXX(desc="replaygain_track_gain",encoding=1,text=x),
		"replaygain_track_peak":lambda x: mutagen.id3.TXXX(desc="replaygain_track_peak",encoding=1,text=x),
	}
	def iterate(k,v):
		if k in tag_transformation_map:
			if type(v) not in (tuple,list): v = [v]
			constructor = tag_transformation_map[k]
			if callable(constructor):
				newvalues = [ constructor(unicode(value)) for value in v ]
			else:
				constructor = getattr(mutagen.id3,constructor)
				newvalues = [ constructor(text=unicode(value),encoding=3) for value in v ]
			map(o.add,newvalues)
			return newvalues

	transform_keys(str.lower,i)
	for k,v in i.items(): iterate(k,v)

def transfer_tags_any_mp3(origin,destination,tag_reader):

	try: i = tag_reader(origin)
	except Exception:
		err("Could not open source file tag")
		return

	try: o = mutagen.id3.ID3(filename=destination)
	except mutagen.id3.ID3NoHeaderError: o = mutagen.id3.ID3()

	copy_generic_tag_values_to_id3(i,o)
	o.save(filename=destination,v1=2)

def transfer_tags_mp3(origin,destination):

	try:
		ape_tag_found = True
		i = mutagen.apev2.APEv2()
		i.load(origin)
		i.save(destination)
	except mutagen.apev2.APENoHeaderError:
		ape_tag_found = False
	except Exception:
		err("Though it exists, an error blocked opening the APEv2 tag")

	try:
		i = mutagen.id3.ID3()
		i.load(origin)
		i.save(destination,v1=2)
	except mutagen.id3.ID3NoHeaderError:
		pass # no ID3 tag, we skip it
	except Exception:
		err("Though it exists, an error blocked opening the ID3 tag")

tag_transfer_functions = {
	"mp3:mp3": lambda x,y,z,w: transfer_tags_mp3(x,y),
	"mp3:aac": lambda x,y,z,w: transfer_tags_mp3(x,y),
	"ogg:mp3": lambda x,y,z,w: transfer_tags_any_mp3(x,y,mutagen.oggvorbis.Open),
	"flac:mp3": lambda x,y,z,w: transfer_tags_any_mp3(x,y,mutagen.flac.Open),
	"mpc:mp3": lambda x,y,z,w: transfer_tags_any_mp3(x,y,mutagen.musepack.Open),
}

def transfer_tags(origin,destination,source_format,target_format):
	m = "%s:%s"%(source_format,target_format)
	if m in tag_transfer_functions:
		transfer_function = tag_transfer_functions[m]
		transfer_function(origin,destination,source_format,target_format)
	return

# ======= / tag transfer functions ==========

def check_transcodable(source_format,target_format):
        """Gets a string describing the source format, and ( a string describing the
        target format ) or ( a list describing strings of target formats ), then
        chooses the target format that is transcodable to, based on the source
        format, and then returns that.  Raises NoEncoderException or
        NoDecoderException if it is not possible to transcode from the sourrce
        format to any of the target formats."""
    
        global decoders
        global encoders
    
        needs_transcoding = False
        if type(target_format) in (list,tuple):
            if source_format in target_format: needs_transcoding = False
            else: needs_transcoding = True
        else:
            if source_format == target_format: needs_transcoding = False
            else: needs_transcoding = True
        
        if not needs_transcoding:
            return source_format
            
        if source_format not in decoders.keys(): raise NoDecoderException,source_format
	if type(target_format) in (list,tuple):
		if source_format in ["flv","mp4"] and "mp3" in target_format:
			target_format = list(target_format)
			target_format.remove("mp3")
		choice = None
		for t in target_format:
			if t in encoders.keys():
				choice = t
				break
		if not choice: raise NoEncoderException,target_format
		target_format = choice
	else:
		if target_format not in encoders.keys(): raise NoEncoderException,target_format
	return target_format

def transcode(uri,target_format):
	"""receives an URI to the file to transcode, and a three letter format code
	returns a filesystem path to the transcoded file"""
	source_format = uri.split(".")[-1].lower()
	target_format = target_format.lower()

	if source_format.startswith("."): raise Exception, "source format cannot start with a dot"
	if target_format.startswith("."): raise Exception, "target format cannot start with a dot"
	
	reencode = config_reencode_same_format or "mp4" == target_format # HACK FIXME

	check_transcodable(source_format,target_format)
	
	tempfiles = []
	def delete_later(path):
		tempfiles.append(path)
		return path
	def cleanup():
		print "Deleting the following files: %r"%tempfiles
		map(os.unlink,tempfiles)
		while tempfiles: tempfiles.pop()

	try:

		# create the temporary copy
		tmp_path = delete_later(maketempcopy(uri))

		if source_format == "mp3":
			cohere_replaygain_tags(tmp_path)
			if config_compute_missing_replaygain and not get_mp3gain_tags(tmp_path):
				apply_mp3gain(tmp_path)
			if config_apply_mp3gain:
				apply_mp3gain(tmp_path,config_apply_mp3gain)

		if source_format != target_format or reencode:
			# decode
			wav_path = delete_later(decode(tmp_path,source_format))
			# encode
			dest_path = delete_later(encode(wav_path,target_format))
			# transfer tags
			transfer_tags(tmp_path,dest_path,source_format,target_format)
		else:
			dest_path = tmp_path

		if target_format == "mp3" and source_format != "mp3":
			cohere_replaygain_tags(dest_path)
			if config_compute_missing_replaygain and not get_mp3gain_tags(dest_path):
				apply_mp3gain(dest_path)
			if config_apply_mp3gain:
				apply_mp3gain(dest_path,config_apply_mp3gain)

	except:
		err("Exception occurred during transcode of %r, cleaning up"%uri)
		cleanup()
		raise

	tempfiles.remove(dest_path)
	cleanup()

	return dest_path


# this function prevents parallel makedirs from stomping on each other
makedirlock = multiprocessing.Lock()
def locked_makedirs(dstdir):
	with makedirlock:
		os.makedirs(dstdir)
# end locked makedirs


def transcode_file(src,dst):
	debug("Transcoding %r to %r",src,dst)
	destformat = os.path.splitext(dst)[1][1:]
	newsong = transcode(urllib.pathname2url(src),destformat)
	rsync(newsong,dst)
	os.unlink(newsong)
	return dst

def cmdline_process(*args):
	format,path,uri = args
	return format,path,transcode(uri,format)

def parallel_transcode(format,paths):
	uris = [ "file://" + urllib.pathname2url(os.path.abspath(path)) for path in paths ]

	items = [ (format,path,uri) for path,uri in zip(paths,uris) ]

	oldsighandler = signal.signal(signal.SIGINT, lambda x,y: sys.exit(0))
	pool = multiprocessing.Pool()
	signal.signal(signal.SIGINT, oldsighandler)

	results = [ pool.apply_async(cmdline_process,item) for item in items ]

	for result in results:
		noresult = True
		while noresult:
			try:
				print "Wait..."
				format,path,transcoded = result.get(1)
				noresult = False
			except multiprocessing.TimeoutError:
				pass
		
		print path
		print transcoded
	pool.close()
	pool.join()

def relativize(listoffiles,commonprefix=None):
	if not commonprefix: commonprefix = os.path.commonprefix(listoffiles)
	return commonprefix, [ os.path.relpath(x,start=commonprefix) for x in listoffiles ]

def vfatprotect(f):
	f = f.replace("./","/")
	for illegal in '?<>\:*|"^': f = f.replace(illegal,"_")
        while "./" in f: f = f.replace("./","/")
        while " /" in f: f = f.replace(" /","/")
	return f

def rsync(src,dst):
	debug("Rsyncing %r to %r",src,dst)
	return subprocess.check_call(['rsync','--modify-window=5','-t',src,dst])

def transfer(src,dst):
	dr = os.path.dirname(dst)
	if not os.path.isdir(dr):
		try: locked_makedirs(dr)
		except OSError,e:
			if e.errno != 17: raise
	try:
		return transcode_file(src,dst)
	except (NoDecoderException,NoEncoderException), e:
		rsync(src,dst)
		return dst

def transfer_wrapper(x):
	signal.signal(signal.SIGINT,signal.SIG_IGN)
	info("\nDispatching: %r\n->	%r"%(x))
	try:
		return transfer(*x)
	except Exception,e:
		err("Transfer failed: %r %s",x,e)


class SyncManager:
	source_songs = None
	destination_songs = None
	sourcedir = None
	destdir = None
	threads = None
	lock = threading.RLock()
	exceptions = None
	
	def __init__(self,sourcedir,destdir):
		self.sourcedir = os.path.abspath(sourcedir)
		self.destdir = os.path.abspath(destdir)
		self.playlistdir = os.path.join(self.destdir,"Playlists")
		self.source_songs = {}
		self.source_song_dates = {}
		self.destination_songs = set()
		self.destination_song_dates = {}
		self.threads = []
		self.exceptions = []
		self.do_not_transfer = set()
		self.playlists = []
		
	def source_song_found(self,path,date):
		self.lock.acquire()
		newpath = path
		newpath = os.path.realpath(path)
		newpath = os.path.relpath(newpath,start=self.sourcedir)
		try:
			srcfmt = os.path.splitext(newpath)[1][1:]
			srcfmt = srcfmt.lower()
			newpath = os.path.splitext(newpath)[0]+".mp3"
			newformat = check_transcodable(srcfmt,["mp3","mp4"])
			newpath = os.path.splitext(newpath)[0]+"."+newformat
		except (NoEncoderException,NoDecoderException),e:
			warning("File %r will be transferred as is because of %r",path,e)
		newpath = vfatprotect(newpath)
                self.source_songs[newpath] = path
                self.source_song_dates[newpath] = date
		if newpath in self.destination_songs and date >= self.destination_song_dates[newpath]:
			#info("Not transferring %r because it is already on the destination device"%newpath)
			self.do_not_transfer.add(newpath)
		self.lock.release()
	
	def destination_song_found(self,path,date):
		self.lock.acquire()
		newpath = path
		newpath = os.path.relpath(newpath,start=self.destdir)
		self.destination_songs.add(newpath)
		self.destination_song_dates[newpath] = date
		if newpath in self.source_songs and date <= self.source_song_dates:
			#info("Not transferring %r because it is already on the destination device"%newpath)
			self.do_not_transfer.add(newpath)
		self.lock.release()
			
	def scan_source(self,source):
		source = os.path.abspath(source)
		# sources are playlist m3u files
		def do_scan():
			sourcedir = os.path.dirname(source)
			files = ( os.path.abspath(os.path.join(sourcedir,x.strip())) for x in file(source).readlines() if x.strip() and not x.startswith("#") )
			for f in files:
				try:
					test = file(f,"r")
					test.close()
					del test
				except Exception,e:
					self.lock.acquire()
					print f
					self.exceptions.append(e)
					self.lock.release()
					raise
				try:
					self.source_song_found(f,os.stat(f).st_mtime)
				except Exception,e:
					self.lock.acquire()
					self.exceptions.append(e)
					self.lock.release()
					raise

		self.playlists.append(source)
		t = threading.Thread(target=do_scan)
		self.threads.append(t)
		t.start()
	
	def scan_destination(self):
		destination = self.destdir
		# destinations are directories
		def do_scan():
			for base,dirs,files in os.walk(destination):
				if base == self.playlistdir: continue
				for f in files:
					try:
                                                thefilename = os.path.join(base,f)
						self.destination_song_found(thefilename,os.stat(thefilename).st_mtime)
					except Exception,e:
						self.lock.acquire()
						self.exceptions.append(e)
						self.lock.release()
						raise
		t = threading.Thread(target=do_scan)
		self.threads.append(t)
		t.start()
	
	def join(self):
		for t in self.threads[:]:
			t.join()
			self.threads.remove(t)
		if self.exceptions:
			raise self.exceptions[0]

        def manifest_transfer(self):
                to_transfer = set(self.source_songs.keys()) - self.do_not_transfer
                srcs_and_dests = [
                        (self.source_songs[k],os.path.join(self.destdir,k))
                        for k in to_transfer ]
                return srcs_and_dests
                
	def transfer_missing_songs(self):
		srcs_and_dests = self.manifest_transfer()
		
		if srcs_and_dests:
			pool = multiprocessing.Pool(8)
			try:
				result = pool.imap_unordered(
						transfer_wrapper,
						srcs_and_dests,
				)
				i = 0
				total = len(srcs_and_dests)
				for r in result:
					i = i + 1
					log("%s of %s done (%s %%).  Last result: %r"%(i,total,i*100/total,r))
				pool.close()
				pool.join()
			except KeyboardInterrupt:
				info('Interrupted.  Waiting for tasks to finish cleanly.')
				pool.terminate()
				sys.exit(1)

	def transfer_playlists(self):
		# map songs in playlists to targets
		reverse_lookup = dict( [ (y,x) for x,y in self.source_songs.items() ] )
		relplaylistpath = os.path.relpath(self.destdir,start=self.playlistdir)
		for srcp in self.playlists:
			srcpdir = os.path.dirname(srcp)
			destp = os.path.join(self.playlistdir,os.path.basename(srcp))
			info("\nRewriting: %r\n->	   %r"%(srcp,destp))
			lines = [ x.strip() for x in file(srcp).readlines() if x.strip() ]
			f = file(destp,"w")
			for line in lines:
				if line.startswith("#"):
					pass
				else:
					path = os.path.abspath(os.path.join(srcpdir,line))
					path = os.path.join(relplaylistpath,reverse_lookup[path])
					line = path
				f.write(line + "\n")
			f.close()
			
	def remove_obsolete_songs(self):
		songsthatneedtobedeleted = set(self.destination_songs) - set(self.source_songs.keys())
		for song in songsthatneedtobedeleted:
			dst = os.path.join(self.destdir,song)
			info("Removing: %r",dst)
			os.unlink(dst)

	def remove_obsolete_playlists(self):
		existingplaylists = glob.glob(os.path.join(self.playlistdir,"*"))
		totransfer_basenames = set ( [ os.path.basename(b) for b in self.playlists ] )
		existing_basenames = set ( [ os.path.basename(b) for b in existingplaylists ] )
		toremove = existing_basenames - totransfer_basenames
		for p in toremove:
			p = os.path.join(self.playlistdir,p)
			info("Removing: %r",p)
			os.unlink(p)


# FIXME provide args for remove and sourcedir too
def sync_playlists(sourceplaylists,synctodir,dryrun=False):
	remove = True
	sm = SyncManager("/var/shared/Entertainment/Music",synctodir)
	for s in sourceplaylists: sm.scan_source(s)
	sm.scan_destination()
	sm.join()
        if dryrun:
            for x,y in sm.manifest_transfer():
                print "Would transfer %r to %r"%(x,y)
        else:
            sm.transfer_missing_songs()
            sm.transfer_playlists()
            if remove:
                    sm.remove_obsolete_playlists()
                    sm.remove_obsolete_songs()
