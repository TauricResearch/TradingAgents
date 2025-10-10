from fontTools.misc import sstruct
from fontTools.misc.fixedTools import (
    fixedToFloat as fi2fl,
    floatToFixed as fl2fi,
    floatToFixedToStr as fl2str,
    strToFixedToFloat as str2fl,
)
from fontTools.misc.textTools import bytesjoin, safeEval
from fontTools.ttLib import TTLibError
from . import DefaultTable
import struct
from collections.abc import MutableMapping


# Apple's documentation of 'trak':
# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6trak.html

TRAK_HEADER_FORMAT = """
	> # big endian
	version:     16.16F
	format:      H
	horizOffset: H
	vertOffset:  H
	reserved:    H
"""

TRAK_HEADER_FORMAT_SIZE = sstruct.calcsize(TRAK_HEADER_FORMAT)


TRACK_DATA_FORMAT = """
	> # big endian
	nTracks:         H
	nSizes:          H
	sizeTableOffset: L
"""

TRACK_DATA_FORMAT_SIZE = sstruct.calcsize(TRACK_DATA_FORMAT)


TRACK_TABLE_ENTRY_FORMAT = """
	> # big endian
	track:      16.16F
	nameIndex:       H
	offset:          H
"""

TRACK_TABLE_ENTRY_FORMAT_SIZE = sstruct.calcsize(TRACK_TABLE_ENTRY_FORMAT)


# size values are actually '16.16F' fixed-point values, but here I do the
# fixedToFloat conversion manually instead of relying on sstruct
SIZE_VALUE_FORMAT = ">l"
SIZE_VALUE_FORMAT_SIZE = struct.calcsize(SIZE_VALUE_FORMAT)

# per-Size values are in 'FUnits', i.e. 16-bit signed integers
PER_SIZE_VALUE_FORMAT = ">h"
PER_SIZE_VALUE_FORMAT_SIZE = struct.calcsize(PER_SIZE_VALUE_FORMAT)


class table__t_r_a_k(DefaultTable.DefaultTable):
    """The AAT ``trak`` table can store per-size adjustments to each glyph's
    sidebearings to make when tracking is enabled, which applications can
    use to provide more visually balanced line spacing.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6trak.html
    """

    dependencies = ["name"]

    def compile(self, ttFont):
        dataList = []
        offset = TRAK_HEADER_FORMAT_SIZE
        for direction in ("horiz", "vert"):
            trackData = getattr(self, direction + "Data", TrackData())
            offsetName = direction + "Offset"
            # set offset to 0 if None or empty
            if not trackData:
                setattr(self, offsetName, 0)
                continue
            # TrackData table format must be longword aligned
            alignedOffset = (offset + 3) & ~3
            padding, offset = b"\x00" * (alignedOffset - offset), alignedOffset
            setattr(self, offsetName, offset)

            data = trackData.compile(offset)
            offset += len(data)
            dataList.append(padding + data)

        self.reserved = 0
        tableData = bytesjoin([sstruct.pack(TRAK_HEADER_FORMAT, self)] + dataList)
        return tableData

    def decompile(self, data, ttFont):
        sstruct.unpack(TRAK_HEADER_FORMAT, data[:TRAK_HEADER_FORMAT_SIZE], self)
        for direction in ("horiz", "vert"):
            trackData = TrackData()
            offset = getattr(self, direction + "Offset")
            if offset != 0:
                trackData.decompile(data, offset)
            setattr(self, direction + "Data", trackData)

    def toXML(self, writer, ttFont):
        writer.simpletag("version", value=self.version)
        writer.newline()
        writer.simpletag("format", value=self.format)
        writer.newline()
        for direction in ("horiz", "vert"):
            dataName = direction + "Data"
            writer.begintag(dataName)
            writer.newline()
            trackData = getattr(self, dataName, TrackData())
            trackData.toXML(writer, ttFont)
            writer.endtag(dataName)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            self.version = safeEval(attrs["value"])
        elif name == "format":
            self.format = safeEval(attrs["value"])
        elif name in ("horizData", "vertData"):
            trackData = TrackData()
            setattr(self, name, trackData)
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content_ = element
                trackData.fromXML(name, attrs, content_, ttFont)


