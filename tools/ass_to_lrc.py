# Simple tool to convert .ass subtitles to .lrc files.

import datetime
import argparse
import re
import pathlib
import os
from typing import Union

HAVE_MUTAGEN = False
try:
	import mutagen
except ImportError:
	pass
else:
	HAVE_MUTAGEN = True

ASS_ENCODING = "utf-8-sig"

LRC_AR_HEADER = '[ar:{artist}]\n'
LRC_TI_HEADER = '[ti:{title}]\n'
LRC_AL_HEADER = '[al:{album}]\n'
LRC_BY_HEADER = '[by:{lrc_author}]\n'
LRC_LE_HEADER = '[length: {length}]\n\n'

LRC_INLINE_HEADER =  '[00:00.00]{title}\n'
LRC_INLINE_HEADER += '[00:00.00]by {artist}\n'
LRC_INLINE_HEADER += '[00:00.00]{album}\n'
LRC_INLINE_HEADER += '[00:00.00]\n'
LRC_INLINE_HEADER += '[00:00.00]({lrc_author})\n'
LRC_INLINE_HEADER += '[00:00.00]\n'
LRC_INLINE_HEADER += '[00:00.00]-----\n'
LRC_INLINE_HEADER += '[00:00.00]\n'


def fileArgument(v):
	p = pathlib.Path(os.path.join(os.getcwd(), v))
	if p.is_file():
		return p
	else:
		raise argparse.ArgumentTypeError('File %s does not exist' % (v))
		
def xfileArgument(v):
	p = pathlib.Path(os.path.join(os.getcwd(), v))
	return p

def assTimeStrToDelta(assTimeStr: str) -> datetime.timedelta:
	sp = assTimeStr.split(".")
	if len(sp) != 2:
		raise Exception("Malformed ass time: {}".format(assTimeStr))
	s = sp[0] + "." + sp[1][0:4]
	t = datetime.datetime.strptime(s, "%H:%M:%S.%f")
	return datetime.timedelta(hours=t.hour, minutes=t.minute, seconds=t.second, microseconds=t.microsecond)


def deltaToAssTimeStr(delta: datetime.timedelta) -> str:
	seconds = delta.total_seconds()
	hours = seconds // 3600
	minutes = (seconds % 3600) // 60
	seconds = seconds % 60
	return "%01d:%02d:%02d.%02d" % (hours, minutes, int(seconds), round((seconds % 1) * 100))


def deltaToLrcDurationStr(delta: datetime.timedelta) -> str:
	seconds = delta.total_seconds()
	minutes = (seconds % 3600) // 60
	seconds = seconds % 60
	return "%01d:%02d" % (minutes, round(seconds))


def deltaToLrcTimeStr(delta: datetime.timedelta) -> str:
	seconds = delta.total_seconds()
	minutes = (seconds % 3600) // 60
	seconds = seconds % 60

	return "%02d:%02d.%02d" % (minutes, int(seconds), round((seconds % 1) * 100))


def secsToDelta(seconds: Union[int, float]) -> datetime.timedelta:
	return datetime.timedelta(seconds=seconds)


class AssEvent:
	def __init__(self, line=None, split=None, format=None, layer=None, start=None, end=None, name=None, style=None, marginl=None, marginr=None, marginv=None, effect=None, text=None):
		self.Format = format
		self.Layer = layer
		self.Start = start
		self.End = end
		self.Name = name
		self.Style = style
		self.MarginL = marginl
		self.MarginR = marginr
		self.MarginV = marginv
		self.Effect = effect
		self.Text = text
		if line is not None:
			line_type, _, ass_variables = line.partition(':')
			if line_type in ("Dialogue", "Comment"):
				split = [x.strip() for x in ass_variables.split(',', 9)]
				self.Format = line_type
				self.Layer, self.Start, self.End, self.Style, self.Name, self.MarginL, self.MarginR, self.MarginV, self.Effect, self.Text = split

	def start(self, delta=False) -> Union[datetime.timedelta, str]:
		return assTimeStrToDelta(self.Start) if delta else self.Start

	def end(self, delta=False) -> Union[datetime.timedelta, str]:
		return assTimeStrToDelta(self.Start) if delta else self.End

	def StrippedText(self) -> str:
		"""Returns Text without ASS Tags"""
		return re.sub(r'{[^\}]*?}', '', self.Text).replace("\\N\\N"," ").replace("\\N","")


def assToLrcLine(start: datetime.timedelta, text: str) -> str:
	return "[{start}]{text}".format(start=deltaToLrcTimeStr(start), text=text)


