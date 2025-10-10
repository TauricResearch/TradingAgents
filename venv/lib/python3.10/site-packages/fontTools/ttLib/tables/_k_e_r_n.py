from fontTools.ttLib import getSearchRange
from fontTools.misc.textTools import safeEval, readHex
from fontTools.misc.fixedTools import fixedToFloat as fi2fl, floatToFixed as fl2fi
from . import DefaultTable
import struct
import sys
import array
import logging


log = logging.getLogger(__name__)


class table__k_e_r_n(DefaultTable.DefaultTable):
    """Kerning table

    The ``kern`` table contains values that contextually adjust the inter-glyph
    spacing for the glyphs in a ``glyf`` table.

    Note that similar contextual spacing adjustments can also be stored
    in the "kern" feature of a ``GPOS`` table.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/kern
    """

    def getkern(self, format):
        for subtable in self.kernTables:
            if subtable.format == format:
                return subtable
        return None  # not found

    def decompile(self, data, ttFont):
        version, nTables = struct.unpack(">HH", data[:4])
        apple = False
        if (len(data) >= 8) and (version == 1):
            # AAT Apple's "new" format. Hm.
            version, nTables = struct.unpack(">LL", data[:8])
            self.version = fi2fl(version, 16)
            data = data[8:]
            apple = True
        else:
            self.version = version
            data = data[4:]
        self.kernTables = []
        for i in range(nTables):
            if self.version == 1.0:
                # Apple
                length, coverage, subtableFormat = struct.unpack(">LBB", data[:6])
            else:
                # in OpenType spec the "version" field refers to the common
                # subtable header; the actual subtable format is stored in
                # the 8-15 mask bits of "coverage" field.
                # This "version" is always 0 so we ignore it here
                _, length, subtableFormat, coverage = struct.unpack(">HHBB", data[:6])
                if nTables == 1 and subtableFormat == 0:
                    # The "length" value is ignored since some fonts
                    # (like OpenSans and Calibri) have a subtable larger than
                    # its value.
                    (nPairs,) = struct.unpack(">H", data[6:8])
                    calculated_length = (nPairs * 6) + 14
                    if length != calculated_length:
                        log.warning(
                            "'kern' subtable longer than defined: "
                            "%d bytes instead of %d bytes" % (calculated_length, length)
                        )
                    length = calculated_length
            if subtableFormat not in kern_classes:
                subtable = KernTable_format_unkown(subtableFormat)
            else:
                subtable = kern_classes[subtableFormat](apple)
            subtable.decompile(data[:length], ttFont)
            self.kernTables.append(subtable)
            data = data[length:]

    def compile(self, ttFont):
        if hasattr(self, "kernTables"):
            nTables = len(self.kernTables)
        else:
            nTables = 0
        if self.version == 1.0:
            # AAT Apple's "new" format.
            data = struct.pack(">LL", fl2fi(self.version, 16), nTables)
        else:
            data = struct.pack(">HH", self.version, nTables)
        if hasattr(self, "kernTables"):
            for subtable in self.kernTables:
                data = data + subtable.compile(ttFont)
        return data

    def toXML(self, writer, ttFont):
        writer.simpletag("version", value=self.version)
        writer.newline()
        for subtable in self.kernTables:
            subtable.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = safeEval(attrs["value"])
            return
        if name != "kernsubtable":
            return
        if not hasattr(self, "kernTables"):
            self.kernTables = []
        format = safeEval(attrs["format"])
        if format not in kern_classes:
            subtable = KernTable_format_unkown(format)
        else:
            apple = self.version == 1.0
            subtable = kern_classes[format](apple)
        self.kernTables.append(subtable)
        subtable.fromXML(name, attrs, content, ttFont)


