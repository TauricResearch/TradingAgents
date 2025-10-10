from fontTools.misc import sstruct
from fontTools.misc.textTools import (
    bytechr,
    byteord,
    bytesjoin,
    strjoin,
    safeEval,
    readHex,
    hexStr,
    deHexStr,
)
from .BitmapGlyphMetrics import (
    BigGlyphMetrics,
    bigGlyphMetricsFormat,
    SmallGlyphMetrics,
    smallGlyphMetricsFormat,
)
from . import DefaultTable
import itertools
import os
import struct
import logging


log = logging.getLogger(__name__)

ebdtTableVersionFormat = """
	> # big endian
	version: 16.16F
"""

ebdtComponentFormat = """
	> # big endian
	glyphCode: H
	xOffset:   b
	yOffset:   b
"""


class table_E_B_D_T_(DefaultTable.DefaultTable):
    """Embedded Bitmap Data table

    The ``EBDT`` table contains monochrome or grayscale bitmap data for
    glyphs. It must be used in concert with the ``EBLC`` table.

    See also https://learn.microsoft.com/en-us/typography/opentype/spec/ebdt
    """

    # Keep a reference to the name of the data locator table.
    locatorName = "EBLC"

    # This method can be overridden in subclasses to support new formats
    # without changing the other implementation. Also can be used as a
    # convenience method for coverting a font file to an alternative format.
    def getImageFormatClass(self, imageFormat):
        return ebdt_bitmap_classes[imageFormat]

    def decompile(self, data, ttFont):
        # Get the version but don't advance the slice.
        # Most of the lookup for this table is done relative
        # to the begining so slice by the offsets provided
        # in the EBLC table.
        sstruct.unpack2(ebdtTableVersionFormat, data, self)

        # Keep a dict of glyphs that have been seen so they aren't remade.
        # This dict maps intervals of data to the BitmapGlyph.
        glyphDict = {}

        # Pull out the EBLC table and loop through glyphs.
        # A strike is a concept that spans both tables.
        # The actual bitmap data is stored in the EBDT.
        locator = ttFont[self.__class__.locatorName]
        self.strikeData = []
        for curStrike in locator.strikes:
            bitmapGlyphDict = {}
            self.strikeData.append(bitmapGlyphDict)
            for indexSubTable in curStrike.indexSubTables:
                dataIter = zip(indexSubTable.names, indexSubTable.locations)
                for curName, curLoc in dataIter:
                    # Don't create duplicate data entries for the same glyphs.
                    # Instead just use the structures that already exist if they exist.
                    if curLoc in glyphDict:
                        curGlyph = glyphDict[curLoc]
                    else:
                        curGlyphData = data[slice(*curLoc)]
                        imageFormatClass = self.getImageFormatClass(
                            indexSubTable.imageFormat
                        )
                        curGlyph = imageFormatClass(curGlyphData, ttFont)
                        glyphDict[curLoc] = curGlyph
                    bitmapGlyphDict[curName] = curGlyph

    def compile(self, ttFont):
        dataList = []
        dataList.append(sstruct.pack(ebdtTableVersionFormat, self))
        dataSize = len(dataList[0])

        # Keep a dict of glyphs that have been seen so they aren't remade.
        # This dict maps the id of the BitmapGlyph to the interval
        # in the data.
        glyphDict = {}

        # Go through the bitmap glyph data. Just in case the data for a glyph
        # changed the size metrics should be recalculated. There are a variety
        # of formats and they get stored in the EBLC table. That is why
        # recalculation is defered to the EblcIndexSubTable class and just
        # pass what is known about bitmap glyphs from this particular table.
        locator = ttFont[self.__class__.locatorName]
        for curStrike, curGlyphDict in zip(locator.strikes, self.strikeData):
            for curIndexSubTable in curStrike.indexSubTables:
                dataLocations = []
                for curName in curIndexSubTable.names:
                    # Handle the data placement based on seeing the glyph or not.
                    # Just save a reference to the location if the glyph has already
                    # been saved in compile. This code assumes that glyphs will only
                    # be referenced multiple times from indexFormat5. By luck the
                    # code may still work when referencing poorly ordered fonts with
                    # duplicate references. If there is a font that is unlucky the
                    # respective compile methods for the indexSubTables will fail
                    # their assertions. All fonts seem to follow this assumption.
                    # More complicated packing may be needed if a counter-font exists.
                    glyph = curGlyphDict[curName]
                    objectId = id(glyph)
                    if objectId not in glyphDict:
                        data = glyph.compile(ttFont)
                        data = curIndexSubTable.padBitmapData(data)
                        startByte = dataSize
                        dataSize += len(data)
                        endByte = dataSize
                        dataList.append(data)
                        dataLoc = (startByte, endByte)
                        glyphDict[objectId] = dataLoc
                    else:
                        dataLoc = glyphDict[objectId]
                    dataLocations.append(dataLoc)
                # Just use the new data locations in the indexSubTable.
                # The respective compile implementations will take care
                # of any of the problems in the convertion that may arise.
                curIndexSubTable.locations = dataLocations

        return bytesjoin(dataList)

    def toXML(self, writer, ttFont):
        # When exporting to XML if one of the data export formats
        # requires metrics then those metrics may be in the locator.
        # In this case populate the bitmaps with "export metrics".
        if ttFont.bitmapGlyphDataFormat in ("row", "bitwise"):
            locator = ttFont[self.__class__.locatorName]
            for curStrike, curGlyphDict in zip(locator.strikes, self.strikeData):
                for curIndexSubTable in curStrike.indexSubTables:
                    for curName in curIndexSubTable.names:
                        glyph = curGlyphDict[curName]
                        # I'm not sure which metrics have priority here.
                        # For now if both metrics exist go with glyph metrics.
                        if hasattr(glyph, "metrics"):
                            glyph.exportMetrics = glyph.metrics
                        else:
                            glyph.exportMetrics = curIndexSubTable.metrics
                        glyph.exportBitDepth = curStrike.bitmapSizeTable.bitDepth

        writer.simpletag("header", [("version", self.version)])
        writer.newline()
        locator = ttFont[self.__class__.locatorName]
        for strikeIndex, bitmapGlyphDict in enumerate(self.strikeData):
            writer.begintag("strikedata", [("index", strikeIndex)])
            writer.newline()
            for curName, curBitmap in bitmapGlyphDict.items():
                curBitmap.toXML(strikeIndex, curName, writer, ttFont)
            writer.endtag("strikedata")
            writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        if name == "header":
            self.version = safeEval(attrs["version"])
        elif name == "strikedata":
            if not hasattr(self, "strikeData"):
                self.strikeData = []
            strikeIndex = safeEval(attrs["index"])

            bitmapGlyphDict = {}
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                if name[4:].startswith(_bitmapGlyphSubclassPrefix[4:]):
                    imageFormat = safeEval(name[len(_bitmapGlyphSubclassPrefix) :])
                    glyphName = attrs["name"]
                    imageFormatClass = self.getImageFormatClass(imageFormat)
                    curGlyph = imageFormatClass(None, None)
                    curGlyph.fromXML(name, attrs, content, ttFont)
                    assert glyphName not in bitmapGlyphDict, (
                        "Duplicate glyphs with the same name '%s' in the same strike."
                        % glyphName
                    )
                    bitmapGlyphDict[glyphName] = curGlyph
                else:
                    log.warning("%s being ignored by %s", name, self.__class__.__name__)

            # Grow the strike data array to the appropriate size. The XML
            # format allows the strike index value to be out of order.
            if strikeIndex >= len(self.strikeData):
                self.strikeData += [None] * (strikeIndex + 1 - len(self.strikeData))
            assert (
                self.strikeData[strikeIndex] is None
            ), "Duplicate strike EBDT indices."
            self.strikeData[strikeIndex] = bitmapGlyphDict


