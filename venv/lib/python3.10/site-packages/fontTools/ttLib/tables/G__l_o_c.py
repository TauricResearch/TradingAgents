from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from . import DefaultTable
import array
import sys


Gloc_header = """
    >        # big endian
    version: 16.16F    # Table version
    flags:        H    # bit 0: 1=long format, 0=short format
                       # bit 1: 1=attribute names, 0=no names
    numAttribs:   H    # NUmber of attributes
"""


class table_G__l_o_c(DefaultTable.DefaultTable):
    """Graphite Index to Glyph Atttributes table

    See also https://graphite.sil.org/graphite_techAbout#graphite-font-tables
    """

    dependencies = ["Glat"]

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.attribIds = None
        self.numAttribs = 0

    def decompile(self, data, ttFont):
        _, data = sstruct.unpack2(Gloc_header, data, self)
        flags = self.flags
        del self.flags
        self.locations = array.array("I" if flags & 1 else "H")
        self.locations.frombytes(data[: len(data) - self.numAttribs * (flags & 2)])
        if sys.byteorder != "big":
            self.locations.byteswap()
        self.attribIds = array.array("H")
        if flags & 2:
            self.attribIds.frombytes(data[-self.numAttribs * 2 :])
            if sys.byteorder != "big":
                self.attribIds.byteswap()

    def compile(self, ttFont):
        data = sstruct.pack(
            Gloc_header,
            dict(
                version=1.0,
                flags=(bool(self.attribIds) << 1) + (self.locations.typecode == "I"),
                numAttribs=self.numAttribs,
            ),
        )
        if sys.byteorder != "big":
            self.locations.byteswap()
        data += self.locations.tobytes()
        if sys.byteorder != "big":
            self.locations.byteswap()
        if self.attribIds:
            if sys.byteorder != "big":
                self.attribIds.byteswap()
            data += self.attribIds.tobytes()
            if sys.byteorder != "big":
                self.attribIds.byteswap()
        return data

    def set(self, locations):
        long_format = max(locations) >= 65536
        self.locations = array.array("I" if long_format else "H", locations)

    def toXML(self, writer, ttFont):
        writer.simpletag("attributes", number=self.numAttribs)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "attributes":
            self.numAttribs = int(safeEval(attrs["number"]))

    def __getitem__(self, index):
        return self.locations[index]

    def __len__(self):
        return len(self.locations)

    def __iter__(self):
        return iter(self.locations)
