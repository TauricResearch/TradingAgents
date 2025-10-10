"""ttLib/sfnt.py -- low-level module to deal with the sfnt file format.

Defines two public classes:

- SFNTReader
- SFNTWriter

(Normally you don't have to use these classes explicitly; they are
used automatically by ttLib.TTFont.)

The reading and writing of sfnt files is separated in two distinct
classes, since whenever the number of tables changes or whenever
a table's length changes you need to rewrite the whole file anyway.
"""

from io import BytesIO
from types import SimpleNamespace
from fontTools.misc.textTools import Tag
from fontTools.misc import sstruct
from fontTools.ttLib import TTLibError, TTLibFileIsCollectionError
import struct
from collections import OrderedDict
import logging


log = logging.getLogger(__name__)


class SFNTReader(object):
    def __new__(cls, *args, **kwargs):
        """Return an instance of the SFNTReader sub-class which is compatible
        with the input file type.
        """
        if args and cls is SFNTReader:
            infile = args[0]
            infile.seek(0)
            sfntVersion = Tag(infile.read(4))
            infile.seek(0)
            if sfntVersion == "wOF2":
                # return new WOFF2Reader object
                from fontTools.ttLib.woff2 import WOFF2Reader

                return object.__new__(WOFF2Reader)
        # return default object
        return object.__new__(cls)

    def __init__(self, file, checkChecksums=0, fontNumber=-1):
        self.file = file
        self.checkChecksums = checkChecksums

        self.flavor = None
        self.flavorData = None
        self.DirectoryEntry = SFNTDirectoryEntry
        self.file.seek(0)
        self.sfntVersion = self.file.read(4)
        self.file.seek(0)
        if self.sfntVersion == b"ttcf":
            header = readTTCHeader(self.file)
            numFonts = header.numFonts
            if not 0 <= fontNumber < numFonts:
                raise TTLibFileIsCollectionError(
                    "specify a font number between 0 and %d (inclusive)"
                    % (numFonts - 1)
                )
            self.numFonts = numFonts
            self.file.seek(header.offsetTable[fontNumber])
            data = self.file.read(sfntDirectorySize)
            if len(data) != sfntDirectorySize:
                raise TTLibError("Not a Font Collection (not enough data)")
            sstruct.unpack(sfntDirectoryFormat, data, self)
        elif self.sfntVersion == b"wOFF":
            self.flavor = "woff"
            self.DirectoryEntry = WOFFDirectoryEntry
            data = self.file.read(woffDirectorySize)
            if len(data) != woffDirectorySize:
                raise TTLibError("Not a WOFF font (not enough data)")
            sstruct.unpack(woffDirectoryFormat, data, self)
        else:
            data = self.file.read(sfntDirectorySize)
            if len(data) != sfntDirectorySize:
                raise TTLibError("Not a TrueType or OpenType font (not enough data)")
            sstruct.unpack(sfntDirectoryFormat, data, self)
        self.sfntVersion = Tag(self.sfntVersion)

        if self.sfntVersion not in ("\x00\x01\x00\x00", "OTTO", "true"):
            raise TTLibError("Not a TrueType or OpenType font (bad sfntVersion)")
        tables = {}
        for i in range(self.numTables):
            entry = self.DirectoryEntry()
            entry.fromFile(self.file)
            tag = Tag(entry.tag)
            tables[tag] = entry
        self.tables = OrderedDict(sorted(tables.items(), key=lambda i: i[1].offset))

        # Load flavor data if any
        if self.flavor == "woff":
            self.flavorData = WOFFFlavorData(self)

    def has_key(self, tag):
        return tag in self.tables

    __contains__ = has_key

    def keys(self):
        return self.tables.keys()

    def __getitem__(self, tag):
        """Fetch the raw table data."""
        entry = self.tables[Tag(tag)]
        data = entry.loadData(self.file)
        if self.checkChecksums:
            if tag == "head":
                # Beh: we have to special-case the 'head' table.
                checksum = calcChecksum(data[:8] + b"\0\0\0\0" + data[12:])
            else:
                checksum = calcChecksum(data)
            if self.checkChecksums > 1:
                # Be obnoxious, and barf when it's wrong
                assert checksum == entry.checkSum, "bad checksum for '%s' table" % tag
            elif checksum != entry.checkSum:
                # Be friendly, and just log a warning.
                log.warning("bad checksum for '%s' table", tag)
        return data

    def __delitem__(self, tag):
        del self.tables[Tag(tag)]

    def close(self):
        self.file.close()

    # We define custom __getstate__ and __setstate__ to make SFNTReader pickle-able
    # and deepcopy-able. When a TTFont is loaded as lazy=True, SFNTReader holds a
    # reference to an external file object which is not pickleable. So in __getstate__
    # we store the file name and current position, and in __setstate__ we reopen the
    # same named file after unpickling.

    def __getstate__(self):
        if isinstance(self.file, BytesIO):
            # BytesIO is already pickleable, return the state unmodified
            return self.__dict__

        # remove unpickleable file attribute, and only store its name and pos
        state = self.__dict__.copy()
        del state["file"]
        state["_filename"] = self.file.name
        state["_filepos"] = self.file.tell()
        return state

    def __setstate__(self, state):
        if "file" not in state:
            self.file = open(state.pop("_filename"), "rb")
            self.file.seek(state.pop("_filepos"))
        self.__dict__.update(state)