class EbdtComponent(object):
    def toXML(self, writer, ttFont):
        writer.begintag("ebdtComponent", [("name", self.name)])
        writer.newline()
        for componentName in sstruct.getformat(ebdtComponentFormat)[1][1:]:
            writer.simpletag(componentName, value=getattr(self, componentName))
            writer.newline()
        writer.endtag("ebdtComponent")
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.name = attrs["name"]
        componentNames = set(sstruct.getformat(ebdtComponentFormat)[1][1:])
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attrs, content = element
            if name in componentNames:
                vars(self)[name] = safeEval(attrs["value"])
            else:
                log.warning("unknown name '%s' being ignored by EbdtComponent.", name)


# Helper functions for dealing with binary.


def _data2binary(data, numBits):
    binaryList = []
    for curByte in data:
        value = byteord(curByte)
        numBitsCut = min(8, numBits)
        for i in range(numBitsCut):
            if value & 0x1:
                binaryList.append("1")
            else:
                binaryList.append("0")
            value = value >> 1
        numBits -= numBitsCut
    return strjoin(binaryList)


def _binary2data(binary):
    byteList = []
    for bitLoc in range(0, len(binary), 8):
        byteString = binary[bitLoc : bitLoc + 8]
        curByte = 0
        for curBit in reversed(byteString):
            curByte = curByte << 1
            if curBit == "1":
                curByte |= 1
        byteList.append(bytechr(curByte))
    return bytesjoin(byteList)


