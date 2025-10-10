from fontTools.misc import sstruct
from fontTools.misc.textTools import bytechr, byteord, strjoin
from . import DefaultTable
import array
from collections.abc import Mapping

hdmxHeaderFormat = """
	>   # big endian!
	version:	H
	numRecords:	H
	recordSize:	l
"""


class _GlyphnamedList(Mapping):
    def __init__(self, reverseGlyphOrder, data):
        self._array = data
        self._map = dict(reverseGlyphOrder)

    def __getitem__(self, k):
        return self._array[self._map[k]]

    def __len__(self):
        return len(self._map)

    def __iter__(self):
        return iter(self._map)

    def keys(self):
        return self._map.keys()


class table__h_d_m_x(DefaultTable.DefaultTable):
    """Horizontal Device Metrics table

    The ``hdmx`` table is an optional table that stores advance widths for
    glyph outlines at specified pixel sizes.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/hdmx
    """

    def decompile(self, data, ttFont):
        numGlyphs = ttFont["maxp"].numGlyphs
        glyphOrder = ttFont.getGlyphOrder()
        dummy, data = sstruct.unpack2(hdmxHeaderFormat, data, self)
        self.hdmx = {}
        for i in range(self.numRecords):
            ppem = byteord(data[0])
            maxSize = byteord(data[1])
            widths = _GlyphnamedList(
                ttFont.getReverseGlyphMap(), array.array("B", data[2 : 2 + numGlyphs])
            )
            self.hdmx[ppem] = widths
            data = data[self.recordSize :]
        assert len(data) == 0, "too much hdmx data"

    def compile(self, ttFont):
        self.version = 0
        numGlyphs = ttFont["maxp"].numGlyphs
        glyphOrder = ttFont.getGlyphOrder()
        self.recordSize = 4 * ((2 + numGlyphs + 3) // 4)
        pad = (self.recordSize - 2 - numGlyphs) * b"\0"
        self.numRecords = len(self.hdmx)
        data = sstruct.pack(hdmxHeaderFormat, self)
        items = sorted(self.hdmx.items())
        for ppem, widths in items:
            data = data + bytechr(ppem) + bytechr(max(widths.values()))
            for glyphName in glyphOrder:
                width = widths[glyphName]
                data = data + bytechr(width)
            data = data + pad
        return data

    def toXML(self, writer, ttFont):
        writer.begintag("hdmxData")
        writer.newline()
        ppems = sorted(self.hdmx.keys())
        records = []
        format = ""
        for ppem in ppems:
            widths = self.hdmx[ppem]
            records.append(widths)
            format = format + "%4d"
        glyphNames = ttFont.getGlyphOrder()[:]
        glyphNames.sort()
        maxNameLen = max(map(len, glyphNames))
        format = "%" + repr(maxNameLen) + "s:" + format + " ;"
        writer.write(format % (("ppem",) + tuple(ppems)))
        writer.newline()
        writer.newline()
        for glyphName in glyphNames:
            row = []
            for ppem in ppems:
                widths = self.hdmx[ppem]
                row.append(widths[glyphName])
            if ";" in glyphName:
                glyphName = "\\x3b".join(glyphName.split(";"))
            writer.write(format % ((glyphName,) + tuple(row)))
            writer.newline()
        writer.endtag("hdmxData")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name != "hdmxData":
            return
        content = strjoin(content)
        lines = content.split(";")
        topRow = lines[0].split()
        assert topRow[0] == "ppem:", "illegal hdmx format"
        ppems = list(map(int, topRow[1:]))
        self.hdmx = hdmx = {}
        for ppem in ppems:
            hdmx[ppem] = {}
        lines = (line.split() for line in lines[1:])
        for line in lines:
            if not line:
                continue
            assert line[0][-1] == ":", "illegal hdmx format"
            glyphName = line[0][:-1]
            if "\\" in glyphName:
                from fontTools.misc.textTools import safeEval

                glyphName = safeEval('"""' + glyphName + '"""')
            line = list(map(int, line[1:]))
            assert len(line) == len(ppems), "illegal hdmx format"
            for i, ppem in enumerate(ppems):
                hdmx[ppem][glyphName] = line[i]
