from io import BytesIO
import sys
import array
import struct
from collections import OrderedDict
from fontTools.misc import sstruct
from fontTools.misc.arrayTools import calcIntBounds
from fontTools.misc.textTools import Tag, bytechr, byteord, bytesjoin, pad
from fontTools.ttLib import (
    TTFont,
    TTLibError,
    getTableModule,
    getTableClass,
    getSearchRange,
)
from fontTools.ttLib.sfnt import (
    SFNTReader,
    SFNTWriter,
    DirectoryEntry,
    WOFFFlavorData,
    sfntDirectoryFormat,
    sfntDirectorySize,
    SFNTDirectoryEntry,
    sfntDirectoryEntrySize,
    calcChecksum,
)
from fontTools.ttLib.tables import ttProgram, _g_l_y_f
import logging


log = logging.getLogger("fontTools.ttLib.woff2")

haveBrotli = False
try:
    try:
        import brotlicffi as brotli
    except ImportError:
        import brotli
    haveBrotli = True
except ImportError:
    pass


class WOFF2Reader(SFNTReader):
    flavor = "woff2"

    def __init__(self, file, checkChecksums=0, fontNumber=-1):
        if not haveBrotli:
            log.error(
                "The WOFF2 decoder requires the Brotli Python extension, available at: "
                "https://github.com/google/brotli"
            )
            raise ImportError("No module named brotli")

        self.file = file

        signature = Tag(self.file.read(4))
        if signature != b"wOF2":
            raise TTLibError("Not a WOFF2 font (bad signature)")

        self.file.seek(0)
        self.DirectoryEntry = WOFF2DirectoryEntry
        data = self.file.read(woff2DirectorySize)
        if len(data) != woff2DirectorySize:
            raise TTLibError("Not a WOFF2 font (not enough data)")
        sstruct.unpack(woff2DirectoryFormat, data, self)

        self.tables = OrderedDict()
        offset = 0
        for i in range(self.numTables):
            entry = self.DirectoryEntry()
            entry.fromFile(self.file)
            tag = Tag(entry.tag)
            self.tables[tag] = entry
            entry.offset = offset
            offset += entry.length

        totalUncompressedSize = offset
        compressedData = self.file.read(self.totalCompressedSize)
        decompressedData = brotli.decompress(compressedData)
        if len(decompressedData) != totalUncompressedSize:
            raise TTLibError(
                "unexpected size for decompressed font data: expected %d, found %d"
                % (totalUncompressedSize, len(decompressedData))
            )
        self.transformBuffer = BytesIO(decompressedData)

        self.file.seek(0, 2)
        if self.length != self.file.tell():
            raise TTLibError("reported 'length' doesn't match the actual file size")

        self.flavorData = WOFF2FlavorData(self)

        # make empty TTFont to store data while reconstructing tables
        self.ttFont = TTFont(recalcBBoxes=False, recalcTimestamp=False)

    def __getitem__(self, tag):
        """Fetch the raw table data. Reconstruct transformed tables."""
        entry = self.tables[Tag(tag)]
        if not hasattr(entry, "data"):
            if entry.transformed:
                entry.data = self.reconstructTable(tag)
            else:
                entry.data = entry.loadData(self.transformBuffer)
        return entry.data

    def reconstructTable(self, tag):
        """Reconstruct table named 'tag' from transformed data."""
        entry = self.tables[Tag(tag)]
        rawData = entry.loadData(self.transformBuffer)
        if tag == "glyf":
            # no need to pad glyph data when reconstructing
            padding = self.padding if hasattr(self, "padding") else None
            data = self._reconstructGlyf(rawData, padding)
        elif tag == "loca":
            data = self._reconstructLoca()
        elif tag == "hmtx":
            data = self._reconstructHmtx(rawData)
        else:
            raise TTLibError("transform for table '%s' is unknown" % tag)
        return data

    def _reconstructGlyf(self, data, padding=None):
        """Return recostructed glyf table data, and set the corresponding loca's
        locations. Optionally pad glyph offsets to the specified number of bytes.
        """
        self.ttFont["loca"] = WOFF2LocaTable()
        glyfTable = self.ttFont["glyf"] = WOFF2GlyfTable()
        glyfTable.reconstruct(data, self.ttFont)
        if padding:
            glyfTable.padding = padding
        data = glyfTable.compile(self.ttFont)
        return data

    def _reconstructLoca(self):
        """Return reconstructed loca table data."""
        if "loca" not in self.ttFont:
            # make sure glyf is reconstructed first
            self.tables["glyf"].data = self.reconstructTable("glyf")
        locaTable = self.ttFont["loca"]
        data = locaTable.compile(self.ttFont)
        if len(data) != self.tables["loca"].origLength:
            raise TTLibError(
                "reconstructed 'loca' table doesn't match original size: "
                "expected %d, found %d" % (self.tables["loca"].origLength, len(data))
            )
        return data

    def _reconstructHmtx(self, data):
        """Return reconstructed hmtx table data."""
        # Before reconstructing 'hmtx' table we need to parse other tables:
        # 'glyf' is required for reconstructing the sidebearings from the glyphs'
        # bounding box; 'hhea' is needed for the numberOfHMetrics field.
        if "glyf" in self.flavorData.transformedTables:
            # transformed 'glyf' table is self-contained, thus 'loca' not needed
            tableDependencies = ("maxp", "hhea", "glyf")
        else:
            # decompiling untransformed 'glyf' requires 'loca', which requires 'head'
            tableDependencies = ("maxp", "head", "hhea", "loca", "glyf")
        for tag in tableDependencies:
            self._decompileTable(tag)
        hmtxTable = self.ttFont["hmtx"] = WOFF2HmtxTable()
        hmtxTable.reconstruct(data, self.ttFont)
        data = hmtxTable.compile(self.ttFont)
        return data

    def _decompileTable(self, tag):
        """Decompile table data and store it inside self.ttFont."""
        data = self[tag]
        if self.ttFont.isLoaded(tag):
            return self.ttFont[tag]
        tableClass = getTableClass(tag)
        table = tableClass(tag)
        self.ttFont.tables[tag] = table
        table.decompile(data, self.ttFont)


