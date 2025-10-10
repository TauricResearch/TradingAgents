from fontTools.misc.textTools import bytesjoin, tobytes, safeEval
from . import DefaultTable
import struct

# https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6ltag.html


class table__l_t_a_g(DefaultTable.DefaultTable):
    """Language Tag table

    The AAT ``ltag`` table contains mappings between the numeric codes used
    in the language field of the ``name`` table and IETF language tags.

    See also https://developer.apple.com/fonts/TrueType-Reference-Manual/RM06/Chap6ltag.html
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.version, self.flags = 1, 0
        self.tags = []

    def addTag(self, tag):
        """Add 'tag' to the list of langauge tags if not already there.

        Returns the integer index of 'tag' in the list of all tags.
        """
        try:
            return self.tags.index(tag)
        except ValueError:
            self.tags.append(tag)
            return len(self.tags) - 1

    def decompile(self, data, ttFont):
        self.version, self.flags, numTags = struct.unpack(">LLL", data[:12])
        assert self.version == 1
        self.tags = []
        for i in range(numTags):
            pos = 12 + i * 4
            offset, length = struct.unpack(">HH", data[pos : pos + 4])
            tag = data[offset : offset + length].decode("ascii")
            self.tags.append(tag)

    def compile(self, ttFont):
        dataList = [struct.pack(">LLL", self.version, self.flags, len(self.tags))]
        stringPool = ""
        for tag in self.tags:
            offset = stringPool.find(tag)
            if offset < 0:
                offset = len(stringPool)
                stringPool = stringPool + tag
            offset = offset + 12 + len(self.tags) * 4
            dataList.append(struct.pack(">HH", offset, len(tag)))
        dataList.append(tobytes(stringPool))
        return bytesjoin(dataList)

    def toXML(self, writer, ttFont):
        writer.simpletag("version", value=self.version)
        writer.newline()
        writer.simpletag("flags", value=self.flags)
        writer.newline()
        for tag in self.tags:
            writer.simpletag("LanguageTag", tag=tag)
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if not hasattr(self, "tags"):
            self.tags = []
        if name == "LanguageTag":
            self.tags.append(attrs["tag"])
        elif "value" in attrs:
            value = safeEval(attrs["value"])
            setattr(self, name, value)