class TrackData(MutableMapping):
    def __init__(self, initialdata={}):
        self._map = dict(initialdata)

    def compile(self, offset):
        nTracks = len(self)
        sizes = self.sizes()
        nSizes = len(sizes)

        # offset to the start of the size subtable
        offset += TRACK_DATA_FORMAT_SIZE + TRACK_TABLE_ENTRY_FORMAT_SIZE * nTracks
        trackDataHeader = sstruct.pack(
            TRACK_DATA_FORMAT,
            {"nTracks": nTracks, "nSizes": nSizes, "sizeTableOffset": offset},
        )

        entryDataList = []
        perSizeDataList = []
        # offset to per-size tracking values
        offset += SIZE_VALUE_FORMAT_SIZE * nSizes
        # sort track table entries by track value
        for track, entry in sorted(self.items()):
            assert entry.nameIndex is not None
            entry.track = track
            entry.offset = offset
            entryDataList += [sstruct.pack(TRACK_TABLE_ENTRY_FORMAT, entry)]
            # sort per-size values by size
            for size, value in sorted(entry.items()):
                perSizeDataList += [struct.pack(PER_SIZE_VALUE_FORMAT, value)]
            offset += PER_SIZE_VALUE_FORMAT_SIZE * nSizes
        # sort size values
        sizeDataList = [
            struct.pack(SIZE_VALUE_FORMAT, fl2fi(sv, 16)) for sv in sorted(sizes)
        ]

        data = bytesjoin(
            [trackDataHeader] + entryDataList + sizeDataList + perSizeDataList
        )
        return data

    def decompile(self, data, offset):
        # initial offset is from the start of trak table to the current TrackData
        trackDataHeader = data[offset : offset + TRACK_DATA_FORMAT_SIZE]
        if len(trackDataHeader) != TRACK_DATA_FORMAT_SIZE:
            raise TTLibError("not enough data to decompile TrackData header")
        sstruct.unpack(TRACK_DATA_FORMAT, trackDataHeader, self)
        offset += TRACK_DATA_FORMAT_SIZE

        nSizes = self.nSizes
        sizeTableOffset = self.sizeTableOffset
        sizeTable = []
        for i in range(nSizes):
            sizeValueData = data[
                sizeTableOffset : sizeTableOffset + SIZE_VALUE_FORMAT_SIZE
            ]
            if len(sizeValueData) < SIZE_VALUE_FORMAT_SIZE:
                raise TTLibError("not enough data to decompile TrackData size subtable")
            (sizeValue,) = struct.unpack(SIZE_VALUE_FORMAT, sizeValueData)
            sizeTable.append(fi2fl(sizeValue, 16))
            sizeTableOffset += SIZE_VALUE_FORMAT_SIZE

        for i in range(self.nTracks):
            entry = TrackTableEntry()
            entryData = data[offset : offset + TRACK_TABLE_ENTRY_FORMAT_SIZE]
            if len(entryData) < TRACK_TABLE_ENTRY_FORMAT_SIZE:
                raise TTLibError("not enough data to decompile TrackTableEntry record")
            sstruct.unpack(TRACK_TABLE_ENTRY_FORMAT, entryData, entry)
            perSizeOffset = entry.offset
            for j in range(nSizes):
                size = sizeTable[j]
                perSizeValueData = data[
                    perSizeOffset : perSizeOffset + PER_SIZE_VALUE_FORMAT_SIZE
                ]
                if len(perSizeValueData) < PER_SIZE_VALUE_FORMAT_SIZE:
                    raise TTLibError(
                        "not enough data to decompile per-size track values"
                    )
                (perSizeValue,) = struct.unpack(PER_SIZE_VALUE_FORMAT, perSizeValueData)
                entry[size] = perSizeValue
                perSizeOffset += PER_SIZE_VALUE_FORMAT_SIZE
            self[entry.track] = entry
            offset += TRACK_TABLE_ENTRY_FORMAT_SIZE

    def toXML(self, writer, ttFont):
        nTracks = len(self)
        nSizes = len(self.sizes())
        writer.comment("nTracks=%d, nSizes=%d" % (nTracks, nSizes))
        writer.newline()
        for track, entry in sorted(self.items()):
            assert entry.nameIndex is not None
            entry.track = track
            entry.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name != "trackEntry":
            return
        entry = TrackTableEntry()
        entry.fromXML(name, attrs, content, ttFont)
        self[entry.track] = entry

    def sizes(self):
        if not self:
            return frozenset()
        tracks = list(self.tracks())
        sizes = self[tracks.pop(0)].sizes()
        for track in tracks:
            entrySizes = self[track].sizes()
            if sizes != entrySizes:
                raise TTLibError(
                    "'trak' table entries must specify the same sizes: "
                    "%s != %s" % (sorted(sizes), sorted(entrySizes))
                )
        return frozenset(sizes)

    def __getitem__(self, track):
        return self._map[track]

    def __delitem__(self, track):
        del self._map[track]

    def __setitem__(self, track, entry):
        self._map[track] = entry

    def __len__(self):
        return len(self._map)

    def __iter__(self):
        return iter(self._map)

    def keys(self):
        return self._map.keys()

    tracks = keys

    def __repr__(self):
        return "TrackData({})".format(self._map if self else "")


class TrackTableEntry(MutableMapping):
    def __init__(self, values={}, nameIndex=None):
        self.nameIndex = nameIndex
        self._map = dict(values)

    def toXML(self, writer, ttFont):
        name = ttFont["name"].getDebugName(self.nameIndex)
        writer.begintag(
            "trackEntry",
            (("value", fl2str(self.track, 16)), ("nameIndex", self.nameIndex)),
        )
        writer.newline()
        if name:
            writer.comment(name)
            writer.newline()
        for size, perSizeValue in sorted(self.items()):
            writer.simpletag("track", size=fl2str(size, 16), value=perSizeValue)
            writer.newline()
        writer.endtag("trackEntry")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.track = str2fl(attrs["value"], 16)
        self.nameIndex = safeEval(attrs["nameIndex"])
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, _ = element
            if name != "track":
                continue
            size = str2fl(attrs["size"], 16)
            self[size] = safeEval(attrs["value"])

    def __getitem__(self, size):
        return self._map[size]

    def __delitem__(self, size):
        del self._map[size]

    def __setitem__(self, size, value):
        self._map[size] = value

    def __len__(self):
        return len(self._map)

    def __iter__(self):
        return iter(self._map)

    def keys(self):
        return self._map.keys()

    sizes = keys

    def __repr__(self):
        return "TrackTableEntry({}, nameIndex={})".format(self._map, self.nameIndex)

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.nameIndex == other.nameIndex and dict(self) == dict(other)

    def __ne__(self, other):
        result = self.__eq__(other)
        return result if result is NotImplemented else not result
