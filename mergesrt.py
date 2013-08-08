#!/usr/bin/python

"""
    mergesrt. Merge multiple srt subtitles into one srt subtitles, especially for dual language users.
    Copyright (C) <2013>  <Weida Zhang>

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import re
import codecs
import sys

USER_ENCODINGS = ["us-ascii", "gbk", "big5", "utf-8", "utf-16"]
# u"." is ugly but it is safe even only ascii is supported.
EMPTY_LINES = [u"\u3000", u"."]
EMPTY_LINE = u"\u3000" # you need the CJK
LINE_MERGER = u" / " # merge two lines to A + LINE_MERGER + B
LINES_PER_SUB = 2
MERGE_EXPAND_LINES = True

u"""
How the player interpret the subtitles are not well defined:

1
A_START --> A_END
A_SUBTITLE

2
B_START --> B_END
B_SUBTITLE

A_END is assumed to be smaller than B_START (or equal?)
So if A_END >= B_START, B_START will be overwritten to A_END + 1

On the other hand, players like mplayer have bugs to trigger the closure of
a subtitle.
for example: the format means ms->ms sb1/ms->ms sb2: the sb showed.

1->9  A: A                        # I mean A here, the A is not showing for 9ms, it is showing for 3 seconds!
1->12 A:                          # correct
1->9  A  / 2->9  B: A B           # No 10ms is met, so they are kept alive (I think this is a bug of mplayer's time event?)
1->9  A  / 2->10 B: A             # B meets 10ms so B is killed
1->10 A  / 2->11 B: B             # A meets 10ms and B is changed to [10:11], so it last for 3 sec
2->10 A  / 3->11 B: B
2->11 A  / 3->12 B: B
1->2  A  / 2->3  B: A B           # same as 1->9 / 2->9
1->2  A  / 2->3  B / 12-23 C : A  # Interesting, B is killed by C, and C suicided
"""

u"""
We do in two steps.
1. The srts are combined to one thread of well-defined-ruled srt:
    X->Y A / Z->W B: means [X-Y) A, [Z->W) B
2. Adjust the X, Y, Z, W or even remove some lines for fixing the bugs
   in various players