class WOFF2Writer(SFNTWriter):
    flavor = "woff2"

    def __init__(
        self,
        file,
        numTables,
        sfntVersion="\000\001\000\000",
        flavor=None,
        flavorData=None,
    ):
        if not haveBrotli:
            log.error(
                "The WOFF2 encoder requires the Brotli Python extension, available at: "
                "https://github.com/google/brotli"
            )
            raise ImportError("No module named brotli")

        self.file = file
        self.numTables = numTables
        self.sfntVersion = Tag(sfntVersion)
        self.flavorData = WOFF2FlavorData(data=flavorData)

        self.directoryFormat = woff2DirectoryFormat
        self.directorySize = woff2DirectorySize
        self.DirectoryEntry = WOFF2DirectoryEntry

        self.signature = Tag("wOF2")

        self.nextTableOffset = 0
        self.transformBuffer = BytesIO()

        self.tables = OrderedDict()

        # make empty TTFont to store data while normalising and transforming tables
        self.ttFont = TTFont(recalcBBoxes=False, recalcTimestamp=False)

    def __setitem__(self, tag, data):
        """Associate new entry named 'tag' with raw table data."""
        if tag in self.tables:
            raise TTLibError("cannot rewrite '%s' table" % tag)
        if tag == "DSIG":
            # always drop DSIG table, since the encoding process can invalidate it
            self.numTables -= 1
            return

        entry = self.DirectoryEntry()
        entry.tag = Tag(tag)
        entry.flags = getKnownTagIndex(entry.tag)
        # WOFF2 table data are written to disk only on close(), after all tags
        # have been specified
        entry.data = data

        self.tables[tag] = entry

    def close(self):
        """All tags must have been specified. Now write the table data and directory."""
        if len(self.tables) != self.numTables:
            raise TTLibError(
                "wrong number of tables; expected %d, found %d"
                % (self.numTables, len(self.tables))
            )

        if self.sfntVersion in ("\x00\x01\x00\x00", "true"):
            isTrueType = True
        elif self.sfntVersion == "OTTO":
            isTrueType = False
        else:
            raise TTLibError("Not a TrueType or OpenType font (bad sfntVersion)")

        # The WOFF2 spec no longer requires the glyph offsets to be 4-byte aligned.
        # However, the reference WOFF2 implementation still fails to reconstruct
        # 'unpadded' glyf tables, therefore we need to 'normalise' them.
        # See:
        # https://github.com/khaledhosny/ots/issues/60
        # https://github.com/google/woff2/issues/15
        if (
            isTrueType
            and "glyf" in self.flavorData.transformedTables
            and "glyf" in self.tables
        ):
            self._normaliseGlyfAndLoca(padding=4)
        self._setHeadTransformFlag()

        # To pass the legacy OpenType Sanitiser currently included in browsers,
        # we must sort the table directory and data alphabetically by tag.
        # See:
        # https://github.com/google/woff2/pull/3
        # https://lists.w3.org/Archives/Public/public-webfonts-wg/2015Mar/0000.html
        #
        # 2023: We rely on this in _transformTables where we expect that
        # "loca" comes after "glyf" table.
        self.tables = OrderedDict(sorted(self.tables.items()))

        self.totalSfntSize = self._calcSFNTChecksumsLengthsAndOffsets()

        fontData = self._transformTables()
        compressedFont = brotli.compress(fontData, mode=brotli.MODE_FONT)

        self.totalCompressedSize = len(compressedFont)
        self.length = self._calcTotalSize()
        self.majorVersion, self.minorVersion = self._getVersion()
        self.reserved = 0

        directory = self._packTableDirectory()
        self.file.seek(0)
        self.file.write(pad(directory + compressedFont, size=4))
        self._writeFlavorData()

    def _normaliseGlyfAndLoca(self, padding=4):
        """Recompile glyf and loca tables, aligning glyph offsets to multiples of
        'padding' size. Update the head table's 'indexToLocFormat' accordingly while
        compiling loca.
        """
        if self.sfntVersion == "OTTO":
            return

        for tag in ("maxp", "head", "loca", "glyf", "fvar"):
            if tag in self.tables:
                self._decompileTable(tag)
        self.ttFont["glyf"].padding = padding
        for tag in ("glyf", "loca"):
            self._compileTable(tag)

    def _setHeadTransformFlag(self):
        """Set bit 11 of 'head' table flags to indicate that the font has undergone
        a lossless modifying transform. Re-compile head table data."""
        self._decompileTable("head")
        self.ttFont["head"].flags |= 1 << 11
        self._compileTable("head")

    def _decompileTable(self, tag):
        """Fetch table data, decompile it, and store it inside self.ttFont."""
        tag = Tag(tag)
        if tag not in self.tables:
            raise TTLibError("missing required table: %s" % tag)
        if self.ttFont.isLoaded(tag):
            return
        data = self.tables[tag].data
        if tag == "loca":
            tableClass = WOFF2LocaTable
        elif tag == "glyf":
            tableClass = WOFF2GlyfTable
        elif tag == "hmtx":
            tableClass = WOFF2HmtxTable
        else:
            tableClass = getTableClass(tag)
        table = tableClass(tag)
        self.ttFont.tables[tag] = table
        table.decompile(data, self.ttFont)

    def _compileTable(self, tag):
        """Compile table and store it in its 'data' attribute."""
        self.tables[tag].data = self.ttFont[tag].compile(self.ttFont)

    def _calcSFNTChecksumsLengthsAndOffsets(self):
        """Compute the 'original' SFNT checksums, lengths and offsets for checksum
        adjustment calculation. Return the total size of the uncompressed font.
        """
        offset = sfntDirectorySize + sfntDirectoryEntrySize * len(self.tables)
        for tag, entry in self.tables.items():
            data = entry.data
            entry.origOffset = offset
            entry.origLength = len(data)
            if tag == "head":
                entry.checkSum = calcChecksum(data[:8] + b"\0\0\0\0" + data[12:])
            else:
                entry.checkSum = calcChecksum(data)
            offset += (entry.origLength + 3) & ~3
        return offset

    def _transformTables(self):
        """Return transformed font data."""
        transformedTables = self.flavorData.transformedTables
        for tag, entry in self.tables.items():
            data = None
            if tag in transformedTables:
                data = self.transformTable(tag)
                if data is not None:
                    entry.transformed = True
            if data is None:
                if tag == "glyf":
                    # Currently we always sort table tags so
                    # 'loca' comes after 'glyf'.
                    transformedTables.discard("loca")
                # pass-through the table data without transformation
                data = entry.data
                entry.transformed = False
            entry.offset = self.nextTableOffset
            entry.saveData(self.transformBuffer, data)
            self.nextTableOffset += entry.length
        self.writeMasterChecksum()
        fontData = self.transformBuffer.getvalue()
        return fontData

    def transformTable(self, tag):
        """Return transformed table data, or None if some pre-conditions aren't
        met -- in which case, the non-transformed table data will be used.
        """
        if tag == "loca":
            data = b""
        elif tag == "glyf":
            for tag in ("maxp", "head", "loca", "glyf"):
                self._decompileTable(tag)
            glyfTable = self.ttFont["glyf"]
            data = glyfTable.transform(self.ttFont)
        elif tag == "hmtx":
            if "glyf" not in self.tables:
                return
            for tag in ("maxp", "head", "hhea", "loca", "glyf", "hmtx"):
                self._decompileTable(tag)
            hmtxTable = self.ttFont["hmtx"]
            data = hmtxTable.transform(self.ttFont)  # can be None
        else:
            raise TTLibError("Transform for table '%s' is unknown" % tag)
        return data

    def _calcMasterChecksum(self):
        """Calculate checkSumAdjustment."""
        checksums = []
        for tag in self.tables.keys():
            checksums.append(self.tables[tag].checkSum)

        # Create a SFNT directory for checksum calculation purposes
        self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(
            self.numTables, 16
        )
        directory = sstruct.pack(sfntDirectoryFormat, self)
        tables = sorted(self.tables.items())
        for tag, entry in tables:
            sfntEntry = SFNTDirectoryEntry()
            sfntEntry.tag = entry.tag
            sfntEntry.checkSum = entry.checkSum
            sfntEntry.offset = entry.origOffset
            sfntEntry.length = entry.origLength
            directory = directory + sfntEntry.toString()

        directory_end = sfntDirectorySize + len(self.tables) * sfntDirectoryEntrySize
        assert directory_end == len(directory)

        checksums.append(calcChecksum(directory))
        checksum = sum(checksums) & 0xFFFFFFFF
        # BiboAfba!
        checksumadjustment = (0xB1B0AFBA - checksum) & 0xFFFFFFFF
        return checksumadjustment

    def writeMasterChecksum(self):
        """Write checkSumAdjustment to the transformBuffer."""
        checksumadjustment = self._calcMasterChecksum()
        self.transformBuffer.seek(self.tables["head"].offset + 8)
        self.transformBuffer.write(struct.pack(">L", checksumadjustment))

    def _calcTotalSize(self):
        """Calculate total size of WOFF2 font, including any meta- and/or private data."""
        offset = self.directorySize
        for entry in self.tables.values():
            offset += len(entry.toString())
        offset += self.totalCompressedSize
        offset = (offset + 3) & ~3
        offset = self._calcFlavorDataOffsetsAndSize(offset)
        return offset

    def _calcFlavorDataOffsetsAndSize(self, start):
        """Calculate offsets and lengths for any meta- and/or private data."""
        offset = start
        data = self.flavorData
        if data.metaData:
            self.metaOrigLength = len(data.metaData)
            self.metaOffset = offset
            self.compressedMetaData = brotli.compress(
                data.metaData, mode=brotli.MODE_TEXT
            )
            self.metaLength = len(self.compressedMetaData)
            offset += self.metaLength
        else:
            self.metaOffset = self.metaLength = self.metaOrigLength = 0
            self.compressedMetaData = b""
        if data.privData:
            # make sure private data is padded to 4-byte boundary
            offset = (offset + 3) & ~3
            self.privOffset = offset
            self.privLength = len(data.privData)
            offset += self.privLength
        else:
            self.privOffset = self.privLength = 0
        return offset

    def _getVersion(self):
        """Return the WOFF2 font's (majorVersion, minorVersion) tuple."""
        data = self.flavorData
        if data.majorVersion is not None and data.minorVersion is not None:
            return data.majorVersion, data.minorVersion
        else:
            # if None, return 'fontRevision' from 'head' table
            if "head" in self.tables:
                return struct.unpack(">HH", self.tables["head"].data[4:8])
            else:
                return 0, 0

    def _packTableDirectory(self):
        """Return WOFF2 table directory data."""
        directory = sstruct.pack(self.directoryFormat, self)
        for entry in self.tables.values():
            directory = directory + entry.toString()
        return directory

    def _writeFlavorData(self):
        """Write metadata and/or private data using appropiate padding."""
        compressedMetaData = self.compressedMetaData
        privData = self.flavorData.privData
        if compressedMetaData and privData:
            compressedMetaData = pad(compressedMetaData, size=4)
        if compressedMetaData:
            self.file.seek(self.metaOffset)
            assert self.file.tell() == self.metaOffset
            self.file.write(compressedMetaData)
        if privData:
            self.file.seek(self.privOffset)
            assert self.file.tell() == self.privOffset
            self.file.write(privData)

    def reordersTables(self):
        return True


