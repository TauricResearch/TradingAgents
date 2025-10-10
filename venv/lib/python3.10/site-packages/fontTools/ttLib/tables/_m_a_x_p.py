from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from . import DefaultTable

maxpFormat_0_5 = """
		>	# big endian
		tableVersion:           i
		numGlyphs:              H
"""

maxpFormat_1_0_add = """
		>	# big endian
		maxPoints:              H
		maxContours:            H
		maxCompositePoints:     H
		maxCompositeContours:   H
		maxZones:               H
		maxTwilightPoints:      H
		maxStorage:             H
		maxFunctionDefs:        H
		maxInstructionDefs:     H
		maxStackElements:       H
		maxSizeOfInstructions:  H
		maxComponentElements:   H
		maxComponentDepth:      H
"""


class table__m_a_x_p(DefaultTable.DefaultTable):
    """Maximum Profile table

    The ``maxp`` table contains the memory requirements for the data in
    the font.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/maxp
    """

    dependencies = ["glyf"]

    def decompile(self, data, ttFont):
        dummy, data = sstruct.unpack2(maxpFormat_0_5, data, self)
        self.numGlyphs = int(self.numGlyphs)
        if self.tableVersion != 0x00005000:
            dummy, data = sstruct.unpack2(maxpFormat_1_0_add, data, self)
        assert len(data) == 0

    def compile(self, ttFont):
        if "glyf" in ttFont:
            if ttFont.isLoaded("glyf") and ttFont.recalcBBoxes:
                self.recalc(ttFont)
        else:
            pass  # CFF
        self.numGlyphs = len(ttFont.getGlyphOrder())
        if self.tableVersion != 0x00005000:
            self.tableVersion = 0x00010000
        data = sstruct.pack(maxpFormat_0_5, self)
        if self.tableVersion == 0x00010000:
            data = data + sstruct.pack(maxpFormat_1_0_add, self)
        return data

    def recalc(self, ttFont):
        """Recalculate the font bounding box, and most other maxp values except
        for the TT instructions values. Also recalculate the value of bit 1
        of the flags field and the font bounding box of the 'head' table.
        """
        glyfTable = ttFont["glyf"]
        hmtxTable = ttFont["hmtx"]
        headTable = ttFont["head"]
        self.numGlyphs = len(glyfTable)
        INFINITY = 100000
        xMin = +INFINITY
        yMin = +INFINITY
        xMax = -INFINITY
        yMax = -INFINITY
        maxPoints = 0
        maxContours = 0
        maxCompositePoints = 0
        maxCompositeContours = 0
        maxComponentElements = 0
        maxComponentDepth = 0
        allXMinIsLsb = 1
        for glyphName in ttFont.getGlyphOrder():
            g = glyfTable[glyphName]
            if g.numberOfContours:
                if hmtxTable[glyphName][1] != g.xMin:
                    allXMinIsLsb = 0
                xMin = min(xMin, g.xMin)
                yMin = min(yMin, g.yMin)
                xMax = max(xMax, g.xMax)
                yMax = max(yMax, g.yMax)
                if g.numberOfContours > 0:
                    nPoints, nContours = g.getMaxpValues()
                    maxPoints = max(maxPoints, nPoints)
                    maxContours = max(maxContours, nContours)
                elif g.isComposite():
                    nPoints, nContours, componentDepth = g.getCompositeMaxpValues(
                        glyfTable
                    )
                    maxCompositePoints = max(maxCompositePoints, nPoints)
                    maxCompositeContours = max(maxCompositeContours, nContours)
                    maxComponentElements = max(maxComponentElements, len(g.components))
                    maxComponentDepth = max(maxComponentDepth, componentDepth)
        if xMin == +INFINITY:
            headTable.xMin = 0
            headTable.yMin = 0
            headTable.xMax = 0
            headTable.yMax = 0
        else:
            headTable.xMin = xMin
            headTable.yMin = yMin
            headTable.xMax = xMax
            headTable.yMax = yMax
        self.maxPoints = maxPoints
        self.maxContours = maxContours
        self.maxCompositePoints = maxCompositePoints
        self.maxCompositeContours = maxCompositeContours
        self.maxComponentElements = maxComponentElements
        self.maxComponentDepth = maxComponentDepth
        if allXMinIsLsb:
            headTable.flags = headTable.flags | 0x2
        else:
            headTable.flags = headTable.flags & ~0x2

    def testrepr(self):
        items = sorted(self.__dict__.items())
        print(". . . . . . . . .")
        for combo in items:
            print("  %s: %s" % combo)
        print(". . . . . . . . .")

    def toXML(self, writer, ttFont):
        if self.tableVersion != 0x00005000:
            writer.comment("Most of this table will be recalculated by the compiler")
            writer.newline()
        formatstring, names, fixes = sstruct.getformat(maxpFormat_0_5)
        if self.tableVersion != 0x00005000:
            formatstring, names_1_0, fixes = sstruct.getformat(maxpFormat_1_0_add)
            names = {**names, **names_1_0}
        for name in names:
            value = getattr(self, name)
            if name == "tableVersion":
                value = hex(value)
            writer.simpletag(name, value=value)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        setattr(self, name, safeEval(attrs["value"]))