"""

def codecs_open(filename, force_encoding=None):
    if force_encoding is not None:
        return codecs.open(filename, encoding=force_encoding)
    for encoding in USER_ENCODINGS:
        try:
            f = codecs.open(filename, encoding=encoding)
            f.read()
            f.close()
            return codecs.open(filename, encoding=encoding)
        except UnicodeDecodeError,e:
            # print >> sys.stderr, "Cannot decode with %s, trying next encoding" % (repr(e.encoding))
            pass
        except LookupError,e:
            print >> sys.stderr, "Python complains (%s), trying next encoding" % (e.message)
    raise Exception("No encodings found, cannot decode %s" % filename)


class Timestamp:
    def __init__(self, seconds, msec):
        self.msec = msec % 1000
        seconds += msec / 1000
        self.hour = seconds / 60 / 60
        self.minute = seconds / 60 % 60
        self.sec = seconds % 60

    _inf = None

    regexp = ur"\d\d:\d\d:\d\d,\d\d\d"

    @classmethod
    def inf(cls):
        if cls._inf is None:
            cls._inf = Timestamp(86400, 0)
        return cls._inf

    @classmethod
    def parse(cls, _str):
        matcher = re.compile(ur"^(\d\d):(\d\d):(\d\d),(\d\d\d)$").match(_str)
        if not matcher:
            raise Exception("Not timestamp format [%s], should not call me." % (_str))
        (hour, minute, sec, msec) = matcher.groups()
        return Timestamp(int(hour) * 60 * 60 + int(minute) * 60 + int(sec), int(msec))

    def to_msec(self):
        return ((((self.hour * 60) + self.minute) * 60) + self.sec) * 1000 + self.msec

    def msec10(self):
        return self.msec % 10 == 0

    def __unicode__(self):
        if Timestamp.inf() == self:
            return u"+Inf"
        else:
            return u"%02d:%02d:%02d,%03d" % (self.hour, self.minute, self.sec, self.msec)

    def __str__(self):
        if Timestamp.inf() == self:
            return "+Inf"
        else:
            return "%02d:%02d:%02d,%03d" % (self.hour, self.minute, self.sec, self.msec)

    def __repr__(self):
        return "Timestamp(%s)" % (str(self))

    def __cmp__(self, b):
        if b is None:
            raise Exception("comparing with None")
        return self.to_msec() - b.to_msec()

    def __sub__(self, b):
        return self.to_msec() - b.to_msec()

    def __add__(self, delta):
        return Timestamp(0, self.to_msec() + delta)

DEBUG_MERGING = False
class SRTLine:
    def merge_text_lines(self, text):
        # TODO: strip the <font></font> tags before calculating the length?
        # TODO: the visual length of different charectors are different
        if DEBUG_MERGING:
            print >> sys.stderr, "Mergeing %d lines into %d lines" % (len(text), LINES_PER_SUB)
            for line in text:
                print >> sys.stderr, "    ", line
        # Currently only find the smallest two lines and merge them
        # Not tested yet.
        while len(text) > LINES_PER_SUB:
            minimum = len(text[0]) + len(text[1])
            best_i = 0
            for i in xrange(len(text) - 1):
                if len(text[i]) + len(text[i + 1]) < minimum:
                    minimum = len(text[i]) + len(text[i + 1])
                    best_i = i
            text = text[:i] + [text[i] + LINE_MERGER + text[i + 1]] + text[i + 2:]
        if DEBUG_MERGING:
            print >> sys.stderr, ">>>>"
            for line in text:
                print >> sys.stderr, "    ", line
        return text

    def __init__(self, start, end, text, align_bottom=True):
        self.start = start
        self.end = end
        if isinstance(text, str) or isinstance(text, unicode):
            self.text = text
        else:
            while len(text) < LINES_PER_SUB:
                if align_bottom:
                    text = [EMPTY_LINE] + text
                else:
                    text = text + [EMPTY_LINE]
            if MERGE_EXPAND_LINES and len(text) > LINES_PER_SUB:
                text = self.merge_text_lines(text)
            self.text = u"\n".join(text)

    def __repr__(self):
        return "SRTLINE(%s,%s,%s)" % (repr(self.start), repr(self.end), repr(self.text))

    def __str__(self):
        return "SRTLINE(%s,%s,%s)" % (str(self.start), str(self.end), self.text)

class MPlayerFilter:
    def __init__(self):
        self.last = None

    def append(self, subno, start, end, text):
        ok = False
        end = Timestamp(0, end.to_msec() / 10 * 10)
        start = Timestamp(0, start.to_msec() / 10 * 10)
        if self.last is None:
            ok = True
        elif (start - self.last >= 10 or self.last.msec10()) and end - start >= 10:
            ok = True
        else:
            if not self.last.msec10() and start - self.last < 10:
                start = Timestamp(0, (self.last.to_msec() + 10) / 10 * 10)
            if end - start >= 10:
                ok = True
        if ok:
            self.last = end
            print subno
            print start, "-->", end
            print text
            print
        else:
            # print >> sys.stderr, subno, "from", start, "to", end, "is filtered out"
            pass
        return ok

class SRTLines:
    def __init__(self, srts, player):
        self.srts = srts
        self.stack = [None] * len(srts)
        self.last_timestamp = Timestamp(0, 0)
        self.subno = 0
        self.player = player

    def conclude(self, timestamp):
        if self.stack.count(None) == len(self.stack):
            return
        self.subno += 1
        text = []
        for srtline in self.stack:
            if srtline is None:
                text.append(u"\n".join([EMPTY_LINE] * LINES_PER_SUB))
            else:
                text.append(srtline.text)
        ok = self.player.append(self.subno, self.last_timestamp, timestamp, u"\n".join(text))
        if not ok:
            self.subno -= 1

    def tell_events(self, timestamp, events):
        self.conclude(timestamp)
        self.last_timestamp = timestamp
        for (srt, event, obj) in events:
            idx = self.srts.index(srt)
            if event == u"ON":
                self.stack[idx] = obj
            elif event == u"OFF":
                self.stack[idx] = None

class SRT:
    def __init__(self, filename, align_bottom, encoding=None):
        self.filename = filename
        self._file = codecs_open(filename, encoding)
        self.lineno = 0
        self.subno = 0
        self.current_time = Timestamp(0, 0)
        self.current_state = 0
        self.align_bottom = align_bottom
        self.next(self.current_time)

    def readline(self):
        self.lineno += 1
        line = self._file.readline()
        if self.lineno == 1 and line.startswith(u"\ufeff"):
            line = line[1:]
        if line == u"":
            return None
        return line.rstrip()

    def readline_until_nonempty(self):
        line = self.readline()
        while line is not None and line.strip() == u"":
            line = self.readline()
        return line

    def next_timestamp(self):
        if self.current:
            if self.current_time < self.current.start:
                return self.current.start
            elif self.current_time < self.current.end:
                return self.current.end
            else:
                raise Exception("current_time(%s) is not smaller than either start(%s) and end(%s)" % (self.current_time, self.current.start, self.current.end))
        else:
            return Timestamp.inf()

    def expect_number(self):
        line = self.readline_until_nonempty()
        if line is None:
            return None
        if re.compile(ur"^\d+$").match(line):
            return int(line)
        else:
            raise Exception("Expect number but I got %s %s:L%d" % (repr(line), self.filename, self.lineno))

    def next(self, current_time):
        if self.subno is None:
            self.current = None
            return
        self.subno = self.expect_number()
        if self.subno is None:
            self.current = None
            return

        line = self.readline()
        if line is None:
            raise Exception("The number is expected but the timestamps fail before EOF")
        line = line.strip()
        regexp = re.compile(ur"^(?P<start>%s) --> (?P<end>%s)$" % (Timestamp.regexp, Timestamp.regexp))
        matcher = regexp.match(line)
        if not matcher:
            raise Exception("Expect start --> end, but I got %s %s:L%d" % (repr(line), self.filename, self.lineno))
        start = Timestamp.parse(matcher.group(u"start"))
        start0 = start
        end = Timestamp.parse(matcher.group(u"end"))
        if start <= current_time:
            start = current_time + 1
        if start0 >= end:
            raise Exception("The input srt has a start >= end: %s %s:L%d" % (repr(line), self.filename, self.lineno))
        if start >= end:
            print >> sys.stderr, "WARNING: The input srt has a start (%s) >= end: %s %s:L%d" % (repr(start), repr(line), self.filename, self.lineno)
            end = start + 1 # it is like we are killing the subline
        text = []
        line = self.readline_until_nonempty()
        if line is None:
            self.current = None
            return
        while line is not None and line != u"":
            text.append(line)
            line = self.readline()

        self.current = SRTLine(start, end, text, self.align_bottom)

    def tell_time(self, current_time):
        self.current_time = current_time
        if self.current is None:
            return None, None
        if current_time < self.current.start:
            return None, self.current # not yet start
        if current_time == self.current.start:
            return u"ON", self.current
        if current_time < self.current.end:
            return None, self.current # not yet end
        if current_time == self.current.end:
            event, obj = u"OFF", self.current
        while self.current is not None and current_time >= self.current.end:
            self.next(current_time)
        return event, obj

    def __repr__(self):
        return "SRT(%s)" % (self.filename)
def mergesrt(srts, player):
    pool = SRTLines(srts, player)
    while True:
        minimum = Timestamp.inf()
        for srt in srts:
            if srt.next_timestamp() < minimum:
                minimum = srt.next_timestamp()
        if minimum == Timestamp.inf():
            break # all the srts finishes
        events = []
        for srt in srts:
            event, obj = srt.tell_time(minimum)
            if event != None:
                events.append((srt, event, obj))
        if len(events) == 0:
            raise Exception("events should not be empty, otherwise the minimum should not be that small.")
        pool.tell_events(minimum, events)

def do_merge(eargs, args):
    srts = []
    align_bottom = True
    for encoding, name in eargs:
        srts.append(SRT(name, align_bottom, encoding=encoding))
        align_bottom = False

    for name in args:
        srts.append(SRT(name, align_bottom))
        align_bottom = False

    player = MPlayerFilter()
    mergesrt(srts, player)


def usage():
    print """Usage:
    mergesrt.py [OPTIONS] [FILES]