def _memoize(f):
    class memodict(dict):
        def __missing__(self, key):
            ret = f(key)
            if isinstance(key, int) or len(key) == 1:
                self[key] = ret
            return ret

    return memodict().__getitem__


# 00100111 -> 11100100 per byte, not to be confused with little/big endian.
# Bitmap data per byte is in the order that binary is written on the page
# with the least significant bit as far right as possible. This is the
# opposite of what makes sense algorithmically and hence this function.
@_memoize
def _reverseBytes(data):
    r"""
    >>> bin(ord(_reverseBytes(0b00100111)))
    '0b11100100'
    >>> _reverseBytes(b'\x00\xf0')
    b'\x00\x0f'
    """
    if isinstance(data, bytes) and len(data) != 1:
        return bytesjoin(map(_reverseBytes, data))
    byte = byteord(data)
    result = 0
    for i in range(8):
        result = result << 1
        result |= byte & 1
        byte = byte >> 1
    return bytechr(result)


# This section of code is for reading and writing image data to/from XML.


def _writeRawImageData(strikeIndex, glyphName, bitmapObject, writer, ttFont):
    writer.begintag("rawimagedata")
    writer.newline()
    writer.dumphex(bitmapObject.imageData)
    writer.endtag("rawimagedata")
    writer.newline()


def _readRawImageData(bitmapObject, name, attrs, content, ttFont):
    bitmapObject.imageData = readHex(content)


def _writeRowImageData(strikeIndex, glyphName, bitmapObject, writer, ttFont):
    metrics = bitmapObject.exportMetrics
    del bitmapObject.exportMetrics
    bitDepth = bitmapObject.exportBitDepth
    del bitmapObject.exportBitDepth

    writer.begintag(
        "rowimagedata", bitDepth=bitDepth, width=metrics.width, height=metrics.height
    )
    writer.newline()
    for curRow in range(metrics.height):
        rowData = bitmapObject.getRow(curRow, bitDepth=bitDepth, metrics=metrics)
        writer.simpletag("row", value=hexStr(rowData))
        writer.newline()
    writer.endtag("rowimagedata")
    writer.newline()