# default compression level for WOFF 1.0 tables and metadata
ZLIB_COMPRESSION_LEVEL = 6

# if set to True, use zopfli instead of zlib for compressing WOFF 1.0.
# The Python bindings are available at https://pypi.python.org/pypi/zopfli
USE_ZOPFLI = False

# mapping between zlib's compression levels and zopfli's 'numiterations'.
# Use lower values for files over several MB in size or it will be too slow
ZOPFLI_LEVELS = {
    # 0: 0,  # can't do 0 iterations...
    1: 1,
    2: 3,
    3: 5,
    4: 8,
    5: 10,
    6: 15,
    7: 25,
    8: 50,
    9: 100,
}


def compress(data, level=ZLIB_COMPRESSION_LEVEL):
    """Compress 'data' to Zlib format. If 'USE_ZOPFLI' variable is True,
    zopfli is used instead of the zlib module.
    The compression 'level' must be between 0 and 9. 1 gives best speed,
    9 gives best compression (0 gives no compression at all).
    The default value is a compromise between speed and compression (6).
    """
    if not (0 <= level <= 9):
        raise ValueError("Bad compression level: %s" % level)
    if not USE_ZOPFLI or level == 0:
        from zlib import compress

        return compress(data, level)
    else:
        from zopfli.zlib import compress

        return compress(data, numiterations=ZOPFLI_LEVELS[level])


