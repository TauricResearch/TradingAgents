from io import BytesIO
from fontTools import cffLib
from . import DefaultTable


class table_C_F_F_(DefaultTable.DefaultTable):
    """Compact Font Format table (version 1)

    The ``CFF`` table embeds a CFF-formatted font. The CFF font format
    predates OpenType and could be used as a standalone font file, but the
    ``CFF`` table is also used to package CFF fonts into an OpenType
    container.

    .. note::
       ``CFF`` has been succeeded by ``CFF2``, which eliminates much of
       the redundancy incurred by embedding CFF version 1 in an OpenType
       font.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cff
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.cff = cffLib.CFFFontSet()
        self._gaveGlyphOrder = False

    def decompile(self, data, otFont):
        self.cff.decompile(BytesIO(data), otFont, isCFF2=False)
        assert len(self.cff) == 1, "can't deal with multi-font CFF tables."

    def compile(self, otFont):
        f = BytesIO()
        self.cff.compile(f, otFont, isCFF2=False)
        return f.getvalue()

    def haveGlyphNames(self):
        if hasattr(self.cff[self.cff.fontNames[0]], "ROS"):
            return False  # CID-keyed font
        else:
            return True

    def getGlyphOrder(self):
        if self._gaveGlyphOrder:
            from fontTools import ttLib

            raise ttLib.TTLibError("illegal use of getGlyphOrder()")
        self._gaveGlyphOrder = True
        return self.cff[self.cff.fontNames[0]].getGlyphOrder()

    def setGlyphOrder(self, glyphOrder):
        pass
        # XXX
        # self.cff[self.cff.fontNames[0]].setGlyphOrder(glyphOrder)

    def toXML(self, writer, otFont):
        self.cff.toXML(writer)

    def fromXML(self, name, attrs, content, otFont):
        if not hasattr(self, "cff"):
            self.cff = cffLib.CFFFontSet()
        self.cff.fromXML(name, attrs, content, otFont)