def _readRowImageData(bitmapObject, name, attrs, content, ttFont):
    bitDepth = safeEval(attrs["bitDepth"])
    metrics = SmallGlyphMetrics()
    metrics.width = safeEval(attrs["width"])
    metrics.height = safeEval(attrs["height"])

    dataRows = []
    for element in content:
        if not isinstance(element, tuple):
            continue
        name, attr, content = element
        # Chop off 'imagedata' from the tag to get just the option.
        if name == "row":
            dataRows.append(deHexStr(attr["value"]))
    bitmapObject.setRows(dataRows, bitDepth=bitDepth, metrics=metrics)


def _writeBitwiseImageData(strikeIndex, glyphName, bitmapObject, writer, ttFont):
    metrics = bitmapObject.exportMetrics
    del bitmapObject.exportMetrics
    bitDepth = bitmapObject.exportBitDepth
    del bitmapObject.exportBitDepth

    # A dict for mapping binary to more readable/artistic ASCII characters.
    binaryConv = {"0": ".", "1": "@"}

    writer.begintag(
        "bitwiseimagedata",
        bitDepth=bitDepth,
        width=metrics.width,
        height=metrics.height,
    )
    writer.newline()
    for curRow in range(metrics.height):
        rowData = bitmapObject.getRow(
            curRow, bitDepth=1, metrics=metrics, reverseBytes=True
        )
        rowData = _data2binary(rowData, metrics.width)
        # Make the output a readable ASCII art form.
        rowData = strjoin(map(binaryConv.get, rowData))
        writer.simpletag("row", value=rowData)
        writer.newline()
    writer.endtag("bitwiseimagedata")
    writer.newline()


def _readBitwiseImageData(bitmapObject, name, attrs, content, ttFont):
    bitDepth = safeEval(attrs["bitDepth"])
    metrics = SmallGlyphMetrics()
    metrics.width = safeEval(attrs["width"])
    metrics.height = safeEval(attrs["height"])

    # A dict for mapping from ASCII to binary. All characters are considered
    # a '1' except space, period and '0' which maps to '0'.
    binaryConv = {" ": "0", ".": "0", "0": "0"}

    dataRows = []
    for element in content:
        if not isinstance(element, tuple):
            continue
        name, attr, content = element
        if name == "row":
            mapParams = zip(attr["value"], itertools.repeat("1"))
            rowData = strjoin(itertools.starmap(binaryConv.get, mapParams))
            dataRows.append(_binary2data(rowData))

    bitmapObject.setRows(
        dataRows, bitDepth=bitDepth, metrics=metrics, reverseBytes=True
    )


def _writeExtFileImageData(strikeIndex, glyphName, bitmapObject, writer, ttFont):
    try:
        folder = os.path.dirname(writer.file.name)
    except AttributeError:
        # fall back to current directory if output file's directory isn't found
        folder = "."
    folder = os.path.join(folder, "bitmaps")
    filename = glyphName + bitmapObject.fileExtension
    if not os.path.isdir(folder):
        os.makedirs(folder)
    folder = os.path.join(folder, "strike%d" % strikeIndex)
    if not os.path.isdir(folder):
        os.makedirs(folder)

    fullPath = os.path.join(folder, filename)
    writer.simpletag("extfileimagedata", value=fullPath)
    writer.newline()

    with open(fullPath, "wb") as file:
        file.write(bitmapObject.imageData)


def _readExtFileImageData(bitmapObject, name, attrs, content, ttFont):
    fullPath = attrs["value"]
    with open(fullPath, "rb") as file:
        bitmapObject.imageData = file.read()


# End of XML writing code.

# Important information about the naming scheme. Used for identifying formats
# in XML.
_bitmapGlyphSubclassPrefix = "ebdt_bitmap_format_"