def assToLrc(args):
	if HAVE_MUTAGEN and args.song_file:
		t = mutagen.File(str(args.song_file))
		info = t.info
		tags = t.tags
		
		if not len(tags):
			print("Specificed song file has no tags")
			exit(1)

		possibleTags = {
			"artist": ["ARTIST", "©ART"],
			"title": ["TITLE", "©nam"],
			"album": ["ALBUM", "©alb"],
			"year": ["DATE", "YEAR", "©day"],
		}
		
		for tagname, taglist in possibleTags.items():
			for pt in taglist:
				try:
					pt in tags
				except ValueError:
					pass
				else:
					if pt in tags and len(tags[pt]):
						setattr(args, tagname, tags[pt][0])

		args.length = deltaToLrcDurationStr(secsToDelta(info.length))
		
	else:
		print("mutagen not installed, not using it")
		
	albumStr = ""
	if args.album is None and args.year:
		albumStr = args.year
	elif args.album and args.year is None:
		albumStr = args.album
	elif args.album and args.year:
		albumStr = F"{args.album} ({args.year})"

	lrc_file = ""
	if args.artist:
		lrc_file += LRC_AR_HEADER.format(artist=args.artist)
	if args.title:
		lrc_file += LRC_TI_HEADER.format(title=args.title)
	if args.album:
		lrc_file += LRC_AL_HEADER.format(album=albumStr)
	if args.lrc_author:
		lrc_file += LRC_BY_HEADER.format(lrc_author=args.lrc_author)
	if args.length:
		lrc_file += LRC_LE_HEADER.format(length=args.length)

	if args.title and args.artist and args.lrc_author and not args.without_inline_header and (args.album is not None or args.year is not None):		
		lrc_file += LRC_INLINE_HEADER.format(
			artist=args.artist,  # ar
			title=args.title,  # ti
			album=albumStr,  # al
			lrc_author=args.lrc_author,  # by
			year="" if args.year is None else args.year
		)

	ass_lines = []
	ass_file = args.input.open('r', encoding=ASS_ENCODING)
	for line in ass_file:
		a = AssEvent(line=line)
		if a.Format in ("Dialogue", "Comment") and "template line" not in a.Effect:
			ass_lines.append(a)

	lrc_lines_rom = [a for a in ass_lines if a.Style == args.rom_style and a.Format == "Dialogue"]
	lrc_lines_jap = [a for a in ass_lines if a.Style == args.jap_style and a.Format == "Dialogue"]
	
	iterator_max = max(len(lrc_lines_jap), len(lrc_lines_rom))

	if args.lrc_format == "romaji+japanese":
		if len(lrc_lines_jap) != len(lrc_lines_rom):
			raise Exception("ASS File Romaji and Japanese line count is not the same!")

	for i in range(0, iterator_max):
		rom_line = None
		jap_line = None
		text = None
		time_start = None
		if i <= len(lrc_lines_jap):
			jap_line = lrc_lines_jap[i]
		if i <= len(lrc_lines_rom):
			rom_line = lrc_lines_rom[i]
		if rom_line:
			time_start = rom_line.start(delta=True)
		elif jap_line:
			time_start = jap_line.start(delta=True)
		if args.lrc_format == "romaji+japanese":
			if jap_line and rom_line:
				text = "{} ({})".format(rom_line.StrippedText(), jap_line.StrippedText())
		elif args.lrc_format == "japanese":
			if jap_line:
				text = jap_line.StrippedText()
		elif args.lrc_format == "romaji":
			if rom_line:
				text = rom_line.StrippedText()
		if text and time_start:
			lrc_line = assToLrcLine(time_start, text)
			lrc_file += lrc_line + "\n"

	if args.output == None:
		print(lrc_file)
	else:
		with args.output.open("w", encoding="utf-8") as o:
			o.write(lrc_file)


parser = argparse.ArgumentParser(description="")
parser.add_argument('-i', '--input-file', action='store', dest='input', type=fileArgument, required=True, help="ASS Subtitle file")
parser.add_argument('-o', '--output-file', action='store', dest='output', type=xfileArgument, default=None, required=False, help="LRC Output file (will be echoed if not defined)")
parser.add_argument('-f', '--format', action='store', dest='lrc_format', help="Format type", choices=['romaji', 'japanese', 'romaji+japanese'], default="romaji")
parser.add_argument('-r', '--romanized-style-name', action='store', dest='rom_style', help="ASS Style name of the Romaji lyrics", default="DefaultRom")
parser.add_argument('-j', '--japanese-style-name', action='store', dest='jap_style', help="ASS Style name of the Japanese lyrics", default="DefaultJap")
parser.add_argument('-u', '--lrc_author', action='store', dest='lrc_author', help="LRC File Author URL/Name", default=None)
parser.add_argument('-a', '--artist', action='store', dest='artist', help="Artist name", default=None)
parser.add_argument('-t', '--title', action='store', dest='title', help="title name", default=None)
parser.add_argument('-b', '--album', action='store', dest='album', help="Album name", default=None)
parser.add_argument('-y', '--year', action='store', dest='year', help="Year of the Album/Song", default=None)
parser.add_argument('-l', '--length', action='store', dest='length', help="Length of the song (MM:SS)", default=None)
parser.add_argument('-w', '--without-inline-header', action='store_true', dest='without_inline_header', help="Remove the inline-header?", default=False)
parser.add_argument('-s', '--song', action='store', dest='song_file', type=fileArgument, help="Use this song file (instead of manually specifying meta-data)", default=None)

assToLrc(parser.parse_args())