# -- woff2 directory helpers and cruft

woff2DirectoryFormat = """
		> # big endian
		signature:           4s   # "wOF2"
		sfntVersion:         4s
		length:              L    # total woff2 file size
		numTables:           H    # number of tables
		reserved:            H    # set to 0
		totalSfntSize:       L    # uncompressed size
		totalCompressedSize: L    # compressed size
		majorVersion:        H    # major version of WOFF file
		minorVersion:        H    # minor version of WOFF file
		metaOffset:          L    # offset to metadata block
		metaLength:          L    # length of compressed metadata
		metaOrigLength:      L    # length of uncompressed metadata
		privOffset:          L    # offset to private data block
		privLength:          L    # length of private data block
"""

woff2DirectorySize = sstruct.calcsize(woff2DirectoryFormat)

woff2KnownTags = (
    "cmap",
    "head",
    "hhea",
    "hmtx",
    "maxp",
    "name",
    "OS/2",
    "post",
    "cvt ",
    "fpgm",
    "glyf",
    "loca",
    "prep",
    "CFF ",
    "VORG",
    "EBDT",
    "EBLC",
    "gasp",
    "hdmx",
    "kern",
    "LTSH",
    "PCLT",
    "VDMX",
    "vhea",
    "vmtx",
    "BASE",
    "GDEF",
    "GPOS",
    "GSUB",
    "EBSC",
    "JSTF",
    "MATH",
    "CBDT",
    "CBLC",
    "COLR",
    "CPAL",
    "SVG ",
    "sbix",
    "acnt",
    "avar",
    "bdat",
    "bloc",
    "bsln",
    "cvar",
    "fdsc",
    "feat",
    "fmtx",
    "fvar",
    "gvar",
    "hsty",
    "just",
    "lcar",
    "mort",
    "morx",
    "opbd",
    "prop",
    "trak",
    "Zapf",
    "Silf",
    "Glat",
    "Gloc",
    "Feat",
    "Sill",
)

woff2FlagsFormat = """
		> # big endian
		flags: B  # table type and flags
"""

woff2FlagsSize = sstruct.calcsize(woff2FlagsFormat)

woff2UnknownTagFormat = """
		> # big endian
		tag: 4s  # 4-byte tag (optional)
"""

woff2UnknownTagSize = sstruct.calcsize(woff2UnknownTagFormat)

woff2UnknownTagIndex = 0x3F

woff2Base128MaxSize = 5
woff2DirectoryEntryMaxSize = (
    woff2FlagsSize + woff2UnknownTagSize + 2 * woff2Base128MaxSize
)

woff2TransformedTableTags = ("glyf", "loca")

woff2GlyfTableFormat = """
		> # big endian
		version:                  H  # = 0x0000
		optionFlags:              H  # Bit 0: we have overlapSimpleBitmap[], Bits 1-15: reserved
		numGlyphs:                H  # Number of glyphs
		indexFormat:              H  # Offset format for loca table
		nContourStreamSize:       L  # Size of nContour stream
		nPointsStreamSize:        L  # Size of nPoints stream
		flagStreamSize:           L  # Size of flag stream
		glyphStreamSize:          L  # Size of glyph stream
		compositeStreamSize:      L  # Size of composite stream
		bboxStreamSize:           L  # Comnined size of bboxBitmap and bboxStream
		instructionStreamSize:    L  # Size of instruction stream
"""

woff2GlyfTableFormatSize = sstruct.calcsize(woff2GlyfTableFormat)

bboxFormat = """
		>	# big endian
		xMin:				h
		yMin:				h
		xMax:				h
		yMax:				h
"""

woff2OverlapSimpleBitmapFlag = 0x0001


def getKnownTagIndex(tag):
    """Return index of 'tag' in woff2KnownTags list. Return 63 if not found."""
    try:
        return woff2KnownTags.index(tag)
    except ValueError:
        return woff2UnknownTagIndex