class SFNTWriter(object):
    def __new__(cls, *args, **kwargs):
        """Return an instance of the SFNTWriter sub-class which is compatible
        with the specified 'flavor'.
        """
        flavor = None
        if kwargs and "flavor" in kwargs:
            flavor = kwargs["flavor"]
        elif args and len(args) > 3:
            flavor = args[3]
        if cls is SFNTWriter:
            if flavor == "woff2":
                # return new WOFF2Writer object
                from fontTools.ttLib.woff2 import WOFF2Writer

                return object.__new__(WOFF2Writer)
        # return default object
        return object.__new__(cls)

    def __init__(
        self,
        file,
        numTables,
        sfntVersion="\000\001\000\000",
        flavor=None,
        flavorData=None,
    ):
        self.file = file
        self.numTables = numTables
        self.sfntVersion = Tag(sfntVersion)
        self.flavor = flavor
        self.flavorData = flavorData

        if self.flavor == "woff":
            self.directoryFormat = woffDirectoryFormat
            self.directorySize = woffDirectorySize
            self.DirectoryEntry = WOFFDirectoryEntry

            self.signature = "wOFF"

            # to calculate WOFF checksum adjustment, we also need the original SFNT offsets
            self.origNextTableOffset = (
                sfntDirectorySize + numTables * sfntDirectoryEntrySize
            )
        else:
            assert not self.flavor, "Unknown flavor '%s'" % self.flavor
            self.directoryFormat = sfntDirectoryFormat
            self.directorySize = sfntDirectorySize
            self.DirectoryEntry = SFNTDirectoryEntry

            from fontTools.ttLib import getSearchRange

            self.searchRange, self.entrySelector, self.rangeShift = getSearchRange(
                numTables, 16
            )

        self.directoryOffset = self.file.tell()
        self.nextTableOffset = (
            self.directoryOffset
            + self.directorySize
            + numTables * self.DirectoryEntry.formatSize
        )
        # clear out directory area
        self.file.seek(self.nextTableOffset)
        # make sure we're actually where we want to be. (old cStringIO bug)
        self.file.write(b"\0" * (self.nextTableOffset - self.file.tell()))
        self.tables = OrderedDict()

    def setEntry(self, tag, entry):
        if tag in self.tables:
            raise TTLibError("cannot rewrite '%s' table" % tag)

        self.tables[tag] = entry

    def __setitem__(self, tag, data):
        """Write raw table data to disk."""
        if tag in self.tables:
            raise TTLibError("cannot rewrite '%s' table" % tag)

        entry = self.DirectoryEntry()
        entry.tag = tag
        entry.offset = self.nextTableOffset
        if tag == "head":
            entry.checkSum = calcChecksum(data[:8] + b"\0\0\0\0" + data[12:])
            self.headTable = data
            entry.uncompressed = True
        else:
            entry.checkSum = calcChecksum(data)
        entry.saveData(self.file, data)

        if self.flavor == "woff":
            entry.origOffset = self.origNextTableOffset
            self.origNextTableOffset += (entry.origLength + 3) & ~3

        self.nextTableOffset = self.nextTableOffset + ((entry.length + 3) & ~3)
        # Add NUL bytes to pad the table data to a 4-byte boundary.
        # Don't depend on f.seek() as we need to add the padding even if no
        # subsequent write follows (seek is lazy), ie. after the final table
        # in the font.
        self.file.write(b"\0" * (self.nextTableOffset - self.file.tell()))
        assert self.nextTableOffset == self.file.tell()

        self.setEntry(tag, entry)

    def __getitem__(self, tag):
        return self.tables[tag]

    def close(self):
        """All tables must have been written to disk. Now write the
        directory.
        """
        tables = sorted(self.tables.items())
        if len(tables) != self.numTables:
            raise TTLibError(
                "wrong number of tables; expected %d, found %d"
                % (self.numTables, len(tables))
            )

        if self.flavor == "woff":
            self.signature = b"wOFF"
            self.reserved = 0

            self.totalSfntSize = 12
            self.totalSfntSize += 16 * len(tables)
            for tag, entry in tables:
                self.totalSfntSize += (entry.origLength + 3) & ~3

            data = self.flavorData if self.flavorData else WOFFFlavorData()
            if data.majorVersion is not None and data.minorVersion is not None:
                self.majorVersion = data.majorVersion
                self.minorVersion = data.minorVersion
            else:
                if hasattr(self, "headTable"):
                    self.majorVersion, self.minorVersion = struct.unpack(
                        ">HH", self.headTable[4:8]
                    )
                else:
                    self.majorVersion = self.minorVersion = 0
            if data.metaData:
                self.metaOrigLength = len(data.metaData)
                self.file.seek(0, 2)
                self.metaOffset = self.file.tell()
                compressedMetaData = compress(data.metaData)
                self.metaLength = len(compressedMetaData)
                self.file.write(compressedMetaData)
            else:
                self.metaOffset = self.metaLength = self.metaOrigLength = 0
            if data.privData:
                self.file.seek(0, 2)
                off = self.file.tell()
                paddedOff = (off + 3) & ~3
                self.file.write(b"\0" * (paddedOff - off))
                self.privOffset = self.file.tell()
                self.privLength = len(data.privData)
                self.file.write(data.privData)
            else:
                self.privOffset = self.privLength = 0

            self.file.seek(0, 2)
            self.length = self.file.tell()

        else:
            assert not self.flavor, "Unknown flavor '%s'" % self.flavor
            pass

        directory = sstruct.pack(self.directoryFormat, self)

        self.file.seek(self.directoryOffset + self.directorySize)
        seenHead = 0
        for tag, entry in tables:
            if tag == "head":
                seenHead = 1
            directory = directory + entry.toString()
        if seenHead:
            self.writeMasterChecksum(directory)
        self.file.seek(self.directoryOffset)
        self.file.write(directory)

    def _calcMasterChecksum(self, directory):
        # calculate checkSumAdjustment
        checksums = []
        for tag in self.tables.keys():
            checksums.append(self.tables[tag].checkSum)

        if self.DirectoryEntry != SFNTDirectoryEntry:
            # Create a SFNT directory for checksum calculation purposes
            from fontTools.ttLib import getSearchRange

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

    def writeMasterChecksum(self, directory):
        checksumadjustment = self._calcMasterChecksum(directory)
        # write the checksum to the file
        self.file.seek(self.tables["head"].offset + 8)
        self.file.write(struct.pack(">L", checksumadjustment))

    def reordersTables(self):
        return False


