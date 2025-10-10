from fontTools.misc import sstruct
from fontTools.misc.textTools import safeEval, num2binary, binary2num
from . import DefaultTable
from .sbixStrike import Strike


sbixHeaderFormat = """
	>
	version:       H	# Version number (set to 1)
	flags:         H	# The only two bits used in the flags field are bits 0
						# and 1. For historical reasons, bit 0 must always be 1.
						# Bit 1 is a sbixDrawOutlines flag and is interpreted as
						# follows:
						#     0: Draw only 'sbix' bitmaps
						#     1: Draw both 'sbix' bitmaps and outlines, in that
						#        order
	numStrikes:    L	# Number of bitmap strikes to follow
"""
sbixHeaderFormatSize = sstruct.calcsize(sbixHeaderFormat)


sbixStrikeOffsetFormat = """
	>
	strikeOffset:  L	# Offset from begining of table to data for the
						# individual strike
"""
sbixStrikeOffsetFormatSize = sstruct.calcsize(sbixStrikeOffsetFormat)


class table__s_b_i_x(DefaultTable.DefaultTable):
    """Standard Bitmap Graphics table

    The ``sbix`` table stores bitmap image data in standard graphics formats
    like JPEG, PNG, or TIFF. The glyphs for which the ``sbix`` table provides
    data are indexed by Glyph ID. For each such glyph, the ``sbix`` table can
    hold different data for different sizes, called "strikes."

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/sbix
    """

    def __init__(self, tag=None):
        DefaultTable.DefaultTable.__init__(self, tag)
        self.version = 1
        self.flags = 1
        self.numStrikes = 0
        self.strikes = {}
        self.strikeOffsets = []

    def decompile(self, data, ttFont):
        # read table header
        sstruct.unpack(sbixHeaderFormat, data[:sbixHeaderFormatSize], self)
        # collect offsets to individual strikes in self.strikeOffsets
        for i in range(self.numStrikes):
            current_offset = sbixHeaderFormatSize + i * sbixStrikeOffsetFormatSize
            offset_entry = sbixStrikeOffset()
            sstruct.unpack(
                sbixStrikeOffsetFormat,
                data[current_offset : current_offset + sbixStrikeOffsetFormatSize],
                offset_entry,
            )
            self.strikeOffsets.append(offset_entry.strikeOffset)

        # decompile Strikes
        for i in range(self.numStrikes - 1, -1, -1):
            current_strike = Strike(rawdata=data[self.strikeOffsets[i] :])
            data = data[: self.strikeOffsets[i]]
            current_strike.decompile(ttFont)
            # print "  Strike length: %xh" % len(bitmapSetData)
            # print "Number of Glyph entries:", len(current_strike.glyphs)
            if current_strike.ppem in self.strikes:
                from fontTools import ttLib

                raise ttLib.TTLibError("Pixel 'ppem' must be unique for each Strike")
            self.strikes[current_strike.ppem] = current_strike

        # after the glyph data records have been extracted, we don't need the offsets anymore
        del self.strikeOffsets
        del self.numStrikes

    def compile(self, ttFont):
        sbixData = b""
        self.numStrikes = len(self.strikes)
        sbixHeader = sstruct.pack(sbixHeaderFormat, self)

        # calculate offset to start of first strike
        setOffset = sbixHeaderFormatSize + sbixStrikeOffsetFormatSize * self.numStrikes

        for si in sorted(self.strikes.keys()):
            current_strike = self.strikes[si]
            current_strike.compile(ttFont)
            # append offset to this strike to table header
            current_strike.strikeOffset = setOffset
            sbixHeader += sstruct.pack(sbixStrikeOffsetFormat, current_strike)
            setOffset += len(current_strike.data)
            sbixData += current_strike.data

        return sbixHeader + sbixData

    def toXML(self, xmlWriter, ttFont):
        xmlWriter.simpletag("version", value=self.version)
        xmlWriter.newline()
        xmlWriter.simpletag("flags", value=num2binary(self.flags, 16))
        xmlWriter.newline()
        for i in sorted(self.strikes.keys()):
            self.strikes[i].toXML(xmlWriter, ttFont)

    def fromXML(self, name, attrs, content, ttFont):
        if name == "version":
            setattr(self, name, safeEval(attrs["value"]))
        elif name == "flags":
            setattr(self, name, binary2num(attrs["value"]))
        elif name == "strike":
            current_strike = Strike()
            for element in content:
                if isinstance(element, tuple):
                    name, attrs, content = element
                    current_strike.fromXML(name, attrs, content, ttFont)
            self.strikes[current_strike.ppem] = current_strike
        else:
            from fontTools import ttLib

            raise ttLib.TTLibError("can't handle '%s' element" % name)


# Helper classes


class sbixStrikeOffset(object):
    pass