class BitmapGlyph(object):
    # For the external file format. This can be changed in subclasses. This way
    # when the extfile option is turned on files have the form: glyphName.ext
    # The default is just a flat binary file with no meaning.
    fileExtension = ".bin"

    # Keep track of reading and writing of various forms.
    xmlDataFunctions = {
        "raw": (_writeRawImageData, _readRawImageData),
        "row": (_writeRowImageData, _readRowImageData),
        "bitwise": (_writeBitwiseImageData, _readBitwiseImageData),
        "extfile": (_writeExtFileImageData, _readExtFileImageData),
    }

    def __init__(self, data, ttFont):
        self.data = data
        self.ttFont = ttFont
        # TODO Currently non-lazy decompilation is untested here...
        # if not ttFont.lazy:
        # 	self.decompile()
        # 	del self.data

    def __getattr__(self, attr):
        # Allow lazy decompile.
        if attr[:2] == "__":
            raise AttributeError(attr)
        if attr == "data":
            raise AttributeError(attr)
        self.decompile()
        del self.data
        return getattr(self, attr)

    def ensureDecompiled(self, recurse=False):
        if hasattr(self, "data"):
            self.decompile()
            del self.data

    # Not a fan of this but it is needed for safer safety checking.
    def getFormat(self):
        return safeEval(self.__class__.__name__[len(_bitmapGlyphSubclassPrefix) :])

    def toXML(self, strikeIndex, glyphName, writer, ttFont):
        writer.begintag(self.__class__.__name__, [("name", glyphName)])
        writer.newline()

        self.writeMetrics(writer, ttFont)
        # Use the internal write method to write using the correct output format.
        self.writeData(strikeIndex, glyphName, writer, ttFont)

        writer.endtag(self.__class__.__name__)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.readMetrics(name, attrs, content, ttFont)
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attr, content = element
            if not name.endswith("imagedata"):
                continue
            # Chop off 'imagedata' from the tag to get just the option.
            option = name[: -len("imagedata")]
            assert option in self.__class__.xmlDataFunctions
            self.readData(name, attr, content, ttFont)

    # Some of the glyphs have the metrics. This allows for metrics to be
    # added if the glyph format has them. Default behavior is to do nothing.
    def writeMetrics(self, writer, ttFont):
        pass

    # The opposite of write metrics.
    def readMetrics(self, name, attrs, content, ttFont):
        pass

    def writeData(self, strikeIndex, glyphName, writer, ttFont):
        try:
            writeFunc, readFunc = self.__class__.xmlDataFunctions[
                ttFont.bitmapGlyphDataFormat
            ]
        except KeyError:
            writeFunc = _writeRawImageData
        writeFunc(strikeIndex, glyphName, self, writer, ttFont)

    def readData(self, name, attrs, content, ttFont):
        # Chop off 'imagedata' from the tag to get just the option.
        option = name[: -len("imagedata")]
        writeFunc, readFunc = self.__class__.xmlDataFunctions[option]
        readFunc(self, name, attrs, content, ttFont)


# A closure for creating a mixin for the two types of metrics handling.
# Most of the code is very similar so its easier to deal with here.
# Everything works just by passing the class that the mixin is for.
def _createBitmapPlusMetricsMixin(metricsClass):
    # Both metrics names are listed here to make meaningful error messages.
    metricStrings = [BigGlyphMetrics.__name__, SmallGlyphMetrics.__name__]
    curMetricsName = metricsClass.__name__
    # Find which metrics this is for and determine the opposite name.
    metricsId = metricStrings.index(curMetricsName)
    oppositeMetricsName = metricStrings[1 - metricsId]

    class BitmapPlusMetricsMixin(object):
        def writeMetrics(self, writer, ttFont):
            self.metrics.toXML(writer, ttFont)

        def readMetrics(self, name, attrs, content, ttFont):
            for element in content:
                if not isinstance(element, tuple):
                    continue
                name, attrs, content = element
                if name == curMetricsName:
                    self.metrics = metricsClass()
                    self.metrics.fromXML(name, attrs, content, ttFont)
                elif name == oppositeMetricsName:
                    log.warning(
                        "Warning: %s being ignored in format %d.",
                        oppositeMetricsName,
                        self.getFormat(),
                    )

    return BitmapPlusMetricsMixin


