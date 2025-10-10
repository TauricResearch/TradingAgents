from fontTools.misc import sstruct
from fontTools.misc.textTools import tobytes, tostr, safeEval
from . import DefaultTable

GMAPFormat = """
		>	# big endian
		tableVersionMajor:	H
		tableVersionMinor: 	H
		flags:	H
		recordsCount:		H
		recordsOffset:		H
		fontNameLength:		H
"""
# psFontName is a byte string which follows the record above. This is zero padded
# to the beginning of the records array. The recordsOffsst is 32 bit aligned.

GMAPRecordFormat1 = """
		>	# big endian
		UV:			L
		cid:		H
		gid:		H
		ggid:		H
		name:		32s
"""


class GMAPRecord(object):
    def __init__(self, uv=0, cid=0, gid=0, ggid=0, name=""):
        self.UV = uv
        self.cid = cid
        self.gid = gid
        self.ggid = ggid
        self.name = name

    def toXML(self, writer, ttFont):
        writer.begintag("GMAPRecord")
        writer.newline()
        writer.simpletag("UV", value=self.UV)
        writer.newline()
        writer.simpletag("cid", value=self.cid)
        writer.newline()
        writer.simpletag("gid", value=self.gid)
        writer.newline()
        writer.simpletag("glyphletGid", value=self.gid)
        writer.newline()
        writer.simpletag("GlyphletName", value=self.name)
        writer.newline()
        writer.endtag("GMAPRecord")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        value = attrs["value"]
        if name == "GlyphletName":
            self.name = value
        else:
            setattr(self, name, safeEval(value))

    def compile(self, ttFont):
        if self.UV is None:
            self.UV = 0
        nameLen = len(self.name)
        if nameLen < 32:
            self.name = self.name + "\0" * (32 - nameLen)
        data = sstruct.pack(GMAPRecordFormat1, self)
        return data

    def __repr__(self):
        return (
            "GMAPRecord[ UV: "
            + str(self.UV)
            + ", cid: "
            + str(self.cid)
            + ", gid: "
            + str(self.gid)
            + ", ggid: "
            + str(self.ggid)
            + ", Glyphlet Name: "
            + str(self.name)
            + " ]"
        )


class table_G_M_A_P_(DefaultTable.DefaultTable):
    """Glyphlets GMAP table

    The ``GMAP`` table is used by Adobe's SING Glyphlets.

    See also https://web.archive.org/web/20080627183635/http://www.adobe.com/devnet/opentype/gdk/topic.html
    """

    dependencies = []

    def decompile(self, data, ttFont):
        dummy, newData = sstruct.unpack2(GMAPFormat, data, self)
        self.psFontName = tostr(newData[: self.fontNameLength])
        assert (
            self.recordsOffset % 4
        ) == 0, "GMAP error: recordsOffset is not 32 bit aligned."
        newData = data[self.recordsOffset :]
        self.gmapRecords = []
        for i in range(self.recordsCount):
            gmapRecord, newData = sstruct.unpack2(
                GMAPRecordFormat1, newData, GMAPRecord()
            )
            gmapRecord.name = gmapRecord.name.strip("\0")
            self.gmapRecords.append(gmapRecord)

    def compile(self, ttFont):
        self.recordsCount = len(self.gmapRecords)
        self.fontNameLength = len(self.psFontName)
        self.recordsOffset = 4 * (((self.fontNameLength + 12) + 3) // 4)
        data = sstruct.pack(GMAPFormat, self)
        data = data + tobytes(self.psFontName)
        data = data + b"\0" * (self.recordsOffset - len(data))
        for record in self.gmapRecords:
            data = data + record.compile(ttFont)
        return data

    def toXML(self, writer, ttFont):
        writer.comment("Most of this table will be recalculated by the compiler")
        writer.newline()
        formatstring, names, fixes = sstruct.getformat(GMAPFormat)
        for name in names:
            value = getattr(self, name)
            writer.simpletag(name, value=value)
            writer.newline()
        writer.simpletag("PSFontName", value=self.psFontName)
        writer.newline()
        for gmapRecord in self.gmapRecords:
            gmapRecord.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name == "GMAPRecord":
            if not hasattr(self, "gmapRecords"):
                self.gmapRecords = []
            gmapRecord = GMAPRecord()
            self.gmapRecords.append(gmapRecord)
            for element in content:
                if isinstance(element, str):
                    continue
                name, attrs, content = element
                gmapRecord.fromXML(name, attrs, content, ttFont)
        else:
            value = attrs["value"]
            if name == "PSFontName":
                self.psFontName = value
            else:
                setattr(self, name, safeEval(value))
