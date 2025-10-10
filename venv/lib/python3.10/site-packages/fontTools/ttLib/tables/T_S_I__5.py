"""TSI{0,1,2,3,5} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its hinting source data.

TSI5 contains the VTT character groups.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

import array
import logging
import sys

from fontTools.misc.textTools import safeEval

from . import DefaultTable

log = logging.getLogger(__name__)


class table_T_S_I__5(DefaultTable.DefaultTable):
    def decompile(self, data, ttFont):
        numGlyphs = ttFont["maxp"].numGlyphs
        a = array.array("H")
        a.frombytes(data)
        if sys.byteorder != "big":
            a.byteswap()
        self.glyphGrouping = {}
        numEntries = len(data) // 2
        if numEntries != numGlyphs:
            diff = numEntries - numGlyphs
            log.warning(
                "Number of entries differs from the number of glyphs in the font "
                f"by {abs(diff)} ({numEntries} entries vs. {numGlyphs} glyphs)."
            )
        for i in range(numEntries):
            self.glyphGrouping[ttFont.getGlyphName(i)] = a[i]

    def compile(self, ttFont):
        glyphNames = ttFont.getGlyphOrder()
        a = array.array("H")
        for glyphName in glyphNames:
            a.append(self.glyphGrouping.get(glyphName, 0))
        if sys.byteorder != "big":
            a.byteswap()
        return a.tobytes()

    def toXML(self, writer, ttFont):
        names = sorted(self.glyphGrouping.keys())
        for glyphName in names:
            writer.simpletag(
                "glyphgroup", name=glyphName, value=self.glyphGrouping[glyphName]
            )
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "glyphGrouping"):
            self.glyphGrouping = {}
        if name != "glyphgroup":
            return
        self.glyphGrouping[attrs["name"]] = safeEval(attrs["value"])