# Since there are only two types of mixin's just create them here.
BitmapPlusBigMetricsMixin = _createBitmapPlusMetricsMixin(BigGlyphMetrics)
BitmapPlusSmallMetricsMixin = _createBitmapPlusMetricsMixin(SmallGlyphMetrics)


# Data that is bit aligned can be tricky to deal with. These classes implement
# helper functionality for dealing with the data and getting a particular row
# of bitwise data. Also helps implement fancy data export/import in XML.
class BitAlignedBitmapMixin(object):
    def _getBitRange(self, row, bitDepth, metrics):
        rowBits = bitDepth * metrics.width
        bitOffset = row * rowBits
        return (bitOffset, bitOffset + rowBits)

    def getRow(self, row, bitDepth=1, metrics=None, reverseBytes=False):
        if metrics is None:
            metrics = self.metrics
        assert 0 <= row and row < metrics.height, "Illegal row access in bitmap"

        # Loop through each byte. This can cover two bytes in the original data or
        # a single byte if things happen to be aligned. The very last entry might
        # not be aligned so take care to trim the binary data to size and pad with
        # zeros in the row data. Bit aligned data is somewhat tricky.
        #
        # Example of data cut. Data cut represented in x's.
        # '|' represents byte boundary.
        # data = ...0XX|XXXXXX00|000... => XXXXXXXX
        # 		or
        # data = ...0XX|XXXX0000|000... => XXXXXX00
        #   or
        # data = ...000|XXXXXXXX|000... => XXXXXXXX
        #   or
        # data = ...000|00XXXX00|000... => XXXX0000
        #
        dataList = []
        bitRange = self._getBitRange(row, bitDepth, metrics)
        stepRange = bitRange + (8,)
        for curBit in range(*stepRange):
            endBit = min(curBit + 8, bitRange[1])
            numBits = endBit - curBit
            cutPoint = curBit % 8
            firstByteLoc = curBit // 8
            secondByteLoc = endBit // 8
            if firstByteLoc < secondByteLoc:
                numBitsCut = 8 - cutPoint
            else:
                numBitsCut = endBit - curBit
            curByte = _reverseBytes(self.imageData[firstByteLoc])
            firstHalf = byteord(curByte) >> cutPoint
            firstHalf = ((1 << numBitsCut) - 1) & firstHalf
            newByte = firstHalf
            if firstByteLoc < secondByteLoc and secondByteLoc < len(self.imageData):
                curByte = _reverseBytes(self.imageData[secondByteLoc])
                secondHalf = byteord(curByte) << numBitsCut
                newByte = (firstHalf | secondHalf) & ((1 << numBits) - 1)
            dataList.append(bytechr(newByte))

        # The way the data is kept is opposite the algorithm used.
        data = bytesjoin(dataList)
        if not reverseBytes:
            data = _reverseBytes(data)
        return data

    def setRows(self, dataRows, bitDepth=1, metrics=None, reverseBytes=False):
        if metrics is None:
            metrics = self.metrics
        if not reverseBytes:
            dataRows = list(map(_reverseBytes, dataRows))

        # Keep track of a list of ordinal values as they are easier to modify
        # than a list of strings. Map to actual strings later.
        numBytes = (self._getBitRange(len(dataRows), bitDepth, metrics)[0] + 7) // 8
        ordDataList = [0] * numBytes
        for row, data in enumerate(dataRows):
            bitRange = self._getBitRange(row, bitDepth, metrics)
            stepRange = bitRange + (8,)
            for curBit, curByte in zip(range(*stepRange), data):
                endBit = min(curBit + 8, bitRange[1])
                cutPoint = curBit % 8
                firstByteLoc = curBit // 8
                secondByteLoc = endBit // 8
                if firstByteLoc < secondByteLoc:
                    numBitsCut = 8 - cutPoint
                else:
                    numBitsCut = endBit - curBit
                curByte = byteord(curByte)
                firstByte = curByte & ((1 << numBitsCut) - 1)
                ordDataList[firstByteLoc] |= firstByte << cutPoint
                if firstByteLoc < secondByteLoc and secondByteLoc < numBytes:
                    secondByte = (curByte >> numBitsCut) & ((1 << 8 - numBitsCut) - 1)
                    ordDataList[secondByteLoc] |= secondByte

        # Save the image data with the bits going the correct way.
        self.imageData = _reverseBytes(bytesjoin(map(bytechr, ordDataList)))


