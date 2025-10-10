from collections import deque
from functools import partial
from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval
from fontTools.misc.lazyTools import LazyDict
from fontTools.ttLib import OPTIMIZE_FONT_SPEED
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from . import DefaultTable
import array
import itertools
import logging
import struct
import sys
import fontTools.ttLib.tables.TupleVariation as tv

log = logging.getLogger(__name__)

# https://www.microsoft.com/typography/otspec/gvar.htm
# https://www.microsoft.com/typography/otspec/otvarcommonformats.htm
#
# Apple's documentation of 'gvar':
# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6gvar.html
#
# FreeType2 source code for parsing 'gvar':
# http://git.savannah.gnu.org/cgit/freetype/freetype2.git/tree/src/truetype/ttgxvar.c

GVAR_HEADER_FORMAT_HEAD = """
	> # big endian
	version:			H
	reserved:			H
	axisCount:			H
	sharedTupleCount:		H
	offsetToSharedTuples:		I
"""
# In between the HEAD and TAIL lies the glyphCount, which is
# of different size: 2 bytes for gvar, and 3 bytes for GVAR.
GVAR_HEADER_FORMAT_TAIL = """
	> # big endian
	flags:				H
	offsetToGlyphVariationData:	I
"""

GVAR_HEADER_SIZE_HEAD = sstruct.calcsize(GVAR_HEADER_FORMAT_HEAD)
GVAR_HEADER_SIZE_TAIL = sstruct.calcsize(GVAR_HEADER_FORMAT_TAIL)