class WOFF2DirectoryEntry(DirectoryEntry):
    def fromFile(self, file):
        pos = file.tell()
        data = file.read(woff2DirectoryEntryMaxSize)
        left = self.fromString(data)
        consumed = len(data) - len(left)
        file.seek(pos + consumed)

    def fromString(self, data):
        if len(data) < 1:
            raise TTLibError("can't read table 'flags': not enough data")
        dummy, data = sstruct.unpack2(woff2FlagsFormat, data, self)
        if self.flags & 0x3F == 0x3F:
            # if bits [0..5] of the flags byte == 63, read a 4-byte arbitrary tag value
            if len(data) < woff2UnknownTagSize:
                raise TTLibError("can't read table 'tag': not enough data")
            dummy, data = sstruct.unpack2(woff2UnknownTagFormat, data, self)
        else:
            # otherwise, tag is derived from a fixed 'Known Tags' table
            self.tag = woff2KnownTags[self.flags & 0x3F]
        self.tag = Tag(self.tag)
        self.origLength, data = unpackBase128(data)
        self.length = self.origLength
        if self.transformed:
            self.length, data = unpackBase128(data)
            if self.tag == "loca" and self.length != 0:
                raise TTLibError("the transformLength of the 'loca' table must be 0")
        # return left over data
        return data

    def toString(self):
        data = bytechr(self.flags)
        if (self.flags & 0x3F) == 0x3F:
            data += struct.pack(">4s", self.tag.tobytes())
        data += packBase128(self.origLength)
        if self.transformed:
            data += packBase128(self.length)
        return data

    @property
    def transformVersion(self):
        """Return bits 6-7 of table entry's flags, which indicate the preprocessing
        transformation version number (between 0 and 3).
        """
        return self.flags >> 6

    @transformVersion.setter
    def transformVersion(self, value):
        assert 0 <= value <= 3
        self.flags |= value << 6

    @property
    def transformed(self):
        """Return True if the table has any transformation, else return False."""
        # For all tables in a font, except for 'glyf' and 'loca', the transformation
        # version 0 indicates the null transform (where the original table data is
        # passed directly to the Brotli compressor). For 'glyf' and 'loca' tables,
        # transformation version 3 indicates the null transform
        if self.tag in {"glyf", "loca"}:
            return self.transformVersion != 3
        else:
            return self.transformVersion != 0

    @transformed.setter
    def transformed(self, booleanValue):
        # here we assume that a non-null transform means version 0 for 'glyf' and
        # 'loca' and 1 for every other table (e.g. hmtx); but that may change as
        # new transformation formats are introduced in the future (if ever).
        if self.tag in {"glyf", "loca"}:
            self.transformVersion = 3 if not booleanValue else 0
        else:
            self.transformVersion = int(booleanValue)