class ByteAlignedBitmapMixin(object):
    def _getByteRange(self, row, bitDepth, metrics):
        rowBytes = (bitDepth * metrics.width + 7) // 8
        byteOffset = row * rowBytes
        return (byteOffset, byteOffset + rowBytes)

    def getRow(self, row, bitDepth=1, metrics=None, reverseBytes=False):
        if metrics is None:
            metrics = self.metrics
        assert 0 <= row and row < metrics.height, "Illegal row access in bitmap"
        byteRange = self._getByteRange(row, bitDepth, metrics)
        data = self.imageData[slice(*byteRange)]
        if reverseBytes:
            data = _reverseBytes(data)
        return data

    def setRows(self, dataRows, bitDepth=1, metrics=None, reverseBytes=False):
        if metrics is None:
            metrics = self.metrics
        if reverseBytes:
            dataRows = map(_reverseBytes, dataRows)
        self.imageData = bytesjoin(dataRows)


class ebdt_bitmap_format_1(
    ByteAlignedBitmapMixin, BitmapPlusSmallMetricsMixin, BitmapGlyph
):
    def decompile(self):
        self.metrics = SmallGlyphMetrics()
        dummy, data = sstruct.unpack2(smallGlyphMetricsFormat, self.data, self.metrics)
        self.imageData = data

    def compile(self, ttFont):
        data = sstruct.pack(smallGlyphMetricsFormat, self.metrics)
        return data + self.imageData


class ebdt_bitmap_format_2(
    BitAlignedBitmapMixin, BitmapPlusSmallMetricsMixin, BitmapGlyph
):
    def decompile(self):
        self.metrics = SmallGlyphMetrics()
        dummy, data = sstruct.unpack2(smallGlyphMetricsFormat, self.data, self.metrics)
        self.imageData = data

    def compile(self, ttFont):
        data = sstruct.pack(smallGlyphMetricsFormat, self.metrics)
        return data + self.imageData


class ebdt_bitmap_format_5(BitAlignedBitmapMixin, BitmapGlyph):
    def decompile(self):
        self.imageData = self.data

    def compile(self, ttFont):
        return self.imageData


class ebdt_bitmap_format_6(
    ByteAlignedBitmapMixin, BitmapPlusBigMetricsMixin, BitmapGlyph
):
    def decompile(self):
        self.metrics = BigGlyphMetrics()
        dummy, data = sstruct.unpack2(bigGlyphMetricsFormat, self.data, self.metrics)
        self.imageData = data

    def compile(self, ttFont):
        data = sstruct.pack(bigGlyphMetricsFormat, self.metrics)
        return data + self.imageData


class ebdt_bitmap_format_7(
    BitAlignedBitmapMixin, BitmapPlusBigMetricsMixin, BitmapGlyph
):
    def decompile(self):
        self.metrics = BigGlyphMetrics()
        dummy, data = sstruct.unpack2(bigGlyphMetricsFormat, self.data, self.metrics)
        self.imageData = data

    def compile(self, ttFont):
        data = sstruct.pack(bigGlyphMetricsFormat, self.metrics)
        return data + self.imageData


