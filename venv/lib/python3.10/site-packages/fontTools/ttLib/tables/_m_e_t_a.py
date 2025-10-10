from fontTools.misc import sstruct
from fontTools.misc.textTools import bytesjoin, strjoin, readHex
from fontTools.ttLib import TTLibError
from . import DefaultTable

# Apple's documentation of 'meta':
# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6meta.html

META_HEADER_FORMAT = """
    > # big endian
    version:     L
    flags:       L
    dataOffset:  L
    numDataMaps: L
"""


DATA_MAP_FORMAT = """
    > # big endian
    tag:         4s
    dataOffset:  L
    dataLength:  L
"""


class table__m_e_t_a(DefaultTable.DefaultTable):
    """Metadata table

    The ``meta`` table contains various metadata values for the font. Each
    category of metadata in the table is identified by a four-character tag.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/meta
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.data = {}

    def decompile(self, data, ttFont):
        headerSize = sstruct.calcsize(META_HEADER_FORMAT)
        header = sstruct.unpack(META_HEADER_FORMAT, data[0:headerSize])
        if header["version"] != 1:
            raise TTLibError("unsupported 'meta' version %d" % header["version"])
        dataMapSize = sstruct.calcsize(DATA_MAP_FORMAT)
        for i in range(header["numDataMaps"]):
            dataMapOffset = headerSize + i * dataMapSize
            dataMap = sstruct.unpack(
                DATA_MAP_FORMAT, data[dataMapOffset : dataMapOffset + dataMapSize]
            )
            tag = dataMap["tag"]
            offset = dataMap["dataOffset"]
            self.data[tag] = data[offset : offset + dataMap["dataLength"]]
            if tag in ["dlng", "slng"]:
                self.data[tag] = self.data[tag].decode("utf-8")

    def compile(self, ttFont):
        keys = sorted(self.data.keys())
        headerSize = sstruct.calcsize(META_HEADER_FORMAT)
        dataOffset = headerSize + len(keys) * sstruct.calcsize(DATA_MAP_FORMAT)
        header = sstruct.pack(
            META_HEADER_FORMAT,
            {
                "version": 1,
                "flags": 0,
                "dataOffset": dataOffset,
                "numDataMaps": len(keys),
            },
        )
        dataMaps = []
        dataBlocks = []
        for tag in keys:
            if tag in ["dlng", "slng"]:
                data = self.data[tag].encode("utf-8")
            else:
                data = self.data[tag]
            dataMaps.append(
                sstruct.pack(
                    DATA_MAP_FORMAT,
                    {"tag": tag, "dataOffset": dataOffset, "dataLength": len(data)},
                )
            )
            dataBlocks.append(data)
            dataOffset += len(data)
        return bytesjoin([header] + dataMaps + dataBlocks)

    def toXML(self, writer, ttFont):
        for tag in sorted(self.data.keys()):
            if tag in ["dlng", "slng"]:
                writer.begintag("text", tag=tag)
                writer.newline()
                writer.write(self.data[tag])
                writer.newline()
                writer.endtag("text")
                writer.newline()
            else:
                writer.begintag("hexdata", tag=tag)
                writer.newline()
                data = self.data[tag]
                if min(data) >= 0x20 and max(data) <= 0x7E:
                    writer.comment("ascii: " + data.decode("ascii"))
                    writer.newline()
                writer.dumphex(data)
                writer.endtag("hexdata")
                writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "hexdata":
            self.data[attrs["tag"]] = readHex(content)
        elif name == "text" and attrs["tag"] in ["dlng", "slng"]:
            self.data[attrs["tag"]] = strjoin(content).strip()
        else:
            raise TTLibError("can't handle '%s' element" % name)
