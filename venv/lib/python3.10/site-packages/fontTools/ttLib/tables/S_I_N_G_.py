from fontTools.misc import sstruct
from fontTools.misc.textTools import bytechr, byteord, tobytes, tostr, safeEval
from . import DefaultTable

SINGFormat = """
		>	# big endian
		tableVersionMajor:	H
		tableVersionMinor: 	H
		glyphletVersion:	H
		permissions:		h
		mainGID:			H
		unitsPerEm:			H
		vertAdvance:		h
		vertOrigin:			h
		uniqueName:			28s
		METAMD5:			16s
		nameLength:			1s
"""
# baseGlyphName is a byte string which follows the record above.


class table_S_I_N_G_(DefaultTable.DefaultTable):
    """Glyphlets SING table

    The ``SING`` table is used by Adobe's SING Glyphlets.

    See also https://web.archive.org/web/20080627183635/http://www.adobe.com/devnet/opentype/gdk/topic.html
    """

    dependencies = []

    def decompile(self, data, ttFont):
        dummy, rest = sstruct.unpack2(SINGFormat, data, self)
        self.uniqueName = self.decompileUniqueName(self.uniqueName)
        self.nameLength = byteord(self.nameLength)
        assert len(rest) == self.nameLength
        self.baseGlyphName = tostr(rest)

        rawMETAMD5 = self.METAMD5
        self.METAMD5 = "[" + hex(byteord(self.METAMD5[0]))
        for char in rawMETAMD5[1:]:
            self.METAMD5 = self.METAMD5 + ", " + hex(byteord(char))
        self.METAMD5 = self.METAMD5 + "]"

    def decompileUniqueName(self, data):
        name = ""
        for char in data:
            val = byteord(char)
            if val == 0:
                break
            if (val > 31) or (val < 128):
                name += chr(val)
            else:
                octString = oct(val)
                if len(octString) > 3:
                    octString = octString[1:]  # chop off that leading zero.
                elif len(octString) < 3:
                    octString.zfill(3)
                name += "\\" + octString
        return name

    def compile(self, ttFont):
        d = self.__dict__.copy()
        d["nameLength"] = bytechr(len(self.baseGlyphName))
        d["uniqueName"] = self.compilecompileUniqueName(self.uniqueName, 28)
        METAMD5List = eval(self.METAMD5)
        d["METAMD5"] = b""
        for val in METAMD5List:
            d["METAMD5"] += bytechr(val)
        assert len(d["METAMD5"]) == 16, "Failed to pack 16 byte MD5 hash in SING table"
        data = sstruct.pack(SINGFormat, d)
        data = data + tobytes(self.baseGlyphName)
        return data

    def compilecompileUniqueName(self, name, length):
        nameLen = len(name)
        if length <= nameLen:
            name = name[: length - 1] + "\000"
        else:
            name += (nameLen - length) * "\000"
        return name

    def toXML(self, writer, ttFont):
        writer.comment("Most of this table will be recalculated by the compiler")
        writer.newline()
        formatstring, names, fixes = sstruct.getformat(SINGFormat)
        for name in names:
            value = getattr(self, name)
            writer.simpletag(name, value=value)
            writer.newline()
        writer.simpletag("baseGlyphName", value=self.baseGlyphName)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        value = attrs["value"]
        if name in ["uniqueName", "METAMD5", "baseGlyphName"]:
            setattr(self, name, value)
        else:
            setattr(self, name, safeEval(value))