# -- sfnt directory helpers and cruft

ttcHeaderFormat = """
		> # big endian
		TTCTag:                  4s # "ttcf"
		Version:                 L  # 0x00010000 or 0x00020000
		numFonts:                L  # number of fonts
		# OffsetTable[numFonts]: L  # array with offsets from beginning of file
		# ulDsigTag:             L  # version 2.0 only
		# ulDsigLength:          L  # version 2.0 only
		# ulDsigOffset:          L  # version 2.0 only
"""

ttcHeaderSize = sstruct.calcsize(ttcHeaderFormat)

sfntDirectoryFormat = """
		> # big endian
		sfntVersion:    4s
		numTables:      H    # number of tables
		searchRange:    H    # (max2 <= numTables)*16
		entrySelector:  H    # log2(max2 <= numTables)
		rangeShift:     H    # numTables*16-searchRange
"""

sfntDirectorySize = sstruct.calcsize(sfntDirectoryFormat)

sfntDirectoryEntryFormat = """
		> # big endian
		tag:            4s
		checkSum:       L
		offset:         L
		length:         L
"""

sfntDirectoryEntrySize = sstruct.calcsize(sfntDirectoryEntryFormat)

woffDirectoryFormat = """
		> # big endian
		signature:      4s   # "wOFF"
		sfntVersion:    4s
		length:         L    # total woff file size
		numTables:      H    # number of tables
		reserved:       H    # set to 0
		totalSfntSize:  L    # uncompressed size
		majorVersion:   H    # major version of WOFF file
		minorVersion:   H    # minor version of WOFF file
		metaOffset:     L    # offset to metadata block
		metaLength:     L    # length of compressed metadata
		metaOrigLength: L    # length of uncompressed metadata
		privOffset:     L    # offset to private data block
		privLength:     L    # length of private data block
"""

woffDirectorySize = sstruct.calcsize(woffDirectoryFormat)

woffDirectoryEntryFormat = """
		> # big endian
		tag:            4s
		offset:         L
		length:         L    # compressed length
		origLength:     L    # original length
		checkSum:       L    # original checksum
"""

woffDirectoryEntrySize = sstruct.calcsize(woffDirectoryEntryFormat)


class DirectoryEntry(object):
    def __init__(self):
        self.uncompressed = False  # if True, always embed entry raw

    def fromFile(self, file):
        sstruct.unpack(self.format, file.read(self.formatSize), self)

    def fromString(self, str):
        sstruct.unpack(self.format, str, self)

    def toString(self):
        return sstruct.pack(self.format, self)

    def __repr__(self):
        if hasattr(self, "tag"):
            return "<%s '%s' at %x>" % (self.__class__.__name__, self.tag, id(self))
        else:
            return "<%s at %x>" % (self.__class__.__name__, id(self))

    def loadData(self, file):
        file.seek(self.offset)
        data = file.read(self.length)
        assert len(data) == self.length
        if hasattr(self.__class__, "decodeData"):
            data = self.decodeData(data)
        return data

    def saveData(self, file, data):
        if hasattr(self.__class__, "encodeData"):
            data = self.encodeData(data)
        self.length = len(data)
        file.seek(self.offset)
        file.write(data)

    def decodeData(self, rawData):
        return rawData

    def encodeData(self, data):
        return data


class SFNTDirectoryEntry(DirectoryEntry):
    format = sfntDirectoryEntryFormat
    formatSize = sfntDirectoryEntrySize