class WOFF2LocaTable(getTableClass("loca")):
    """Same as parent class. The only difference is that it attempts to preserve
    the 'indexFormat' as encoded in the WOFF2 glyf table.
    """

    def __init__(self, tag=None):
        self.tableTag = Tag(tag or "loca")

    def compile(self, ttFont):
        try:
            max_location = max(self.locations)
        except AttributeError:
            self.set([])
            max_location = 0
        if "glyf" in ttFont and hasattr(ttFont["glyf"], "indexFormat"):
            # copile loca using the indexFormat specified in the WOFF2 glyf table
            indexFormat = ttFont["glyf"].indexFormat
            if indexFormat == 0:
                if max_location >= 0x20000:
                    raise TTLibError("indexFormat is 0 but local offsets > 0x20000")
                if not all(l % 2 == 0 for l in self.locations):
                    raise TTLibError(
                        "indexFormat is 0 but local offsets not multiples of 2"
                    )
                locations = array.array("H")
                for location in self.locations:
                    locations.append(location // 2)
            else:
                locations = array.array("I", self.locations)
            if sys.byteorder != "big":
                locations.byteswap()
            data = locations.tobytes()
        else:
            # use the most compact indexFormat given the current glyph offsets
            data = super(WOFF2LocaTable, self).compile(ttFont)
        return data


class WOFF2GlyfTable(getTableClass("glyf")):
    """Decoder/Encoder for WOFF2 'glyf' table transform."""

    subStreams = (
        "nContourStream",
        "nPointsStream",
        "flagStream",
        "glyphStream",
        "compositeStream",
        "bboxStream",
        "instructionStream",
    )

    def __init__(self, tag=None):
        self.tableTag = Tag(tag or "glyf")

    def reconstruct(self, data, ttFont):
        """Decompile transformed 'glyf' data."""
        inputDataSize = len(data)

        if inputDataSize < woff2GlyfTableFormatSize:
            raise TTLibError("not enough 'glyf' data")
        dummy, data = sstruct.unpack2(woff2GlyfTableFormat, data, self)
        offset = woff2GlyfTableFormatSize

        for stream in self.subStreams:
            size = getattr(self, stream + "Size")
            setattr(self, stream, data[:size])
            data = data[size:]
            offset += size

        hasOverlapSimpleBitmap = self.optionFlags & woff2OverlapSimpleBitmapFlag
        self.overlapSimpleBitmap = None
        if hasOverlapSimpleBitmap:
            overlapSimpleBitmapSize = (self.numGlyphs + 7) >> 3
            self.overlapSimpleBitmap = array.array("B", data[:overlapSimpleBitmapSize])
            offset += overlapSimpleBitmapSize

        if offset != inputDataSize:
            raise TTLibError(
                "incorrect size of transformed 'glyf' table: expected %d, received %d bytes"
                % (offset, inputDataSize)
            )

        bboxBitmapSize = ((self.numGlyphs + 31) >> 5) << 2
        bboxBitmap = self.bboxStream[:bboxBitmapSize]
        self.bboxBitmap = array.array("B", bboxBitmap)
        self.bboxStream = self.bboxStream[bboxBitmapSize:]

        self.nContourStream = array.array("h", self.nContourStream)
        if sys.byteorder != "big":
            self.nContourStream.byteswap()
        assert len(self.nContourStream) == self.numGlyphs

        if "head" in ttFont:
            ttFont["head"].indexToLocFormat = self.indexFormat
        try:
            self.glyphOrder = ttFont.getGlyphOrder()
        except:
            self.glyphOrder = None
        if self.glyphOrder is None:
            self.glyphOrder = [".notdef"]
            self.glyphOrder.extend(["glyph%.5d" % i for i in range(1, self.numGlyphs)])
        else:
            if len(self.glyphOrder) != self.numGlyphs:
                raise TTLibError(
                    "incorrect glyphOrder: expected %d glyphs, found %d"
                    % (len(self.glyphOrder), self.numGlyphs)
                )

        glyphs = self.glyphs = {}
        for glyphID, glyphName in enumerate(self.glyphOrder):
            glyph = self._decodeGlyph(glyphID)
            glyphs[glyphName] = glyph

    def transform(self, ttFont):
        """Return transformed 'glyf' data"""
        self.numGlyphs = len(self.glyphs)
        assert len(self.glyphOrder) == self.numGlyphs
        if "maxp" in ttFont:
            ttFont["maxp"].numGlyphs = self.numGlyphs
        self.indexFormat = ttFont["head"].indexToLocFormat

        for stream in self.subStreams:
            setattr(self, stream, b"")
        bboxBitmapSize = ((self.numGlyphs + 31) >> 5) << 2
        self.bboxBitmap = array.array("B", [0] * bboxBitmapSize)

        self.overlapSimpleBitmap = array.array("B", [0] * ((self.numGlyphs + 7) >> 3))
        for glyphID in range(self.numGlyphs):
            try:
                self._encodeGlyph(glyphID)
            except NotImplementedError:
                return None
        hasOverlapSimpleBitmap = any(self.overlapSimpleBitmap)

        self.bboxStream = self.bboxBitmap.tobytes() + self.bboxStream
        for stream in self.subStreams:
            setattr(self, stream + "Size", len(getattr(self, stream)))
        self.version = 0
        self.optionFlags = 0
        if hasOverlapSimpleBitmap:
            self.optionFlags |= woff2OverlapSimpleBitmapFlag
        data = sstruct.pack(woff2GlyfTableFormat, self)
        data += bytesjoin([getattr(self, s) for s in self.subStreams])
        if hasOverlapSimpleBitmap:
            data += self.overlapSimpleBitmap.tobytes()
        return data

    def _decodeGlyph(self, glyphID):
        glyph = getTableModule("glyf").Glyph()
        glyph.numberOfContours = self.nContourStream[glyphID]
        if glyph.numberOfContours == 0:
            return glyph
        elif glyph.isComposite():
            self._decodeComponents(glyph)
        else:
            self._decodeCoordinates(glyph)
            self._decodeOverlapSimpleFlag(glyph, glyphID)
        self._decodeBBox(glyphID, glyph)
        return glyph

    def _decodeComponents(self, glyph):
        data = self.compositeStream
        glyph.components = []
        more = 1
        haveInstructions = 0
        while more:
            component = getTableModule("glyf").GlyphComponent()
            more, haveInstr, data = component.decompile(data, self)
            haveInstructions = haveInstructions | haveInstr
            glyph.components.append(component)
        self.compositeStream = data
        if haveInstructions:
            self._decodeInstructions(glyph)

    def _decodeCoordinates(self, glyph):
        data = self.nPointsStream
        endPtsOfContours = []
        endPoint = -1
        for i in range(glyph.numberOfContours):
            ptsOfContour, data = unpack255UShort(data)
            endPoint += ptsOfContour
            endPtsOfContours.append(endPoint)
        glyph.endPtsOfContours = endPtsOfContours
        self.nPointsStream = data
        self._decodeTriplets(glyph)
        self._decodeInstructions(glyph)

    def _decodeOverlapSimpleFlag(self, glyph, glyphID):
        if self.overlapSimpleBitmap is None or glyph.numberOfContours <= 0:
            return
        byte = glyphID >> 3
        bit = glyphID & 7
        if self.overlapSimpleBitmap[byte] & (0x80 >> bit):
            glyph.flags[0] |= _g_l_y_f.flagOverlapSimple

    def _decodeInstructions(self, glyph):
        glyphStream = self.glyphStream
        instructionStream = self.instructionStream
        instructionLength, glyphStream = unpack255UShort(glyphStream)
        glyph.program = ttProgram.Program()
        glyph.program.fromBytecode(instructionStream[:instructionLength])
        self.glyphStream = glyphStream
        self.instructionStream = instructionStream[instructionLength:]

    def _decodeBBox(self, glyphID, glyph):
        haveBBox = bool(self.bboxBitmap[glyphID >> 3] & (0x80 >> (glyphID & 7)))
        if glyph.isComposite() and not haveBBox:
            raise TTLibError("no bbox values for composite glyph %d" % glyphID)
        if haveBBox:
            dummy, self.bboxStream = sstruct.unpack2(bboxFormat, self.bboxStream, glyph)
        else:
            glyph.recalcBounds(self)

    def _decodeTriplets(self, glyph):
        def withSign(flag, baseval):
            assert 0 <= baseval and baseval < 65536, "integer overflow"
            return baseval if flag & 1 else -baseval

        nPoints = glyph.endPtsOfContours[-1] + 1
        flagSize = nPoints
        if flagSize > len(self.flagStream):
            raise TTLibError("not enough 'flagStream' data")
        flagsData = self.flagStream[:flagSize]
        self.flagStream = self.flagStream[flagSize:]
        flags = array.array("B", flagsData)

        triplets = array.array("B", self.glyphStream)
        nTriplets = len(triplets)
        assert nPoints <= nTriplets

        x = 0
        y = 0
        glyph.coordinates = getTableModule("glyf").GlyphCoordinates.zeros(nPoints)
        glyph.flags = array.array("B")
        tripletIndex = 0
        for i in range(nPoints):
            flag = flags[i]
            onCurve = not bool(flag >> 7)
            flag &= 0x7F
            if flag < 84:
                nBytes = 1
            elif flag < 120:
                nBytes = 2
            elif flag < 124:
                nBytes = 3
            else:
                nBytes = 4
            assert (tripletIndex + nBytes) <= nTriplets
            if flag < 10:
                dx = 0
                dy = withSign(flag, ((flag & 14) << 7) + triplets[tripletIndex])
            elif flag < 20:
                dx = withSign(flag, (((flag - 10) & 14) << 7) + triplets[tripletIndex])
                dy = 0
            elif flag < 84:
                b0 = flag - 20
                b1 = triplets[tripletIndex]
                dx = withSign(flag, 1 + (b0 & 0x30) + (b1 >> 4))
                dy = withSign(flag >> 1, 1 + ((b0 & 0x0C) << 2) + (b1 & 0x0F))
            elif flag < 120:
                b0 = flag - 84
                dx = withSign(flag, 1 + ((b0 // 12) << 8) + triplets[tripletIndex])
                dy = withSign(
                    flag >> 1, 1 + (((b0 % 12) >> 2) << 8) + triplets[tripletIndex + 1]
                )
            elif flag < 124:
                b2 = triplets[tripletIndex + 1]
                dx = withSign(flag, (triplets[tripletIndex] << 4) + (b2 >> 4))
                dy = withSign(
                    flag >> 1, ((b2 & 0x0F) << 8) + triplets[tripletIndex + 2]
                )
            else:
                dx = withSign(
                    flag, (triplets[tripletIndex] << 8) + triplets[tripletIndex + 1]
                )
                dy = withSign(
                    flag >> 1,
                    (triplets[tripletIndex + 2] << 8) + triplets[tripletIndex + 3],
                )
            tripletIndex += nBytes
            x += dx
            y += dy
            glyph.coordinates[i] = (x, y)
            glyph.flags.append(int(onCurve))
        bytesConsumed = tripletIndex
        self.glyphStream = self.glyphStream[bytesConsumed:]

    def _encodeGlyph(self, glyphID):
        glyphName = self.getGlyphName(glyphID)
        glyph = self[glyphName]
        self.nContourStream += struct.pack(">h", glyph.numberOfContours)
        if glyph.numberOfContours == 0:
            return
        elif glyph.isComposite():
            self._encodeComponents(glyph)
        else:
            self._encodeCoordinates(glyph)
            self._encodeOverlapSimpleFlag(glyph, glyphID)
        self._encodeBBox(glyphID, glyph)

    def _encodeComponents(self, glyph):
        lastcomponent = len(glyph.components) - 1
        more = 1
        haveInstructions = 0
        for i, component in enumerate(glyph.components):
            if i == lastcomponent:
                haveInstructions = hasattr(glyph, "program")
                more = 0
            self.compositeStream += component.compile(more, haveInstructions, self)
        if haveInstructions:
            self._encodeInstructions(glyph)

    def _encodeCoordinates(self, glyph):
        lastEndPoint = -1
        if _g_l_y_f.flagCubic in glyph.flags:
            raise NotImplementedError
        for endPoint in glyph.endPtsOfContours:
            ptsOfContour = endPoint - lastEndPoint
            self.nPointsStream += pack255UShort(ptsOfContour)
            lastEndPoint = endPoint
        self._encodeTriplets(glyph)
        self._encodeInstructions(glyph)

    def _encodeOverlapSimpleFlag(self, glyph, glyphID):
        if glyph.numberOfContours <= 0:
            return
        if glyph.flags[0] & _g_l_y_f.flagOverlapSimple:
            byte = glyphID >> 3
            bit = glyphID & 7
            self.overlapSimpleBitmap[byte] |= 0x80 >> bit

    def _encodeInstructions(self, glyph):
        instructions = glyph.program.getBytecode()
        self.glyphStream += pack255UShort(len(instructions))
        self.instructionStream += instructions

    def _encodeBBox(self, glyphID, glyph):
        assert glyph.numberOfContours != 0, "empty glyph has no bbox"
        if not glyph.isComposite():
            # for simple glyphs, compare the encoded bounding box info with the calculated
            # values, and if they match omit the bounding box info
            currentBBox = glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax
            calculatedBBox = calcIntBounds(glyph.coordinates)
            if currentBBox == calculatedBBox:
                return
        self.bboxBitmap[glyphID >> 3] |= 0x80 >> (glyphID & 7)
        self.bboxStream += sstruct.pack(bboxFormat, glyph)

    def _encodeTriplets(self, glyph):
        assert len(glyph.coordinates) == len(glyph.flags)
        coordinates = glyph.coordinates.copy()
        coordinates.absoluteToRelative()

        flags = array.array("B")
        triplets = array.array("B")
        for i, (x, y) in enumerate(coordinates):
            onCurve = glyph.flags[i] & _g_l_y_f.flagOnCurve
            absX = abs(x)
            absY = abs(y)
            onCurveBit = 0 if onCurve else 128
            xSignBit = 0 if (x < 0) else 1
            ySignBit = 0 if (y < 0) else 1
            xySignBits = xSignBit + 2 * ySignBit

            if x == 0 and absY < 1280:
                flags.append(onCurveBit + ((absY & 0xF00) >> 7) + ySignBit)
                triplets.append(absY & 0xFF)
            elif y == 0 and absX < 1280:
                flags.append(onCurveBit + 10 + ((absX & 0xF00) >> 7) + xSignBit)
                triplets.append(absX & 0xFF)
            elif absX < 65 and absY < 65:
                flags.append(
                    onCurveBit
                    + 20
                    + ((absX - 1) & 0x30)
                    + (((absY - 1) & 0x30) >> 2)
                    + xySignBits
                )
                triplets.append((((absX - 1) & 0xF) << 4) | ((absY - 1) & 0xF))
            elif absX < 769 and absY < 769:
                flags.append(
                    onCurveBit
                    + 84
                    + 12 * (((absX - 1) & 0x300) >> 8)
                    + (((absY - 1) & 0x300) >> 6)
                    + xySignBits
                )
                triplets.append((absX - 1) & 0xFF)
                triplets.append((absY - 1) & 0xFF)
            elif absX < 4096 and absY < 4096:
                flags.append(onCurveBit + 120 + xySignBits)
                triplets.append(absX >> 4)
                triplets.append(((absX & 0xF) << 4) | (absY >> 8))
                triplets.append(absY & 0xFF)
            else:
                flags.append(onCurveBit + 124 + xySignBits)
                triplets.append(absX >> 8)
                triplets.append(absX & 0xFF)
                triplets.append(absY >> 8)
                triplets.append(absY & 0xFF)

        self.flagStream += flags.tobytes()
        self.glyphStream += triplets.tobytes()


class WOFF2HmtxTable(getTableClass("hmtx")):
    def __init__(self, tag=None):
        self.tableTag = Tag(tag or "hmtx")

    def reconstruct(self, data, ttFont):
        (flags,) = struct.unpack(">B", data[:1])
        data = data[1:]
        if flags & 0b11111100 != 0:
            raise TTLibError("Bits 2-7 of '%s' flags are reserved" % self.tableTag)

        # When bit 0 is _not_ set, the lsb[] array is present
        hasLsbArray = flags & 1 == 0
        # When bit 1 is _not_ set, the leftSideBearing[] array is present
        hasLeftSideBearingArray = flags & 2 == 0
        if hasLsbArray and hasLeftSideBearingArray:
            raise TTLibError(
                "either bits 0 or 1 (or both) must set in transformed '%s' flags"
                % self.tableTag
            )

        glyfTable = ttFont["glyf"]
        headerTable = ttFont["hhea"]
        glyphOrder = glyfTable.glyphOrder
        numGlyphs = len(glyphOrder)
        numberOfHMetrics = min(int(headerTable.numberOfHMetrics), numGlyphs)

        assert len(data) >= 2 * numberOfHMetrics
        advanceWidthArray = array.array("H", data[: 2 * numberOfHMetrics])
        if sys.byteorder != "big":
            advanceWidthArray.byteswap()
        data = data[2 * numberOfHMetrics :]

        if hasLsbArray:
            assert len(data) >= 2 * numberOfHMetrics
            lsbArray = array.array("h", data[: 2 * numberOfHMetrics])
            if sys.byteorder != "big":
                lsbArray.byteswap()
            data = data[2 * numberOfHMetrics :]
        else:
            # compute (proportional) glyphs' lsb from their xMin
            lsbArray = array.array("h")
            for i, glyphName in enumerate(glyphOrder):
                if i >= numberOfHMetrics:
                    break
                glyph = glyfTable[glyphName]
                xMin = getattr(glyph, "xMin", 0)
                lsbArray.append(xMin)

        numberOfSideBearings = numGlyphs - numberOfHMetrics
        if hasLeftSideBearingArray:
            assert len(data) >= 2 * numberOfSideBearings
            leftSideBearingArray = array.array("h", data[: 2 * numberOfSideBearings])
            if sys.byteorder != "big":
                leftSideBearingArray.byteswap()
            data = data[2 * numberOfSideBearings :]
        else:
            # compute (monospaced) glyphs' leftSideBearing from their xMin
            leftSideBearingArray = array.array("h")
            for i, glyphName in enumerate(glyphOrder):
                if i < numberOfHMetrics:
                    continue
                glyph = glyfTable[glyphName]
                xMin = getattr(glyph, "xMin", 0)
                leftSideBearingArray.append(xMin)

        if data:
            raise TTLibError("too much '%s' table data" % self.tableTag)

        self.metrics = {}
        for i in range(numberOfHMetrics):
            glyphName = glyphOrder[i]
            advanceWidth, lsb = advanceWidthArray[i], lsbArray[i]
            self.metrics[glyphName] = (advanceWidth, lsb)
        lastAdvance = advanceWidthArray[-1]
        for i in range(numberOfSideBearings):
            glyphName = glyphOrder[i + numberOfHMetrics]
            self.metrics[glyphName] = (lastAdvance, leftSideBearingArray[i])

    def transform(self, ttFont):
        glyphOrder = ttFont.getGlyphOrder()
        glyf = ttFont["glyf"]
        hhea = ttFont["hhea"]
        numberOfHMetrics = hhea.numberOfHMetrics

        # check if any of the proportional glyphs has left sidebearings that
        # differ from their xMin bounding box values.
        hasLsbArray = False
        for i in range(numberOfHMetrics):
            glyphName = glyphOrder[i]
            lsb = self.metrics[glyphName][1]
            if lsb != getattr(glyf[glyphName], "xMin", 0):
                hasLsbArray = True
                break

        # do the same for the monospaced glyphs (if any) at the end of hmtx table
        hasLeftSideBearingArray = False
        for i in range(numberOfHMetrics, len(glyphOrder)):
            glyphName = glyphOrder[i]
            lsb = self.metrics[glyphName][1]
            if lsb != getattr(glyf[glyphName], "xMin", 0):
                hasLeftSideBearingArray = True
                break

        # if we need to encode both sidebearings arrays, then no transformation is
        # applicable, and we must use the untransformed hmtx data
        if hasLsbArray and hasLeftSideBearingArray:
            return

        # set bit 0 and 1 when the respective arrays are _not_ present
        flags = 0
        if not hasLsbArray:
            flags |= 1 << 0
        if not hasLeftSideBearingArray:
            flags |= 1 << 1

        data = struct.pack(">B", flags)

        advanceWidthArray = array.array(
            "H",
            [
                self.metrics[glyphName][0]
                for i, glyphName in enumerate(glyphOrder)
                if i < numberOfHMetrics
            ],
        )
        if sys.byteorder != "big":
            advanceWidthArray.byteswap()
        data += advanceWidthArray.tobytes()

        if hasLsbArray:
            lsbArray = array.array(
                "h",
                [
                    self.metrics[glyphName][1]
                    for i, glyphName in enumerate(glyphOrder)
                    if i < numberOfHMetrics
                ],
            )
            if sys.byteorder != "big":
                lsbArray.byteswap()
            data += lsbArray.tobytes()

        if hasLeftSideBearingArray:
            leftSideBearingArray = array.array(
                "h",
                [
                    self.metrics[glyphOrder[i]][1]
                    for i in range(numberOfHMetrics, len(glyphOrder))
                ],
            )
            if sys.byteorder != "big":
                leftSideBearingArray.byteswap()
            data += leftSideBearingArray.tobytes()

        return data


class WOFF2FlavorData(WOFFFlavorData):
    Flavor = "woff2"

    def __init__(self, reader=None, data=None, transformedTables=None):
        """Data class that holds the WOFF2 header major/minor version, any
        metadata or private data (as bytes strings), and the set of
        table tags that have transformations applied (if reader is not None),
        or will have once the WOFF2 font is compiled.

        Args:
                reader: an SFNTReader (or subclass) object to read flavor data from.
                data: another WOFFFlavorData object to initialise data from.
                transformedTables: set of strings containing table tags to be transformed.

        Raises:
                ImportError if the brotli module is not installed.

        NOTE: The 'reader' argument, on the one hand, and the 'data' and
        'transformedTables' arguments, on the other hand, are mutually exclusive.
        """
        if not haveBrotli:
            raise ImportError("No module named brotli")

        if reader is not None:
            if data is not None:
                raise TypeError("'reader' and 'data' arguments are mutually exclusive")
            if transformedTables is not None:
                raise TypeError(
                    "'reader' and 'transformedTables' arguments are mutually exclusive"
                )

        if transformedTables is not None and (
            "glyf" in transformedTables
            and "loca" not in transformedTables
            or "loca" in transformedTables
            and "glyf" not in transformedTables
        ):
            raise ValueError("'glyf' and 'loca' must be transformed (or not) together")
        super(WOFF2FlavorData, self).__init__(reader=reader)
        if reader:
            transformedTables = [
                tag for tag, entry in reader.tables.items() if entry.transformed
            ]
        elif data:
            self.majorVersion = data.majorVersion
            self.majorVersion = data.minorVersion
            self.metaData = data.metaData
            self.privData = data.privData
            if transformedTables is None and hasattr(data, "transformedTables"):
                transformedTables = data.transformedTables

        if transformedTables is None:
            transformedTables = woff2TransformedTableTags

        self.transformedTables = set(transformedTables)

    def _decompress(self, rawData):
        return brotli.decompress(rawData)


def unpackBase128(data):
    r"""Read one to five bytes from UIntBase128-encoded input string, and return
    a tuple containing the decoded integer plus any leftover data.

    >>> unpackBase128(b'\x3f\x00\x00') == (63, b"\x00\x00")
    True
    >>> unpackBase128(b'\x8f\xff\xff\xff\x7f')[0] == 4294967295
    True
    >>> unpackBase128(b'\x80\x80\x3f')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
      File "<stdin>", line 1, in ?
    TTLibError: UIntBase128 value must not start with leading zeros
    >>> unpackBase128(b'\x8f\xff\xff\xff\xff\x7f')[0]  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
      File "<stdin>", line 1, in ?
    TTLibError: UIntBase128-encoded sequence is longer than 5 bytes
    >>> unpackBase128(b'\x90\x80\x80\x80\x00')[0]  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
      File "<stdin>", line 1, in ?
    TTLibError: UIntBase128 value exceeds 2**32-1
    """
    if len(data) == 0:
        raise TTLibError("not enough data to unpack UIntBase128")
    result = 0
    if byteord(data[0]) == 0x80:
        # font must be rejected if UIntBase128 value starts with 0x80
        raise TTLibError("UIntBase128 value must not start with leading zeros")
    for i in range(woff2Base128MaxSize):
        if len(data) == 0:
            raise TTLibError("not enough data to unpack UIntBase128")
        code = byteord(data[0])
        data = data[1:]
        # if any of the top seven bits are set then we're about to overflow
        if result & 0xFE000000:
            raise TTLibError("UIntBase128 value exceeds 2**32-1")
        # set current value = old value times 128 bitwise-or (byte bitwise-and 127)
        result = (result << 7) | (code & 0x7F)
        # repeat until the most significant bit of byte is false
        if (code & 0x80) == 0:
            # return result plus left over data
            return result, data
    # make sure not to exceed the size bound
    raise TTLibError("UIntBase128-encoded sequence is longer than 5 bytes")


def base128Size(n):
    """Return the length in bytes of a UIntBase128-encoded sequence with value n.

    >>> base128Size(0)
    1
    >>> base128Size(24567)
    3
    >>> base128Size(2**32-1)
    5
    """
    assert n >= 0
    size = 1
    while n >= 128:
        size += 1
        n >>= 7
    return size


def packBase128(n):
    r"""Encode unsigned integer in range 0 to 2**32-1 (inclusive) to a string of
    bytes using UIntBase128 variable-length encoding. Produce the shortest possible
    encoding.

    >>> packBase128(63) == b"\x3f"
    True
    >>> packBase128(2**32-1) == b'\x8f\xff\xff\xff\x7f'
    True
    """
    if n < 0 or n >= 2**32:
        raise TTLibError("UIntBase128 format requires 0 <= integer <= 2**32-1")
    data = b""
    size = base128Size(n)
    for i in range(size):
        b = (n >> (7 * (size - i - 1))) & 0x7F
        if i < size - 1:
            b |= 0x80
        data += struct.pack("B", b)
    return data


def unpack255UShort(data):
    """Read one to three bytes from 255UInt16-encoded input string, and return a
    tuple containing the decoded integer plus any leftover data.

    >>> unpack255UShort(bytechr(252))[0]
    252

    Note that some numbers (e.g. 506) can have multiple encodings:
    >>> unpack255UShort(struct.pack("BB", 254, 0))[0]
    506
    >>> unpack255UShort(struct.pack("BB", 255, 253))[0]
    506
    >>> unpack255UShort(struct.pack("BBB", 253, 1, 250))[0]
    506
    """
    code = byteord(data[:1])
    data = data[1:]
    if code == 253:
        # read two more bytes as an unsigned short
        if len(data) < 2:
            raise TTLibError("not enough data to unpack 255UInt16")
        (result,) = struct.unpack(">H", data[:2])
        data = data[2:]
    elif code == 254:
        # read another byte, plus 253 * 2
        if len(data) == 0:
            raise TTLibError("not enough data to unpack 255UInt16")
        result = byteord(data[:1])
        result += 506
        data = data[1:]
    elif code == 255:
        # read another byte, plus 253
        if len(data) == 0:
            raise TTLibError("not enough data to unpack 255UInt16")
        result = byteord(data[:1])
        result += 253
        data = data[1:]
    else:
        # leave as is if lower than 253
        result = code
    # return result plus left over data
    return result, data


def pack255UShort(value):
    r"""Encode unsigned integer in range 0 to 65535 (inclusive) to a bytestring
    using 255UInt16 variable-length encoding.

    >>> pack255UShort(252) == b'\xfc'
    True
    >>> pack255UShort(506) == b'\xfe\x00'
    True
    >>> pack255UShort(762) == b'\xfd\x02\xfa'
    True
    """
    if value < 0 or value > 0xFFFF:
        raise TTLibError("255UInt16 format requires 0 <= integer <= 65535")
    if value < 253:
        return struct.pack(">B", value)
    elif value < 506:
        return struct.pack(">BB", 255, value - 253)
    elif value < 762:
        return struct.pack(">BB", 254, value - 506)
    else:
        return struct.pack(">BH", 253, value)


def compress(input_file, output_file, transform_tables=None):
    """Compress OpenType font to WOFF2.

    Args:
            input_file: a file path, file or file-like object (open in binary mode)
                    containing an OpenType font (either CFF- or TrueType-flavored).
            output_file: a file path, file or file-like object where to save the
                    compressed WOFF2 font.
            transform_tables: Optional[Iterable[str]]: a set of table tags for which
                    to enable preprocessing transformations. By default, only 'glyf'
                    and 'loca' tables are transformed. An empty set means disable all
                    transformations.
    """
    log.info("Processing %s => %s" % (input_file, output_file))

    font = TTFont(input_file, recalcBBoxes=False, recalcTimestamp=False)
    font.flavor = "woff2"

    if transform_tables is not None:
        font.flavorData = WOFF2FlavorData(
            data=font.flavorData, transformedTables=transform_tables
        )

    font.save(output_file, reorderTables=False)


def decompress(input_file, output_file):
    """Decompress WOFF2 font to OpenType font.

    Args:
            input_file: a file path, file or file-like object (open in binary mode)
                    containing a compressed WOFF2 font.
            output_file: a file path, file or file-like object where to save the
                    decompressed OpenType font.
    """
    log.info("Processing %s => %s" % (input_file, output_file))

    font = TTFont(input_file, recalcBBoxes=False, recalcTimestamp=False)
    font.flavor = None
    font.flavorData = None
    font.save(output_file, reorderTables=True)


def main(args=None):
    """Compress and decompress WOFF2 fonts"""
    import argparse
    from fontTools import configLogger
    from fontTools.ttx import makeOutputFileName

    class _HelpAction(argparse._HelpAction):
        def __call__(self, parser, namespace, values, option_string=None):
            subparsers_actions = [
                action
                for action in parser._actions
                if isinstance(action, argparse._SubParsersAction)
            ]
            for subparsers_action in subparsers_actions:
                for choice, subparser in subparsers_action.choices.items():
                    print(subparser.format_help())
            parser.exit()

    class _NoGlyfTransformAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            namespace.transform_tables.difference_update({"glyf", "loca"})

    class _HmtxTransformAction(argparse.Action):
        def __call__(self, parser, namespace, values, option_string=None):
            namespace.transform_tables.add("hmtx")

    parser = argparse.ArgumentParser(
        prog="fonttools ttLib.woff2", description=main.__doc__, add_help=False
    )

    parser.add_argument(
        "-h", "--help", action=_HelpAction, help="show this help message and exit"
    )

    parser_group = parser.add_subparsers(title="sub-commands")
    parser_compress = parser_group.add_parser(
        "compress", description="Compress a TTF or OTF font to WOFF2"
    )
    parser_decompress = parser_group.add_parser(
        "decompress", description="Decompress a WOFF2 font to OTF"
    )

    for subparser in (parser_compress, parser_decompress):
        group = subparser.add_mutually_exclusive_group(required=False)
        group.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="print more messages to console",
        )
        group.add_argument(
            "-q",
            "--quiet",
            action="store_true",
            help="do not print messages to console",
        )

    parser_compress.add_argument(
        "input_file",
        metavar="INPUT",
        help="the input OpenType font (.ttf or .otf)",
    )
    parser_decompress.add_argument(
        "input_file",
        metavar="INPUT",
        help="the input WOFF2 font",
    )

    parser_compress.add_argument(
        "-o",
        "--output-file",
        metavar="OUTPUT",
        help="the output WOFF2 font",
    )
    parser_decompress.add_argument(
        "-o",
        "--output-file",
        metavar="OUTPUT",
        help="the output OpenType font",
    )

    transform_group = parser_compress.add_argument_group()
    transform_group.add_argument(
        "--no-glyf-transform",
        dest="transform_tables",
        nargs=0,
        action=_NoGlyfTransformAction,
        help="Do not transform glyf (and loca) tables",
    )
    transform_group.add_argument(
        "--hmtx-transform",
        dest="transform_tables",
        nargs=0,
        action=_HmtxTransformAction,
        help="Enable optional transformation for 'hmtx' table",
    )

    parser_compress.set_defaults(
        subcommand=compress,
        transform_tables={"glyf", "loca"},
    )
    parser_decompress.set_defaults(subcommand=decompress)

    options = vars(parser.parse_args(args))

    subcommand = options.pop("subcommand", None)
    if not subcommand:
        parser.print_help()
        return

    quiet = options.pop("quiet")
    verbose = options.pop("verbose")
    configLogger(
        level=("ERROR" if quiet else "DEBUG" if verbose else "INFO"),
    )

    if not options["output_file"]:
        if subcommand is compress:
            extension = ".woff2"
        elif subcommand is decompress:
            # choose .ttf/.otf file extension depending on sfntVersion
            with open(options["input_file"], "rb") as f:
                f.seek(4)  # skip 'wOF2' signature
                sfntVersion = f.read(4)
            assert len(sfntVersion) == 4, "not enough data"
            extension = ".otf" if sfntVersion == b"OTTO" else ".ttf"
        else:
            raise AssertionError(subcommand)
        options["output_file"] = makeOutputFileName(
            options["input_file"], outputDir=None, extension=extension
        )

    try:
        subcommand(**options)
    except TTLibError as e:
        parser.error(e)


if __name__ == "__main__":
    sys.exit(main())
