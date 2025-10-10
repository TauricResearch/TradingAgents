from fontTools.misc import sstruct
from fontTools.misc.textTools import readHex, safeEval
import struct


sbixGlyphHeaderFormat = """
	>
	originOffsetX: h	# The x-value of the point in the glyph relative to its
						# lower-left corner which corresponds to the origin of
						# the glyph on the screen, that is the point on the
						# baseline at the left edge of the glyph.
	originOffsetY: h	# The y-value of the point in the glyph relative to its
						# lower-left corner which corresponds to the origin of
						# the glyph on the screen, that is the point on the
						# baseline at the left edge of the glyph.
	graphicType:  4s	# e.g. "png "
"""

sbixGlyphHeaderFormatSize = sstruct.calcsize(sbixGlyphHeaderFormat)


class Glyph(object):
    def __init__(
        self,
        glyphName=None,
        referenceGlyphName=None,
        originOffsetX=0,
        originOffsetY=0,
        graphicType=None,
        imageData=None,
        rawdata=None,
        gid=0,
    ):
        self.gid = gid
        self.glyphName = glyphName
        self.referenceGlyphName = referenceGlyphName
        self.originOffsetX = originOffsetX
        self.originOffsetY = originOffsetY
        self.rawdata = rawdata
        self.graphicType = graphicType
        self.imageData = imageData

        # fix self.graphicType if it is null terminated or too short
        if self.graphicType is not None:
            if self.graphicType[-1] == "\0":
                self.graphicType = self.graphicType[:-1]
            if len(self.graphicType) > 4:
                from fontTools import ttLib

                raise ttLib.TTLibError(
                    "Glyph.graphicType must not be longer than 4 characters."
                )
            elif len(self.graphicType) < 4:
                # pad with spaces
                self.graphicType += "    "[: (4 - len(self.graphicType))]

    def is_reference_type(self):
        """Returns True if this glyph is a reference to another glyph's image data."""
        return self.graphicType == "dupe" or self.graphicType == "flip"

    def decompile(self, ttFont):
        self.glyphName = ttFont.getGlyphName(self.gid)
        if self.rawdata is None:
            from fontTools import ttLib

            raise ttLib.TTLibError("No table data to decompile")
        if len(self.rawdata) > 0:
            if len(self.rawdata) < sbixGlyphHeaderFormatSize:
                from fontTools import ttLib

                # print "Glyph %i header too short: Expected %x, got %x." % (self.gid, sbixGlyphHeaderFormatSize, len(self.rawdata))
                raise ttLib.TTLibError("Glyph header too short.")

            sstruct.unpack(
                sbixGlyphHeaderFormat, self.rawdata[:sbixGlyphHeaderFormatSize], self
            )

            if self.is_reference_type():
                # this glyph is a reference to another glyph's image data
                (gid,) = struct.unpack(">H", self.rawdata[sbixGlyphHeaderFormatSize:])
                self.referenceGlyphName = ttFont.getGlyphName(gid)
            else:
                self.imageData = self.rawdata[sbixGlyphHeaderFormatSize:]
                self.referenceGlyphName = None
        # clean up
        del self.rawdata
        del self.gid

    def compile(self, ttFont):
        if self.glyphName is None:
            from fontTools import ttLib

            raise ttLib.TTLibError("Can't compile Glyph without glyph name")
            # TODO: if ttFont has no maxp, cmap etc., ignore glyph names and compile by index?
            # (needed if you just want to compile the sbix table on its own)
        self.gid = struct.pack(">H", ttFont.getGlyphID(self.glyphName))
        if self.graphicType is None:
            rawdata = b""
        else:
            rawdata = sstruct.pack(sbixGlyphHeaderFormat, self)
            if self.is_reference_type():
                rawdata += struct.pack(">H", ttFont.getGlyphID(self.referenceGlyphName))
            else:
                assert self.imageData is not None
                rawdata += self.imageData
        self.rawdata = rawdata

    def toXML(self, xmlWriter, ttFont):
        if self.graphicType is None:
            # TODO: ignore empty glyphs?
            # a glyph data entry is required for each glyph,
            # but empty ones can be calculated at compile time
            xmlWriter.simpletag("glyph", name=self.glyphName)
            xmlWriter.newline()
            return
        xmlWriter.begintag(
            "glyph",
            graphicType=self.graphicType,
            name=self.glyphName,
            originOffsetX=self.originOffsetX,
            originOffsetY=self.originOffsetY,
        )
        xmlWriter.newline()
        if self.is_reference_type():
            # this glyph is a reference to another glyph id.
            xmlWriter.simpletag("ref", glyphname=self.referenceGlyphName)
        else:
            xmlWriter.begintag("hexdata")
            xmlWriter.newline()
            xmlWriter.dumphex(self.imageData)
            xmlWriter.endtag("hexdata")
        xmlWriter.newline()
        xmlWriter.endtag("glyph")
        xmlWriter.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "ref":
            # this glyph i.e. a reference to another glyph's image data.
            # in this case imageData contains the glyph id of the reference glyph
            # get glyph id from glyphname
            glyphname = safeEval("'''" + attrs["glyphname"] + "'''")
            self.imageData = struct.pack(">H", ttFont.getGlyphID(glyphname))
            self.referenceGlyphName = glyphname
        elif name == "hexdata":
            self.imageData = readHex(content)
        else:
            from fontTools import ttLib

            raise ttLib.TTLibError("can't handle '%s' element" % name)
