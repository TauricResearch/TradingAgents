from fontTools.misc.textTools import bytesjoin, safeEval
from . import DefaultTable
import struct


class table_V_O_R_G_(DefaultTable.DefaultTable):
    """Vertical Origin table

    The ``VORG`` table contains the vertical origin of each glyph
    in a `CFF` or `CFF2` font.

    This table is structured so that you can treat it like a dictionary keyed by glyph name.

    ``ttFont['VORG'][<glyphName>]`` will return the vertical origin for any glyph.

    ``ttFont['VORG'][<glyphName>] = <value>`` will set the vertical origin for any glyph.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/vorg
    """

    def decompile(self, data, ttFont):
        self.getGlyphName = (
            ttFont.getGlyphName
        )  # for use in get/set item functions, for access by GID
        (
            self.majorVersion,
            self.minorVersion,
            self.defaultVertOriginY,
            self.numVertOriginYMetrics,
        ) = struct.unpack(">HHhH", data[:8])
        assert (
            self.majorVersion <= 1
        ), "Major version of VORG table is higher than I know how to handle"
        data = data[8:]
        vids = []
        gids = []
        pos = 0
        for i in range(self.numVertOriginYMetrics):
            gid, vOrigin = struct.unpack(">Hh", data[pos : pos + 4])
            pos += 4
            gids.append(gid)
            vids.append(vOrigin)

        self.VOriginRecords = vOrig = {}
        glyphOrder = ttFont.getGlyphOrder()
        try:
            names = [glyphOrder[gid] for gid in gids]
        except IndexError:
            getGlyphName = self.getGlyphName
            names = map(getGlyphName, gids)

        for name, vid in zip(names, vids):
            vOrig[name] = vid

    def compile(self, ttFont):
        vorgs = list(self.VOriginRecords.values())
        names = list(self.VOriginRecords.keys())
        nameMap = ttFont.getReverseGlyphMap()
        try:
            gids = [nameMap[name] for name in names]
        except KeyError:
            nameMap = ttFont.getReverseGlyphMap(rebuild=True)
            gids = [nameMap[name] for name in names]
        vOriginTable = list(zip(gids, vorgs))
        self.numVertOriginYMetrics = len(vorgs)
        vOriginTable.sort()  # must be in ascending GID order
        dataList = [struct.pack(">Hh", rec[0], rec[1]) for rec in vOriginTable]
        header = struct.pack(
            ">HHhH",
            self.majorVersion,
            self.minorVersion,
            self.defaultVertOriginY,
            self.numVertOriginYMetrics,
        )
        dataList.insert(0, header)
        data = bytesjoin(dataList)
        return data

    def toXML(self, writer, ttFont):
        writer.simpletag("majorVersion", value=self.majorVersion)
        writer.newline()
        writer.simpletag("minorVersion", value=self.minorVersion)
        writer.newline()
        writer.simpletag("defaultVertOriginY", value=self.defaultVertOriginY)
        writer.newline()
        writer.simpletag("numVertOriginYMetrics", value=self.numVertOriginYMetrics)
        writer.newline()
        vOriginTable = []
        glyphNames = self.VOriginRecords.keys()
        for glyphName in glyphNames:
            try:
                gid = ttFont.getGlyphID(glyphName)
            except:
                assert 0, (
                    "VORG table contains a glyph name not in ttFont.getGlyphNames(): "
                    + str(glyphName)
                )
            vOriginTable.append([gid, glyphName, self.VOriginRecords[glyphName]])
        vOriginTable.sort()
        for entry in vOriginTable:
            vOriginRec = VOriginRecord(entry[1], entry[2])
            vOriginRec.toXML(writer, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "VOriginRecords"):
            self.VOriginRecords = {}
        self.getGlyphName = (
            ttFont.getGlyphName
        )  # for use in get/set item functions, for access by GID
        if name == "VOriginRecord":
            vOriginRec = VOriginRecord()
            for element in content:
                if isinstance(element, str):
                    continue
                name, attrs, content = element
                vOriginRec.fromXML(name, attrs, content, ttFont)
            self.VOriginRecords[vOriginRec.glyphName] = vOriginRec.vOrigin
        elif "value" in attrs:
            setattr(self, name, safeEval(attrs["value"]))

    def __getitem__(self, glyphSelector):
        if isinstance(glyphSelector, int):
            # its a gid, convert to glyph name
            glyphSelector = self.getGlyphName(glyphSelector)

        if glyphSelector not in self.VOriginRecords:
            return self.defaultVertOriginY

        return self.VOriginRecords[glyphSelector]

    def __setitem__(self, glyphSelector, value):
        if isinstance(glyphSelector, int):
            # its a gid, convert to glyph name
            glyphSelector = self.getGlyphName(glyphSelector)

        if value != self.defaultVertOriginY:
            self.VOriginRecords[glyphSelector] = value
        elif glyphSelector in self.VOriginRecords:
            del self.VOriginRecords[glyphSelector]

    def __delitem__(self, glyphSelector):
        del self.VOriginRecords[glyphSelector]


class VOriginRecord(object):
    def __init__(self, name=None, vOrigin=None):
        self.glyphName = name
        self.vOrigin = vOrigin

    def toXML(self, writer, ttFont):
        writer.begintag("VOriginRecord")
        writer.newline()
        writer.simpletag("glyphName", value=self.glyphName)
        writer.newline()
        writer.simpletag("vOrigin", value=self.vOrigin)
        writer.newline()
        writer.endtag("VOriginRecord")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        value = attrs["value"]
        if name == "glyphName":
            setattr(self, name, value)
        else:
            setattr(self, name, safeEval(value))
