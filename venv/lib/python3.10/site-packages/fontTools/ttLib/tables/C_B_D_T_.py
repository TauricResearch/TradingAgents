# Copyright 2013 Google, Inc. All Rights Reserved.
#
# Google Author(s): Matt Fontaine


from fontTools.misc.textTools import bytesjoin
from fontTools.misc import sstruct
from . import E_B_D_T_
from .BitmapGlyphMetrics import (
    BigGlyphMetrics,
    bigGlyphMetricsFormat,
    SmallGlyphMetrics,
    smallGlyphMetricsFormat,
)
from .E_B_D_T_ import (
    BitmapGlyph,
    BitmapPlusSmallMetricsMixin,
    BitmapPlusBigMetricsMixin,
)
import struct


class table_C_B_D_T_(E_B_D_T_.table_E_B_D_T_):
    """Color Bitmap Data table

    The ``CBDT`` table contains color bitmap data for glyphs. It must
    be used in concert with the ``CBLC`` table.

    It is backwards-compatible with the monochrome/grayscale ``EBDT`` table.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/cbdt
    """

    # Change the data locator table being referenced.
    locatorName = "CBLC"

    # Modify the format class accessor for color bitmap use.
    def getImageFormatClass(self, imageFormat):
        try:
            return E_B_D_T_.table_E_B_D_T_.getImageFormatClass(self, imageFormat)
        except KeyError:
            return cbdt_bitmap_classes[imageFormat]


# Helper method for removing export features not supported by color bitmaps.
# Write data in the parent class will default to raw if an option is unsupported.
def _removeUnsupportedForColor(dataFunctions):
    dataFunctions = dict(dataFunctions)
    del dataFunctions["row"]
    return dataFunctions


class ColorBitmapGlyph(BitmapGlyph):
    fileExtension = ".png"
    xmlDataFunctions = _removeUnsupportedForColor(BitmapGlyph.xmlDataFunctions)


class cbdt_bitmap_format_17(BitmapPlusSmallMetricsMixin, ColorBitmapGlyph):
    def decompile(self):
        self.metrics = SmallGlyphMetrics()
        dummy, data = sstruct.unpack2(smallGlyphMetricsFormat, self.data, self.metrics)
        (dataLen,) = struct.unpack(">L", data[:4])
        data = data[4:]

        # For the image data cut it to the size specified by dataLen.
        assert dataLen <= len(data), "Data overun in format 17"
        self.imageData = data[:dataLen]

    def compile(self, ttFont):
        dataList = []
        dataList.append(sstruct.pack(smallGlyphMetricsFormat, self.metrics))
        dataList.append(struct.pack(">L", len(self.imageData)))
        dataList.append(self.imageData)
        return bytesjoin(dataList)


class cbdt_bitmap_format_18(BitmapPlusBigMetricsMixin, ColorBitmapGlyph):
    def decompile(self):
        self.metrics = BigGlyphMetrics()
        dummy, data = sstruct.unpack2(bigGlyphMetricsFormat, self.data, self.metrics)
        (dataLen,) = struct.unpack(">L", data[:4])
        data = data[4:]

        # For the image data cut it to the size specified by dataLen.
        assert dataLen <= len(data), "Data overun in format 18"
        self.imageData = data[:dataLen]

    def compile(self, ttFont):
        dataList = []
        dataList.append(sstruct.pack(bigGlyphMetricsFormat, self.metrics))
        dataList.append(struct.pack(">L", len(self.imageData)))
        dataList.append(self.imageData)
        return bytesjoin(dataList)


class cbdt_bitmap_format_19(ColorBitmapGlyph):
    def decompile(self):
        (dataLen,) = struct.unpack(">L", self.data[:4])
        data = self.data[4:]

        assert dataLen <= len(data), "Data overun in format 19"
        self.imageData = data[:dataLen]

    def compile(self, ttFont):
        return struct.pack(">L", len(self.imageData)) + self.imageData


# Dict for CBDT extended formats.
cbdt_bitmap_classes = {
    17: cbdt_bitmap_format_17,
    18: cbdt_bitmap_format_18,
    19: cbdt_bitmap_format_19,
}
