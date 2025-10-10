"""TSI{0,1,2,3,5} are private tables used by Microsoft Visual TrueType (VTT)
tool to store its hinting source data.

TSI0 is the index table containing the lengths and offsets for the glyph
programs and 'extra' programs ('fpgm', 'prep', and 'cvt') that are contained
in the TSI1 table.

See also https://learn.microsoft.com/en-us/typography/tools/vtt/tsi-tables
"""

import logging
import struct

from . import DefaultTable

log = logging.getLogger(__name__)

tsi0Format = ">HHL"


def fixlongs(glyphID, textLength, textOffset):
    return int(glyphID), int(textLength), textOffset


class table_T_S_I__0(DefaultTable.DefaultTable):
    dependencies = ["TSI1"]

    def decompile(self, data, ttFont):
        numGlyphs = ttFont["maxp"].numGlyphs
        indices = []
        size = struct.calcsize(tsi0Format)
        numEntries = len(data) // size
        if numEntries != numGlyphs + 5:
            diff = numEntries - numGlyphs - 5
            log.warning(
                "Number of glyphPrograms differs from the number of glyphs in the font "
                f"by {abs(diff)} ({numEntries - 5} programs vs. {numGlyphs} glyphs)."
            )
        for _ in range(numEntries):
            glyphID, textLength, textOffset = fixlongs(
                *struct.unpack(tsi0Format, data[:size])
            )
            indices.append((glyphID, textLength, textOffset))
            data = data[size:]
        assert len(data) == 0
        assert indices[-5] == (0xFFFE, 0, 0xABFC1F34), "bad magic number"
        self.indices = indices[:-5]
        self.extra_indices = indices[-4:]

    def compile(self, ttFont):
        if not hasattr(self, "indices"):
            # We have no corresponding table (TSI1 or TSI3); let's return
            # no data, which effectively means "ignore us".
            return b""
        data = b""
        for index, textLength, textOffset in self.indices:
            data = data + struct.pack(tsi0Format, index, textLength, textOffset)
        data = data + struct.pack(tsi0Format, 0xFFFE, 0, 0xABFC1F34)
        for index, textLength, textOffset in self.extra_indices:
            data = data + struct.pack(tsi0Format, index, textLength, textOffset)
        return data

    def set(self, indices, extra_indices):
        # gets called by 'TSI1' or 'TSI3'
        self.indices = indices
        self.extra_indices = extra_indices

    def toXML(self, writer, ttFont):
        writer.comment("This table will be calculated by the compiler")
        writer.newline()
