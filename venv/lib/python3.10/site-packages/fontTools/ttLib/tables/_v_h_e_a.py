from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from fontTools.misc.fixedTools import (
    ensureVersionIsLong as fi2ve,
    versionToFixed as ve2fi,
)
from . import DefaultTable
import math


vheaFormat = """
		>	# big endian
		tableVersion:		L
		ascent:			h
		descent:		h
		lineGap:		h
		advanceHeightMax:	H
		minTopSideBearing:	h
		minBottomSideBearing:	h
		yMaxExtent:		h
		caretSlopeRise:		h
		caretSlopeRun:		h
		caretOffset:		h
		reserved1:		h
		reserved2:		h
		reserved3:		h
		reserved4:		h
		metricDataFormat:	h
		numberOfVMetrics:	H
"""


class table__v_h_e_a(DefaultTable.DefaultTable):
    """Vertical Header table

    The ``vhea`` table contains information needed during vertical
    text layout.

    .. note::
       This converter class is kept in sync with the :class:`._h_h_e_a.table__h_h_e_a`
       table constructor.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/vhea
    """

    # Note: Keep in sync with table__h_h_e_a

    dependencies = ["vmtx", "glyf", "CFF ", "CFF2"]

    def decompile(self, data, ttFont):
        sstruct.unpack(vheaFormat, data, self)

    def compile(self, ttFont):
        if ttFont.recalcBBoxes and (
            ttFont.isLoaded("glyf")
            or ttFont.isLoaded("CFF ")
            or ttFont.isLoaded("CFF2")
        ):
            self.recalc(ttFont)
        self.tableVersion = fi2ve(self.tableVersion)
        return sstruct.pack(vheaFormat, self)

    def recalc(self, ttFont):
        if "vmtx" not in ttFont:
            return

        vmtxTable = ttFont["vmtx"]
        self.advanceHeightMax = max(adv for adv, _ in vmtxTable.metrics.values())

        boundsHeightDict = {}
        if "glyf" in ttFont:
            glyfTable = ttFont["glyf"]
            for name in ttFont.getGlyphOrder():
                g = glyfTable[name]
                if g.numberOfContours == 0:
                    continue
                if g.numberOfContours < 0 and not hasattr(g, "yMax"):
                    # Composite glyph without extents set.
                    # Calculate those.
                    g.recalcBounds(glyfTable)
                boundsHeightDict[name] = g.yMax - g.yMin
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
                    boundsHeightDict[name] = int(
                        math.ceil(bounds[3]) - math.floor(bounds[1])
                    )

        if boundsHeightDict:
            minTopSideBearing = float("inf")
            minBottomSideBearing = float("inf")
            yMaxExtent = -float("inf")
            for name, boundsHeight in boundsHeightDict.items():
                advanceHeight, tsb = vmtxTable[name]
                bsb = advanceHeight - tsb - boundsHeight
                extent = tsb + boundsHeight
                minTopSideBearing = min(minTopSideBearing, tsb)
                minBottomSideBearing = min(minBottomSideBearing, bsb)
                yMaxExtent = max(yMaxExtent, extent)
            self.minTopSideBearing = minTopSideBearing
            self.minBottomSideBearing = minBottomSideBearing
            self.yMaxExtent = yMaxExtent

        else:  # No glyph has outlines.
            self.minTopSideBearing = 0
            self.minBottomSideBearing = 0
            self.yMaxExtent = 0

    def toXML(self, writer, ttFont):
        formatstring, names, fixes = sstruct.getformat(vheaFormat)
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

    # reserved0 is caretOffset for legacy reasons
    @property
    def reserved0(self):
        return self.caretOffset

    @reserved0.setter
    def reserved0(self, value):
        self.caretOffset = value