class ComponentBitmapGlyph(BitmapGlyph):
    def toXML(self, strikeIndex, glyphName, writer, ttFont):
        writer.begintag(self.__class__.__name__, [("name", glyphName)])
        writer.newline()

        self.writeMetrics(writer, ttFont)

        writer.begintag("components")
        writer.newline()
        for curComponent in self.componentArray:
            curComponent.toXML(writer, ttFont)
        writer.endtag("components")
        writer.newline()

        writer.endtag(self.__class__.__name__)
        writer.newline()

    def fromXML(self, name, attrs, content, ttFont):
        self.readMetrics(name, attrs, content, ttFont)
        for element in content:
            if not isinstance(element, tuple):
                continue
            name, attr, content = element
            if name == "components":
                self.componentArray = []
                for compElement in content:
                    if not isinstance(compElement, tuple):
                        continue
                    name, attrs, content = compElement
                    if name == "ebdtComponent":
                        curComponent = EbdtComponent()
                        curComponent.fromXML(name, attrs, content, ttFont)
                        self.componentArray.append(curComponent)
                    else:
                        log.warning("'%s' being ignored in component array.", name)


class ebdt_bitmap_format_8(BitmapPlusSmallMetricsMixin, ComponentBitmapGlyph):
    def decompile(self):
        self.metrics = SmallGlyphMetrics()
        dummy, data = sstruct.unpack2(smallGlyphMetricsFormat, self.data, self.metrics)
        data = data[1:]

        (numComponents,) = struct.unpack(">H", data[:2])
        data = data[2:]
        self.componentArray = []
        for i in range(numComponents):
            curComponent = EbdtComponent()
            dummy, data = sstruct.unpack2(ebdtComponentFormat, data, curComponent)
            curComponent.name = self.ttFont.getGlyphName(curComponent.glyphCode)
            self.componentArray.append(curComponent)

    def compile(self, ttFont):
        dataList = []
        dataList.append(sstruct.pack(smallGlyphMetricsFormat, self.metrics))
        dataList.append(b"\0")
        dataList.append(struct.pack(">H", len(self.componentArray)))
        for curComponent in self.componentArray:
            curComponent.glyphCode = ttFont.getGlyphID(curComponent.name)
            dataList.append(sstruct.pack(ebdtComponentFormat, curComponent))
        return bytesjoin(dataList)


class ebdt_bitmap_format_9(BitmapPlusBigMetricsMixin, ComponentBitmapGlyph):
    def decompile(self):
        self.metrics = BigGlyphMetrics()
        dummy, data = sstruct.unpack2(bigGlyphMetricsFormat, self.data, self.metrics)
        (numComponents,) = struct.unpack(">H", data[:2])
        data = data[2:]
        self.componentArray = []
        for i in range(numComponents):
            curComponent = EbdtComponent()
            dummy, data = sstruct.unpack2(ebdtComponentFormat, data, curComponent)
            curComponent.name = self.ttFont.getGlyphName(curComponent.glyphCode)
            self.componentArray.append(curComponent)

    def compile(self, ttFont):
        dataList = []
        dataList.append(sstruct.pack(bigGlyphMetricsFormat, self.metrics))
        dataList.append(struct.pack(">H", len(self.componentArray)))
        for curComponent in self.componentArray:
            curComponent.glyphCode = ttFont.getGlyphID(curComponent.name)
            dataList.append(sstruct.pack(ebdtComponentFormat, curComponent))
        return bytesjoin(dataList)


# Dictionary of bitmap formats to the class representing that format
# currently only the ones listed in this map are the ones supported.
ebdt_bitmap_classes = {
    1: ebdt_bitmap_format_1,
    2: ebdt_bitmap_format_2,
    5: ebdt_bitmap_format_5,
    6: ebdt_bitmap_format_6,
    7: ebdt_bitmap_format_7,
    8: ebdt_bitmap_format_8,
    9: ebdt_bitmap_format_9,
}
