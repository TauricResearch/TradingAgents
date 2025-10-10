from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from fontTools.misc.fixedTools import (
    ensureVersionIsLong as fi2ve,
    versionToFixed as ve2fi,
)
from . import DefaultTable
import math


hheaFormat = """
		>  # big endian
		tableVersion:           L
		ascent:                 h
		descent:                h
		lineGap:                h
		advanceWidthMax:        H
		minLeftSideBearing:     h
		minRightSideBearing:    h
		xMaxExtent:             h
		caretSlopeRise:         h
		caretSlopeRun:          h
		caretOffset:            h
		reserved0:              h
		reserved1:              h
		reserved2:              h
		reserved3:              h
		metricDataFormat:       h
		numberOfHMetrics:       H
"""


class table__h_h_e_a(DefaultTable.DefaultTable):
    """Horizontal Header table

    The ``hhea`` table contains information needed during horizontal
    text layout.

    .. note::
       This converter class is kept in sync with the :class:`._v_h_e_a.table__v_h_e_a`
       table constructor.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/hhea
    """

    # Note: Keep in sync with table__v_h_e_a

    dependencies = ["hmtx", "glyf", "CFF ", "CFF2"]

    # OpenType spec renamed these, add aliases for compatibility
    @property
    def ascender(self):
        return self.ascent

    @ascender.setter
    def ascender(self, value):
        self.ascent = value

    @property
    def descender(self):
        return self.descent

    @descender.setter
    def descender(self, value):
        self.descent = value

    def decompile(self, data, ttFont):
        sstruct.unpack(hheaFormat, data, self)

    def compile(self, ttFont):
        if ttFont.recalcBBoxes and (
            ttFont.isLoaded("glyf")
            or ttFont.isLoaded("CFF ")
            or ttFont.isLoaded("CFF2")
        ):
            self.recalc(ttFont)
        self.tableVersion = fi2ve(self.tableVersion)
        return sstruct.pack(hheaFormat, self)

    def recalc(self, ttFont):
        if "hmtx" not in ttFont:
            return

        hmtxTable = ttFont["hmtx"]
        self.advanceWidthMax = max(adv for adv, _ in hmtxTable.metrics.values())

        boundsWidthDict = {}
        if "glyf" in ttFont:
            glyfTable = ttFont["glyf"]
            for name in ttFont.getGlyphOrder():
                g = glyfTable[name]
                if g.numberOfContours == 0:
                    continue
                if g.numberOfContours < 0 and not hasattr(g, "xMax"):
                    # Composite glyph without extents set.
                    # Calculate those.
                    g.recalcBounds(glyfTable)
                boundsWidthDict[name] = g.xMax - g.xMin
        elif "CFF " in ttFont or "CFF2" in ttFont:
            if "CFF " in ttFont:
                topDict = ttFont["CFF "].cff.topDictIndex[0]
            else:
                topDict = ttFont["CFF2"].cff.topDictIndex[0]
            charStrings = topDict.CharStrings
            for name in ttFont.getGlyphOrder():
                cs = charStrings[name]
                bounds = cs.calcBounds(charStrings)
                if bounds is not None:
                    boundsWidthDict[name] = int(
                        math.ceil(bounds[2]) - math.floor(bounds[0])
                    )

        if boundsWidthDict:
            minLeftSideBearing = float("inf")
            minRightSideBearing = float("inf")
            xMaxExtent = -float("inf")
            for name, boundsWidth in boundsWidthDict.items():
                advanceWidth, lsb = hmtxTable[name]
                rsb = advanceWidth - lsb - boundsWidth
                extent = lsb + boundsWidth
                minLeftSideBearing = min(minLeftSideBearing, lsb)
                minRightSideBearing = min(minRightSideBearing, rsb)
                xMaxExtent = max(xMaxExtent, extent)
            self.minLeftSideBearing = minLeftSideBearing
            self.minRightSideBearing = minRightSideBearing
            self.xMaxExtent = xMaxExtent

        else:  # No glyph has outlines.
            self.minLeftSideBearing = 0
            self.minRightSideBearing = 0
            self.xMaxExtent = 0

    def toXML(self, writer, ttFont):
        formatstring, names, fixes = sstruct.getformat(hheaFormat)
        for name in names:
            value = getattr(self, name)
            if name == "tableVersion":
                value = fi2ve(value)
                value = "0x%08x" % value
            writer.simpletag(name, value=value)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "tableVersion":
            setattr(self, name, ve2fi(attrs["value"]))
            return
        setattr(self, name, safeEval(attrs["value"]))
