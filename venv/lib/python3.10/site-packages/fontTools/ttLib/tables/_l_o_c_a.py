from . import DefaultTable
import sys
import array
import logging


log = logging.getLogger(__name__)


class table__l_o_c_a(DefaultTable.DefaultTable):
    """Index to Location table

    The ``loca`` table stores the offsets in the ``glyf`` table that correspond
    to the descriptions of each glyph. The glyphs are references by Glyph ID.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/loca
    """

    dependencies = ["glyf"]

    def decompile(self, data, ttFont):
        longFormat = ttFont["head"].indexToLocFormat
        if longFormat:
            format = "I"
        else:
            format = "H"
        locations = array.array(format)
        locations.frombytes(data)
        if sys.byteorder != "big":
            locations.byteswap()
        if not longFormat:
            locations = array.array("I", (2 * l for l in locations))
        if len(locations) < (ttFont["maxp"].numGlyphs + 1):
            log.warning(
                "corrupt 'loca' table, or wrong numGlyphs in 'maxp': %d %d",
                len(locations) - 1,
                ttFont["maxp"].numGlyphs,
            )
        self.locations = locations

    def compile(self, ttFont):
        try:
            max_location = max(self.locations)
        except AttributeError:
            self.set([])
            max_location = 0
        if max_location < 0x20000 and all(l % 2 == 0 for l in self.locations):
            locations = array.array("H")
            for location in self.locations:
                locations.append(location // 2)
            ttFont["head"].indexToLocFormat = 0
        else:
            locations = array.array("I", self.locations)
            ttFont["head"].indexToLocFormat = 1
        if sys.byteorder != "big":
            locations.byteswap()
        return locations.tobytes()

    def set(self, locations):
        self.locations = array.array("I", locations)

    def toXML(self, writer, ttFont):
        writer.comment("The 'loca' table will be calculated by the compiler")
        writer.newline()

    def __getitem__(self, index):
        return self.locations[index]

    def __len__(self):
        return len(self.locations)
