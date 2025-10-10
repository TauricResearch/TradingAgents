from fontTools.misc.textTools import safeEval
from . import DefaultTable
import struct
import array

# XXX I've lowered the strictness, to make sure Apple's own Chicago
# XXX gets through. They're looking into it, I hope to raise the standards
# XXX back to normal eventually.


class table_L_T_S_H_(DefaultTable.DefaultTable):
    """Linear Threshold table

    The ``LTSH`` table contains per-glyph settings indicating the ppem sizes
    at which the advance width metric should be scaled linearly, despite the
    effects of any TrueType instructions that might otherwise alter the
    advance width.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/ltsh
    """

    def decompile(self, data, ttFont):
        version, numGlyphs = struct.unpack(">HH", data[:4])
        data = data[4:]
        assert version == 0, "unknown version: %s" % version
        assert (len(data) % numGlyphs) < 4, "numGlyphs doesn't match data length"
        # ouch: the assertion is not true in Chicago!
        # assert numGlyphs == ttFont['maxp'].numGlyphs
        yPels = array.array("B")
        yPels.frombytes(data)
        self.yPels = {}
        for i in range(numGlyphs):
            self.yPels[ttFont.getGlyphName(i)] = yPels[i]

    def compile(self, ttFont):
        version = 0
        names = list(self.yPels.keys())
        numGlyphs = len(names)
        yPels = [0] * numGlyphs
        # ouch: the assertion is not true in Chicago!
        # assert len(self.yPels) == ttFont['maxp'].numGlyphs == numGlyphs
        for name in names:
            yPels[ttFont.getGlyphID(name)] = self.yPels[name]
        yPels = array.array("B", yPels)
        return struct.pack(">HH", version, numGlyphs) + yPels.tobytes()

    def toXML(self, writer, ttFont):
        names = sorted(self.yPels.keys())
        for name in names:
            writer.simpletag("yPel", name=name, value=self.yPels[name])
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "yPels"):
            self.yPels = {}
        if name != "yPel":
            return  # ignore unknown tags
        self.yPels[attrs["name"]] = safeEval(attrs["value"])