class WOFFDirectoryEntry(DirectoryEntry):
    format = woffDirectoryEntryFormat
    formatSize = woffDirectoryEntrySize

    def __init__(self):
        super(WOFFDirectoryEntry, self).__init__()
        # With fonttools<=3.1.2, the only way to set a different zlib
        # compression level for WOFF directory entries was to set the class
        # attribute 'zlibCompressionLevel'. This is now replaced by a globally
        # defined `ZLIB_COMPRESSION_LEVEL`, which is also applied when
        # compressing the metadata. For backward compatibility, we still
        # use the class attribute if it was already set.
        if not hasattr(WOFFDirectoryEntry, "zlibCompressionLevel"):
            self.zlibCompressionLevel = ZLIB_COMPRESSION_LEVEL

    def decodeData(self, rawData):
        import zlib

        if self.length == self.origLength:
            data = rawData
        else:
            assert self.length < self.origLength
            data = zlib.decompress(rawData)
            assert len(data) == self.origLength
        return data

    def encodeData(self, data):
        self.origLength = len(data)
        if not self.uncompressed:
            compressedData = compress(data, self.zlibCompressionLevel)
        if self.uncompressed or len(compressedData) >= self.origLength:
            # Encode uncompressed
            rawData = data
            self.length = self.origLength
        else:
            rawData = compressedData
            self.length = len(rawData)
        return rawData


class WOFFFlavorData:
    Flavor = "woff"

    def __init__(self, reader=None):
        self.majorVersion = None
        self.minorVersion = None
        self.metaData = None
        self.privData = None
        if reader:
            self.majorVersion = reader.majorVersion
            self.minorVersion = reader.minorVersion
            if reader.metaLength:
                reader.file.seek(reader.metaOffset)
                rawData = reader.file.read(reader.metaLength)
                assert len(rawData) == reader.metaLength
                data = self._decompress(rawData)
                assert len(data) == reader.metaOrigLength
                self.metaData = data
            if reader.privLength:
                reader.file.seek(reader.privOffset)
                data = reader.file.read(reader.privLength)
                assert len(data) == reader.privLength
                self.privData = data

    def _decompress(self, rawData):
        import zlib

        return zlib.decompress(rawData)


def calcChecksum(data):
    """Calculate the checksum for an arbitrary block of data.

    If the data length is not a multiple of four, it assumes
    it is to be padded with null byte.

            >>> print(calcChecksum(b"abcd"))
            1633837924
            >>> print(calcChecksum(b"abcdxyz"))
            3655064932
    """
    remainder = len(data) % 4
    if remainder:
        data += b"\0" * (4 - remainder)
    value = 0
    blockSize = 4096
    assert blockSize % 4 == 0
    for i in range(0, len(data), blockSize):
        block = data[i : i + blockSize]
        longs = struct.unpack(">%dL" % (len(block) // 4), block)
        value = (value + sum(longs)) & 0xFFFFFFFF
    return value


def readTTCHeader(file):
    file.seek(0)
    data = file.read(ttcHeaderSize)
    if len(data) != ttcHeaderSize:
        raise TTLibError("Not a Font Collection (not enough data)")
    self = SimpleNamespace()
    sstruct.unpack(ttcHeaderFormat, data, self)
    if self.TTCTag != "ttcf":
        raise TTLibError("Not a Font Collection")
    assert self.Version == 0x00010000 or self.Version == 0x00020000, (
        "unrecognized TTC version 0x%08x" % self.Version
    )
    self.offsetTable = struct.unpack(
        ">%dL" % self.numFonts, file.read(self.numFonts * 4)
    )
    if self.Version == 0x00020000:
        pass  # ignoring version 2.0 signatures
    return self


def writeTTCHeader(file, numFonts):
    self = SimpleNamespace()
    self.TTCTag = "ttcf"
    self.Version = 0x00010000
    self.numFonts = numFonts
    file.seek(0)
    file.write(sstruct.pack(ttcHeaderFormat, self))
    offset = file.tell()
    file.write(struct.pack(">%dL" % self.numFonts, *([0] * self.numFonts)))
    return offset


if __name__ == "__main__":
    import sys
    import doctest

    sys.exit(doctest.testmod().failed)