class table__g_v_a_r(DefaultTable.DefaultTable):
    """Glyph Variations table

    The ``gvar`` table provides the per-glyph variation data that
    describe how glyph outlines in the ``glyf`` table change across
    the variation space that is defined for the font in the ``fvar``
    table.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/gvar
    """

    dependencies = ["fvar", "glyf"]
    gid_size = 2

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.version, self.reserved = 1, 0
        self.variations = {}

    def compile(self, ttFont):
        axisTags = [axis.axisTag for axis in ttFont["fvar"].axes]
        sharedTuples = tv.compileSharedTuples(
            axisTags, itertools.chain(*self.variations.values())
        )
        sharedTupleIndices = {coord: i for i, coord in enumerate(sharedTuples)}
        sharedTupleSize = sum([len(c) for c in sharedTuples])
        compiledGlyphs = self.compileGlyphs_(ttFont, axisTags, sharedTupleIndices)
        offset = 0
        offsets = []
        for glyph in compiledGlyphs:
            offsets.append(offset)
            offset += len(glyph)
        offsets.append(offset)
        compiledOffsets, tableFormat = self.compileOffsets_(offsets)

        GVAR_HEADER_SIZE = GVAR_HEADER_SIZE_HEAD + self.gid_size + GVAR_HEADER_SIZE_TAIL
        header = {}
        header["version"] = self.version
        header["reserved"] = self.reserved
        header["axisCount"] = len(axisTags)
        header["sharedTupleCount"] = len(sharedTuples)
        header["offsetToSharedTuples"] = GVAR_HEADER_SIZE + len(compiledOffsets)
        header["flags"] = tableFormat
        header["offsetToGlyphVariationData"] = (
            header["offsetToSharedTuples"] + sharedTupleSize
        )

        result = [
            sstruct.pack(GVAR_HEADER_FORMAT_HEAD, header),
            len(compiledGlyphs).to_bytes(self.gid_size, "big"),
            sstruct.pack(GVAR_HEADER_FORMAT_TAIL, header),
        ]

        result.append(compiledOffsets)
        result.extend(sharedTuples)
        result.extend(compiledGlyphs)
        return b"".join(result)

    def compileGlyphs_(self, ttFont, axisTags, sharedCoordIndices):
        optimizeSpeed = ttFont.cfg[OPTIMIZE_FONT_SPEED]
        result = []
        glyf = ttFont["glyf"]
        for glyphName in ttFont.getGlyphOrder():
            variations = self.variations.get(glyphName, [])
            if not variations:
                result.append(b"")
                continue
            pointCountUnused = 0  # pointCount is actually unused by compileGlyph
            result.append(
                compileGlyph_(
                    self.gid_size,
                    variations,
                    pointCountUnused,
                    axisTags,
                    sharedCoordIndices,
                    optimizeSize=not optimizeSpeed,
                )
            )
        return result

    def decompile(self, data, ttFont):
        axisTags = [axis.axisTag for axis in ttFont["fvar"].axes]
        glyphs = ttFont.getGlyphOrder()

        # Parse the header
        GVAR_HEADER_SIZE = GVAR_HEADER_SIZE_HEAD + self.gid_size + GVAR_HEADER_SIZE_TAIL
        sstruct.unpack(GVAR_HEADER_FORMAT_HEAD, data[:GVAR_HEADER_SIZE_HEAD], self)
        self.glyphCount = int.from_bytes(
            data[GVAR_HEADER_SIZE_HEAD : GVAR_HEADER_SIZE_HEAD + self.gid_size], "big"
        )
        sstruct.unpack(
            GVAR_HEADER_FORMAT_TAIL,
            data[GVAR_HEADER_SIZE_HEAD + self.gid_size : GVAR_HEADER_SIZE],
            self,
        )

        assert len(glyphs) == self.glyphCount, (len(glyphs), self.glyphCount)
        assert len(axisTags) == self.axisCount, (
            len(axisTags),
            self.axisCount,
            axisTags,
        )
        sharedCoords = tv.decompileSharedTuples(
            axisTags, self.sharedTupleCount, data, self.offsetToSharedTuples
        )
        variations = {}
        offsetToData = self.offsetToGlyphVariationData
        glyf = ttFont["glyf"]

        def get_read_item():
            reverseGlyphMap = ttFont.getReverseGlyphMap()
            tableFormat = self.flags & 1

            def read_item(glyphName):
                gid = reverseGlyphMap[glyphName]
                offsetSize = 2 if tableFormat == 0 else 4
                startOffset = GVAR_HEADER_SIZE + offsetSize * gid
                endOffset = startOffset + offsetSize * 2
                offsets = table__g_v_a_r.decompileOffsets_(
                    data[startOffset:endOffset],
                    tableFormat=tableFormat,
                    glyphCount=1,
                )
                gvarData = data[offsetToData + offsets[0] : offsetToData + offsets[1]]
                if not gvarData:
                    return []
                glyph = glyf[glyphName]
                numPointsInGlyph = self.getNumPoints_(glyph)
                return decompileGlyph_(
                    self.gid_size, numPointsInGlyph, sharedCoords, axisTags, gvarData
                )

            return read_item

        read_item = get_read_item()
        l = LazyDict({glyphs[gid]: read_item for gid in range(self.glyphCount)})

        self.variations = l

        if ttFont.lazy is False:  # Be lazy for None and True
            self.ensureDecompiled()

    def ensureDecompiled(self, recurse=False):
        # The recurse argument is unused, but part of the signature of
        # ensureDecompiled across the library.
        # Use a zero-length deque to consume the lazy dict
        deque(self.variations.values(), maxlen=0)

    @staticmethod
    def decompileOffsets_(data, tableFormat, glyphCount):
        if tableFormat == 0:
            # Short format: array of UInt16
            offsets = array.array("H")
            offsetsSize = (glyphCount + 1) * 2
        else:
            # Long format: array of UInt32
            offsets = array.array("I")
            offsetsSize = (glyphCount + 1) * 4
        offsets.frombytes(data[0:offsetsSize])
        if sys.byteorder != "big":
            offsets.byteswap()

        # In the short format, offsets need to be multiplied by 2.
        # This is not documented in Apple's TrueType specification,
        # but can be inferred from the FreeType implementation, and
        # we could verify it with two sample GX fonts.
        if tableFormat == 0:
            offsets = [off * 2 for off in offsets]

        return offsets

    @staticmethod
    def compileOffsets_(offsets):
        """Packs a list of offsets into a 'gvar' offset table.

        Returns a pair (bytestring, tableFormat). Bytestring is the
        packed offset table. Format indicates whether the table
        uses short (tableFormat=0) or long (tableFormat=1) integers.
        The returned tableFormat should get packed into the flags field
        of the 'gvar' header.
        """
        assert len(offsets) >= 2
        for i in range(1, len(offsets)):
            assert offsets[i - 1] <= offsets[i]
        if max(offsets) <= 0xFFFF * 2:
            packed = array.array("H", [n >> 1 for n in offsets])
            tableFormat = 0
        else:
            packed = array.array("I", offsets)
            tableFormat = 1
        if sys.byteorder != "big":
            packed.byteswap()
        return (packed.tobytes(), tableFormat)

    def toXML(self, writer, ttFont):
        writer.simpletag("version", value=self.version)
        writer.newline()
        writer.simpletag("reserved", value=self.reserved)
        writer.newline()
        axisTags = [axis.axisTag for axis in ttFont["fvar"].axes]
        for glyphName in ttFont.getGlyphNames():
            variations = self.variations.get(glyphName)
            if not variations:
                continue
            writer.begintag("glyphVariations", glyph=glyphName)
            writer.newline()
            for gvar in variations:
                gvar.toXML(writer, axisTags)
            writer.endtag("glyphVariations")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = safeEval(attrs["value"])
        elif name == "reserved":
            self.reserved = safeEval(attrs["value"])
        elif name == "glyphVariations":
            if not hasattr(self, "variations"):
                self.variations = {}
            glyphName = attrs["glyph"]
            glyph = ttFont["glyf"][glyphName]
            numPointsInGlyph = self.getNumPoints_(glyph)
            glyphVariations = []
            for element in content:
                if isinstance(element, tuple):
                    name, attrs, content = element
                    if name == "tuple":
                        gvar = TupleVariation({}, [None] * numPointsInGlyph)
                        glyphVariations.append(gvar)
                        for tupleElement in content:
                            if isinstance(tupleElement, tuple):
                                tupleName, tupleAttrs, tupleContent = tupleElement
                                gvar.fromXML(tupleName, tupleAttrs, tupleContent)
            self.variations[glyphName] = glyphVariations

    @staticmethod
    def getNumPoints_(glyph):
        NUM_PHANTOM_POINTS = 4

        if glyph.isComposite():
            return len(glyph.components) + NUM_PHANTOM_POINTS
        else:
            # Empty glyphs (eg. space, nonmarkingreturn) have no "coordinates" attribute.
            return len(getattr(glyph, "coordinates", [])) + NUM_PHANTOM_POINTS


