"""xmlWriter.py -- Simple XML authoring class"""

from fontTools.misc.textTools import byteord, strjoin, tobytes, tostr
import sys
import os
import string
import logging
import itertools

INDENT = "  "
TTX_LOG = logging.getLogger("fontTools.ttx")
REPLACEMENT = "?"
ILLEGAL_XML_CHARS = dict.fromkeys(
    itertools.chain(
        range(0x00, 0x09),
        (0x0B, 0x0C),
        range(0x0E, 0x20),
        range(0xD800, 0xE000),
        (0xFFFE, 0xFFFF),
    ),
    REPLACEMENT,
)


class XMLWriter(object):
    def __init__(
        self,
        fileOrPath,
        indentwhite=INDENT,
        idlefunc=None,
        encoding="utf_8",
        newlinestr="\n",
    ):
        if encoding.lower().replace("-", "").replace("_", "") != "utf8":
            raise Exception("Only UTF-8 encoding is supported.")
        if fileOrPath == "-":
            fileOrPath = sys.stdout
        if not hasattr(fileOrPath, "write"):
            self.filename = fileOrPath
            self.file = open(fileOrPath, "wb")
            self._closeStream = True
        else:
            self.filename = None
            # assume writable file object
            self.file = fileOrPath
            self._closeStream = False

        # Figure out if writer expects bytes or unicodes
        try:
            # The bytes check should be first.  See:
            # https://github.com/fonttools/fonttools/pull/233
            self.file.write(b"")
            self.totype = tobytes
        except TypeError:
            # This better not fail.
            self.file.write("")
            self.totype = tostr
        self.indentwhite = self.totype(indentwhite)
        if newlinestr is None:
            self.newlinestr = self.totype(os.linesep)
        else:
            self.newlinestr = self.totype(newlinestr)
        self.indentlevel = 0
        self.stack = []
        self.needindent = 1
        self.idlefunc = idlefunc
        self.idlecounter = 0
        self._writeraw('<?xml version="1.0" encoding="UTF-8"?>')
        self.newline()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.close()

    def close(self):
        if self._closeStream:
            self.file.close()

    def write(self, string, indent=True):
        """Writes text."""
        self._writeraw(escape(string), indent=indent)

    def writecdata(self, string):
        """Writes text in a CDATA section."""
        self._writeraw("<![CDATA[" + string + "]]>")

    def write8bit(self, data, strip=False):
        """Writes a bytes() sequence into the XML, escaping
        non-ASCII bytes.  When this is read in xmlReader,
        the original bytes can be recovered by encoding to
        'latin-1'."""
        self._writeraw(escape8bit(data), strip=strip)

    def write_noindent(self, string):
        """Writes text without indentation."""
        self._writeraw(escape(string), indent=False)

    def _writeraw(self, data, indent=True, strip=False):
        """Writes bytes, possibly indented."""
        if indent and self.needindent:
            self.file.write(self.indentlevel * self.indentwhite)
            self.needindent = 0
        s = self.totype(data, encoding="utf_8")
        if strip:
            s = s.strip()
        self.file.write(s)

    def newline(self):
        self.file.write(self.newlinestr)
        self.needindent = 1
        idlecounter = self.idlecounter
        if not idlecounter % 100 and self.idlefunc is not None:
            self.idlefunc()
        self.idlecounter = idlecounter + 1

    def comment(self, data):
        data = escape(data)
        lines = data.split("\n")
        self._writeraw("<!-- " + lines[0])
        for line in lines[1:]:
            self.newline()
            self._writeraw("     " + line)
        self._writeraw(" -->")

    def simpletag(self, _TAG_, *args, **kwargs):
        attrdata = self.stringifyattrs(*args, **kwargs)
        data = "<%s%s/>" % (_TAG_, attrdata)
        self._writeraw(data)

    def begintag(self, _TAG_, *args, **kwargs):
        attrdata = self.stringifyattrs(*args, **kwargs)
        data = "<%s%s>" % (_TAG_, attrdata)
        self._writeraw(data)
        self.stack.append(_TAG_)
        self.indent()

    def endtag(self, _TAG_):
        assert self.stack and self.stack[-1] == _TAG_, "nonmatching endtag"
        del self.stack[-1]
        self.dedent()
        data = "</%s>" % _TAG_
        self._writeraw(data)

    def dumphex(self, data):
        linelength = 16
        hexlinelength = linelength * 2
        chunksize = 8
        for i in range(0, len(data), linelength):
            hexline = hexStr(data[i : i + linelength])
            line = ""
            white = ""
            for j in range(0, hexlinelength, chunksize):
                line = line + white + hexline[j : j + chunksize]
                white = " "
            self._writeraw(line)
            self.newline()

    def indent(self):
        self.indentlevel = self.indentlevel + 1

    def dedent(self):
        assert self.indentlevel > 0
        self.indentlevel = self.indentlevel - 1

    def stringifyattrs(self, *args, **kwargs):
        if kwargs:
            assert not args
            attributes = sorted(kwargs.items())
        elif args:
            assert len(args) == 1
            attributes = args[0]
        else:
            return ""
        data = ""
        for attr, value in attributes:
            if not isinstance(value, (bytes, str)):
                value = str(value)
            data = data + ' %s="%s"' % (attr, escapeattr(value))
        return data


def escape(data):
    """Escape characters not allowed in `XML 1.0 <https://www.w3.org/TR/xml/#NT-Char>`_."""
    data = tostr(data, "utf_8")
    data = data.replace("&", "&amp;")
    data = data.replace("<", "&lt;")
    data = data.replace(">", "&gt;")
    data = data.replace("\r", "&#13;")

    newData = data.translate(ILLEGAL_XML_CHARS)
    if newData != data:
        maxLen = 10
        preview = repr(data)
        if len(data) > maxLen:
            preview = repr(data[:maxLen])[1:-1] + "..."
        TTX_LOG.warning(
            "Illegal XML character(s) found; replacing offending " "string %r with %r",
            preview,
            REPLACEMENT,
        )
    return newData


def escapeattr(data):
    data = escape(data)
    data = data.replace('"', "&quot;")
    return data


def escape8bit(data):
    """Input is Unicode string."""

    def escapechar(c):
        n = ord(c)
        if 32 <= n <= 127 and c not in "<&>":
            return c
        else:
            return "&#" + repr(n) + ";"

    return strjoin(map(escapechar, data.decode("latin-1")))


def hexStr(s):
    h = string.hexdigits
    r = ""
    for c in s:
        i = byteord(c)
        r = r + h[(i >> 4) & 0xF] + h[i & 0xF]
    return r