FILES:
    FILES can be multiple items of the following format:
            -e INPUT_ENCODING,FILE
    or:
            FILE
    But -e encoding,FILE items must be before FILE items
    Try without -e first to detect the encodings automatically.

    See the examples below:
        mergesrt.py abc.chs.srt abc.cht.srt abc.eng.srt
        mergesrt.py -e gbk,abc.chs.srt -e big5,abc.cht.srt abc.eng.srt
    The following is NOT permitted:
        mergesrt.py abc.eng.srt -e gbk,abc.chs.srt -e big5,abc.cht.srt

OPTIONS:
    -e INPUT_ENCODING,FILE: most of the time encodings are automatically detected, but you can force encoding it gets wrong;
    -E OUTPUT_ENCODING: output encoding (by default your system's locale setting, refer to your `locale` or `chcp`);
    -l LINES_PER_SUB: indicates how many lines for each language in each subtitle;
    -M: do not merge lines and do not prepend/append empty lines;
    -O OUTPUT_FILE: output_filename;
    -s 'EMPTY_LINE': the characters you want to use as empty line by default u"\\u3000"(a CJK space).

    """

def do_main():
    import locale
    import getopt
    global MERGE_EXPAND_LINES, EMPTY_LINE, EMPTY_LINES, LINES_PER_SUB

    output_filename = "-"
    if sys.stdout.isatty():
        output_encoding = sys.stdout.encoding
        old_encoding = output_encoding
    else:
        output_encoding = locale.getpreferredencoding()
        old_encoding = "us-ascii"

    opts, args = getopt.getopt(sys.argv[1:], "l:Me:E:s:")
    eargs = []
    for o, a in opts:
        if o == "-l":
            LINES_PER_SUB = int(a)
        elif o == "-M":
            MERGE_EXPAND_LINES = False
        elif o == "-e":
            idx = a.index(",")
            if idx < 0:
                raise Exception("Cannot find \",\", in option -e %s" % a)
            eargs.append((a[:idx], a[idx + 1:]))
        elif o == "-E":
            output_encoding = a
        elif o == "-s":
            EMPTY_LINES = [unicode(a, locale.getdefaultlocale()[1])]
        elif o == "-O":
            output_filename = a
        else:
            usage()
            return 1
    if len(eargs) + len(args) == 0:
        usage()
        return 1

    if output_filename != "-" or output_encoding != old_encoding:
        if output_filename == "-":
            sys.stdout = codecs.getwriter(output_encoding)(sys.stdout)
        else:
            sys.stdout = codecs.open(output_filename, mode="w", encoding=output_encoding)
    try:
        for EMPTY_LINE in EMPTY_LINES:
            try:
                EMPTY_LINE.encode(output_encoding)
                break
            except (LookupError, UnicodeEncodeError):
                pass
        do_merge(eargs, args)
    except LookupError, e:
        if output_encoding != "utf-8":
            raise Exception("Python complains (%s). Please try to force output encoding by e.g. -E utf-8" % (e.message)) 
        else:
            raise Exception("Python complains (%s) (Please report bug.)" % (e.message)) 
    except UnicodeEncodeError, e:
        if output_encoding != "utf-8":
            raise Exception("Cannot encode %s to %s (You will want to try to force output encoding by e.g. -E utf-8)" % (repr(e.object), repr(e.encoding)))
        else:
            raise Exception("Cannot encode %s to utf-8 (Please report bug.)" % (repr(e.object)))
    return 0

if __name__ == "__main__":
    sys.exit(do_main())