def compileGlyph_(
    dataOffsetSize,
    variations,
    pointCount,
    axisTags,
    sharedCoordIndices,
    *,
    optimizeSize=True,
):
    assert dataOffsetSize in (2, 3)
    tupleVariationCount, tuples, data = tv.compileTupleVariationStore(
        variations, pointCount, axisTags, sharedCoordIndices, optimizeSize=optimizeSize
    )
    if tupleVariationCount == 0:
        return b""

    offsetToData = 2 + dataOffsetSize + len(tuples)

    result = [
        tupleVariationCount.to_bytes(2, "big"),
        offsetToData.to_bytes(dataOffsetSize, "big"),
        tuples,
        data,
    ]
    if (offsetToData + len(data)) % 2 != 0:
        result.append(b"\0")  # padding
    return b"".join(result)


def decompileGlyph_(dataOffsetSize, pointCount, sharedTuples, axisTags, data):
    assert dataOffsetSize in (2, 3)
    if len(data) < 2 + dataOffsetSize:
        return []

    tupleVariationCount = int.from_bytes(data[:2], "big")
    offsetToData = int.from_bytes(data[2 : 2 + dataOffsetSize], "big")

    dataPos = offsetToData
    return tv.decompileTupleVariationStore(
        "gvar",
        axisTags,
        tupleVariationCount,
        pointCount,
        sharedTuples,
        data,
        2 + dataOffsetSize,
        offsetToData,
    )
