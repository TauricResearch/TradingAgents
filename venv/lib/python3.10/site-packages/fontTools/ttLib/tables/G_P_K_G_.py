from fontTools.misc import sstruct
from fontTools.misc.textTools import bytesjoin, safeEval, readHex
from . import DefaultTable
import sys
import array

GPKGFormat = """
		>	# big endian
		version:	H
		flags:	H
		numGMAPs:		H
		numGlyplets:		H
"""
# psFontName is a byte string which follows the record above. This is zero padded
# to the beginning of the records array. The recordsOffsst is 32 bit aligned.


class table_G_P_K_G_(DefaultTable.DefaultTable):
    """Glyphlets GPKG table

    The ``GPKG`` table is used by Adobe's SING Glyphlets.

    See also https://web.archive.org/web/20080627183635/http://www.adobe.com/devnet/opentype/gdk/topic.html
    """

    def decompile(self, data, ttFont):
        dummy, newData = sstruct.unpack2(GPKGFormat, data, self)

        GMAPoffsets = array.array("I")
        endPos = (self.numGMAPs + 1) * 4
        GMAPoffsets.frombytes(newData[:endPos])
        if sys.byteorder != "big":
            GMAPoffsets.byteswap()
        self.GMAPs = []
        for i in range(self.numGMAPs):
            start = GMAPoffsets[i]
            end = GMAPoffsets[i + 1]
            self.GMAPs.append(data[start:end])
        pos = endPos
        endPos = pos + (self.numGlyplets + 1) * 4
        glyphletOffsets = array.array("I")
        glyphletOffsets.frombytes(newData[pos:endPos])
        if sys.byteorder != "big":
            glyphletOffsets.byteswap()
        self.glyphlets = []
        for i in range(self.numGlyplets):
            start = glyphletOffsets[i]
            end = glyphletOffsets[i + 1]
            self.glyphlets.append(data[start:end])

    def compile(self, ttFont):
        self.numGMAPs = len(self.GMAPs)
        self.numGlyplets = len(self.glyphlets)
        GMAPoffsets = [0] * (self.numGMAPs + 1)
        glyphletOffsets = [0] * (self.numGlyplets + 1)

        dataList = [sstruct.pack(GPKGFormat, self)]

        pos = len(dataList[0]) + (self.numGMAPs + 1) * 4 + (self.numGlyplets + 1) * 4
        GMAPoffsets[0] = pos
        for i in range(1, self.numGMAPs + 1):
            pos += len(self.GMAPs[i - 1])
            GMAPoffsets[i] = pos
        gmapArray = array.array("I", GMAPoffsets)
        if sys.byteorder != "big":
            gmapArray.byteswap()
        dataList.append(gmapArray.tobytes())

        glyphletOffsets[0] = pos
        for i in range(1, self.numGlyplets + 1):
            pos += len(self.glyphlets[i - 1])
            glyphletOffsets[i] = pos
        glyphletArray = array.array("I", glyphletOffsets)
        if sys.byteorder != "big":
            glyphletArray.byteswap()
        dataList.append(glyphletArray.tobytes())
        dataList += self.GMAPs
        dataList += self.glyphlets
        data = bytesjoin(dataList)
        return data

    def toXML(self, writer, ttFont):
        writer.comment("Most of this table will be recalculated by the compiler")
        writer.newline()
        formatstring, names, fixes = sstruct.getformat(GPKGFormat)
        for name in names:
            value = getattr(self, name)
            writer.simpletag(name, value=value)
            writer.newline()

        writer.begintag("GMAPs")
        writer.newline()
        for gmapData in self.GMAPs:
            writer.begintag("hexdata")
            writer.newline()
            writer.dumphex(gmapData)
            writer.endtag("hexdata")
            writer.newline()
        writer.endtag("GMAPs")
        writer.newline()

        writer.begintag("glyphlets")
        writer.newline()
        for glyphletData in self.glyphlets:
            writer.begintag("hexdata")
            writer.newline()
            writer.dumphex(glyphletData)
            writer.endtag("hexdata")
            writer.newline()
        writer.endtag("glyphlets")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "GMAPs":
            if not hasattr(self, "GMAPs"):
                self.GMAPs = []
            for element in content:
                if isinstance(element, str):
                    continue
                itemName, itemAttrs, itemContent = element
                if itemName == "hexdata":
                    self.GMAPs.append(readHex(itemContent))
        elif name == "glyphlets":
            if not hasattr(self, "glyphlets"):
                self.glyphlets = []
            for element in content:
                if isinstance(element, str):
                    continue
                itemName, itemAttrs, itemContent = element
                if itemName == "hexdata":
                    self.glyphlets.append(readHex(itemContent))
        else:
            setattr(self, name, safeEval(attrs["value"]))