class KernTable_format_0(object):
    # 'version' is kept for backward compatibility
    version = format = 0

    def __init__(self, apple=False):
        self.apple = apple

    def decompile(self, data, ttFont):
        if not self.apple:
            version, length, subtableFormat, coverage = struct.unpack(">HHBB", data[:6])
            if version != 0:
                from fontTools.ttLib import TTLibError

                raise TTLibError("unsupported kern subtable version: %d" % version)
            tupleIndex = None
            # Should we also assert length == len(data)?
            data = data[6:]
        else:
            length, coverage, subtableFormat, tupleIndex = struct.unpack(
                ">LBBH", data[:8]
            )
            data = data[8:]
        assert self.format == subtableFormat, "unsupported format"
        self.coverage = coverage
        self.tupleIndex = tupleIndex

        self.kernTable = kernTable = {}

        nPairs, searchRange, entrySelector, rangeShift = struct.unpack(
            ">HHHH", data[:8]
        )
        data = data[8:]

        datas = array.array("H", data[: 6 * nPairs])
        if sys.byteorder != "big":
            datas.byteswap()
        it = iter(datas)
        glyphOrder = ttFont.getGlyphOrder()
        for k in range(nPairs):
            left, right, value = next(it), next(it), next(it)
            if value >= 32768:
                value -= 65536
            try:
                kernTable[(glyphOrder[left], glyphOrder[right])] = value
            except IndexError:
                # Slower, but will not throw an IndexError on an invalid
                # glyph id.
                kernTable[(ttFont.getGlyphName(left), ttFont.getGlyphName(right))] = (
                    value
                )
        if len(data) > 6 * nPairs + 4:  # Ignore up to 4 bytes excess
            log.warning(
                "excess data in 'kern' subtable: %d bytes", len(data) - 6 * nPairs
            )

    def compile(self, ttFont):
        nPairs = min(len(self.kernTable), 0xFFFF)
        searchRange, entrySelector, rangeShift = getSearchRange(nPairs, 6)
        searchRange &= 0xFFFF
        entrySelector = min(entrySelector, 0xFFFF)
        rangeShift = min(rangeShift, 0xFFFF)
        data = struct.pack(">HHHH", nPairs, searchRange, entrySelector, rangeShift)

        # yeehee! (I mean, turn names into indices)
        try:
            reverseOrder = ttFont.getReverseGlyphMap()
            kernTable = sorted(
                (reverseOrder[left], reverseOrder[right], value)
                for ((left, right), value) in self.kernTable.items()
            )
        except KeyError:
            # Slower, but will not throw KeyError on invalid glyph id.
            getGlyphID = ttFont.getGlyphID
            kernTable = sorted(
                (getGlyphID(left), getGlyphID(right), value)
                for ((left, right), value) in self.kernTable.items()
            )

        for left, right, value in kernTable:
            data = data + struct.pack(">HHh", left, right, value)

        if not self.apple:
            version = 0
            length = len(data) + 6
            if length >= 0x10000:
                log.warning(
                    '"kern" subtable overflow, '
                    "truncating length value while preserving pairs."
                )
                length &= 0xFFFF
            header = struct.pack(">HHBB", version, length, self.format, self.coverage)
        else:
            if self.tupleIndex is None:
                # sensible default when compiling a TTX from an old fonttools
                # or when inserting a Windows-style format 0 subtable into an
                # Apple version=1.0 kern table
                log.warning("'tupleIndex' is None; default to 0")
                self.tupleIndex = 0
            length = len(data) + 8
            header = struct.pack(
                ">LBBH", length, self.coverage, self.format, self.tupleIndex
            )
        return header + data

    def toXML(self, writer, ttFont):
        attrs = dict(coverage=self.coverage, format=self.format)
        if self.apple:
            if self.tupleIndex is None:
                log.warning("'tupleIndex' is None; default to 0")
                attrs["tupleIndex"] = 0
            else:
                attrs["tupleIndex"] = self.tupleIndex
        writer.begintag("kernsubtable", **attrs)
        writer.newline()
        items = sorted(self.kernTable.items())
        for (left, right), value in items:
            writer.simpletag("pair", [("l", left), ("r", right), ("v", value)])
            writer.newline()
        writer.endtag("kernsubtable")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.coverage = safeEval(attrs["coverage"])
        subtableFormat = safeEval(attrs["format"])
        if self.apple:
            if "tupleIndex" in attrs:
                self.tupleIndex = safeEval(attrs["tupleIndex"])
            else:
                # previous fontTools versions didn't export tupleIndex
                log.warning("Apple kern subtable is missing 'tupleIndex' attribute")
                self.tupleIndex = None
        else:
            self.tupleIndex = None
        assert subtableFormat == self.format, "unsupported format"
        if not hasattr(self, "kernTable"):
            self.kernTable = {}
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            self.kernTable[(attrs["l"], attrs["r"])] = safeEval(attrs["v"])

    def __getitem__(self, pair):
        return self.kernTable[pair]

    def __setitem__(self, pair, value):
        self.kernTable[pair] = value

    def __delitem__(self, pair):
        del self.kernTable[pair]


class KernTable_format_unkown(object):
    def __init__(self, format):
        self.format = format

    def decompile(self, data, ttFont):
        self.data = data

    def compile(self, ttFont):
        return self.data

    def toXML(self, writer, ttFont):
        writer.begintag("kernsubtable", format=self.format)
        writer.newline()
        writer.comment("unknown 'kern' subtable format")
        writer.newline()
        writer.dumphex(self.data)
        writer.endtag("kernsubtable")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.decompile(readHex(content), ttFont)


kern_classes = {0: KernTable_format_0}
